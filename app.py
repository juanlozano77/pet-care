import os
import random
from io import BytesIO
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from math import ceil
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import pymysql
import boto3
from botocore.client import Config
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()

# --- CONFIGURACIÓN DE LA APLICACIÓN ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'compunube'

# --- CONFIGURACIÓN DE MYSQL ---
def get_db():
    if 'db' not in g:
        g.db = pymysql.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME" ),
            port=int(os.getenv("DB_PORT")),
            ssl={"ssl_mode": "REQUIRED"},
            cursorclass=pymysql.cursors.DictCursor
        )
        print(g)
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- CONFIGURACIÓN DE DIGITALOCEAN SPACES ---
SPACE_NAME = os.getenv("SPACE_NAME")
SPACE_REGION = os.getenv("SPACE_REGION")
ACCESS_KEY = os.getenv("SPACE_ACCESS_KEY")
SECRET_KEY = os.getenv("SPACE_SECRET_KEY")

def get_space_client():
    return boto3.client(
        's3',
        region_name=SPACE_REGION,
        endpoint_url=f'https://{SPACE_REGION}.digitaloceanspaces.com', 
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY
    )

# --- FLASK-LOGIN CONFIG ---
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.email = user_data['email']
        self.nombre = user_data['nombre']
        self.tipo_usuario = user_data['tipo_usuario']

    def get_id(self):
        return str(self.id)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    if user_data:
        return User(user_data)
    return None

# --- VARIABLES GLOBALES ---
PER_PAGE = 5

class Pagination:
    def __init__(self, page, per_page, total, items):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items

    @property
    def pages(self): return int(ceil(self.total / self.per_page))

    @property
    def has_prev(self): return self.page > 1

    @property
    def has_next(self): return self.page < self.pages

    @property
    def prev_num(self): return self.page - 1

    @property
    def next_num(self): return self.page + 1

    def iter_pages(self, left_edge=1, right_edge=1, left_current=1, right_current=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or (self.page - left_current - 1 < num < self.page + right_current) or num > self.pages - right_edge:
                if last + 1 != num: yield None
                yield num
                last = num

# --- INICIALIZAR TABLAS EN MYSQL ---
def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        schema_sql = f.read()
    for statement in schema_sql.split(";"):
        if statement.strip():
            try:
                db.cursor().execute(statement)
            except Exception as e:
                print(f"⚠️ Error al ejecutar: {statement[:50]}... -> {e}")
    db.commit()

# --- RUTAS PÚBLICAS Y DE AUTENTICACIÓN ---
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
        user_data = cursor.fetchone()

        if user_data and check_password_hash(user_data['password'], password):
            user_obj = User(user_data)
            login_user(user_obj)
            if current_user.tipo_usuario == 'admin': # Asumiendo que tu User object tiene 'tipo_usuario'
                return redirect(url_for('admin_main'))
            
             
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc != '':
                next_page = None
            # Si no hay una página 'next' segura, decide a dónde ir según el rol.
            if not next_page:
                if current_user.tipo_usuario == 'admin': # Asumiendo que tu User object tiene 'tipo_usuario'
                    next_page = url_for('admin_main')
                    return redirect(next_page)
                    
                else:
                    next_page = url_for('dashboard')

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))

        flash('Email o contraseña incorrectos.', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        email = request.form.get('email')
        nombre = request.form.get('nombre')
        password = request.form.get('password')
        tipo_usuario = request.form.get('tipoUsuario')

        cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
        if cursor.fetchone():
            flash('El correo electrónico ya está registrado.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        cursor.execute("INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (%s, %s, %s, %s)",
                       (nombre, email, hashed_password, tipo_usuario))
        usuario_id = cursor.lastrowid
        db.commit()

        if tipo_usuario == 'cuidador':
            descripcion = request.form.get('descripcion', '').strip()
            localidad = request.form.get('localidad', '').strip()
            partido = request.form.get('partido', '').strip()
            lat = request.form.get('lat')
            lng = request.form.get('lng')
            foto = request.files.get('foto')
            ubicacion = f"{localidad}, {partido}".strip()

            try:
                lat = float(lat) if lat else None
                lng = float(lng) if lng else None
            except ValueError:
                lat = None
                lng = None

            image_url = None
            if foto and foto.filename:
                s3 = get_space_client()
                filename = f"cuidadores/{usuario_id}_{foto.filename}"
                s3.upload_fileobj(BytesIO(foto.read()), SPACE_NAME, filename, ExtraArgs={'ACL': 'public-read'})
                image_url = f"https://{SPACE_NAME}.{SPACE_REGION}.digitaloceanspaces.com/{filename}" 

            cursor.execute('''INSERT INTO cuidadores (usuario_id, descripcion, ubicacion, lat, lng, rating, foto)
                              VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                          (usuario_id, descripcion, ubicacion, lat, lng, float(request.form.get('rating') or 0), image_url))
            db.commit()

            servicios = request.form.getlist('servicios')
            for servicio in servicios:
                cursor.execute("INSERT INTO servicios_cuidadores (cuidador_id, servicio) VALUES (%s, %s)", (usuario_id, servicio))
            db.commit()

        flash('¡Registro completado! Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('index'))

# --- DASHBOARD ---
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.id, u.nombre, c.descripcion, c.ubicacion, c.lat, c.lng, c.rating, c.foto,
               GROUP_CONCAT(s.servicio) AS servicios
        FROM usuarios u
        JOIN cuidadores c ON u.id = c.usuario_id
        LEFT JOIN servicios_cuidadores s ON u.id = s.cuidador_id
        WHERE u.tipo_usuario = 'cuidador'
        GROUP BY u.id
    """)
    rows = cursor.fetchall()

    cuidadores = []
    for row in rows:
        cuidador_dict = dict(row)
        servicios_str = row['servicios'] if row['servicios'] else ''
        cuidador_dict['servicios'] = servicios_str.split(',') if servicios_str else []
        cuidador_dict['foto'] = row['foto']
        cuidadores.append(cuidador_dict)

    return render_template('dashboard.html', cuidadores=cuidadores)

@app.route('/api/foto/<int:user_id>')
@login_required
def get_foto(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT foto FROM cuidadores WHERE usuario_id = %s", (user_id,))
    row = cursor.fetchone()
    if row and row['foto']:
        return redirect(row['foto'])
    return url_for('static', filename='assets/img/placeholder.jpg')

# --- ADMINISTRACIÓN ---

def handle_crud_redirect():
    # # NUEVO: Función central para manejar la redirección
    source_page = request.form.get('source_page', 'cu-1')
    return redirect(url_for('admin_main', page=source_page))
@app.route('/admin/')
@app.route('/admin/page/<string:page>')
@login_required
def admin_main(page="cu-1"):
    if current_user.tipo_usuario != 'admin':
        flash('No tienes permiso para acceder a esta página.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        page_type, page_num = page.split('-', 1)
        page_num = int(page_num)
    except ValueError:
        flash("Página no válida.", "danger")
        return redirect(url_for("admin_main"))

    offset = (page_num - 1) * PER_PAGE
    db = get_db()
    cursor = db.cursor()

    cuidadores = clientes = reseñas = comentarios = None # # NUEVO: Añadido `comentarios`
    page_type_name = ""

    if page_type == "cu":
        cursor.execute("SELECT COUNT(*) AS count FROM usuarios WHERE tipo_usuario = 'cuidador'")
        total = cursor.fetchone()['count']
        cursor.execute("""
            SELECT u.*, c.descripcion, c.ubicacion, c.lat, c.lng, c.rating,c.foto, GROUP_CONCAT(s.servicio) as servicios
            FROM usuarios u LEFT JOIN cuidadores c ON u.id = c.usuario_id LEFT JOIN servicios_cuidadores s ON u.id = s.cuidador_id
            WHERE u.tipo_usuario = 'cuidador' GROUP BY u.id ORDER BY u.id ASC LIMIT %s OFFSET %s""", (PER_PAGE, offset))
        rows = cursor.fetchall()
        cuidadores = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "cuidadores"
    elif page_type == "cl":
        cursor.execute("SELECT COUNT(*) AS count FROM usuarios WHERE tipo_usuario = 'cliente'")
        total = cursor.fetchone()['count']
        cursor.execute("SELECT * FROM usuarios WHERE tipo_usuario = 'cliente' LIMIT %s OFFSET %s", (PER_PAGE, offset))
        rows = cursor.fetchall()
        clientes = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "clientes"
    elif page_type == "re":
        cursor.execute("SELECT COUNT(*) AS count FROM reseñas")
        total = cursor.fetchone()['count']
        # # MODIFICADO: Join para obtener nombres
        cursor.execute("""
            SELECT r.*, cu.nombre as cuidador_nombre, cl.nombre as cliente_nombre
            FROM reseñas r
            JOIN usuarios cu ON r.cuidador_id = cu.id
            JOIN usuarios cl ON r.cliente_id = cl.id
            LIMIT %s OFFSET %s""", (PER_PAGE, offset))
        rows = cursor.fetchall()
        reseñas = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "reseñas"
    # # NUEVO: Bloque para manejar los comentarios
    elif page_type == "co":
        cursor.execute("SELECT COUNT(*) AS count FROM mensajes_contacto")
        total = cursor.fetchone()['count']
        cursor.execute("SELECT * FROM mensajes_contacto ORDER BY id DESC LIMIT %s OFFSET %s", (PER_PAGE, offset))
        rows = cursor.fetchall()
        comentarios = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "comentarios"

    # Datos para los modales
    cursor.execute("SELECT id, nombre FROM usuarios WHERE tipo_usuario = 'cuidador' ORDER BY nombre")
    all_cuidadores = cursor.fetchall()
    cursor.execute("SELECT id, nombre FROM usuarios WHERE tipo_usuario = 'cliente' ORDER BY nombre")
    all_clientes = cursor.fetchall()

    return render_template("admin.html",
                           cuidadores=cuidadores,
                           clientes=clientes,
                           reseñas=reseñas,
                           comentarios=comentarios, # # NUEVO
                           all_cuidadores=all_cuidadores,
                           all_clientes=all_clientes,
                           type=page_type_name,
                           current_page=page) # #

# --- CRUD CUIDADORES ---
@app.route('/admin/cuidador/add', methods=['POST'])
@login_required
def add_cuidador():
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        password = generate_password_hash("default_password", method='pbkdf2:sha256')
        cursor = db.cursor()
        cursor.execute("INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (%s, %s, %s, 'cuidador')",
                      (request.form['nombre'], request.form['email'], password))
        usuario_id = cursor.lastrowid
        db.commit()

        descripcion = request.form.get('descripcion', '').strip()
        ubicacion = request.form.get('ubicacion', '').strip()
        lat = float(request.form.get('lat') or 0)
        lng = float(request.form.get('lng') or 0)
        rating = float(request.form.get('rating') or 0)

        foto = request.files.get('foto')
        image_url = None
        if foto and foto.filename:
            s3 = get_space_client()
            filename = f"cuidadores/{usuario_id}_{foto.filename}"
            s3.upload_fileobj(BytesIO(foto.read()), SPACE_NAME, filename, ExtraArgs={'ACL': 'public-read'})
            image_url = f"https://{SPACE_NAME}.{SPACE_REGION}.digitaloceanspaces.com/{filename}" 

        cursor.execute('''INSERT INTO cuidadores (usuario_id, descripcion, ubicacion, lat, lng, rating, foto)
                         VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                      (usuario_id, descripcion, ubicacion, lat, lng, rating, image_url))
        db.commit()

        servicios = request.form.getlist('servicios')
        for servicio in servicios:
            cursor.execute("INSERT INTO servicios_cuidadores (cuidador_id, servicio) VALUES (%s, %s)", (usuario_id, servicio))
        db.commit()

        flash('🐾 Cuidador añadido!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/admin/cuidador/edit/<int:id>', methods=['POST'])
@login_required
def edit_cuidador(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("UPDATE usuarios SET nombre = %s, email = %s WHERE id = %s",
                      (request.form['nombre'], request.form['email'], id))

        params = [request.form['descripcion'], request.form['ubicacion'],
                  float(request.form.get('lat') or 0), float(request.form.get('lng') or 0),
                  float(request.form.get('rating') or 0)]

        foto_query_part = ""
        if 'foto' in request.files and request.files['foto'].filename:
            foto = request.files['foto']
            s3 = get_space_client()
            filename = f"cuidadores/{id}_{foto.filename}"
            s3.upload_fileobj(BytesIO(foto.read()), SPACE_NAME, filename, ExtraArgs={'ACL': 'public-read'})
            nueva_url = f"https://{SPACE_NAME}.{SPACE_REGION}.digitaloceanspaces.com/{filename}" 
            params.append(nueva_url)
            foto_query_part = ", foto = %s"

        params.append(id)
        cursor.execute(f"UPDATE cuidadores SET descripcion=%s, ubicacion=%s, lat=%s, lng=%s, rating=%s{foto_query_part} WHERE usuario_id=%s",
                       tuple(params))
        db.commit()

        cursor.execute("DELETE FROM servicios_cuidadores WHERE cuidador_id = %s", (id,))
        servicios = request.form.getlist('servicios')
        for servicio in servicios:
            cursor.execute("INSERT INTO servicios_cuidadores (cuidador_id, servicio) VALUES (%s, %s)", (id, servicio))
        db.commit()

        flash('🐾 Cuidador actualizado!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/admin/cuidador/delete/<int:id>', methods=['POST'])
@login_required
def delete_cuidador(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        db.cursor().execute("DELETE FROM usuarios WHERE id = %s", (id,))
        db.commit()
        flash('🐾 Cuidador eliminado.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

# --- CLIENTES ---
@app.route('/admin/cliente/add', methods=['POST'])
@login_required
def add_cliente():
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        db.cursor().execute("INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (%s, %s, %s, 'cliente')",
                           (request.form['nombre'], request.form['email'], password))
        db.commit()
        flash('👤 Cliente añadido!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/admin/cliente/edit/<int:id>', methods=['POST'])
@login_required
def edit_cliente(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("UPDATE usuarios SET nombre = %s, email = %s WHERE id = %s",
                      (request.form['nombre'], request.form['email'], id))
        if request.form['password']:
            cursor.execute("UPDATE usuarios SET password = %s WHERE id = %s",
                          (generate_password_hash(request.form['password'], method='pbkdf2:sha256'), id))
        db.commit()
        flash('👤 Cliente actualizado!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/admin/cliente/delete/<int:id>', methods=['POST'])
@login_required
def delete_cliente(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        db.cursor().execute("DELETE FROM usuarios WHERE id = %s", (id,))
        db.commit()
        flash('👤 Cliente eliminado.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return redirect(url_for('admin_main'))

# --- RESEÑAS ---
@app.route('/admin/reseña/add', methods=['POST'])
@login_required
def add_reseña():
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("""INSERT INTO reseñas (cuidador_id, cliente_id, texto, calificacion)
                          VALUES (%s, %s, %s, %s)""",
                      (request.form['cuidador_id'], request.form['cliente_id'], request.form['texto'], request.form['calificacion']))
        db.commit()
        flash('⭐ Reseña añadida!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/admin/reseña/edit/<int:id>', methods=['POST'])
@login_required
def edit_reseña(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("""UPDATE reseñas SET cuidador_id=%s, cliente_id=%s, texto=%s, calificacion=%s WHERE id=%s""",
                      (request.form['cuidador_id'], request.form['cliente_id'], request.form['texto'],
                       int(request.form['calificacion']), id))
        db.commit()
        flash('⭐ Reseña actualizada!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/admin/reseña/delete/<int:id>', methods=['POST'])
@login_required
def delete_reseña(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        db.cursor().execute("DELETE FROM reseñas WHERE id = %s", (id,))
        db.commit()
        flash('⭐ Reseña eliminada.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

@app.route('/api/reviews/<int:cuidador_id>')
def get_reviews(cuidador_id):
    """
    Devuelve las reseñas de un cuidador específico en formato JSON.
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Hacemos un JOIN con la tabla de usuarios para obtener el nombre del cliente que hizo la reseña
        cursor.execute("""
            SELECT r.texto, r.calificacion, u.nombre as cliente_nombre
            FROM reseñas r
            JOIN usuarios u ON r.cliente_id = u.id
            WHERE r.cuidador_id = %s
            ORDER BY r.id DESC
        """, (cuidador_id,))
        
        reseñas = cursor.fetchall()
        
        return jsonify({
            "status": "success",
            "data": reseñas
        })

    except Exception as e:
        print(f"Error fetching reviews for cuidador {cuidador_id}: {e}")
        return jsonify({
            "status": "error",
            "message": "No se pudieron cargar las reseñas."
        }), 500

# --- CONTACTO ---
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        db = get_db()
        try:
            cursor = db.cursor()
            cursor.execute("INSERT INTO mensajes_contacto (nombre, email, asunto, mensaje) VALUES (%s, %s, %s, %s)",
                          (request.form['name'], request.form['email'], request.form['subject'], request.form['message']))
            db.commit()
            flash('¡Gracias por tu mensaje!', 'success')
        except Exception as e:
            db.rollback()
            flash('Error al enviar tu mensaje.', 'danger')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/admin/comentario/delete/<int:id>', methods=['POST'])
@login_required
def delete_comentario(id):
    if current_user.tipo_usuario != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    try:
        db.cursor().execute("DELETE FROM mensajes_contacto WHERE id = %s", (id,))
        db.commit()
        flash('💬 Comentario eliminado.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return handle_crud_redirect()

# --- ARRANQUE ---
if __name__ == '__main__':
    app.run(debug=True)