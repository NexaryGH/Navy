from flask import Flask, request, render_template, send_from_directory, redirect, url_for, session, Response
import os
import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from functools import wraps
from queue import Queue

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Clave secreta para manejar sesiones

# Directorios
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, "data")
UPLOAD_FOLDER = os.path.join(DATA_FOLDER, "uploads")
USERS_FILE = os.path.join(DATA_FOLDER, "users.json")
MESSAGES_FILE = os.path.join(DATA_FOLDER, "messages.json")
FILES_INFO_FILE = os.path.join(DATA_FOLDER, "files_info.json")

# Crear directorios si no existen
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Listas para colas de clientes suscritos
message_clients = []
file_clients = []

# Decoradores
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def verified_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('verified'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Funciones de manejo de datos
def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump([], f)
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar {USERS_FILE}: {str(e)}")

def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
    except Exception as e:
        raise RuntimeError(f"No se pudo guardar {USERS_FILE}: {str(e)}")

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, 'w') as f:
            json.dump([], f)
    try:
        with open(MESSAGES_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar {MESSAGES_FILE}: {str(e)}")

def save_messages(messages):
    try:
        with open(MESSAGES_FILE, 'w') as f:
            json.dump(messages, f, indent=4)
    except Exception as e:
        raise RuntimeError(f"No se pudo guardar {MESSAGES_FILE}: {str(e)}")

def load_files_info():
    if not os.path.exists(FILES_INFO_FILE):
        with open(FILES_INFO_FILE, 'w') as f:
            json.dump([], f)
    try:
        with open(FILES_INFO_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"No se pudo cargar {FILES_INFO_FILE}: {str(e)}")

def save_files_info(files_info):
    try:
        with open(FILES_INFO_FILE, 'w') as f:
            json.dump(files_info, f, indent=4)
    except Exception as e:
        raise RuntimeError(f"No se pudo guardar {FILES_INFO_FILE}: {str(e)}")

def check_verification_and_bans():
    if 'logged_in' in session:
        users = load_users()
        user = next((u for u in users if u['username'] == session['username']), None)
        if user:
            session['verified'] = user.get('verified', False)
            session['tester'] = user.get('tester', False)
            session['bans'] = user.get('bans', {})
            bans = session['bans']
            for ban_type in list(bans.keys()):
                ban_info = bans[ban_type]
                start_time = datetime.strptime(ban_info['start_time'], '%Y-%m-%d %H:%M:%S')
                duration = timedelta(minutes=ban_info['duration'])
                if datetime.now() > start_time + duration:
                    del bans[ban_type]
                    user['bans'] = bans
                    save_users(users)

# Filtros Jinja2
def datetime_filter(value):
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')

def timedelta_minutes(minutes):
    return timedelta(minutes=minutes)

app.jinja_env.filters['datetime'] = datetime_filter
app.jinja_env.filters['timedelta_minutes'] = timedelta_minutes

@app.before_request
def before_request():
    check_verification_and_bans()

# Rutas de autenticación
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username_or_email = request.form['username_or_email']
        password = request.form['password']
        user = next((u for u in users if (u['username'] == username_or_email or u['email'] == username_or_email) and u['password'] == password), None)
        if user:
            session['logged_in'] = True
            session['username'] = user['username']
            session['email'] = user['email']
            session['verified'] = user.get('verified', False)
            session['tester'] = user.get('tester', False)
            session['bans'] = user.get('bans', {})
            if session['bans'].get('full_ban'):
                return redirect(url_for('banned'))
            return redirect(url_for('index'))
        return render_template('login.html', error="Credenciales incorrectas")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return render_template('register.html', error="Correo electrónico no válido")
        if any(u['email'] == email for u in users):
            return render_template('register.html', error="El correo electrónico ya está registrado")
        if any(u['username'] == username for u in users):
            return render_template('register.html', error="El nombre de usuario ya existe")
        new_user = {
            'username': username,
            'email': email,
            'password': password,
            'verified': False,
            'tester': False,
            'bans': {}
        }
        users.append(new_user)
        save_users(users)
        # Iniciar sesión automáticamente después del registro
        session['logged_in'] = True
        session['username'] = new_user['username']
        session['email'] = new_user['email']
        session['verified'] = new_user['verified']
        session['tester'] = new_user['tester']
        session['bans'] = new_user['bans']
        if session['bans'].get('full_ban'):
            return redirect(url_for('banned'))
        return redirect(url_for('index'))  # Redirigir a index en lugar de login
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/banned')
@login_required
def banned():
    ban_info = session['bans'].get('full_ban', {})
    return render_template('banned.html', ban_info=ban_info)

# Rutas principales
@app.route("/", methods=['GET', 'POST'])
@login_required
def index():
    if session['bans'].get('full_ban'):
        return redirect(url_for('banned'))
    bans_info = session['bans']
    bans_with_end_time = {}
    for ban_type, ban_info in bans_info.items():
        start_time = datetime.strptime(ban_info['start_time'], '%Y-%m-%d %H:%M:%S')
        end_time = start_time + timedelta(minutes=ban_info['duration'])
        bans_with_end_time[ban_type] = {
            'reason': ban_info['reason'],
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S')
        }
    return render_template(
        "index.html",
        username=session['username'],
        verified=session['verified'],
        tester=session['tester'],
        bans=bans_with_end_time,
        session=session
    )

@app.route("/post", methods=["POST"])
@login_required
def post_message_and_file():
    if session['bans'].get('full_ban') or session['bans'].get('message_restriction') or session['bans'].get('upload_restriction'):
        return redirect(url_for('index'))
    message = request.form.get('message')
    file = request.files.get('file')
    if not message and not file:
        return "Debes enviar al menos un mensaje o un archivo", 400
    messages = load_messages()
    new_message = {
        "username": session['username'],
        "message": message or "",
        "verified": session['verified'],
        "tester": session['tester'],
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "file": None
    }
    if file and file.filename != "":
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)
        file_info = {
            "name": file.filename,
            "owner": session['username'],
            "owner_verified": session['verified'],
            "owner_tester": session['tester'],
            "upload_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "size": f"{os.path.getsize(file_path) / 1024:.2f} KB"
        }
        files_info = load_files_info()
        files_info.append(file_info)
        save_files_info(files_info)
        new_message["file"] = file_info
        for client_queue in file_clients[:]:
            try:
                client_queue.put(file_info)
            except:
                file_clients.remove(client_queue)
    messages.append(new_message)
    save_messages(messages)
    for client_queue in message_clients[:]:
        try:
            client_queue.put(new_message)
        except:
            message_clients.remove(client_queue)
    return redirect(url_for('show_messages'))

@app.route("/files")
@login_required
def list_files():
    files_info = load_files_info()
    return render_template("files.html", files=files_info, tester=session['tester'], session=session)

@app.route("/download/<filename>")
@login_required
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/delete/<filename>", methods=["POST"])
@login_required
def delete_file(filename):
    file_info = get_file_info(filename)
    if not file_info:
        return "Archivo no encontrado", 404
    if session['username'] == file_info['owner'] or (session['verified'] and not file_info['owner_verified']):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        files_info = load_files_info()
        files_info = [fi for fi in files_info if fi['name'] != filename]
        save_files_info(files_info)
        for client_queue in file_clients[:]:
            try:
                client_queue.put({"action": "delete", "name": filename})
            except:
                file_clients.remove(client_queue)
        return redirect(url_for('list_files'))
    return "No tienes permiso para eliminar este archivo", 403

@app.route("/delete_message/<int:message_id>", methods=["POST"])
@login_required
def delete_message(message_id):
    messages = load_messages()
    if message_id < 0 or message_id >= len(messages):
        return "Mensaje no encontrado", 404
    message = messages[message_id]
    if session['username'] == message['username'] or (session['verified'] and not message['verified'] and not session['tester']):
        messages.pop(message_id)
        save_messages(messages)
        for client_queue in message_clients[:]:
            try:
                client_queue.put({"action": "delete", "id": message_id})
            except:
                message_clients.remove(client_queue)
        return redirect(url_for('show_messages'))
    return "No tienes permiso para eliminar este mensaje", 403

@app.route("/stream_messages")
@login_required
def stream_messages():
    def event_stream():
        client_queue = Queue()
        message_clients.append(client_queue)
        try:
            while True:
                message = client_queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        except GeneratorExit:
            if client_queue in message_clients:
                message_clients.remove(client_queue)
    return Response(event_stream(), content_type="text/event-stream")

@app.route("/stream_files")
@login_required
def stream_files():
    def event_stream():
        client_queue = Queue()
        file_clients.append(client_queue)
        try:
            while True:
                file_event = client_queue.get()
                yield f"data: {json.dumps(file_event)}\n\n"
        except GeneratorExit:
            if client_queue in file_clients:
                file_clients.remove(client_queue)
    return Response(event_stream(), content_type="text/event-stream")

@app.route("/messages")
@login_required
def show_messages():
    messages = load_messages()
    return render_template(
        "messages.html",
        messages=messages,
        username=session['username'],
        verified=session['verified'],
        tester=session['tester']
    )

@app.route("/dashboard", methods=['GET', 'POST'])
@login_required
@verified_required
def dashboard():
    users = load_users()
    if request.method == 'POST':
        target_username = request.form['username']
        action = request.form['action']
        duration = int(request.form['duration'])
        reason = request.form['reason']
        for user in users:
            if user['username'] == target_username:
                user['bans'] = user.get('bans', {})
                if action == 'ban':
                    user['bans']['full_ban'] = {
                        'reason': reason,
                        'duration': duration,
                        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                elif action == 'restrict_messages':
                    user['bans']['message_restriction'] = {
                        'reason': reason,
                        'duration': duration,
                        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                elif action == 'restrict_uploads':
                    user['bans']['upload_restriction'] = {
                        'reason': reason,
                        'duration': duration,
                        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                save_users(users)
                break
    return render_template('dashboard.html', users=users)

@app.route("/remove_ban", methods=["POST"])
@login_required
@verified_required
def remove_ban():
    username = request.form.get('username')
    ban_type = request.form.get('ban_type')
    users = load_users()
    for user in users:
        if user['username'] == username and ban_type in user.get('bans', {}):
            del user['bans'][ban_type]
            save_users(users)
            break
    return redirect(url_for('dashboard'))

def get_file_info(filename):
    files_info = load_files_info()
    for file_info in files_info:
        if file_info['name'] == filename:
            return file_info
    return None

if __name__ == "__main__":
    try:
        load_users()
        load_messages()
        load_files_info()
        app.run(host="0.0.0.0", port=5000, debug=True)
    except RuntimeError as e:
        print(f"Error al iniciar la aplicación: {str(e)}")