import warnings
warnings.filterwarnings("ignore")

from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
# 雲端必須使用環境變數中的 SECRET_KEY
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mantou_fallback_key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# 雲端部署通常使用 eventlet，這裡讓它自動選擇
socketio = SocketIO(app, cors_allowed_origins="*")

# --- MongoDB 連線 (改為讀取環境變數) ---
# 本地端會讀取後面的預設值，雲端則讀取 MONGO_URL
MONGO_URI = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017/")
db_connected = False
collection = None

try:
    # 增加 tlsAllowInvalidCertificates 以確保雲端連線順利
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['mantou_chat']
    collection = db['messages']
    client.admin.command('ping')
    db_connected = True
    print("✅ [資料庫] 連線成功！")
except Exception as e:
    print(f"❌ [資料庫] 連線失敗: {e}")

USERS = {
    "白饅頭": generate_password_hash("0918"),
    "黑糖饅頭": generate_password_hash("1128")
}

# HTML 裡面的 Socket 連線必須改回自動偵測
html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>饅頭聊天室</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: "Microsoft JhengHei", sans-serif; background-color: #FFF9E3; margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .chat-container { width: 95%; max-width: 500px; height: 85vh; background: white; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); display: flex; flex-direction: column; overflow: hidden; }
        .chat-header { background: #FFD580; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; font-weight: bold; color: #5D4037; }
        #msg_box { flex: 1; overflow-y: auto; padding: 20px; background: #fdfdfd; }
        .msg-row { display: flex; flex-direction: column; margin-bottom: 15px; }
        .msg-content { max-width: 80%; padding: 10px 15px; border-radius: 18px; font-size: 15px; background: #E0F7FA; color: #006064; }
        .my-msg { align-items: flex-end; }
        .my-msg .msg-content { background: #FFD580; color: #5D4037; border-bottom-right-radius: 2px; }
        .time { font-size: 11px; color: #bbb; margin-top: 4px; }
        .input-area { padding: 15px; display: flex; gap: 10px; border-top: 1px solid #eee; background: #fff; }
        input { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 25px; outline: none; }
        button { padding: 0 20px; background: #FFD580; border: none; border-radius: 25px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
{% if not logged_in %}
    <div style="background:white; padding:40px; border-radius:20px; text-align:center; width:320px;">
        <h2>登入</h2>
        <form method="POST">
            <input name="username" placeholder="帳號" required style="width:100%; margin-bottom:10px;"><br>
            <input name="password" type="password" placeholder="密碼" required style="width:100%; margin-bottom:10px;"><br>
            <button type="submit" style="width:100%">登入</button>
        </form>
    </div>
{% else %}
    <div class="chat-container">
        <div class="chat-header"><span>{{ username }}</span><a href="/logout">登出</a></div>
        <div id="msg_box">
            {% for item in history %}
            <div class="msg-row {{ 'my-msg' if item.user == username else 'other-msg' }}">
                <div class="msg-content">{{ item.msg }}</div>
                <div class="time">{{ item.user }} · {{ item.time }}</div>
            </div>
            {% endfor %}
        </div>
        <div class="input-area">
            <input id="in" placeholder="輸入訊息..." onkeydown="if(event.keyCode==13) send()">
            <button onclick="send()">送出</button>
        </div>
    </div>
    <script>
        // 雲端部署不能寫死 127.0.0.1，要讓它自動偵測當前網址
        var socket = io({ transports: ['websocket', 'polling'] });
        
        function send() {
            var input = document.getElementById('in');
            if(input.value.trim() !== "") {
                socket.emit('client_send', {msg: input.value});
                input.value = '';
            }
        }
        socket.on('server_response', function(data) {
            var box = document.getElementById('msg_box');
            var row = document.createElement("div");
            row.className = "msg-row " + (data.user === "{{ username }}" ? "my-msg" : "other-msg");
            row.innerHTML = `<div class="msg-content">${data.msg}</div><div class="time">${data.user} · ${data.time}</div>`;
            box.appendChild(row);
            box.scrollTop = box.scrollHeight;
        });
    </script>
{% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        if u in USERS and check_password_hash(USERS[u], p):
            session.permanent = True
            session['username'] = u
            return redirect('/')
    
    msgs = []
    if 'username' in session and db_connected and collection is not None:
        try:
            # 雲端讀取歷史訊息
            msgs = list(collection.find())
            for m in msgs: m['_id'] = str(m['_id'])
        except:
            pass
    return render_template_string(html_code, logged_in='username' in session, username=session.get('username'), history=msgs)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@socketio.on('client_send')
def handle_msg(data):
    user = session.get('username', '訪客')
    tz = timezone(timedelta(hours=8))
    t = datetime.now(tz).strftime("%H:%M")
    doc = {"user": user, "msg": data['msg'], "time": t}
    if db_connected and collection is not None:
        res = collection.insert_one(doc)
        doc['_id'] = str(res.inserted_id)
    emit('server_response', doc, broadcast=True)

if __name__ == '__main__':
    # Render 會給一個 PORT 環境變數，沒有的話預設 10000
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)