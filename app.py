from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from datetime import datetime
from pymongo import MongoClient
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'any_secret_key' 
socketio = SocketIO(app)

# --- ☁️ MongoDB 雲端連線設定 ---
# 請將下方引號內的 <db_password> 換成你複製的密碼
MONGO_URL = "mongodb+srv://unicornntd001_db_user:mantou0929forever@goodgodme.ckniblg.mongodb.net/mantou_chat?retryWrites=true&w=majority"

try:
    client = MongoClient(MONGO_URL)
    db = client['mantou_chat']      # 資料庫名稱
    collection = db['messages']      # 存放訊息的表格
    print("✅ 成功連線至 MongoDB 雲端資料庫！")
except Exception as e:
    print(f"❌ 連線失敗: {e}")

# 兩組帳號
USERS = {"白饅頭": "0918", "黑糖饅頭": "1128"}

# --- 🎨 前端 HTML + CSS + JS (秒刪版) ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>饅頭聊天室 - 雲端存檔版</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        .msg-row { display: flex; margin-bottom: 10px; flex-direction: column; position: relative; }
        .msg-content { max-width: 70%; padding: 8px 12px; border-radius: 15px; font-size: 14px; box-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
        .time { font-size: 10px; color: #aaa; margin: 0 5px; align-self: flex-end; }
        .my-msg { align-items: flex-end; }
        .my-msg .msg-content { background-color: #FFD580; border-bottom-right-radius: 2px; }
        .other-msg { align-items: flex-start; }
        .other-msg .msg-content { background-color: #E0F7FA; border-bottom-left-radius: 2px; }
        .user-name { font-size: 12px; font-weight: bold; color: #555; margin-bottom: 2px; }
        .delete-btn { cursor: pointer; color: #ccc; font-size: 16px; margin: 0 10px; visibility: hidden; }
        .msg-row:hover .delete-btn { visibility: visible; }
        .delete-btn:hover { color: red; }
    </style>
</head>
<body style="font-family: sans-serif; padding: 20px; background-color: #FFF9E3;">

    {% if not logged_in %}
        <div style="text-align:center; margin-top:100px;">
            <h2>登入饅頭系統 (Cloud)</h2>
            <form method="POST">
                <input name="username" placeholder="帳號" required style="padding:10px;"><br><br>
                <input name="password" type="password" placeholder="密碼" required style="padding:10px;"><br><br>
                <button type="submit" style="padding:10px 20px;">登入</button>
            </form>
            {% if error %}<p style="color:red;">{{ error }}</p>{% endif %}
        </div>
    {% else %}
        <h2>使用者：<span style="color:blue;">{{ username }}</span> | <a href="/logout">登出</a></h2>
        
        <div id="msg_box" style="border:1px solid #ccc; height:400px; overflow-y:auto; padding:15px; margin-bottom:10px; background:white; display: flex; flex-direction: column;">
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
        
        <div style="display: flex; gap: 10px;">
            <input id="input_msg" type="text" style="flex: 1; padding:10px;" placeholder="輸入訊息...">
            <button onclick="send()" style="padding:10px 20px;">傳送</button>
        </div>

        <script>
            var socket = io();
            var myName = "{{ username }}";

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
                socket.emit('client_delete', { msg_id: msgId });
            }

            document.getElementById('input_msg').addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { send(); }
            });
        </script>
    {% endif %}
</body>
</html>
"""

# --- 🐍 後端邏輯 ---

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

    # 從 MongoDB 讀取歷史訊息
    history = []
    if 'username' in session:
        # 抓取所有訊息並轉為列表，將 MongoDB 的 ID 轉為字串方便前端使用
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

@socketio.on('client_send')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M:%S")
    full_data = {"user": data['user'], "msg": data['msg'], "time": now}
    
    # 💾 直接存入雲端資料庫
    collection.insert_one(full_data)
    
    emit('server_response', broadcast=True)

@socketio.on('client_delete')
def handle_delete(data):
    from bson.objectid import ObjectId
    msg_id = data.get('msg_id')
    if msg_id:
        # 🗑️ 從雲端資料庫刪除指定 ID 的訊息
        collection.delete_one({"_id": ObjectId(msg_id)})
        emit('server_delete', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=9290)