# 1. 必須放在最頂端，確保所有網路連線（MongoDB/Socket）都能非同步執行
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os

app = Flask(__name__)
# 優先從環境變數讀取 Secret Key，增加安全性
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mantou_default_secret_123')

# 初始化 SocketIO，針對 Render 雲端環境設定 cors 與 async_mode
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- MongoDB 設定 ---
# 建議在 Render 的 Dashboard -> Environment 設定 MONGO_URL 變數
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://unicornntd001_db_user:dgObjoajC4nf1zmd@goodgodme.ckniblg.mongodb.net/mantou_chat?retryWrites=true&w=majority")

try:
    client = MongoClient(MONGO_URL)
    db = client['mantou_chat']    
    collection = db['messages']    
    print("✅ 成功連線至 MongoDB 雲端資料庫！")
except Exception as e:
    print(f"❌ 連線失敗: {e}")

# --- 使用者資料 ---
USERS = {"白饅頭": "0918", "黑糖饅頭": "1128"}

# --- HTML 模板 ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>饅頭聊天室 - 雲端版</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: sans-serif; padding: 20px; background-color: #FFF9E3; margin: 0; }
        .msg-row { display: flex; margin-bottom: 10px; flex-direction: column; position: relative; }
        .msg-content { max-width: 70%; padding: 8px 12px; border-radius: 15px; font-size: 14px; box-shadow: 1px 1px 2px rgba(0,0,0,0.1); word-wrap: break-word; }
        .time { font-size: 10px; color: #aaa; margin: 0 5px; align-self: flex-end; }
        .my-msg { align-items: flex-end; }
        .my-msg .msg-content { background-color: #FFD580; border-bottom-right-radius: 2px; }
        .other-msg { align-items: flex-start; }
        .other-msg .msg-content { background-color: #E0F7FA; border-bottom-left-radius: 2px; }
        .user-name { font-size: 12px; font-weight: bold; color: #555; margin-bottom: 2px; }
        .delete-btn { cursor: pointer; color: #ccc; font-size: 16px; margin: 0 10px; visibility: hidden; }
        .msg-row:hover .delete-btn { visibility: visible; }
        .delete-btn:hover { color: red; }
        #msg_box { border:1px solid #ccc; height:400px; overflow-y:auto; padding:15px; margin-bottom:10px; background:white; display: flex; flex-direction: column; border-radius: 10px; }
        .input-area { display: flex; gap: 10px; }
        input { border-radius: 5px; border: 1px solid #ccc; outline: none; }
    </style>
</head>
<body>
    {% if not logged_in %}
        <div style="text-align:center; margin-top:100px;">
            <h2>登入饅頭系統 (Cloud)</h2>
            <form method="POST">
                <input name="username" placeholder="帳號" required style="padding:10px;"><br><br>
                <input name="password" type="password" placeholder="密碼" required style="padding:10px;"><br><br>
                <button type="submit" style="padding:10px 20px; cursor:pointer;">登入</button>
            </form>
            {% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
        </div>
    {% else %}
        <div style="max-width: 600px; margin: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3>使用者：<span style="color:orange;">{{ username }}</span></h3>
                <a href="/logout" style="text-decoration: none; color: #666;">登出</a>
            </div>
            
            <div id="msg_box">
                {% for item in history %}
                    {% set is_me = (item.user == username) %}
                    <div class="msg-row {{ 'my-msg' if is_me else 'other-msg' }}">
                        <div class="user-name">{{ '我' if is_me else item.user }}</div>
                        <div style="display: flex; align-items: center; {{ 'flex-direction: row-reverse;' if is_me }}">
                            <div class="msg-content">{{ item.msg }}</div>
                            <span class="time">{{ item.time }}</span>
                            {% if is_me %}
                                <span class="delete-btn" onclick="deleteMsg('{{ item._id }}')">×</span>
                            {% endif %}
                        </div>
                    </div>
                {% endfor %}
            </div>
            
            <div class="input-area">
                <input id="input_msg" type="text" style="flex: 1; padding:10px;" placeholder="輸入訊息..." autocomplete="off">
                <button onclick="send()" style="padding:10px 20px; background:#FFB347; border:none; border-radius:5px; color:white; cursor:pointer;">傳送</button>
            </div>
        </div>

        <script>
            var socket = io();
            var myName = "{{ username }}";
            var msgBox = document.getElementById('msg_box');
            msgBox.scrollTop = msgBox.scrollHeight;

            socket.on('server_response', function() { window.location.reload(); });
            socket.on('server_delete', function() { window.location.reload(); });

            function send() {
                var input = document.getElementById('input_msg');
                if (input.value.trim() !== "") {
                    socket.emit('client_send', {msg: input.value, user: myName});
                    input.value = '';
                }
            }

            function deleteMsg(msgId) {
                if(confirm("確定要刪除這條訊息嗎？")) {
                    socket.emit('client_delete', { msg_id: msgId });
                }
            }

            document.getElementById('input_msg').addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { send(); }
            });
        </script>
    {% endif %}
</body>
</html>
"""

# --- 路由與邏輯 ---
@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in USERS and USERS[username] == password:
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = "帳號或密碼錯誤"

    history = []
    if 'username' in session:
        # 從 MongoDB 讀取歷史訊息
        msgs = list(collection.find().sort("_id", 1))
        for m in msgs:
            m['_id'] = str(m['_id'])
            history.append(m)
        return render_template_string(html_code, logged_in=True, username=session.get('username'), history=history, error=error)
    
    return render_template_string(html_code, logged_in=False, error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

# --- Socket 事件 ---
@socketio.on('client_send')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M:%S")
    full_data = {"user": data['user'], "msg": data['msg'], "time": now}
    # 存入 MongoDB
    collection.insert_one(full_data)
    # 廣播更新
    emit('server_response', broadcast=True)

@socketio.on('client_delete')
def handle_delete(data):
    msg_id = data.get('msg_id')
    if msg_id:
        try:
            collection.delete_one({"_id": ObjectId(msg_id)})
            emit('server_delete', broadcast=True)
        except Exception as e:
            print(f"刪除失敗: {e}")

if __name__ == '__main__':
    # 本地測試時使用，Render 佈署時會使用 Gunicorn 指令
    port = int(os.environ.get("PORT", 9290))
    socketio.run(app, debug=True, host='0.0.0.0', port=port)