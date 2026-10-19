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
    lote = db.Column(db.String(50), nullable=True)
    caducidad = db.Column(db.String(20), nullable=True)
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
# PLANTILLA HTML INTEGRADA
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
                                    <option value="{{ item.code }} - {{ item.name }}">Gen: {{ item.stock_general }} | Qx: {{ item.stock_quirofano }} | Lote: {{ item.lote or 'S/L' }}</option>
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

                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Lote</label>
                                <input type="text" name="lote" placeholder="Ej. LOT-2026-X" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Fecha Caducidad</label>
                                <input type="date" name="caducidad" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none">
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
        <!-- PESTAÑA 2: INVENTARIO CON EDICIÓN PROTEGIDA -->
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div class="flex flex-col md:flex-row justify-between items-center gap-4 mb-6 border-b pb-4">
                <div>
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-boxes-stacked text-blue-600"></i> Stock General e Inventario
                    </h2>
                    <p class="text-xs text-slate-500">Existencias en tiempo real por almacén. Edición exclusiva de Administrador.</p>
                </div>

                <div class="w-full md:w-80 relative">
                    <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-3 text-slate-400 text-sm"></i>
                    <input type="text" id="inventorySearch" onkeyup="filterInventory()" placeholder="Buscar por código, nombre, lote..." class="w-full pl-10 pr-4 py-2 border rounded-xl text-xs bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none font-medium">
                </div>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left text-slate-600" id="inventoryTable">
                    <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                        <tr>
                            <th class="p-3">Código</th>
                            <th class="p-3">Descripción</th>
                            <th class="p-3">Categoría / Presentación</th>
                            <th class="p-3">Lote / Caducidad</th>
                            <th class="p-3 text-center">General</th>
                            <th class="p-3 text-center">Quirófano</th>
                            <th class="p-3 text-center">Acción (Admin)</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {% for item in items %}
                        <tr class="hover:bg-slate-50 transition inventory-row">
                            <td class="p-3 font-mono text-xs font-bold text-blue-900 col-code">{{ item.code }}</td>
                            <td class="p-3 font-bold text-slate-900 col-name">
                                {{ item.name }}
                                <span class="block text-[11px] text-slate-400 font-normal">Vía: {{ item.via_administracion or 'N/A' }}</span>
                            </td>
                            <td class="p-3 col-cat">
                                <span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                                    {{ item.category }} {% if item.presentacion %}({{ item.presentacion }}){% endif %}
                                </span>
                            </td>
                            <td class="p-3 text-xs text-slate-600">
                                <span class="font-medium text-slate-800">Lote: {{ item.lote or 'S/L' }}</span>
                                <span class="block text-[10px] text-slate-400">Cad: {{ item.caducidad or 'S/F' }}</span>
                            </td>
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
                            <td class="p-3 text-center">
                                <button onclick="openEditModal('{{ item.id }}', '{{ item.code }}', '{{ item.name }}', '{{ item.category }}', '{{ item.via_administracion or '' }}', '{{ item.presentacion or '' }}', '{{ item.lote or '' }}', '{{ item.caducidad or '' }}', '{{ item.unit }}', '{{ item.stock_general }}', '{{ item.stock_quirofano }}')" class="px-3 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-xs font-bold transition shadow-sm flex items-center gap-1 mx-auto">
                                    <i class="fa-solid fa-lock"></i> Editar
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- MODAL DE EDICIÓN -->
        <div id="editModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden flex items-center justify-center p-4 z-50">
            <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto">
                <div class="flex justify-between items-center mb-4 border-b pb-2">
                    <h3 class="font-bold text-lg text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-pen-to-square text-amber-500"></i> Modificar Insumo (Administrador)
                    </h3>
                    <button onclick="closeEditModal()" class="text-slate-400 hover:text-slate-600 text-lg">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>

                <form action="/update_item" method="POST" class="space-y-3">
                    <input type="hidden" name="item_id" id="edit_item_id">
                    
                    <div class="p-3 bg-amber-50 rounded-xl border border-amber-200">
                        <label class="block text-xs font-bold text-amber-900 uppercase mb-1">🔒 PIN / Contraseña de Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="Ingrese PIN de Administrador (5678)" class="w-full p-2 border rounded-lg text-xs bg-white font-bold outline-none focus:ring-2 focus:ring-amber-500">
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Código</label>
                            <input type="text" name="code" id="edit_code" required class="w-full p-2 border rounded-xl text-xs font-mono font-bold bg-slate-50">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Categoría</label>
                            <select name="category" id="edit_category" required class="w-full p-2 border rounded-xl text-xs bg-slate-50">
                                <option value="Medicamento">Medicamento</option>
                                <option value="Material Curación">Material Curación</option>
                                <option value="Solución / Inyectable">Solución / Inyectable</option>
                            </select>
                        </div>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre / Descripción</label>
                        <input type="text" name="name" id="edit_name" required class="w-full p-2 border rounded-xl text-xs font-bold">
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Vía Administr.</label>
                            <input type="text" name="via_administracion" id="edit_via" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Presentación</label>
                            <input type="text" name="presentacion" id="edit_presentacion" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Lote</label>
                            <input type="text" name="lote" id="edit_lote" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Fecha Caducidad</label>
                            <input type="date" name="caducidad" id="edit_caducidad" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                    </div>

                    <div class="grid grid-cols-3 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Unidad</label>
                            <input type="text" name="unit" id="edit_unit" required class="w-full p-2 border rounded-xl text-xs">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Stock General</label>
                            <input type="number" name="stock_general" id="edit_stock_general" required class="w-full p-2 border rounded-xl text-xs font-bold">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Stock Quirófano</label>
                            <input type="number" name="stock_quirofano" id="edit_stock_quirofano" required class="w-full p-2 border rounded-xl text-xs font-bold">
                        </div>
                    </div>

                    <div class="flex gap-2 pt-3">
                        <button type="button" onclick="closeEditModal()" class="w-1/2 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs transition">Cancelar</button>
                        <button type="submit" class="w-1/2 py-2 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-xl text-xs transition">Guardar Cambios</button>
                    </div>
                </form>
            </div>
        </div>

        {% elif view == 'bitacora' %}
        <!-- PESTAÑA 3: BITÁCORA E HISTÓRICO CON FILTRO DÍA / ENTRADAS / SALIDAS -->
        <div class="space-y-6">
            
            <!-- TARJETAS CON TOTALES RESUMEN DEL DÍA -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div class="bg-white p-4 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-bold text-slate-500 uppercase">Salidas a Pacientes</p>
                        <h3 class="text-2xl font-black text-rose-600 mt-1">{{ total_salidas }} <span class="text-xs font-normal text-slate-400">pzas</span></h3>
                    </div>
                    <div class="w-12 h-12 bg-rose-100 text-rose-600 rounded-2xl flex items-center justify-center text-xl">
                        <i class="fa-solid fa-arrow-up-from-bracket"></i>
                    </div>
                </div>

                <div class="bg-white p-4 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-bold text-slate-500 uppercase">Entradas / Stock</p>
                        <h3 class="text-2xl font-black text-emerald-600 mt-1">{{ total_entradas }} <span class="text-xs font-normal text-slate-400">pzas</span></h3>
                    </div>
                    <div class="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-2xl flex items-center justify-center text-xl">
                        <i class="fa-solid fa-arrow-down-to-bracket"></i>
                    </div>
                </div>

                <div class="bg-white p-4 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-bold text-slate-500 uppercase">Traspasos a Qx</p>
                        <h3 class="text-2xl font-black text-blue-600 mt-1">{{ total_traspasos }} <span class="text-xs font-normal text-slate-400">pzas</span></h3>
                    </div>
                    <div class="w-12 h-12 bg-blue-100 text-blue-600 rounded-2xl flex items-center justify-center text-xl">
                        <i class="fa-solid fa-arrow-right-arrow-left"></i>
                    </div>
                </div>
            </div>

            <!-- FILTROS DE BÚSQUEDA Y FECHA -->
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4 border-b pb-3 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora e Histórico de Auditoría
                        </h2>
                        <p class="text-xs text-slate-500">Consulte los movimientos registrados filtrando por fecha o tipo de operación.</p>
                    </div>
                </div>

                <!-- FORMULARIO DE FILTRADO DE FECHA -->
                <form action="/bitacora" method="GET" class="grid grid-cols-1 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-6 bg-slate-50 p-4 rounded-xl border border-slate-200">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Filtrar por Fecha/Día</label>
                        <input type="date" name="filter_date" value="{{ selected_date }}" class="w-full p-2 border rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 outline-none font-bold">
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Tipo de Movimiento</label>
                        <select name="filter_type" class="w-full p-2 border rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                            <option value="">Todos los Tipos</option>
                            <option value="Salida" {% if selected_type == 'Salida' %}selected{% endif %}>Salidas a Paciente</option>
                            <option value="Entrada" {% if selected_type == 'Entrada' %}selected{% endif %}>Entradas (Stock)</option>
                            <option value="Traspaso Qx" {% if selected_type == 'Traspaso Qx' %}selected{% endif %}>Traspasos a Quirófano</option>
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Buscar Medicamento</label>
                        <input type="text" name="search_item" value="{{ search_item }}" placeholder="Ej. Paracetamol" class="w-full p-2 border rounded-xl text-xs bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <div class="flex items-end gap-2">
                        <button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-3 rounded-xl text-xs transition flex items-center justify-center gap-1">
                            <i class="fa-solid fa-filter"></i> Filtrar
                        </button>
                        <a href="/bitacora" class="bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold py-2 px-3 rounded-xl text-xs transition flex items-center justify-center">
                            <i class="fa-solid fa-rotate-left"></i>
                        </a>
                    </div>
                </form>

                <!-- TABLA DE HISTÓRICO -->
                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-600">
                        <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                            <tr>
                                <th class="p-3">Fecha y Hora</th>
                                <th class="p-3">Tipo</th>
                                <th class="p-3">Medicamento / Insumo</th>
                                <th class="p-3 text-center">Cant.</th>
                                <th class="p-3">Servicio / Almacén</th>
                                <th class="p-3">Paciente / Expediente</th>
                                <th class="p-3">Responsable</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for mov in movements %}
                            <tr class="hover:bg-slate-50">
                                <td class="p-3 text-slate-500 font-mono">{{ mov.timestamp.strftime('%d/%m/%Y %H:%M') if mov.timestamp else 'N/A' }}</td>
                                <td class="p-3 font-bold">
                                    <span class="px-2.5 py-1 rounded-full text-[10px] uppercase font-bold {% if mov.type == 'Entrada' %}bg-emerald-100 text-emerald-800{% elif mov.type == 'Salida' %}bg-rose-100 text-rose-800{% else %}bg-blue-100 text-blue-800{% endif %}">
                                        {{ mov.type }}
                                    </span>
                                </td>
                                <td class="p-3 font-bold text-slate-900">{{ mov.item_name }}</td>
                                <td class="p-3 text-center font-bold text-sm text-slate-900">{{ mov.quantity }}</td>
                                <td class="p-3 text-slate-600">
                                    {{ mov.service or 'N/A' }}
                                    <span class="block text-[10px] text-slate-400 font-normal">Orig: {{ mov.warehouse }}</span>
                                </td>
                                <td class="p-3 font-medium text-slate-900">
                                    {% if mov.patient_name %}
                                        {{ mov.patient_name }} <span class="text-slate-400 text-[10px]">({{ mov.patient_id or 'S/E' }})</span>
                                    {% else %}
                                        <span class="text-slate-400">-</span>
                                    {% endif %}
                                </td>
                                <td class="p-3 text-indigo-900 font-bold">{{ mov.user_name }}</td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="7" class="p-8 text-center text-slate-400 italic">
                                    No se encontraron registros de movimientos con los filtros seleccionados.
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

        </div>

        {% elif view == 'usuarios' %}
        <!-- PESTAÑA 4: GESTIÓN DE USUARIOS (PROTEGIDA) -->
        {% if not is_admin %}
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 max-w-md mx-auto text-center">
            <div class="w-16 h-16 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center text-2xl mx-auto mb-4">
                <i class="fa-solid fa-lock"></i>
            </div>
            <h2 class="text-lg font-bold text-slate-900">Acceso Restringido a Administrador</h2>
            <p class="text-xs text-slate-500 mt-1 mb-6">Ingrese la contraseña del Administrador para acceder a la gestión de usuarios y contraseñas.</p>

            <form action="/auth_admin" method="POST" class="space-y-4">
                <input type="password" name="admin_pin" required placeholder="Contraseña de Administrador" class="w-full p-3 border rounded-xl text-center text-lg tracking-widest focus:ring-2 focus:ring-blue-500 outline-none">
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition">
                    Desbloquear Pestaña
                </button>
            </form>
        </div>
        {% else %}
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-user-plus text-blue-600"></i> Registrar o Modificar Usuario
                </h2>

                <form action="/save_user" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre Completo</label>
                        <input type="text" name="name" required placeholder="Ej. Dr. Juan Pérez" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Rol / Cargo</label>
                        <select name="role" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                            <option value="Enfermería Quirófano">Enfermería Quirófano</option>
                            <option value="Enfermería Urgencias">Enfermería Urgencias</option>
                            <option value="Médico Anestesiólogo">Médico Anestesiólogo</option>
                            <option value="Farmacéutico">Farmacéutico</option>
                            <option value="Administrador">Administrador</option>
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Asignar PIN / Contraseña</label>
                        <input type="password" name="pin" required placeholder="PIN numérico" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2">
                        <i class="fa-solid fa-user-check"></i> Guardar Usuario y PIN
                    </button>
                </form>
            </div>

            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-users text-blue-600"></i> Personal Registrado
                </h2>
                
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {% for u in users %}
                    <div class="p-4 rounded-xl border border-slate-100 bg-slate-50 flex items-center justify-between">
                        <div>
                            <h4 class="font-bold text-slate-900 text-sm">{{ u.name }}</h4>
                            <p class="text-xs text-slate-500">{{ u.role }}</p>
                        </div>
                        <span class="text-xs font-mono bg-white px-3 py-1 rounded-lg border text-slate-600 font-semibold">PIN: {{ u.pin }}</span>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        {% endif %}

        {% elif view == 'etiquetas' %}
        <!-- PESTAÑA 5: ETIQUETAS DU -->
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 text-center">
            <h2 class="text-xl font-bold text-slate-900 mb-2 flex items-center justify-center gap-2">
                <i class="fa-solid fa-tags text-blue-600"></i> Módulo de Impresión de Etiquetas DU
            </h2>
            <p class="text-xs text-slate-500 max-w-md mx-auto mb-6">Módulo listo para vincular la plantilla de impresión de medicamentos en formato Dosis Unitaria.</p>
            <div class="p-8 bg-blue-50 rounded-2xl border-2 border-dashed border-blue-200 inline-block">
                <i class="fa-solid fa-print text-4xl text-blue-500 mb-2"></i>
                <p class="text-sm font-bold text-slate-700">Impresión Estándar Configurada</p>
            </div>
        </div>
        {% endif %}

    </main>

    <script>
        function selectUser(id) {
            var elem = document.getElementById('userSelect');
            if(elem) elem.value = id;
        }

        function filterInventory() {
            var input = document.getElementById("inventorySearch");
            var filter = input.value.toLowerCase();
            var rows = document.getElementsByClassName("inventory-row");

            for (var i = 0; i < rows.length; i++) {
                var text = rows[i].innerText.toLowerCase();
                if (text.includes(filter)) {
                    rows[i].style.display = "";
                } else {
                    rows[i].style.display = "none";
                }
            }
        }

        function openEditModal(id, code, name, category, via, presentacion, lote, caducidad, unit, general, quirofano) {
            document.getElementById('edit_item_id').value = id;
            document.getElementById('edit_code').value = code;
            document.getElementById('edit_name').value = name;
            document.getElementById('edit_category').value = category;
            document.getElementById('edit_via').value = via;
            document.getElementById('edit_presentacion').value = presentacion;
            document.getElementById('edit_lote').value = lote;
            document.getElementById('edit_caducidad').value = caducidad;
            document.getElementById('edit_unit').value = unit;
            document.getElementById('edit_stock_general').value = general;
            document.getElementById('edit_stock_quirofano').value = quirofano;
            document.getElementById('editModal').classList.remove('hidden');
        }

        function closeEditModal() {
            document.getElementById('editModal').classList.add('hidden');
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
    return render_template_string(HTML_TEMPLATE, view="terminal", items=items, users=users)

@app.route("/inventario")
def inventario():
    items = Item.query.order_by(Item.name).all()
    return render_template_string(HTML_TEMPLATE, view="inventario", items=items)

@app.route("/bitacora")
def bitacora():
    filter_date = request.args.get("filter_date", "").strip()
    filter_type = request.args.get("filter_type", "").strip()
    search_item = request.args.get("search_item", "").strip()

    query = Movement.query

    if filter_date:
        try:
            target_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
            query = query.filter(db.func.date(Movement.timestamp) == target_date)
        except ValueError:
            pass

    if filter_type:
        query = query.filter(Movement.type == filter_type)

    if search_item:
        query = query.filter(Movement.item_name.ilike(f"%{search_item}%"))

    movements = query.order_by(Movement.timestamp.desc()).all()

    total_salidas = sum(m.quantity for m in movements if m.type == "Salida")
    total_entradas = sum(m.quantity for m in movements if m.type == "Entrada")
    total_traspasos = sum(m.quantity for m in movements if m.type == "Traspaso Qx")

    return render_template_string(
        HTML_TEMPLATE, 
        view="bitacora", 
        movements=movements,
        selected_date=filter_date,
        selected_type=filter_type,
        search_item=search_item,
        total_salidas=total_salidas,
        total_entradas=total_entradas,
        total_traspasos=total_traspasos
    )

@app.route("/usuarios")
def usuarios():
    users = User.query.order_by(User.name).all()
    is_admin = request.args.get("admin") == "true"
    return render_template_string(HTML_TEMPLATE, view="usuarios", users=users, is_admin=is_admin)

@app.route("/auth_admin", methods=["POST"])
def auth_admin():
    admin_pin = request.form.get("admin_pin")
    admin_user = User.query.filter_by(role="Administrador").first()
    
    if admin_pin == "5678" or (admin_user and admin_user.pin == admin_pin):
        flash("Acceso concedido a la gestión de usuarios.", "success")
        return redirect(url_for("usuarios", admin="true"))
    else:
        flash("Contraseña de Administrador incorrecta.", "error")
        return redirect(url_for("usuarios"))

@app.route("/add_item", methods=["POST"])
def add_item():
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    category = request.form.get("category")
    via_administracion = request.form.get("via_administracion")
    presentacion = request.form.get("presentacion")
    lote = request.form.get("lote", "").strip()
    caducidad = request.form.get("caducidad", "").strip()
    unit = request.form.get("unit", "pza").strip()
    stock_general = int(request.form.get("stock_general", 0))

    if Item.query.filter_by(code=code).first():
        flash("El código o clave ya existe en el inventario.", "error")
        return redirect(url_for("terminal"))

    new_item = Item(
        code=code, 
        name=name, 
        category=category, 
        via_administracion=via_administracion,
        presentacion=presentacion,
        lote=lote,
        caducidad=caducidad,
        unit=unit, 
        stock_general=stock_general, 
        stock_quirofano=0
    )
    db.session.add(new_item)
    db.session.commit()

    flash(f"Medicamento '{name}' registrado exitosamente con código {code}.", "success")
    return redirect(url_for("terminal"))

@app.route("/update_item", methods=["POST"])
def update_item():
    admin_pin = request.form.get("admin_pin")
    admin_user = User.query.filter_by(role="Administrador").first()

    if admin_pin != "5678" and (not admin_user or admin_user.pin != admin_pin):
        flash("❌ Acceso denegado: PIN de Administrador incorrecto.", "error")
        return redirect(url_for("inventario"))

    item_id = request.form.get("item_id")
    item = Item.query.get(item_id)
    if not item:
        flash("Insumo no encontrado.", "error")
        return redirect(url_for("inventario"))

    item.code = request.form.get("code", "").strip().upper()
    item.name = request.form.get("name", "").strip()
    item.category = request.form.get("category")
    item.via_administracion = request.form.get("via_administracion")
    item.presentacion = request.form.get("presentacion")
    item.lote = request.form.get("lote", "").strip()
    item.caducidad = request.form.get("caducidad", "").strip()
    item.unit = request.form.get("unit", "pza").strip()
    item.stock_general = int(request.form.get("stock_general", 0))
    item.stock_quirofano = int(request.form.get("stock_quirofano", 0))

    db.session.commit()
    flash(f"✅ Insumo '{item.name}' actualizado correctamente por el Administrador.", "success")
    return redirect(url_for("inventario"))

@app.route("/save_user", methods=["POST"])
def save_user():
    name = request.form.get("name", "").strip()
    role = request.form.get("role")
    pin = request.form.get("pin", "").strip()

    if not name or not pin:
        flash("Complete todos los campos requeridos.", "error")
        return redirect(url_for("usuarios", admin="true"))

    user = User.query.filter_by(name=name).first()
    if user:
        user.role = role
        user.pin = pin
        flash(f"PIN/Contraseña actualizada para {name}.", "success")
    else:
        new_user = User(name=name, role=role, pin=pin)
        db.session.add(new_user)
        flash(f"Usuario {name} registrado con éxito.", "success")
    
    db.session.commit()
    return redirect(url_for("usuarios", admin="true"))

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
    patient_name = request.form.get("patient_name")
    patient_id = request.form.get("patient_id")
    notes = request.form.get("notes")

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN o contraseña de usuario incorrecta.", "error")
        return redirect(url_for("terminal"))

    item_code = item_search.split(" - ")[0] if " - " in item_search else item_search
    item = Item.query.filter((Item.code == item_code) | (Item.name.ilike(f"%{item_search}%"))).first()

    if not item:
        flash("Insumo no encontrado. Seleccione una opción válida del buscador.", "error")
        return redirect(url_for("terminal"))

    if mov_type == "Entrada":
        if warehouse == "Almacén General":
            item.stock_general += quantity
        else:
            item.stock_quirofano += quantity

    elif mov_type == "Salida":
        if warehouse == "Almacén General":
            if item.stock_general < quantity:
                flash(f"Stock insuficiente en Almacén General ({item.stock_general} disponibles).", "error")
                return redirect(url_for("terminal"))
            item.stock_general -= quantity
        else:
            if item.stock_quirofano < quantity:
                flash(f"Stock insuficiente en Quirófano ({item.stock_quirofano} disponibles).", "error")
                return redirect(url_for("terminal"))
            item.stock_quirofano -= quantity

    elif mov_type == "Traspaso Qx":
        if item.stock_general < quantity:
            flash("Stock insuficiente en Almacén General para el traspaso.", "error")
            return redirect(url_for("terminal"))
        item.stock_general -= quantity
        item.stock_quirofano += quantity

    mov = Movement(
        item_code=item.code,
        item_name=item.name,
        type=mov_type,
        quantity=quantity,
        warehouse=warehouse,
        service=service,
        patient_name=patient_name,
        patient_id=patient_id,
        user_name=user.name,
        notes=notes
    )
    db.session.add(mov)
    db.session.commit()

    flash("Movimiento / Surtido registrado guardado exitosamente.", "success")
    return redirect(url_for("terminal"))

# -----------------------------------------------------------------------------
# DATOS SEMILLA E INICIALIZACIÓN DE MIGRACIONES AUTOMÁTICAS
# -----------------------------------------------------------------------------

def seed_database():
    with app.app_context():
        db.create_all()

        try:
            db.session.execute(text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS patient_name VARCHAR(150);"))
            db.session.execute(text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS patient_id VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS via_administracion VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS presentacion VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS lote VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS caducidad VARCHAR(20);"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        if User.query.count() == 0:
            users_list = [
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678"),
                User(name="Dra. Sofia Ramos", role="Farmacéutico", pin="4321"),
                User(name="Hannia Martinez Salas", role="Enfermería Quirófano", pin="1234"),
                User(name="Carlos Rivera López", role="Enfermería Urgencias", pin="1111"),
                User(name="Dra. María Elena Castro", role="Médico Anestesiólogo", pin="2222")
            ]
            db.session.add_all(users_list)

        if Item.query.count() == 0:
            items_list = [
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", via_administracion="Oral", presentacion="Tableta", lote="LOT-9821", caducidad="2027-12-31", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-4410", caducidad="2027-08-15", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-1102", caducidad="2026-11-20", stock_general=30, stock_quirofano=10),
                Item(code="MAT-001", name="Jeringa 10ml c/Aguja", category="Material Curación", via_administracion="N/A", presentacion="Otro", lote="LOT-0012", caducidad="2028-05-01", stock_general=300, stock_quirofano=50),
                Item(code="MAT-002", name="Equipo Venoclisis Normogotero", category="Material Curación", via_administracion="N/A", presentacion="Otro", lote="LOT-0099", caducidad="2028-01-10", stock_general=100, stock_quirofano=25)
            ]
            db.session.add_all(items_list)

        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
