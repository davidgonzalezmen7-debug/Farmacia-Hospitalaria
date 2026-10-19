import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "farmacia_secret_key_123")

# Configuración de Base de Datos PostgreSQL / SQLite (compatible con psycopg2 en Render)
db_url = os.environ.get("DATABASE_URL", "sqlite:///farmacia.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and "+psycopg2" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -----------------------------------------------------------------------------
# MODELOS DE BASE DE DATOS
# -----------------------------------------------------------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # Administrador / Farmacéutico / Enfermería / Médico
    pin = db.Column(db.String(20), nullable=False)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    stock_general = db.Column(db.Integer, default=0)
    stock_quirofano = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default="pza")

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    warehouse = db.Column(db.String(50), nullable=False)
    service = db.Column(db.String(100), nullable=True)
    user_name = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.String(200), nullable=True)

# -----------------------------------------------------------------------------
# PLANTILLA HTML INTEGRADA (DISEÑO MODERNO CON MODALES Y PESTAÑAS)
# -----------------------------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farmacia Hospitalaria - Control e Inventario</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 font-sans">
    
    <!-- Encabezado Principal -->
    <header class="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 text-white shadow-lg border-b border-indigo-700">
        <div class="max-w-7xl mx-auto px-4 py-4 flex flex-col md:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-3">
                <div class="bg-blue-600 p-2.5 rounded-xl shadow-inner">
                    <i class="fa-solid fa-hospital-user text-2xl text-white"></i>
                </div>
                <div>
                    <h1 class="text-2xl font-extrabold tracking-tight">Farmacia Hospitalaria</h1>
                    <p class="text-xs text-blue-200">Terminal Compartida & Control de Dosis Unitaria</p>
                </div>
            </div>
            
            <nav class="flex flex-wrap gap-2 text-sm font-semibold">
                <a href="/terminal{% if current_user %}?user_id={{ current_user.id }}{% endif %}" class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 transition flex items-center gap-2">
                    <i class="fa-solid fa-clipboard-list"></i> Captura
                </a>
                <a href="/usuarios" class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 transition flex items-center gap-2">
                    <i class="fa-solid fa-users-gear"></i> Personal / Usuarios
                </a>
                <a href="/etiquetas" class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 transition flex items-center gap-2">
                    <i class="fa-solid fa-tags"></i> Etiquetas DU
                </a>
            </nav>
        </div>
    </header>

    <main class="max-w-7xl mx-auto p-4 md:p-6">
        
        <!-- Mensajes Flash -->
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="p-4 mb-4 text-sm rounded-xl shadow-sm flex items-center gap-3 {% if category == 'error' %}bg-rose-100 text-rose-800 border border-rose-300{% else %}bg-emerald-100 text-emerald-800 border border-emerald-300{% endif %}">
                <i class="fa-solid {% if category == 'error' %}fa-circle-xmark{% else %}fa-circle-check{% endif %} text-lg"></i>
                <span class="font-medium">{{ message }}</span>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {% if view == 'terminal' %}
        
        <!-- SELECCIÓN DE USUARIO O CAPTURA DE MOVIMIENTO -->
        {% if not current_user %}
        <!-- MENÚ DE SELECCIÓN DE USUARIO -->
        <div class="mb-8">
            <div class="text-center max-w-xl mx-auto mb-6">
                <h2 class="text-2xl font-bold text-slate-900">Bienvenido al Sistema</h2>
                <p class="text-sm text-slate-500 mt-1">Seleccione su usuario e ingrese su PIN para registrar un movimiento.</p>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                {% for u in users %}
                <button onclick="openPinModal('{{ u.id }}', '{{ u.name }}', '{{ u.role }}')" class="bg-white p-5 rounded-2xl shadow-sm hover:shadow-md border border-slate-200 hover:border-blue-500 transition duration-200 text-center group flex flex-col items-center">
                    <div class="w-16 h-16 rounded-full bg-blue-50 group-hover:bg-blue-600 group-hover:text-white text-blue-600 flex items-center justify-center text-2xl font-bold transition mb-3">
                        <i class="fa-solid {% if 'Admin' in u.role or 'Farmacia' in u.role %}fa-user-shield{% elif 'Enfermer' in u.role %}fa-user-nurse{% else %}fa-user-doctor{% endif %}"></i>
                    </div>
                    <h3 class="font-bold text-slate-900 text-sm group-hover:text-blue-600 transition">{{ u.name }}</h3>
                    <span class="mt-1 text-xs px-2.5 py-0.5 rounded-full font-medium bg-slate-100 text-slate-600">{{ u.role }}</span>
                </button>
                {% endfor %}
            </div>
        </div>
        {% else %}
        <!-- USUARIO ACTIVO BANNER -->
        <div class="bg-blue-900 text-white p-4 rounded-2xl shadow-md mb-6 flex justify-between items-center">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-blue-700 flex items-center justify-center text-white text-lg">
                    <i class="fa-solid fa-user-check"></i>
                </div>
                <div>
                    <p class="text-xs text-blue-200">Usuario Autenticado</p>
                    <h3 class="font-bold text-base">{{ current_user.name }} <span class="text-xs font-normal text-blue-300">({{ current_user.role }})</span></h3>
                </div>
            </div>
            <a href="/terminal" class="text-xs bg-blue-800 hover:bg-blue-700 px-3 py-1.5 rounded-lg transition font-medium border border-blue-600">
                <i class="fa-solid fa-right-from-bracket"></i> Cambiar Usuario
            </a>
        </div>
        {% endif %}

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <!-- FORMULARIO DE CAPTURA -->
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-pen-to-square text-blue-600"></i> Registrar Movimiento
                </h2>

                <form action="/register" method="POST" class="space-y-4">
                    {% if current_user %}
                        <input type="hidden" name="user_id" value="{{ current_user.id }}">
                    {% else %}
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Personal Responsable</label>
                            <select name="user_id" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                                <option value="">Seleccione Usuario...</option>
                                {% for u in users %}
                                    <option value="{{ u.id }}">{{ u.name }} ({{ u.role }})</option>
                                {% endfor %}
                            </select>
                        </div>
                    {% endif %}

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN de Seguridad</label>
                        <input type="password" name="pin" required placeholder="PIN personal" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <!-- BUSCADOR DE INSUMOS -->
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Insumo / Medicamento (Buscador)</label>
                        <input list="items_list" name="item_search" required placeholder="Escriba código o nombre..." class="w-full p-2.5 border rounded-xl text-sm bg-blue-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none font-medium">
                        <datalist id="items_list">
                            {% for item in items %}
                                <option value="{{ item.code }} - {{ item.name }}">General: {{ item.stock_general }} | Quirófano: {{ item.stock_quirofano }}</option>
                            {% endfor %}
                        </datalist>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Tipo Movimiento</label>
                            <select name="type" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                                <option value="Salida">Salida</option>
                                <option value="Traspaso Qx">Traspaso Qx</option>
                                <option value="Entrada">Entrada</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Almacén</label>
                            <select name="warehouse" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                                <option value="Almacén General">Almacén General</option>
                                <option value="Quirófano">Quirófano</option>
                            </select>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Cantidad</label>
                            <input type="number" min="1" name="quantity" required value="1" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Servicio / Cama</label>
                            <input type="text" name="service" placeholder="Ej. Urgencias" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                        </div>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Notas adicionales</label>
                        <input type="text" name="notes" placeholder="Observaciones..." class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2">
                        <i class="fa-solid fa-check"></i> Guardar Movimiento
                    </button>
                </form>
            </div>

            <!-- VISTA DE EXISTENCIAS Y BITÁCORA PRIVADA -->
            <div class="space-y-6 lg:col-span-2">
                
                <!-- Existencias -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-boxes-stacked text-indigo-600"></i> Stock en Inventario
                    </h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm text-left text-slate-600">
                            <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                <tr>
                                    <th class="p-3">Código</th>
                                    <th class="p-3">Insumo</th>
                                    <th class="p-3 text-center">General</th>
                                    <th class="p-3 text-center">Quirófano</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for item in items %}
                                <tr class="hover:bg-slate-50 transition">
                                    <td class="p-3 font-mono text-xs font-bold text-blue-900">{{ item.code }}</td>
                                    <td class="p-3 font-medium text-slate-900">
                                        {{ item.name }}
                                        <span class="block text-[11px] text-slate-400 font-normal">{{ item.category }}</span>
                                    </td>
                                    <td class="p-3 text-center">
                                        <span class="px-2.5 py-1 rounded-full text-xs font-bold {% if item.stock_general < 10 %}bg-rose-100 text-rose-700{% else %}bg-slate-100 text-slate-800{% endif %}">
                                            {{ item.stock_general }} {{ item.unit }}
                                        </span>
                                    </td>
                                    <td class="p-3 text-center">
                                        <span class="px-2.5 py-1 rounded-full text-xs font-bold {% if item.stock_quirofano < 5 %}bg-amber-100 text-amber-700{% else %}bg-slate-100 text-slate-800{% endif %}">
                                            {{ item.stock_quirofano }} {{ item.unit }}
                                        </span>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- BITÁCORA PRIVADA PARA ADMINISTRACIÓN -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-user-lock text-slate-700"></i> Bitácora de Auditoría (Administración)
                    </h2>

                    {% if is_admin %}
                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left text-slate-600">
                            <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                <tr>
                                    <th class="p-2.5">Fecha</th>
                                    <th class="p-2.5">Tipo</th>
                                    <th class="p-2.5">Insumo</th>
                                    <th class="p-2.5 text-center">Cant.</th>
                                    <th class="p-2.5">Responsable</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for mov in movements %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2.5 text-slate-400">{{ mov.timestamp.strftime('%d/%m %H:%M') }}</td>
                                    <td class="p-2.5 font-bold text-slate-800">{{ mov.type }}</td>
                                    <td class="p-2.5 font-medium text-slate-900">{{ mov.item_name }}</td>
                                    <td class="p-2.5 text-center font-bold">{{ mov.quantity }}</td>
                                    <td class="p-2.5 text-indigo-900 font-semibold">{{ mov.user_name }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% else %}
                    <div class="p-6 text-center bg-slate-50 rounded-xl border border-dashed border-slate-300">
                        <p class="text-xs text-slate-500">🔒 <strong>Acceso Restringido:</strong> La bitácora completa solo es accesible al iniciar sesión como <strong>Administrador / Farmacia Titular</strong>.</p>
                    </div>
                    {% endif %}
                </div>

            </div>

        </div>

        <!-- MODAL PIN SEGURIDAD -->
        <div id="pinModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden flex items-center justify-center p-4 z-50">
            <div class="bg-white rounded-2xl max-w-sm w-full p-6 shadow-2xl border border-slate-100">
                <div class="text-center mb-4">
                    <div class="w-12 h-12 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mx-auto text-xl mb-2">
                        <i class="fa-solid fa-lock"></i>
                    </div>
                    <h3 class="font-bold text-lg text-slate-900" id="modalUserName">Confirmar Identidad</h3>
                    <p class="text-xs text-slate-500" id="modalUserRole"></p>
                </div>

                <form action="/login_pin" method="POST" class="space-y-4">
                    <input type="hidden" name="user_id" id="modalUserId">
                    <div>
                        <input type="password" name="pin" required placeholder="Ingrese PIN" class="w-full text-center text-xl tracking-widest p-3 border rounded-xl focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>
                    <div class="flex gap-2">
                        <button type="button" onclick="closePinModal()" class="w-1/2 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-sm transition">Cancelar</button>
                        <button type="submit" class="w-1/2 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-sm transition">Ingresar</button>
                    </div>
                </form>
            </div>
        </div>

        {% elif view == 'usuarios' %}
        <!-- MÓDULO DE GESTIÓN Y CREACIÓN DE USUARIOS -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-user-plus text-blue-600"></i> Registrar Nuevo Usuario
                </h2>

                <form action="/create_user" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre Completo</label>
                        <input type="text" name="name" required placeholder="Ej. Dr. Juan Pérez" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Rol / Cargo</label>
                        <select name="role" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                            <option value="Enfermería">Enfermería</option>
                            <option value="Médico">Médico</option>
                            <option value="Farmacéutico">Farmacéutico</option>
                            <option value="Administrador">Administrador</option>
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN de Acceso (Contraseña)</label>
                        <input type="password" name="pin" required placeholder="PIN numérico" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2">
                        <i class="fa-solid fa-user-check"></i> Crear Usuario
                    </button>
                </form>
            </div>

            <!-- PERSONAL REGISTRADO -->
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-users text-indigo-600"></i> Personal Autorizado Registrado
                </h2>
                
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {% for u in users %}
                    <div class="p-4 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between">
                        <div>
                            <h4 class="font-bold text-slate-900 text-sm">{{ u.name }}</h4>
                            <p class="text-xs text-slate-500">{{ u.role }}</p>
                        </div>
                        <span class="text-xs font-mono bg-white px-2.5 py-1 rounded-lg border text-slate-400">PIN: ****</span>
                    </div>
                    {% endfor %}
                </div>
            </div>

        </div>

        {% elif view == 'etiquetas' %}
        <!-- PESTAÑA GENERACIÓN DE ETIQUETAS DU -->
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-200">
            <h2 class="text-xl font-bold text-slate-900 mb-2 flex items-center gap-2">
                <i class="fa-solid fa-tags text-blue-600"></i> Módulo de Etiquetas de Dosis Unitaria (DU)
            </h2>
            <p class="text-sm text-slate-500 mb-6">Módulo estandarizado para generación e impresión de etiquetas de medicamentos.</p>
            
            <div class="p-10 border-2 border-dashed border-blue-200 rounded-2xl text-center bg-blue-50/50">
                <i class="fa-solid fa-print text-4xl text-blue-500 mb-3"></i>
                <p class="text-slate-700 font-bold">Impresión de Etiquetas Lista para Vincular</p>
                <p class="text-xs text-slate-500 max-w-md mx-auto mt-1">Este espacio permitirá generar e imprimir en formato físico etiquetas estandarizadas para Dosis Unitaria a partir de las existencias registradas.</p>
            </div>
        </div>
        {% endif %}

    </main>

    <script>
        function openPinModal(id, name, role) {
            document.getElementById('modalUserId').value = id;
            document.getElementById('modalUserName').innerText = name;
            document.getElementById('modalUserRole').innerText = role;
            document.getElementById('pinModal').classList.remove('hidden');
        }
        function closePinModal() {
            document.getElementById('pinModal').classList.add('hidden');
        }
    </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# RUTAS DE LA APLICACIÓN
# -----------------------------------------------------------------------------

@app.route("/")
@app.route("/terminal")
def terminal():
    items = Item.query.order_by(Item.name).all()
    users = User.query.order_by(User.name).all()
    movements = Movement.query.order_by(Movement.timestamp.desc()).limit(50).all()
    
    user_id = request.args.get("user_id")
    current_user = User.query.get(user_id) if user_id else None
    is_admin = current_user and current_user.role in ["Administrador", "Farmacéutico", "Farmacia Titular"]
    
    return render_template_string(
        HTML_TEMPLATE, 
        view="terminal", 
        items=items, 
        users=users, 
        movements=movements, 
        current_user=current_user,
        is_admin=is_admin
    )

@app.route("/login_pin", methods=["POST"])
def login_pin():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    
    user = User.query.get(user_id)
    if user and user.pin == pin:
        flash(f"Bienvenido/a {user.name}", "success")
        return redirect(url_for("terminal", user_id=user.id))
    else:
        flash("PIN o contraseña incorrecta.", "error")
        return redirect(url_for("terminal"))

@app.route("/usuarios")
def usuarios():
    users = User.query.order_by(User.name).all()
    return render_template_string(HTML_TEMPLATE, view="usuarios", users=users)

@app.route("/create_user", methods=["POST"])
def create_user():
    name = request.form.get("name", "").strip()
    role = request.form.get("role")
    pin = request.form.get("pin", "").strip()

    if not name or not pin:
        flash("Por favor complete todos los campos obligatorios.", "error")
        return redirect(url_for("usuarios"))

    new_user = User(name=name, role=role, pin=pin)
    db.session.add(new_user)
    db.session.commit()

    flash(f"Usuario {name} registrado con éxito.", "success")
    return redirect(url_for("usuarios"))

@app.route("/etiquetas")
def etiquetas():
    return render_template_string(HTML_TEMPLATE, view="etiquetas")

@app.route("/register", methods=["POST"])
def register_movement():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    item_search = request.form.get("item_search", "").strip()
    mov_type = request.form.get("type")
    warehouse = request.form.get("warehouse")
    quantity = int(request.form.get("quantity", 1))
    service = request.form.get("service")
    notes = request.form.get("notes")

    # Validar Usuario y PIN
    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN o contraseña de verificación incorrecta.", "error")
        return redirect(url_for("terminal", user_id=user_id if user else None))

    # Buscar insumo por clave o nombre
    item_code = item_search.split(" - ")[0] if " - " in item_search else item_search
    item = Item.query.filter((Item.code == item_code) | (Item.name.ilike(f"%{item_search}%"))).first()

    if not item:
        flash("Insumo no encontrado. Seleccione una opción válida de la lista.", "error")
        return redirect(url_for("terminal", user_id=user.id))

    # Lógica de Stock
    if mov_type == "Entrada":
        if warehouse == "Almacén General":
            item.stock_general += quantity
        else:
            item.stock_quirofano += quantity

    elif mov_type == "Salida":
        if warehouse == "Almacén General":
            if item.stock_general < quantity:
                flash(f"Stock insuficiente en Almacén General ({item.stock_general} disponibes).", "error")
                return redirect(url_for("terminal", user_id=user.id))
            item.stock_general -= quantity
        else:
            if item.stock_quirofano < quantity:
                flash(f"Stock insuficiente en Quirófano ({item.stock_quirofano} disponibles).", "error")
                return redirect(url_for("terminal", user_id=user.id))
            item.stock_quirofano -= quantity

    elif mov_type == "Traspaso Qx":
        if item.stock_general < quantity:
            flash("Stock insuficiente en Almacén General para el traspaso.", "error")
            return redirect(url_for("terminal", user_id=user.id))
        item.stock_general -= quantity
        item.stock_quirofano += quantity

    # Guardar en Bitácora
    mov = Movement(
        item_code=item.code,
        item_name=item.name,
        type=mov_type,
        quantity=quantity,
        warehouse=warehouse,
        service=service,
        user_name=user.name,
        notes=notes
    )
    db.session.add(mov)
    db.session.commit()

    flash("Movimiento registrado y guardado exitosamente.", "success")
    return redirect(url_for("terminal", user_id=user.id))

# -----------------------------------------------------------------------------
# INICIALIZACIÓN DE DATOS PRECARGADOS (SEEMED DATABASE)
# -----------------------------------------------------------------------------

def seed_database():
    with app.app_context():
        db.create_all()
        
        # Cargar lista completa de usuarios si la tabla está vacía
        if User.query.count() == 0:
            users_list = [
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678"),
                User(name="Dra. Sofia Ramos", role="Farmacia Titular", pin="4321"),
                User(name="Hannia Martinez Salas", role="Enfermera Quirófano", pin="1234"),
                User(name="Carlos Rivera López", role="Enfermero Urgencias", pin="1111"),
                User(name="Dra. María Elena Castro", role="Anestesióloga", pin="2222")
            ]
            db.session.add_all(users_list)

        # Cargar catálogo de prueba si la tabla está vacía
        if Item.query.count() == 0:
            items_list = [
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", stock_general=30, stock_quirofano=10),
                Item(code="MAT-001", name="Jeringa 10ml c/Aguja", category="Material", stock_general=300, stock_quirofano=50),
                Item(code="MAT-002", name="Equipo Venoclisis Normogotero", category="Material", stock_general=100, stock_quirofano=25)
            ]
            db.session.add_all(items_list)

        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
