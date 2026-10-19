import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "farmacia_secret_key_123")

# Configuración de Base de Datos PostgreSQL / SQLite
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
    role = db.Column(db.String(50), nullable=False)
    pin = db.Column(db.String(20), nullable=False)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    via_administracion = db.Column(db.String(50), nullable=True)
    presentacion = db.Column(db.String(50), nullable=True)
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
    patient_name = db.Column(db.String(150), nullable=True)
    patient_id = db.Column(db.String(50), nullable=True)
    user_name = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.String(200), nullable=True)

# -----------------------------------------------------------------------------
# PLANTILLA HTML INTEGRADA CON BUSCADOR EN TIEMPO REAL
# -----------------------------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farmacia Hospitalaria - Control de Inventario</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 font-sans">
    
    <!-- Encabezado y Menú Principal -->
    <header class="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 text-white shadow-lg sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 py-3 flex flex-col md:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-3">
                <div class="bg-blue-600 p-2.5 rounded-xl shadow-inner">
                    <i class="fa-solid fa-hospital-user text-2xl text-white"></i>
                </div>
                <div>
                    <h1 class="text-xl font-extrabold tracking-tight">Farmacia Hospitalaria</h1>
                    <p class="text-[11px] text-blue-200">Terminal Compartida & Control de Dosis Unitaria</p>
                </div>
            </div>
            
            <!-- Pestañas de Navegación -->
            <nav class="flex flex-wrap gap-1.5 text-xs font-bold">
                <a href="/terminal" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'terminal' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-pen-to-square"></i> Captura y Surtido
                </a>
                <a href="/inventario" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'inventario' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-boxes-stacked"></i> Inventario
                </a>
                <a href="/bitacora" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'bitacora' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-clock-rotate-left"></i> Bitácora e Histórico
                </a>
                <a href="/usuarios" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'usuarios' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-lock"></i> Usuarios / PINs (Admin)
                </a>
                <a href="/etiquetas" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'etiquetas' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
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
        <!-- PESTAÑA 1: CAPTURA Y SURTIDO -->
        <div class="space-y-6">
            
            <!-- Seleccionar Personal -->
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-users text-blue-600"></i> Seleccionar Personal Responsable
                    </h2>
                    <p class="text-xs text-slate-500">Haga clic sobre su nombre para cargarlo en el formulario de captura.</p>
                </div>

                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                    {% for u in users %}
                    <button type="button" onclick="selectUser('{{ u.id }}')" class="p-3.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-400 transition text-center group flex flex-col items-center">
                        <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-lg mb-2 group-hover:scale-110 transition">
                            <i class="fa-solid {% if 'Admin' in u.role or 'Farmacia' in u.role %}fa-user-shield{% elif 'Enfermer' in u.role %}fa-user-nurse{% else %}fa-user-doctor{% endif %}"></i>
                        </div>
                        <h4 class="font-bold text-slate-800 text-xs group-hover:text-blue-600 truncate w-full">{{ u.name }}</h4>
                        <span class="text-[10px] text-slate-500 mt-0.5">{{ u.role }}</span>
                    </button>
                    {% endfor %}
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                <!-- Formulario de Registro de Movimiento y Paciente -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-prescription-bottle-medical text-blue-600"></i> Registrar Movimiento / Surtido a Paciente
                    </h2>

                    <form action="/register" method="POST" class="space-y-4">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Usuario Responsable</label>
                                <select name="user_id" id="userSelect" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                                    <option value="">Seleccione Usuario...</option>
                                    {% for u in users %}
                                        <option value="{{ u.id }}">{{ u.name }} ({{ u.role }})</option>
                                    {% endfor %}
                                </select>
                            </div>

                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN / Contraseña</label>
                                <input type="password" name="pin" required placeholder="PIN de Seguridad" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                            </div>
                        </div>

                        <!-- BUSCADOR PARA SURTIDO -->
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Insumo / Medicamento (Buscador)</label>
                            <input list="items_list" name="item_search" required placeholder="Escriba código de barras, clave o nombre..." class="w-full p-2.5 border rounded-xl text-sm bg-blue-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none font-medium">
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
                                    <option value="Salida">Salida a Paciente / Servicio</option>
                                    <option value="Traspaso Qx">Traspaso a Quirófano</option>
                                    <option value="Entrada">Entrada (Stock)</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Almacén Origen</label>
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
                                <input type="text" name="service" placeholder="Ej. Urgencias / Cama 4" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                            </div>
                        </div>

                        <!-- DATOS DEL PACIENTE -->
                        <div class="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                            <h3 class="text-xs font-bold text-blue-900 uppercase flex items-center gap-1.5">
                                <i class="fa-solid fa-bed-pulse"></i> Datos del Paciente (Para Surtido)
                            </h3>
                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-[11px] font-semibold text-slate-600 mb-1">Nombre Completo del Paciente</label>
                                    <input type="text" name="patient_name" placeholder="Ej. Juan Pérez López" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                                </div>
                                <div>
                                    <label class="block text-[11px] font-semibold text-slate-600 mb-1">No. Expediente / Cama</label>
                                    <input type="text" name="patient_id" placeholder="Ej. EXP-9823 / Cama 12" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                                </div>
                            </div>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Notas adicionales</label>
                            <input type="text" name="notes" placeholder="Observaciones opcionales..." class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                        </div>

                        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2">
                            <i class="fa-solid fa-check"></i> Guardar Movimiento / Surtido
                        </button>
                    </form>
                </div>

                <!-- Formulario para Alta de Nuevo Medicamento -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-plus-circle text-emerald-600"></i> Dar de Alta Nuevo Medicamento
                    </h2>

                    <form action="/add_item" method="POST" class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Código / Clave</label>
                            <input type="text" name="code" required placeholder="Ej. MED-005" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none">
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre / Descripción</label>
                            <input type="text" name="name" required placeholder="Ej. Omeprazol 40mg" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none">
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Categoría</label>
                            <select name="category" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-emerald-500 outline-none">
                                <option value="Medicamento">Medicamento</option>
                                <option value="Material Curación">Material Curación</option>
                                <option value="Solución / Inyectable">Solución / Inyectable</option>
                            </select>
                        </div>

                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Vía Administr.</label>
                                <select name="via_administracion" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-emerald-500 outline-none">
                                    <option value="Oral">Oral</option>
                                    <option value="Intravenosa">Intravenosa (IV)</option>
                                    <option value="Intramuscular">Intramuscular (IM)</option>
                                    <option value="Subcutánea">Subcutánea</option>
                                    <option value="Tópica">Tópica</option>
                                    <option value="Oftálmica">Oftálmica</option>
                                    <option value="Nasal">Nasal</option>
                                    <option value="Inhalatoria">Inhalatoria</option>
                                    <option value="Sublingual">Sublingual</option>
                                    <option value="Otra">Otra</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Presentación</label>
                                <select name="presentacion" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-emerald-500 outline-none">
                                    <option value="Tableta">Tableta</option>
                                    <option value="Cápsula">Cápsula</option>
                                    <option value="Ampolleta">Ampolleta</option>
                                    <option value="Frasco Ámpula">Frasco Ámpula</option>
                                    <option value="Solución">Solución</option>
                                    <option value="Jarabe">Jarabe</option>
                                    <option value="Crema">Crema</option>
                                    <option value="Ungüento">Ungüento</option>
                                    <option value="Parche">Parche</option>
                                    <option value="Otro">Otro</option>
                                </select>
                            </div>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Unidad</label>
                                <input type="text" name="unit" required value="pza" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Stock Inicial</label>
                                <input type="number" min="0" name="stock_general" required value="50" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none">
                            </div>
                        </div>

                        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2 mt-4">
                            <i class="fa-solid fa-box-archive"></i> Registrar Medicamento
                        </button>
                    </form>
                </div>

            </div>

        </div>

        {% elif view == 'inventario' %}
        <!-- PESTAÑA 2: INVENTARIO COMPLETO CON BUSCADOR EN TIEMPO REAL -->
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div class="flex flex-col md:flex-row justify-between items-center gap-4 mb-6 border-b pb-4">
                <div>
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-boxes-stacked text-blue-600"></i> Stock General de Inventario
                    </h2>
                    <p class="text-xs text-slate-500">Existencias en tiempo real por almacén.</p>
                </div>

                <!-- BUSCADOR DE INSUMOS -->
                <div class="w-full md:w-80 relative">
                    <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-3 text-slate-400 text-sm"></i>
                    <input type="text" id="inventorySearch" onkeyup="filterInventory()" placeholder="Buscar por código, nombre o vía..." class="w-full pl-10 pr-4 py-2 border rounded-xl text-xs bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none font-medium">
                </div>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left text-slate-600" id="inventoryTable">
                    <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                        <tr>
                            <th class="p-3">Código</th>
                            <th class="p-3">Descripción</th>
                            <th class="p-3">Categoría / Presentación</th>
                            <th class="p-3">Vía Administr.</th>
                            <th class="p-3 text-center">Almacén General</th>
                            <th class="p-3 text-center">Subalmacén Quirófano</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {% for item in items %}
                        <tr class="hover:bg-slate-50 transition inventory-row">
                            <td class="p-3 font-mono text-xs font-bold text-blue-900 col-code">{{ item.code }}</td>
                            <td class="p-3 font-bold text-slate-900 col-name">{{ item.name }}</td>
                            <td class="p-3 col-cat">
                                <span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                                    {{ item.category }} {% if item.presentacion %}({{ item.presentacion }}){% endif %}
                                </span>
                            </td>
                            <td class="p-3 text-xs font-semibold text-slate-700 col-via">{{ item.via_administracion or 'N/A' }}</td>
                            <td class="p-3 text-center">
                                <span class="px-3 py-1 rounded-full text-xs font-bold {% if item.stock_general < 10 %}bg-rose-100 text-rose-700{% else %}bg-emerald-100 text-emerald-800{% endif %}">
                                    {{ item.stock_general }} {{ item.unit }}
                                </span>
                            </td>
                            <td class="p-3 text-center">
                                <span class="px-3 py-1 rounded-full text-xs font-bold {% if item.stock_quirofano < 5 %}bg-amber-100 text-amber-700{% else %}bg-blue-100 text-blue-800{% endif %}">
                                    {{ item.stock_quirofano }} {{ item.unit }}
                                </span>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        {% elif view == 'bitacora' %}
        <!-- PESTAÑA 3: BITÁCORA E HISTÓRICO -->
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div class="mb-6 border-b pb-4">
                <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                    <i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora de Movimientos y Surtido a Pacientes
                </h2>
                <p class="text-xs text-slate-500">Registro cronológico completo de auditoría.</p>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-xs text-left text-slate-600">
                    <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                        <tr>
                            <th class="p-3">Fecha</th>
                            <th class="p-3">Tipo</th>
                            <th class="p-3">Medicamento / Insumo</th>
                            <th class="p-3 text
