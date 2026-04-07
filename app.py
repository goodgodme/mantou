# 1. 必須放在最頂端，確保所有網路連線（MongoDB/Socket）都能非同步執行
from flask import Flask, render_template_string, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")  # 移除 eventlet

# --- MongoDB ---
MONGO_URL = os.environ.get("MONGO_URL")
client = MongoClient(MONGO_URL)
db = client['mantou_chat']
collection = db['messages']

# --- 使用者（已加密）---
USERS = {
    "白饅頭": generate_password_hash("0918"),
    "黑糖饅頭": generate_password_hash("1128")
}

# --- HTML ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>饅頭聊天室 - 升級版</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: sans-serif; padding: 20px; background-color: #FFF9E3; margin: 0; }
        .msg-row { display: flex; flex-direction: column; margin-bottom: 10px; }
        .msg-content { max-width: 70%; padding: 8px 12px; border-radius: 15px; }
        .my-msg { align-items: flex-end; }
        .my-msg .msg-content { background: #FFD580; }
        .other-msg { align-items: flex-start; }
        .other-msg .msg-content { background: #E0F7FA; }
        .time { font-size: 10px; color: #aaa; }
        #msg_box { height:400px; overflow-y:auto; background:white; padding:10px; }
    </style>
</head>
<body>
{% if not logged_in %}
<form method="POST">
    <input name="username" placeholder="帳號"><br>
    <input name="password" type="password" placeholder="密碼"><br>
    <button>登入</button>
</form>
<p style="color:red;">{{ error }}</p>
{% else %}
<h3>{{ username }}</h3>
<a href="/logout">登出</a>

<div id="msg_box">
{% for item in history %}
<div class="msg-row {{ 'my-msg' if item.user == username else 'other-msg' }}">
    <div>{{ item.msg }}</div>
    <div class="time">{{ item.time }}</div>
</div>
{% endfor %}
</div>

<input id="input_msg">
<button onclick="send()">送出</button>

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
        <div>${data.msg}</div>
        <div class="time">${data.time}</div>
    `;

    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
});
</script>

{% endif %}
</body>
</html>
"""

# --- 路由 ---
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
        msgs = list(collection.find().sort("_id", 1))
        for m in msgs:
            m['_id'] = str(m['_id'])

        return render_template_string(
            html_code,
            logged_in=True,
            username=session['username'],
            history=msgs
        )

    return render_template_string(html_code, logged_in=False, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Socket ---
@socketio.on('client_send')
def handle_msg(data):
    if 'username' not in session:
        return

    msg = data.get('msg')
    user = session['username']
    time = datetime.now().strftime("%H:%M:%S")

    doc = {"user": user, "msg": msg, "time": time}
    collection.insert_one(doc)

    emit('server_response', doc, broadcast=True)

@socketio.on('client_delete')
def handle_delete(data):
    if 'username' not in session:
        return

    msg_id = data.get('msg_id')

    collection.delete_one({
        "_id": ObjectId(msg_id),
        "user": session['username']  # 🔥 防止刪別人
    })

    emit('server_delete', {"msg_id": msg_id}, broadcast=True)

# --- 啟動 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 9290))
    socketio.run(app, host='0.0.0.0', port=port)