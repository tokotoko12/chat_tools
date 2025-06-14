from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # CHANGE THIS!
app.config['TESTING'] = False # Default to False, can be overridden for tests
socketio = SocketIO(app)

# In-memory store for messages. In a real app, use a database.
chat_messages = []

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'password':
            session['username'] = request.form['username']
            return redirect(url_for('chat'))
        else:
            error = 'Invalid Credentials. Please try again.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])

@socketio.on('connect')
def handle_connect():
    if 'username' not in session:
        # This can happen if a user opens /chat directly without being logged in
        # or if their session expires and SocketIO tries to reconnect.
        print('SocketIO connect attempt from unauthenticated user.')
        return False # Reject connection

    print(f"Client connected: {session['username']}, sid: {request.sid}")
    join_room(session['username']) # Use username as a room, helpful for direct messaging later

    # Send existing messages to the newly connected client
    emit('load_messages', chat_messages)

@socketio.on('disconnect')
def handle_disconnect():
    if 'username' in session:
        print(f"Client disconnected: {session['username']}, sid: {request.sid}")
        leave_room(session['username'])
    else:
        print(f"Unauthenticated client disconnected, sid: {request.sid}")


@socketio.on('send_message')
def handle_send_message_event(data):
    if 'username' not in session:
        print("Unauthenticated user tried to send message.")
        return # Ignore message if user not in session

    message_text = data.get('message', '').strip()
    if not message_text:
        return # Ignore empty messages

    print(f"Received message: '{message_text}' from {session['username']}")

    message_data = {
        'user': session['username'],
        'message': message_text,
        'sid': request.sid # Store sender's session ID
    }

    chat_messages.append(message_data)
    if len(chat_messages) > 100: # Keep only the last 100 messages
        chat_messages.pop(0)

    # Broadcast to all. Client-side will determine if it's their own message.
    emit('receive_message', message_data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=False, host='0.0.0.0')
