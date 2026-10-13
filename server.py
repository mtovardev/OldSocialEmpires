print (" [+] Cargando...")
import os
import json
import urllib
import threading
import webview
import uuid
import tempfile
import subprocess
import sys
if os.name == 'nt':
    os.system("color")
    os.system("title Servidor Privado SE")
else:
    import sys
    sys.stdout.write("\x1b]2;Servidor Privado SE\x07")

print (" [+] Cargando game config...")
from get_game_config import get_game_config, patch_game_config

print (" [+] Cargando server...")
from flask import Flask, render_template, send_from_directory, request, redirect, session, abort
from flask.debughelpers import attach_enctype_error_multidict
from command import command
from engine import timestamp_now
from version import version_name, version_code
from constants import Constant
from quests import get_quest_map
from bundle import ASSETS_DIR, STUB_DIR, TEMPLATES_DIR, BASE_DIR

# ============================================================
# DESCARGA DE ASSETS DESDE UPSTASH BLOB
# ============================================================

UPSTASH_URL = os.environ.get('https://bb157b505402.blob.upstash.io', '')

def download_assets_if_needed():
    """Descarga los assets desde Upstash si no existen localmente."""
    if not UPSTASH_URL:
        print(" [!] UPSTASH_URL no configurada. Usando assets locales.")
        return
    
    print(f" [+] Verificando assets desde: {UPSTASH_URL}")
    
    files_to_download = [
        "swf/SELoader.swf",
        "swf/SocialEmpires0926bsec.swf",
        "swf/20130417_projectiles.swf",
        "swf/20131010_magicParticles.swf",
        "swf/120608_dynamic.swf",
    ]
    
    for file in files_to_download:
        local_path = os.path.join(ASSETS_DIR, file)
        if not os.path.exists(local_path):
            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                url = f"{UPSTASH_URL}/{file}"
                print(f" [+] Descargando: {file}")
                urllib.request.urlretrieve(url, local_path)
            except Exception as e:
                print(f" [!] Error al descargar {file}: {e}")

download_assets_if_needed()

host = '127.0.0.1'
port = 5050

app = Flask(__name__, template_folder=TEMPLATES_DIR)

# ============================================================
# BASE DE DATOS
# ============================================================
print (" [+] Creando base de datos...")
from database import db, User, Village
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR_DB = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR_DB, "socialempires.db")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'SECRET_KEY'

try:
    db.init_app(app)
    with app.app_context():
        db.create_all()

    if os.path.exists(DB_PATH):
        print (f" [+] Base de datos creada correctamente en: {DB_PATH}")
    else:
        print (f" [!] ERROR: No se pudo crear el archivo de base de datos en: {DB_PATH}")
        print (f" [!] Verifica que tengas permisos de escritura en esa carpeta.")
        exit(1)

except Exception as e:
    print (f" [!] ERROR al crear la base de datos: {e}")
    print (f" [!] Asegúrate de tener instalado flask-sqlalchemy:")
    print (f" [!]     python -m pip install flask-sqlalchemy")
    exit(1)

# ============================================================
# CARGAR JUGADORES (después de la base de datos)
# ============================================================
print (" [+] Cargando players...")
from get_player_info import get_player_info, get_neighbor_info
from sessions import load_saved_villages, all_saves_userid, all_saves_info, save_info, new_village, fb_friends_str, load_village_from_db

with app.app_context():
    load_saved_villages()

print (" [+] Configurando rutas del servidor...")

# ============================================================
# MODO MANTENIMIENTO
# ============================================================

def is_maintenance_mode():
    """Lee el estado del mantenimiento desde maintenance.json"""
    try:
        with open('maintenance.json', 'r') as f:
            data = json.load(f)
            return data.get('maintenance', False)
    except FileNotFoundError:
        return False

@app.before_request
def check_maintenance():
    if is_maintenance_mode():
        if request.path != '/maintenance' and not request.path.startswith('/css/') and not request.path.startswith('/img/'):
            abort(503)

@app.errorhandler(503)
def maintenance_page(error):
    return render_template('maintenance.html'), 503

# ============================================================
# RUTAS
# ============================================================

## PAGES AND RESOURCES

@app.route("/", methods=['GET', 'POST'])
def login():
    session.pop('USERID', default=None)
    session.pop('GAMEVERSION', default=None)
    load_saved_villages()
    if request.method == 'POST':
        session['USERID'] = request.form['USERID']
        session['GAMEVERSION'] = request.form['GAMEVERSION']
        return redirect("/play.html")
    if request.method == 'GET':
        saves_info = all_saves_info()
        return render_template("login.html", saves_info=saves_info, version=version_name)

@app.route("/login", methods=['POST'])
def login_post():
    username = request.form['username']
    password = request.form['password']

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        with app.app_context():
            load_village_from_db(user.userid)
            
        session['USERID'] = user.userid
        session['GAMEVERSION'] = "SocialEmpires0926bsec.swf"
        return redirect("/profile.html")
    else:
        return render_template("login.html", error="Usuario o contraseña incorrectos", version=version_name)

@app.route("/register.html")
def register():
    return render_template("register.html", version=version_name)

@app.route("/register", methods=['POST'])
def register_post():
    username = request.form['username']
    email = request.form['email']
    empire_name = request.form['empire_name']
    password = request.form['password']

    if User.query.filter_by(username=username).first():
        return render_template("register.html", error="El nombre de usuario ya está en uso", version=version_name)
    if User.query.filter_by(email=email).first():
        return render_template("register.html", error="El correo ya está registrado", version=version_name)

    USERID = new_village(empire_name=empire_name, player_name=username)

    user = User(username=username, email=email, userid=USERID)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['USERID'] = USERID
    session['GAMEVERSION'] = "SocialEmpires0926bsec.swf"
    return redirect("/profile.html")

@app.route("/forgot-password", methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = user.generate_reset_token()
            db.session.commit()
            return f"Token de recuperación: {token}"
        return "Si el correo existe, recibirás un enlace de recuperación."
    return render_template("forgot_password.html", version=version_name)

@app.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        return "Token inválido o expirado"

    if request.method == 'POST':
        new_password = request.form['password']
        user.set_password(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        return redirect("/")

    return render_template("reset_password.html", token=token, version=version_name)

@app.route("/profile.html")
def profile():
    if 'USERID' not in session:
        return redirect("/")

    USERID = session['USERID']

    if USERID not in all_saves_userid():
        with app.app_context():
            load_village_from_db(USERID)

    info = save_info(USERID)
    if info is None:
        session.pop('USERID', default=None)
        session.pop('GAMEVERSION', default=None)
        return render_template("login.html", 
                             error="Tu aldea no se encontró. Por favor, crea una nueva cuenta.", 
                             version=version_name)
    
    return render_template("profile.html", save_info=save_info(session['USERID']), version=version_name)

@app.route("/play.html")
def play():
    print(session)

    if 'USERID' not in session:
        return redirect("/")
    if 'GAMEVERSION' not in session:
        return redirect("/")

    if session['USERID'] not in all_saves_userid():
        return redirect("/")

    USERID = session['USERID']

    if USERID not in all_saves_userid():
        with app.app_context():
            load_village_from_db(USERID)

    info = save_info(USERID)
    if info is None:
        session.pop('USERID', default=None)
        session.pop('GAMEVERSION', default=None)
        return render_template("login.html", 
                             error="Tu aldea no se encontró. Por favor, crea una nueva cuenta.", 
                             version=version_name)

    USERID = session['USERID']
    GAMEVERSION = session['GAMEVERSION']
    return render_template("play.html", save_info=save_info(USERID), serverTime=timestamp_now(), version=version_name, GAMEVERSION=GAMEVERSION, SERVERIP=host)

@app.route("/new.html")
def new():
    session['USERID'] = new_village()
    session['GAMEVERSION'] = "SocialEmpires0926bsec.swf"
    return redirect("play.html")

@app.route("/crossdomain.xml")
def crossdomain():
    return send_from_directory(STUB_DIR, "crossdomain.xml")

@app.route("/img/<path:path>")
def images(path):
    return send_from_directory(TEMPLATES_DIR + "/img", path)

@app.route("/css/<path:path>")
def css(path):
    return send_from_directory(TEMPLATES_DIR + "/css", path)

@app.route("/logout")
def logout():
    session.pop('USERID', default=None)
    session.pop('GAMEVERSION', default=None)
    return redirect("/")

## GAME STATIC

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_projectiles.swf")
def similar_05122012_projectiles():
    return send_from_directory(ASSETS_DIR + "/swf", "20130417_projectiles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_magicParticles.swf")
def similar_05122012_magicParticles():
    return send_from_directory(ASSETS_DIR + "/swf", "20131010_magicParticles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_dynamic.swf")
def similar_05122012_dynamic():
    return send_from_directory(ASSETS_DIR + "/swf", "120608_dynamic.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/<path:path>")
def static_assets_loader(path):
    if not os.path.exists(ASSETS_DIR + "/"+ path):
        if not os.path.exists(f"{BASE_DIR}/download_assets/assets/{path}"):
            directory = os.path.dirname(f"{BASE_DIR}/download_assets/assets/{path}")
            if not os.path.exists(directory):
                os.makedirs(directory)

            URL = f"{UPSTASH_URL}/{path}"
            try:
                response = urllib.request.urlretrieve(URL, f"{BASE_DIR}/download_assets/assets/{path}")
            except urllib.error.HTTPError:
                return ("", 404)

            print(f"====== DOWNLOADED ASSET: {URL}")
            return send_from_directory("{BASE_DIR}/download_assets/assets", path)
        else:
            print(f"====== USING EXTERNAL: download_assets/assets/{path}")
            return send_from_directory("{BASE_DIR}/download_assets/assets", path)
    else:
        return send_from_directory(ASSETS_DIR, path)

## GAME DYNAMIC

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/track_game_status.php", methods=['POST'])
def track_game_status_response():
    status = request.values['status']
    installId = request.values['installId']
    user_id = request.values['user_id']

    print(f"track_game_status: status={status}, installId={installId}, user_id={user_id}. --", request.values)
    return ("", 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_game_config.php", methods=['GET','POST'])
def get_game_config_response():
    spdebug = None

    USERID = request.values['USERID']
    user_key = request.values['user_key']
    if 'spdebug' in request.values:
        spdebug = request.values['spdebug']
    language = request.values['language']

    print(f"get_game_config: USERID: {USERID}. --", request.values)
    return get_game_config()

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_player_info.php", methods=['POST'])
def get_player_info_response():

    USERID = request.values['USERID']
    user_key = request.values['user_key']
    spdebug = request.values['spdebug'] if 'spdebug' in request.values else None
    language = request.values['language']
    neighbors = request.values['neighbors'] if 'neighbors' in request.values else None
    client_id = request.values['client_id']
    user = request.values['user'] if 'user' in request.values else None
    map = int(request.values['map']) if 'map' in request.values else None

    print(f"get_player_info: USERID: {USERID}. user: {user} --", request.values)

    if user is None:
        return (get_player_info(USERID), 200)
    elif user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
    or user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
    or user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
        return (get_neighbor_info(user, map), 200)
    elif user.startswith("100000"):
        return get_quest_map(user)
    else:
        return (get_neighbor_info(user, map), 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/sync_error_track.php", methods=['POST'])
def sync_error_track_response():
    spdebug = None

    USERID = request.values['USERID']
    user_key = request.values['user_key']
    if 'spdebug' in request.values:
        spdebug = request.values['spdebug']
    language = request.values['language']
    error = request.values['error']
    current_failed = request.values['current_failed']
    tries = request.values['tries'] if 'tries' in request.values else None
    survival = request.values['survival']
    previous_failed = request.values['previous_failed']
    description = request.values['description']
    user_id = request.values['user_id']

    print(f"sync_error_track: USERID: {USERID}. [Error: {error}] tries: {tries}. --", request.values)
    return ("", 200)

@app.route("/null")
def flash_sync_error_response():
    sp_ref_cat = request.values['sp_ref_cat']

    if sp_ref_cat == "flash_sync_error":
        reason = "reload On Sync Error"
    elif sp_ref_cat == "flash_reload_quest":
        reason = "reload On End Quest"
    elif sp_ref_cat == "flash_reload_attack":
        reason = "reload On End Attack"

    print("flash_sync_error", reason, ". --", request.values)
    return redirect("/play.html")

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php", methods=['POST'])
def command_response():
    spdebug = None

    USERID = request.values['USERID']
    user_key = request.values['user_key']
    if 'spdebug' in request.values:
        spdebug = request.values['spdebug']
    language = request.values['language']
    client_id = request.values['client_id']

    print(f"command: USERID: {USERID}. --", request.values)

    data_str = request.values['data']
    data_hash = data_str[:64]
    assert data_str[64] == ';'
    data_payload = data_str[65:]
    data = json.loads(data_payload)

    command(USERID, data)

    return ({"result": "success"}, 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_continent_ranking.php")
def get_continent_ranking_response():

    USERID = request.values['USERID']
    worldChange = request.values['worldChange']
    if 'spdebug' in request.values:
        spdebug = request.values['spdebug']
    town_id = request.values['map']
    user_key = request.values['user_key']

    response = {
        "world_id": 0,
        "continent": [
            {"posicion": 0, "nivel": 1, "user_id": 1111},
            {"posicion": 1, "nivel": 0},
            {"posicion": 2, "nivel": 0},
            {"posicion": 3, "nivel": 0},
            {"posicion": 4, "nivel": 0},
            {"posicion": 5, "nivel": 0},
            {"posicion": 6, "nivel": 0},
            {"posicion": 7, "nivel": 0}
        ]
    }
    return(response)

# ============================================================
# MAIN
# ============================================================

def start_flask():
    app.secret_key = 'SECRET_KEY'
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    import sys
    if 'RENDER' in os.environ:
        start_flask()
    else:
        import threading
        import webview
        flask_thread = threading.Thread(target=start_flask)
        flask_thread.daemon = True
        flask_thread.start()
        window = webview.create_window(
            'Social Empires - Servidor Privado',
            f'http://127.0.0.1:{port}',
            width=1280,
            height=720,
            resizable=True,
            fullscreen=False
        )
        webview.start()
