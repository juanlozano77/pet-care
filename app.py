import sqlite3
import os
import random
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from math import ceil
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# --- 1. CONFIGURACIÓN DE LA APLICACIÓN ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'compunube'
DB_NAME = 'database.db'
PER_PAGE = 10  # Registros a mostrar por página

# --- 2. CONFIGURACIÓN DE FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "warning"

class User(UserMixin):
    def __init__(self, id, email, nombre, tipo_usuario='cliente'):
        self.id = id
        self.email = email
        self.nombre = nombre
        self.tipo_usuario = tipo_usuario

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user_data = db.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    if user_data:
        return User(id=user_data['id'], email=user_data['email'], nombre=user_data['nombre'], tipo_usuario=user_data['tipo_usuario'])
    return None

# --- 3. CLASE Y FUNCIONES DE BASE DE DATOS Y PAGINACIÓN ---
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

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            tipo_usuario TEXT CHECK(tipo_usuario IN ('cliente', 'cuidador', 'admin')) DEFAULT 'cliente'
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cuidadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER UNIQUE,
            descripcion TEXT,
            ubicacion TEXT,
            lat REAL,
            lng REAL,
            foto BLOB,
            rating REAL DEFAULT 0,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicios_cuidadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cuidador_id INTEGER,
            servicio TEXT,
            FOREIGN KEY(cuidador_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reseñas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cuidador_id INTEGER,
            cliente_id INTEGER,
            texto TEXT,
            calificacion INTEGER CHECK(calificacion >= 1 AND calificacion <= 5),
            FOREIGN KEY(cuidador_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY(cliente_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )""")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensajes_contacto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT NOT NULL,
            asunto TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            leido BOOLEAN DEFAULT 0
        )""")
        
        # Insertar datos de ejemplo si la tabla está vacía
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        if cursor.fetchone()[0] == 0:
        # --- CLIENTES ---
            clientes_para_insertar = [
            ("Juan Pérez", "juan@example.com", generate_password_hash("pass123", method='pbkdf2:sha256')),
            ("Ana Gómez", "ana@example.com", generate_password_hash("pass456", method='pbkdf2:sha256')),
            ("Carlos Méndez", "carlos@example.com", generate_password_hash("pass789", method='pbkdf2:sha256')),
            ("Laura Fernández", "laura@example.com", generate_password_hash("pass101", method='pbkdf2:sha256')),
            ("Diego Torres", "diego@example.com", generate_password_hash("pass202", method='pbkdf2:sha256')),
            ("Marcela Rojas", "marcela@example.com", generate_password_hash("pass303", method='pbkdf2:sha256')),
            ("Gonzalo Díaz", "gonzalo@example.com", generate_password_hash("pass404", method='pbkdf2:sha256')),
            ("Silvia Luna", "silvia@example.com", generate_password_hash("pass505", method='pbkdf2:sha256')),
            ("Federico Ruiz", "fede@example.com", generate_password_hash("pass606", method='pbkdf2:sha256')),
            ("Valeria Mendoza", "valeria@example.com", generate_password_hash("pass707", method='pbkdf2:sha256')),
            ]
            for nombre, email, password in clientes_para_insertar:
                cursor.execute("""
                INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (?, ?, ?, 'cliente')
                """, (nombre, email, password))

            # Obtener IDs de los clientes
            cliente_ids = [row['id'] for row in db.execute("SELECT id FROM usuarios WHERE tipo_usuario = 'cliente'").fetchall()]

            # --- CUIDADORES CON DATOS REALES DE ZONA SUR BA ---
            cuidadores_datos = [
            {
            "nombre": "María López",
            "email": "maria@pets.com",
            "password": generate_password_hash("pass789", method='pbkdf2:sha256'),
            "descripcion": "Ofrezco alojamiento seguro en mi casa con patio.",
            "ubicacion": "Lanús, Buenos Aires",
            "lat": -34.7062,
            "lng": -58.3900,
            "rating": 4.8,
            "servicios": ["Alojamiento", "Paseos"],
            }   ,
            {
            "nombre": "Carlos Rossi",
            "email": "carlos@pets.com",
            "password": generate_password_hash("pass101", method='pbkdf2:sha256'),
            "descripcion": "Cuido mascotas con necesidades especiales o de alto riesgo.",
            "ubicacion": "Avellaneda, Buenos Aires",
            "lat": -34.6680,
            "lng": -58.3740,
            "rating": 4.5,
            "servicios": ["Cuidado Especializado", "Transporte"],
            },
            {
            "nombre": "Laura Martínez",
            "email": "laura@pets.com",
            "password": generate_password_hash("pass202", method='pbkdf2:sha256'),
            "descripcion": "Peluquería profesional canina y felina.",
            "ubicacion": "Lomas de Zamora, Buenos Aires",
            "lat": -34.7480,
            "lng": -58.4530,
            "rating": 4.7,
            "servicios": ["Peluquería", "Baño", "Corte de uñas"],
            },
            {
            "nombre": "Javier Domínguez",
            "email": "javier@pets.com",
            "password": generate_password_hash("pass303", method='pbkdf2:sha256'),
            "descripcion": "Paseos diarios en grupo pequeños y seguros.",
            "ubicacion": "Quilmes, Buenos Aires",
            "lat": -34.7190,
            "lng": -58.2580,
            "rating": 4.6,
            "servicios": ["Paseos", "Visitas a domicilio"],
            },
            {
            "nombre": "Verónica Sosa",
            "email": "veronica@pets.com",
            "password": generate_password_hash("pass404", method='pbkdf2:sha256'),
            "descripcion": "Experiencia con animales mayores y post-operatorios.",
            "ubicacion": "Florencio Varela, Buenos Aires",
            "lat": -34.7680,
            "lng": -58.2620,
            "rating": 4.9,
            "servicios": ["Cuidado Especializado", "Rehabilitación", "Paseos"],
            },
            {
            "nombre": "Martín Roldán",
            "email": "martin@pets.com",
            "password": generate_password_hash("pass505", method='pbkdf2:sha256'),
            "descripcion": "Ofrezco guardería canina durante todo el día.",
            "ubicacion": "Temperley, Buenos Aires",
            "lat": -34.7620,
            "lng": -58.4220,
            "rating": 4.3,
            "servicios": ["Guardería", "Paseos", "Alojamiento"],
            }   ,
            {
            "nombre": "Lucía Benítez",
            "email": "lucia@pets.com",
            "password": generate_password_hash("pass606", method='pbkdf2:sha256'),
            "descripcion": "Cuido gatos con experiencia en alimentación especializada.",
            "ubicacion": "Adrogué, Buenos Aires",
            "lat": -34.7625,
            "lng": -58.4280,
            "rating": 4.7,
            "servicios": ["Cuidado de gatos", "Alimentación especializada"],
            },
            {
            "nombre": "Nicolás Ortega",
            "email": "nicolas@pets.com",
            "password": generate_password_hash("pass707", method='pbkdf2:sha256'),
            "descripcion": "Servicio de transporte pet friendly desde y hacia zoológicos y clínicas.",
            "ubicacion": "Wilde, Buenos Aires",
            "lat": -34.7120,
            "lng": -58.3860,
            "rating": 4.6,
            "servicios": ["Transporte", "Paseos"],
            },
            {
            "nombre": "Patricia Duarte",
            "email": "patricia@pets.com",
            "password": generate_password_hash("pass808", method='pbkdf2:sha256'),
            "descripcion": "Cuido mascotas en mi hogar familiar. Tienen espacio interior y exterior.",
            "ubicacion": "Valentín Alsina, Buenos Aires",
            "lat": -34.7150,
            "lng": -58.3840,
            "rating": 4.5,
            "servicios": ["Alojamiento", "Paseos", "Guardería"],
            },
            {
            "nombre": "Roberto Ledesma",
            "email": "roberto@pets.com",
            "password": generate_password_hash("pass909", method='pbkdf2:sha256'),
            "descripcion": "Especialista en perros grandes y de raza pura.",
            "ubicacion": "Sarandí, Buenos Aires",
            "lat": -34.7140,
            "lng": -58.3800,
            "rating": 4.8,
            "servicios": ["Cuidado Especializado", "Alojamiento", "Paseos"],
            },
            {
            "nombre": "Mariana Juárez",
            "email": "mariana@pets.com",
            "password": generate_password_hash("pass1010", method='pbkdf2:sha256'),
            "descripcion": "Ofrezco servicios personalizados para mascotas nerviosas o con miedo a personas nuevas.",
            "ubicacion": "Claypole, Buenos Aires",
            "lat": -34.7840,
            "lng": -58.4150,
            "rating": 4.4,
            "servicios": ["Cuidado Especializado", "Paseos"],
            },
            {
            "nombre": "Fernando Acosta",
            "email": "fernando@pets.com",
            "password": generate_password_hash("pass1111", method='pbkdf2:sha256'),
            "descripcion": "Guardería canina con juegos y monitores profesionales.",
            "ubicacion": "Ezeiza, Buenos Aires",
            "lat": -34.8000,
            "lng": -58.5000,
            "rating": 4.2,
            "servicios": ["Guardería", "Paseos", "Entrenamiento básico"],
            },
            {
            "nombre": "Sofía Ávila",
            "email": "sofia@pets.com",
            "password": generate_password_hash("pass1212", method='pbkdf2:sha256'),
            "descripcion": "Tengo experiencia con mascotas que requieren medicación constante.",
            "ubicacion": "Esteban Echeverría, Buenos Aires",
            "lat": -34.8200,
            "lng": -58.4500,
            "rating": 4.7,
            "servicios": ["Cuidado Especializado", "Alojamiento"],
            },
            {
            "nombre": "Hugo Almada",
            "email": "hugo@pets.com",
            "password": generate_password_hash("pass1313", method='pbkdf2:sha256'),
            "descripcion": "Cuido gatos y perros en un entorno tranquilo y seguro.",
            "ubicacion": "San Francisco Solano, Buenos Aires",
            "lat": -34.7200,
            "lng": -58.3800,
            "rating": 4.5,
            "servicios": ["Alojamiento", "Paseos", "Guardería"],
            },
            {
            "nombre": "Carla Márquez",
            "email": "carla@pets.com",
            "password": generate_password_hash("pass1414", method='pbkdf2:sha256'),
            "descripcion": "Espacio amplio y techado ideal para mascotas alérgicas al sol.",
            "ubicacion": "Rafael Calzada, Buenos Aires",
            "lat": -34.7500,
            "lng": -58.4100,
            "rating": 4.6,
            "servicios": ["Alojamiento", "Guardería", "Peluquería"],
            },
            {
            "nombre": "Alejandro Salinas",
            "email": "alejandro@pets.com",
            "password": generate_password_hash("pass1515", method='pbkdf2:sha256'),
            "descripcion": "Paseos temprano en la mañana y tarde-noche.",
            "ubicacion": "Ciudad Evita, Buenos Aires",
            "lat": -34.7300,
            "lng": -58.4000,
            "rating": 4.3,
            "servicios": ["Paseos", "Guardería"],
            },
            {
            "nombre": "Romina Vega",
            "email": "romina@pets.com",
            "password": generate_password_hash("pass1616", method='pbkdf2:sha256'),
            "descripcion": "Trabajo con veterinarios locales para brindar servicio completo.",
            "ubicacion": "Gerli, Buenos Aires",
            "lat": -34.7000,
            "lng": -58.3900,
            "rating": 4.7,
            "servicios": ["Cuidado Especializado", "Alojamiento", "Peluquería", "Paseos"],
            },
            {
            "nombre": "Agustín Funes",
            "email": "agustin@pets.com",
            "password": generate_password_hash("pass1717", method='pbkdf2:sha256'),
            "descripcion": "Cuido perros de razas pequeñas y medianas en mi departamento espacioso.",
            "ubicacion": "Piñeyro, Buenos Aires",
            "lat": -34.7300,
            "lng": -58.3700,
            "rating": 4.4,
            "servicios": ["Alojamiento", "Paseos"],
            },
            {
            "nombre": "Paula Navarro",
            "email": "paula@pets.com",
            "password": generate_password_hash("pass1818", method='pbkdf2:sha256'),
            "descripcion": "Amo los gatos y ofrezco hospedaje silencioso y sin perros.",
            "ubicacion": "Don Torcuato, Buenos Aires",
            "lat": -34.4980,
            "lng": -58.5680,
            "rating": 4.8,
            "servicios": ["Cuidado de gatos", "Guardería"],
            },
            {
            "nombre": "Facundo Bravo",
            "email": "facundo@pets.com",
            "password": generate_password_hash("pass1919", method='pbkdf2:sha256'),
            "descripcion": "Mi casa tiene un jardín grande y hago paseos controlados.",
            "ubicacion": "Bernal, Buenos Aires",
            "lat": -34.7200,
            "lng": -58.3800,
            "rating": 4.6,
            "servicios": ["Alojamiento", "Paseos", "Guardería"],
            },
            {
            "nombre": "Damián Rojas",
            "email": "damian@pets.com",
            "password": generate_password_hash("pass2020", method='pbkdf2:sha256'),
            "descripcion": "Experiencia con cachorros y entrenamiento básico.",
            "ubicacion": "Villa Dominico, Buenos Aires",
            "lat": -34.7000,
            "lng": -58.3900,
            "rating": 4.5,
            "servicios": ["Paseos", "Entrenamiento", "Alojamiento"],
            },
            {
            "nombre": "Belén Cáceres",
            "email": "belen@pets.com",
            "password": generate_password_hash("pass2121", method='pbkdf2:sha256'),
            "descripcion": "Cuido mascotas en mi casa con sistema de cámaras disponibles las 24hs.",
            "ubicacion": "Monte Chingolo, Buenos Aires",
            "lat": -34.7200,
            "lng": -58.3700,
            "rating": 4.6,
            "servicios": ["Alojamiento", "Visitas a domicilio"],
            },
            {
            "nombre": "Tomás León",
            "email": "tomas@pets.com",
            "password": generate_password_hash("pass2222", method='pbkdf2:sha256'),
            "descripcion": "Ofrezco masajes relajantes y terapias naturales.",
            "ubicacion": "Dock Sud, Buenos Aires",
            "lat": -34.7300,
            "lng": -58.4100,
            "rating": 4.3,
            "servicios": ["Cuidado Especializado", "Paseos", "Masajes"],
            },
            {
            "nombre": "Inés Bustamante",
            "email": "ines@pets.com",
            "password": generate_password_hash("pass2323", method='pbkdf2:sha256'),
            "descripcion": "Tengo experiencia con perros sordos, ciegos o discapacitados.",
            "ubicacion": "José Mármol, Buenos Aires",
            "lat": -34.7400,
            "lng": -58.4100,
            "rating": 4.9,
            "servicios": ["Cuidado Especializado", "Paseos", "Alojamiento"],
            },
            {
            "nombre": "Santiago Núñez",
            "email": "santiago@pets.com",
            "password": generate_password_hash("pass2424", method='pbkdf2:sha256'),
            "descripcion": "Mis mascotas viven como si estuvieran en su propia casa.",
            "ubicacion": "Ezeiza, Buenos Aires",
            "lat": -34.8000,
            "lng": -58.5000,
            "rating": 4.7,
            "servicios": ["Alojamiento", "Paseos", "Guardería"],
            },
            {
            "nombre": "Camila Ochoa",
            "email": "camila@pets.com",
            "password": generate_password_hash("pass2525", method='pbkdf2:sha256'),
            "descripcion": "Soy médica veterinaria y ofrezco cuidados profesionales y atención médica básica.",
            "ubicacion": "Adrogué, Buenos Aires",
            "lat": -34.7625,
            "lng": -58.4280,
            "rating": 4.9,
            "servicios": ["Cuidado Especializado", "Alojamiento", "Peluquería"],
            },
            {
            "nombre": "Luciano Franco",
            "email": "luciano@pets.com",
            "password": generate_password_hash("pass2626", method='pbkdf2:sha256'),
            "descripcion": "Tengo experiencia con perros agresivos o con ansiedad por separación.",
            "ubicacion": "Lanús, Buenos Aires",
            "lat": -34.7062,
            "lng": -58.3900,
            "rating": 4.8,
            "servicios": ["Cuidado Especializado", "Alojamiento", "Entrenamiento"],
            },
            {
            "nombre": "Celeste Ibarra",
            "email": "celeste@pets.com",
            "password": generate_password_hash("pass2727", method='pbkdf2:sha256'),
            "descripcion": "Ofrezco servicios de peluquería y spa para mascotas.",
            "ubicacion": "Wilde, Buenos Aires",
            "lat": -34.7120,
            "lng": -58.3860,
            "rating": 4.6,
            "servicios": ["Peluquería", "Spa", "Paseos"],
            },
            {
            "nombre": "Andrés Mena",
            "email": "andres@pets.com",
            "password": generate_password_hash("pass2828", method='pbkdf2:sha256'),
            "descripcion": "Cuido mascotas en una finca amplia con acceso a áreas verdes y sombra.",
            "ubicacion": "Florencio Varela, Buenos Aires",
            "lat": -34.7680,
            "lng": -58.2620,
            "rating": 4.5,
            "servicios": ["Alojamiento", "Paseos", "Guardería"],
            },
            {
            "nombre": "Daniela Soria",
            "email": "daniela@pets.com",
            "password": generate_password_hash("pass2929", method='pbkdf2:sha256'),
            "descripcion": "Tengo experiencia con mascotas alérgicas y dietas especiales.",
            "ubicacion": "Claypole, Buenos Aires",
            "lat": -34.7840,
            "lng": -58.4150,
            "rating": 4.7,
            "servicios": ["Cuidado Especializado", "Alojamiento", "Paseos"],
            },
            {
            "nombre": "Sebastián Lagos",
            "email": "sebas@pets.com",
            "password": generate_password_hash("pass3030", method='pbkdf2:sha256'),
            "descripcion": "Transporte puerta a puerta con vehículos adaptados para mascotas.",
            "ubicacion": "Valentín Alsina, Buenos Aires",
            "lat": -34.7150,
            "lng": -58.3840,
            "rating": 4.6,
            "servicios": ["Transporte", "Paseos", "Visitas a domicilio"],
            }
            ]

            # Insertar todos los cuidadores
            for cuidador in cuidadores_datos:
                cursor.execute("""
                    INSERT INTO usuarios (nombre, email, password, tipo_usuario) 
                    VALUES (?, ?, ?, 'cuidador')
                    """, (cuidador["nombre"], cuidador["email"], cuidador["password"]))
                usuario_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO cuidadores (usuario_id, descripcion, ubicacion, lat, lng, rating) 
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                    usuario_id,
                    cuidador["descripcion"],
                    cuidador["ubicacion"],
                    cuidador["lat"],
                    cuidador["lng"],
                    cuidador["rating"]
                    ))

                if cuidador.get("servicios"):
                    cursor.executemany("""
                    INSERT INTO servicios_cuidadores (cuidador_id, servicio) VALUES (?, ?)
                    """, [(usuario_id, servicio) for servicio in cuidador["servicios"]])

            # --- RESEÑAS ALEATORIAS PARA CUIDADORES ---
            # --- RESEÑAS POSITIVAS (4.5 a 5 estrellas) ---
            reseñas_datos = []
            # Lista de textos positivos
            reseña_textos = [
            "Excelente servicio, mi mascota regresó muy feliz.",
            "Muy recomendable. Trato profesional y amable.",
            "Volveré a dejar a mi perro con este cuidador.",
            "Cuidador muy responsable y dedicado.",
            "La comunicación fue excelente, todo claro desde el principio.",
            "Mi perro se sintió como en casa. Totalmente satisfecho.",
            "Cuida cada detalle. Mi gato estaba muy cómodo.",
            "Servicio rápido y eficiente. Totalmente satisfecho.",
            "El lugar es seguro y amplio. Muy buena experiencia.",
            "Tienen mucha paciencia con los animales. Excelente trabajo.",
            "Muy buen trato, atención personalizada y constante.",
            "Profesionalismo y cariño con mis mascotas. Volveré a usar sus servicios.",
            "Siempre me mantuvo informado del estado de mi mascota.",
            "Amor y dedicación en cada momento. ¡Gracias!",
            "Muy limpio y organizado. Todo bajo control.",
            "Mis mascotas están felices después de su estadía.",
            "Trato amoroso y respetuoso. Altamente recomendado.",
            "Muy buen ambiente y espacio para jugar.",
            "Cuidó a mi mascota enferma con mucho mimo y responsabilidad.",
            "Servicio impecable. Superó mis expectativas.",
            "Muy atento y comprometido con el bienestar animal.",
            "Dejé a mi perro por trabajo y volvió más feliz que nunca.",
            "Gran atención al detalle. Mi mascota comió muy bien y durmió tranquila.",
            "Un lugar seguro y lleno de amor. Lo recomiendo sin dudar.",
            "Me encantó cómo interactuó con mi gato tímido. Excelente manejo.",
            "Paseos diarios, comida balanceada y mucho cariño. ¡Impecable!",
            "Muy profesional y puntual. Comunicación fluida y clara.",
            "Cuidador con vocación real. Mis mascotas lo adoraron.",
            "Lo mejor que le pudo pasar a mi perro. Gracias por tu trabajo.",
            "Superó todas mis expectativas. Volveré a confiar en ti."
            ]

            # Obtener listado de clientes y cuidadores
            cliente_ids = [row['id'] for row in db.execute("SELECT id FROM usuarios WHERE tipo_usuario = 'cliente'").fetchall()]
            cuidador_ids = [row['id'] for row in db.execute("SELECT id FROM usuarios WHERE tipo_usuario = 'cuidador'").fetchall()]

            # Generar 30 reseñas aleatorias con calificación entre 4.5 y 5
            for i in range(30):
                cliente_id = random.choice(cliente_ids)
                cuidador_id = random.choice(cuidador_ids)
                texto = random.choice(reseña_textos)
                calificacion = round(random.uniform(4.5, 5), 1)  # Entre 4.5 y 5 estrellas
                reseñas_datos.append((cuidador_id, cliente_id, texto, int(calificacion)))

                # Insertar las reseñas
                cursor.executemany("""
                INSERT INTO reseñas (cuidador_id, cliente_id, texto, calificacion)
                 VALUES (?, ?, ?, ?)
                """, reseñas_datos)

            print("Reseñas insertadas correctamente.")
            
            print("Datos de ejemplo insertados.")
        

        admin_user = cursor.execute("SELECT * FROM usuarios WHERE email = 'admin@admin.com'").fetchone()
        if not admin_user:
            hashed_password = generate_password_hash('admin', method='pbkdf2:sha256')
            cursor.execute("INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (?, ?, ?, 'admin')",
                           ('Administrador', 'admin@admin.com', hashed_password))
            print("Usuario administrador creado.")
        
        
        db.commit()

# --- 4. RUTAS PÚBLICAS Y DE AUTENTICACIÓN ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()

        user_data = db.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        if user_data and check_password_hash(user_data['password'], password):
            user_obj = User(id=user_data['id'], email=user_data['email'], nombre=user_data['nombre'], tipo_usuario=user_data['tipo_usuario'])
            login_user(user_obj)
            if user_obj.tipo_usuario == 'admin':
                return redirect(url_for('admin_main'))
            return redirect(url_for('dashboard'))
        else:
            flash('Email o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        
        db = get_db()
        email = request.form.get('email')
        nombre = request.form.get('nombre')
        password = request.form.get('password')
        tipo_usuario = request.form.get('tipoUsuario')
       
        if db.execute('SELECT id FROM usuarios WHERE email = ?', (email,)).fetchone():
            flash('El correo electrónico ya está registrado.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (?, ?, ?, ?)',
            (nombre, email, hashed_password, tipo_usuario)
        )
        usuario_id = cursor.lastrowid
        print ("lo mande")

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

            foto_data = foto.read() if foto and foto.filename != '' else None

            cursor.execute('''
                INSERT INTO cuidadores (usuario_id, descripcion, ubicacion, lat, lng, foto)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (usuario_id, descripcion, ubicacion, lat, lng, foto_data))

        db.commit()
        flash('¡Registro completado! Ahora puedes iniciar sesión.', 'success')
        return jsonify({
            "status": "success",
            "user_id": usuario_id,
            "tipo": tipo_usuario
        })

    return render_template('register.html')
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado la sesión.', 'info')
    return redirect(url_for('index'))

# --- 5. RUTAS PROTEGIDAS Y APIS ---
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    rows = db.execute("""
        SELECT u.id, u.nombre, c.descripcion, c.ubicacion, c.lat, c.lng, c.rating,
               GROUP_CONCAT(s.servicio) AS servicios
        FROM usuarios u
        JOIN cuidadores c ON u.id = c.usuario_id
        LEFT JOIN servicios_cuidadores s ON u.id = s.cuidador_id
        WHERE u.tipo_usuario = 'cuidador' GROUP BY u.id
    """).fetchall()
    
    cuidadores = []
    for row in rows:
        cuidador_dict = dict(row)
        servicios_str = row['servicios'] if row['servicios'] is not None else ''
        cuidador_dict['servicios'] = servicios_str.split(',') if servicios_str else []
        cuidador_dict['image'] = url_for('get_foto', user_id=row['id'])
        cuidadores.append(cuidador_dict)
    
    return render_template('dashboard.html', cuidadores=cuidadores)

@app.route('/api/foto/<int:user_id>')
@login_required
def get_foto(user_id):
    db = get_db()
    foto_data = db.execute("SELECT foto FROM cuidadores WHERE usuario_id = ?", (user_id,)).fetchone()
    if foto_data and foto_data['foto']:
        return foto_data['foto'], 200, {'Content-Type': 'image/jpeg'}
    try:
        return app.send_static_file('assets/img/placeholder.jpg')
    except FileNotFoundError:
        return "Not found", 404
        
@app.route('/admin/')
@app.route('/admin/page/<string:page>')
@login_required
def admin_main(page="cu-1"):
    if not current_user.is_authenticated or current_user.tipo_usuario != 'admin':
        flash('No tienes permiso para acceder a esta página.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        page_type, page_num = page.split("-", 1)
        page_num = int(page_num)
    except ValueError:
        flash("Página no válida.", "danger")
        return redirect(url_for("admin_main"))

    db = get_db()
    offset = (page_num - 1) * PER_PAGE

    # Inicializar todas las posibles variables
    cuidadores = None
    clientes = None
    reseñas = None
    page_type_name = ""

    if page_type == "cu":  # Cuidadores
        total = db.execute("SELECT COUNT(*) FROM usuarios WHERE tipo_usuario = 'cuidador'").fetchone()[0]
        rows = db.execute("""
            SELECT u.*, c.descripcion, c.ubicacion, c.lat, c.lng, c.rating, GROUP_CONCAT(s.servicio) as servicios
            FROM usuarios u
            LEFT JOIN cuidadores c ON u.id = c.usuario_id
            LEFT JOIN servicios_cuidadores s ON u.id = s.cuidador_id
            WHERE u.tipo_usuario = 'cuidador'
            GROUP BY u.id
            ORDER BY u.id ASC
            LIMIT ? OFFSET ?
        """, (PER_PAGE, offset)).fetchall()
        cuidadores = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "cuidadores"

    elif page_type == "cl":  # Clientes
        total = db.execute("SELECT COUNT(*) FROM usuarios WHERE tipo_usuario = 'cliente'").fetchone()[0]
        rows = db.execute("SELECT * FROM usuarios WHERE tipo_usuario = 'cliente' ORDER BY id ASC LIMIT ? OFFSET ?", (PER_PAGE, offset)).fetchall()
        clientes = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "clientes"

    elif page_type == "re":  # Reseñas
        total = db.execute("SELECT COUNT(*) FROM reseñas").fetchone()[0]
        rows = db.execute("""
            SELECT r.*, cu.nombre AS cuidador_nombre, cl.nombre AS cliente_nombre
            FROM reseñas r
            JOIN usuarios cu ON r.cuidador_id = cu.id
            JOIN usuarios cl ON r.cliente_id = cl.id
            ORDER BY r.id ASC
            LIMIT ? OFFSET ?
        """, (PER_PAGE, offset)).fetchall()
        reseñas = Pagination(page_num, PER_PAGE, total, rows)
        page_type_name = "reseñas"

    else:
        flash("Tipo de página no reconocido.", "danger")
        return redirect(url_for("admin_main"))

    # Obtener listas para selects
    all_cuidadores = db.execute("SELECT id, nombre FROM usuarios WHERE tipo_usuario = 'cuidador' ORDER BY nombre").fetchall()
    all_clientes = db.execute("SELECT id, nombre FROM usuarios WHERE tipo_usuario = 'cliente' ORDER BY nombre").fetchall()

    # Pasamos siempre las tres variables, aunque sean None
    return render_template(
        "admin.html",
        cuidadores=cuidadores,
        clientes=clientes,
        reseñas=reseñas,
        all_cuidadores=all_cuidadores,
        all_clientes=all_clientes,
        type=page_type_name
    )
# --- 7. RUTAS CRUD COMPLETAS ---

# CUIDADORES
@app.route('/admin/cuidador/add', methods=['POST'])
@login_required
def add_cuidador():
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    try:
        password = generate_password_hash("default_password", method='pbkdf2:sha256')
        cursor = db.cursor()
        cursor.execute("INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (?, ?, ?, 'cuidador')",
                       (request.form['nombre'], request.form['email'], password))
        usuario_id = cursor.lastrowid
        foto_data = request.files['foto'].read() if 'foto' in request.files and request.files['foto'].filename != '' else None
        cursor.execute("INSERT INTO cuidadores (usuario_id, descripcion, ubicacion, lat, lng, rating, foto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (usuario_id, request.form['descripcion'], request.form['ubicacion'], 
                        float(request.form.get('lat') or 0), float(request.form.get('lng') or 0), 
                        float(request.form.get('rating') or 0), foto_data))
        servicios = request.form.getlist('servicios')
        if servicios:
            cursor.executemany("INSERT INTO servicios_cuidadores (cuidador_id, servicio) VALUES (?, ?)", [(usuario_id, s) for s in servicios])
        db.commit()
        flash('🐾 Cuidador añadido con éxito!', 'success')
    except sqlite3.IntegrityError:
        db.rollback()
        flash('El email ya está en uso.', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return redirect(url_for('admin_main'))

@app.route('/admin/cuidador/edit/<int:id>', methods=['POST'])
@login_required
def edit_cuidador(id):
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    try:
       
        db.execute("UPDATE usuarios SET nombre = ?, email = ? WHERE id = ?", (request.form['nombre'], request.form['email'], id))
        params = [request.form['descripcion'], request.form['ubicacion'],
            float(request.form.get('lat') or 0), float(request.form.get('lng') or 0),
            float(request.form.get('rating') or 0)]
        foto_query_part = ""
        if 'foto' in request.files and request.files['foto'].filename != '':
            foto_query_part = ", foto = ?"
            params.append(request.files['foto'].read())
        params.append(id)
        db.execute(f"UPDATE cuidadores SET descripcion=?, ubicacion=?, lat=?, lng=?, rating=?{foto_query_part} WHERE usuario_id=?", tuple(params))
        db.execute("DELETE FROM servicios_cuidadores WHERE cuidador_id = ?", (id,))
        servicios = request.form.getlist('servicios')
        if servicios:
            print("Hay servicios")
            db.executemany("INSERT INTO servicios_cuidadores (cuidador_id, servicio) VALUES (?, ?)", [(id, s) for s in servicios])
        db.commit()
        flash('🐾 Cuidador actualizado!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return redirect(url_for('admin_main'))

@app.route('/admin/cuidador/delete/<int:id>', methods=['POST'])
@login_required
def delete_cuidador(id):
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    db.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    db.commit()
    flash('🐾 Cuidador eliminado.', 'success')
    return redirect(url_for('admin_main'))

# CLIENTES
@app.route('/admin/cliente/add', methods=['POST'])
@login_required
def add_cliente():
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    if not request.form['password']:
        flash('La contraseña es obligatoria.', 'danger')
        return redirect(url_for('admin_main'))
    db = get_db()
    try:
        hashed_password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        db.execute("INSERT INTO usuarios (nombre, email, password, tipo_usuario) VALUES (?, ?, ?, 'cliente')",
                   (request.form['nombre'], request.form['email'], hashed_password))
        db.commit()
        flash('👤 Cliente añadido!', 'success')
    except sqlite3.IntegrityError:
        flash('El email ya está registrado.', 'danger')
    return redirect(url_for('admin_main'))

@app.route('/admin/cliente/edit/<int:id>', methods=['POST'])
@login_required
def edit_cliente(id):
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    password = request.form['password']
    if password:
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        db.execute("UPDATE usuarios SET nombre = ?, email = ?, password = ? WHERE id = ?",
                   (request.form['nombre'], request.form['email'], hashed_password, id))
    else:
        db.execute("UPDATE usuarios SET nombre = ?, email = ? WHERE id = ?", (request.form['nombre'], request.form['email'], id))
    db.commit()
    flash('👤 Cliente actualizado!', 'success')
    return redirect(url_for('admin_main'))

@app.route('/admin/cliente/delete/<int:id>', methods=['POST'])
@login_required
def delete_cliente(id):
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    db.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    db.commit()
    flash('👤 Cliente eliminado.', 'success')
    return redirect(url_for('admin_main'))

# RESEÑAS
@app.route('/admin/reseña/add', methods=['POST'])
@login_required
def add_reseña():
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    try:
        db.execute("INSERT INTO reseñas (cuidador_id, cliente_id, texto, calificacion) VALUES (?, ?, ?, ?)",
                   (request.form['cuidador_id'], request.form['cliente_id'], request.form['texto'], request.form['calificacion']))
        db.commit()
        flash('⭐ Reseña añadida!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return redirect(url_for('admin_main'))

@app.route('/admin/reseña/edit/<int:id>', methods=['POST'])
@login_required
def edit_reseña(id):
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    try:
        db.execute("UPDATE reseñas SET cuidador_id = ?, cliente_id = ?, texto = ?, calificacion = ? WHERE id = ?",
                   (request.form['cuidador_id'], request.form['cliente_id'], request.form['texto'], request.form['calificacion'], id))
        db.commit()
        flash('⭐ Reseña actualizada!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ocurrió un error: {e}', 'danger')
    return redirect(url_for('admin_main'))

@app.route('/admin/reseña/delete/<int:id>', methods=['POST'])
@login_required
def delete_reseña(id):
    if current_user.tipo_usuario != 'admin': return redirect(url_for('dashboard'))
    db = get_db()
    db.execute("DELETE FROM reseñas WHERE id = ?", (id,))
    db.commit()
    flash('⭐ Reseña eliminada.', 'success')
    return redirect(url_for('admin_main'))
@app.route('/api/reviews/<int:cuidador_id>')
@login_required
def get_reviews_by_cuidador(cuidador_id):
    db = get_db()
    reseñas = db.execute("""
        SELECT r.texto, r.calificacion, u.nombre AS cliente_nombre FROM reseñas r
        JOIN usuarios u ON r.cliente_id = u.id
        WHERE r.cuidador_id = ? ORDER BY r.id DESC
    """, (cuidador_id,)).fetchall()
    return jsonify({"status": "success", "data": [dict(row) for row in reseñas]})
# No necesitas las importaciones de smtplib, ssl, etc. ¡Puedes borrarlas!

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Obtiene los datos del formulario
        nombre = request.form.get('name')
        email = request.form.get('email')
        asunto = request.form.get('subject')
        mensaje = request.form.get('message')

        try:
            db = get_db()
            db.execute(
                "INSERT INTO mensajes_contacto (nombre, email, asunto, mensaje) VALUES (?, ?, ?, ?)",
                (nombre, email, asunto, mensaje)
            )
            db.commit()
            flash('¡Gracias por tu mensaje! Lo hemos recibido correctamente.', 'success')
        except Exception as e:
            print(f"Error al guardar el mensaje: {e}")
            flash('Lo sentimos, hubo un problema al guardar tu mensaje.', 'danger')

        return redirect(url_for('contact'))

    # Si el método es GET, simplemente muestra el formulario
    return render_template('contact.html')


# --- 8. ARRANQUE DE LA APLICACIÓN ---
if __name__ == '__main__':
    with app.app_context():        
        init_db()
    app.run(debug=True)