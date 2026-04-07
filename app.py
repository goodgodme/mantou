# 1. 確保最上方沒有 import eventlet
from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

# 強制指定使用 threading 模式，徹底避開 eventlet 警告
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# --- MongoDB 連線 (加入 2秒逾時，避免卡死) ---
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017/")
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
db = client['mantou_chat']
collection = db['messages']

# --- 使用者名單 ---
USERS = {
    "白饅頭": generate_password_hash("0918"),
    "黑糖饅頭": generate_password_hash("1128")
}

# --- HTML 介面 (置中美化 + 移除升級版字樣) ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>饅頭聊天室</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: "Microsoft JhengHei", sans-serif; 
            background-color: #FFF9E3; /* 米黃色背景 */
            margin: 0; 
            display: flex;
            justify-content: center; 
            align-items: center;     
            min-height: 100vh; /* 強制垂直置中關鍵 */
        }

        /* 登入小卡片 */
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            text-align: center;
            width: 320px;
        }
        .login-container h2 { color: #8B4513; margin: 0 0 20px 0; }
        .login-container input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
            outline: none;
        }
        .login-container button {
            width: 100%;
            padding: 12px;
            background-color: #FFD580;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            color: #5D4037;
            margin-top: 10px;
        }

        /* 聊天室主容器 */
        .chat-container {
            width: 95%;
            max-width: 500px;
            height: 85vh;
            background: white;
            border-radius: 20px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .chat-header {
            background: #FFD580;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: bold;
            color: #5D4037;
        }
        #msg_box { 
            flex: 1;
            overflow-y: auto; 
            padding: 20px;
            background: #fdfdfd;
        }

        /* 對話氣泡樣式 */
        .msg-row { display: flex; flex-direction: column; margin-bottom: 15px; }
        .msg-content { 
            max-width: 80%; 
            padding: 10px 15px; 
            border-radius: 18px; 
            font-size: 15px;
            line-height: 1.4;
        }
        .my-msg { align-items: flex-end; }
        .my-msg .msg-content { background: #FFD580; color: #5D4037; border-bottom-right-radius: 2px; }
        .other-msg { align-items: flex-start; }
        .other-msg .msg-content { background: #E0F7FA; color: #006064; border-bottom-left-radius: 2px; }
        .time { font-size: 11px; color: #bbb; margin-top: 4px; }

        /* 輸入區 */
        .input-area {
            padding: 15px;
            display: flex;
            gap: 10px;
            background: #fff;
            border-top: 1px solid #eee;
        }
        #input_msg { 
            flex: 1;
            padding: 12px; 
            border: 1px solid #ddd;
            border-radius: 25px;
            outline: none;
        }
        .send-btn {
            padding: 0 20px;
            background: #FFD580;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            color: #5D4037;
        }
    </style>
</head>
<body>

{% if not logged_in %}
<div class="login-container">
    <h2>饅頭聊天室</h2>
    <form method="POST">
        <input name="username" placeholder="帳號" required>
        <input name="password" type="password" placeholder="密碼" required>
        <button type="submit">登入</button>
    </form>
    {% if error %}<p style="color:red; font-size: 14px; margin-top:10px;">{{ error }}</p>{% endif %}
</div>

{% else %}
<div class="chat-container">
    <div class="chat-header">
        <span>你好，{{ username }}</span>
        <a href="/logout" style="color: #5D4037; font-size: 14px; text-decoration: none;">登出</a>
    </div>

    <div id="msg_box">
    {% for item in history %}
    <div class="msg-row {{ 'my-msg' if item.user == username else 'other-msg' }}">
        <div class="msg-content">{{ item.msg }}</div>
        <div class="time">{{ item.user }} · {{ item.time }}</div>
    </div>
    {% endfor %}
    </div>

    <div class="input-area">
        <input id="input_msg" placeholder="輸入訊息..." onkeydown="if(event.keyCode==13) send()">
        <button class="send-btn" onclick="send()">送出</button>
    </div>
</div>

<script>
    var socket = io();
    var myName = "{{ username }}";

    function send(){
        let input = document.getElementById("input_msg");
        if(input.value.trim() !== ""){
            socket.emit("client_send", {msg: input.value});
            input.value = "";
        }
    }

    socket.on("server_response", function(data){
        let box = document.getElementById("msg_box");
        let row = document.createElement("div");
        row.className = "msg-row " + (data.user === myName ? "my-msg" : "other-msg");
        row.innerHTML = `
            <div class="msg-content">${data.msg}</div>
            <div class="time">${data.user} · ${data.time}</div>
        `;
        box.appendChild(row);
        box.scrollTop = box.scrollHeight;
    });

    // 進入時自動捲動到底部
    window.onload = function() {
        let box = document.getElementById("msg_box");
        box.scrollTop = box.scrollHeight;
    };
</script>
{% endif %}
</body>
</html>
"""

# --- 路由與後端邏輯 ---
@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in USERS and check_password_hash(USERS[username], password):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = "帳密錯誤"

    if 'username' in session:
        try:
            msgs = list(collection.find().sort("_id", 1))
            for m in msgs: m['_id'] = str(m['_id'])
        except Exception:
            msgs = []
            error = "⚠️ 資料庫連線失敗，請檢查 MongoDB 是否啟動"

        return render_template_string(html_code, logged_in=True, username=session['username'], history=msgs, error=error)

    return render_template_string(html_code, logged_in=False, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Socket 通訊 ---
@socketio.on('client_send')
def handle_msg(data):
    if 'username' not in session: return
    user = session['username']
    msg = data.get('msg')
    time = datetime.now().strftime("%H:%M")
    doc = {"user": user, "msg": msg, "time": time}
    try:
        collection.insert_one(doc)
        doc['_id'] = str(doc['_id']) 
        emit('server_response', doc, broadcast=True)
    except Exception as e:
        print(f"寫入失敗: {e}")

if __name__ == '__main__':
    # 執行前再次確認 MongoDB 已開啟
    port = int(os.environ.get("PORT", 9290))
    socketio.run(app, host='0.0.0.0', port=port)