import os
from datetime import datetime, date, timedelta
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
    code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    via_administracion = db.Column(db.String(50), nullable=True)
    presentacion = db.Column(db.String(50), nullable=True)
    lote = db.Column(db.String(50), nullable=True)
    caducidad = db.Column(db.String(20), nullable=True)
    etiqueta = db.Column(db.String(50), default="Ninguna")
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

class ControlledLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    item_name = db.Column(db.String(150), nullable=False)
    patient_name = db.Column(db.String(150), nullable=False)
    prescription_num = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    doctor_name = db.Column(db.String(150), nullable=True)
    user_name = db.Column(db.String(100), nullable=False)

# -----------------------------------------------------------------------------
# PLANTILLA HTML DIVIDIDA
# -----------------------------------------------------------------------------

HTML_HEADER = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farmacia Hospitalaria - Control de Inventario</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        @media print {
            header, nav, .no-print, button, form {
                display: none !important;
            }
            body {
                background-color: white !important;
            }
            .print-container {
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
            }
        }
    </style>
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 font-sans">
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
            <nav class="flex flex-wrap gap-1.5 text-xs font-bold">
                <a href="/terminal" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'terminal' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-pen-to-square"></i> Captura y Surtido
                </a>
                <a href="/inventario" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'inventario' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-boxes-stacked"></i> Inventario
                </a>
                <a href="/controlados" class="px-3.5 py-2 rounded-xl transition flex items-center gap-2 {% if view == 'controlados' %}bg-rose-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-rose-100{% endif %}">
                    <i class="fa-solid fa-capsules"></i> Controlados
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
    <main class="max-w-7xl mx-auto p-4 md:p-6 print-container">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="p-4 mb-4 text-sm rounded-xl shadow-sm flex items-center gap-3 no-print {% if category == 'error' %}bg-rose-100 text-rose-800 border border-rose-300{% else %}bg-emerald-100 text-emerald-800 border border-emerald-300{% endif %}">
                <i class="fa-solid {% if category == 'error' %}fa-circle-xmark{% else %}fa-circle-check{% endif %} text-lg"></i>
                <span class="font-medium">{{ message }}</span>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}
"""

HTML_VIEW_TERMINAL = """
        {% if view == 'terminal' %}
        <div class="space-y-6">
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

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Insumo / Medicamento (Buscador)</label>
                            <input list="items_list" name="item_search" required placeholder="Escriba código de barras, clave o nombre..." class="w-full p-2.5 border rounded-xl text-sm bg-blue-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none font-medium">
                            <datalist id="items_list">
                                {% for item in items %}
                                    <option value="{{ item.code }} - {{ item.name }} (Lote: {{ item.lote or 'S/L' }})">Gen: {{ item.stock_general }} | Qx: {{ item.stock_quirofano }} | {{ item.etiqueta }}</option>
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
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Etiqueta Especial</label>
                            <select name="etiqueta" class="w-full p-2.5 border rounded-xl text-sm bg-amber-50 focus:bg-white focus:ring-2 focus:ring-emerald-500 outline-none font-bold">
                                <option value="Ninguna">Ninguna</option>
                                <option value="Alto Riesgo">🔴 Alto Riesgo</option>
                                <option value="Controlado">🟣 Medicamento Controlado</option>
                                <option value="Antibiótico">🟡 Antibiótico</option>
                                <option value="Refrigeración">🔵 Refrigeración</option>
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
                            <i class="fa-solid fa-box-archive"></i> Registrar / Agrupar Medicamento
                        </button>
                    </form>
                </div>
            </div>
        </div>
"""

HTML_VIEW_INVENTARIO = """
        {% elif view == 'inventario' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div class="flex flex-col md:flex-row justify-between items-center gap-4 mb-6 border-b pb-4">
                <div>
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-boxes-stacked text-blue-600"></i> Stock General e Inventario
                    </h2>
                    <p class="text-xs text-slate-500">Existencias por lote. Alertas automáticas por próximas caducidades y etiquetas de seguridad.</p>
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
                            <th class="p-3">Etiqueta Especial</th>
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
                            <td class="p-3">
                                {% if item.etiqueta == 'Alto Riesgo' %}
                                    <span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300">🔴 Alto Riesgo</span>
                                {% elif item.etiqueta == 'Controlado' %}
                                    <span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-300">🟣 Controlado</span>
                                {% elif item.etiqueta == 'Antibiótico' %}
                                    <span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">🟡 Antibiótico</span>
                                {% elif item.etiqueta == 'Refrigeración' %}
                                    <span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-sky-100 text-sky-800 border border-sky-300">🔵 Refrigeración</span>
                                {% else %}
                                    <span class="text-slate-400 text-xs">-</span>
                                {% endif %}
                            </td>
                            <td class="p-3 text-xs text-slate-600">
                                <span class="font-medium text-slate-800">Lote: {{ item.lote or 'S/L' }}</span>
                                <span class="block text-[10px] mt-0.5">
                                    {% if item.caducidad and item.caducidad.strip() != '' %}
                                        {% set cad_date = item.caducidad %}
                                        {% if cad_date < today_str %}
                                            <span class="px-2 py-0.5 bg-rose-200 text-rose-900 font-bold rounded flex items-center gap-1 w-fit"><i class="fa-solid fa-triangle-exclamation"></i> VENCIDO ({{ cad_date }})</span>
                                        {% elif cad_date <= warning_str %}
                                            <span class="px-2 py-0.5 bg-amber-200 text-amber-900 font-bold rounded flex items-center gap-1 w-fit"><i class="fa-solid fa-clock"></i> Próximo a vencer ({{ cad_date }})</span>
                                        {% else %}
                                            <span class="text-slate-500 font-mono">Cad: {{ cad_date }}</span>
                                        {% endif %}
                                    {% else %}
                                        <span class="text-slate-400">Cad: S/F</span>
                                    {% endif %}
                                </span>
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
                                <button onclick="openEditModal('{{ item.id }}', '{{ item.code }}', '{{ item.name }}', '{{ item.category }}', '{{ item.via_administracion or '' }}', '{{ item.presentacion or '' }}', '{{ item.lote or '' }}', '{{ item.caducidad or '' }}', '{{ item.unit }}', '{{ item.stock_general }}', '{{ item.stock_quirofano }}', '{{ item.etiqueta or 'Ninguna' }}')" class="px-3 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-xs font-bold transition shadow-sm flex items-center gap-1 mx-auto">
                                    <i class="fa-solid fa-lock"></i> Editar
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

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
                        <input type="password" name="admin_pin" required placeholder="Ingrese PIN de Administrador" class="w-full p-2 border rounded-lg text-xs bg-white font-bold outline-none focus:ring-2 focus:ring-amber-500">
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

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Etiqueta Especial</label>
                        <select name="etiqueta" id="edit_etiqueta" class="w-full p-2 border rounded-xl text-xs font-bold bg-amber-50">
                            <option value="Ninguna">Ninguna</option>
                            <option value="Alto Riesgo">🔴 Alto Riesgo</option>
                            <option value="Controlado">🟣 Medicamento Controlado</option>
                            <option value="Antibiótico">🟡 Antibiótico</option>
                            <option value="Refrigeración">🔵 Refrigeración</option>
                        </select>
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
"""

HTML_VIEW_CONTROLADOS = """
        {% elif view == 'controlados' %}
        <div class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Formulario de Registro para Medicamento Controlado -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-file-prescription text-rose-600"></i> Surtir Medicamento Controlado
                    </h2>

                    <form action="/add_controlled" method="POST" class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Medicamento Controlado</label>
                            <select name="item_name" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-rose-500 outline-none font-bold">
                                <option value="">Seleccione Medicamento...</option>
                                {% for item in controlled_items %}
                                    <option value="{{ item.name }}">{{ item.name }} (Lote: {{ item.lote or 'S/L' }})</option>
                                {% else %}
                                    <option value="">No hay medicamentos marcados como 'Controlado'</option>
                                {% endfor %}
                            </select>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" name="patient_name" required placeholder="Ej. Roberto Gómez Bolaños" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-rose-500 outline-none">
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">No. Receta / Folio Controlado</label>
                            <input type="text" name="prescription_num" required placeholder="Ej. REC-2026-9901" class="w-full p-2.5 border rounded-xl text-sm font-mono focus:ring-2 focus:ring-rose-500 outline-none">
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Cantidad</label>
                                <input type="number" min="1" value="1" name="quantity" required class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-rose-500 outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Médico Prescriptor</label>
                                <input type="text" name="doctor_name" placeholder="Ej. Dr. Ramírez" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-rose-500 outline-none">
                            </div>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Usuario Responsable</label>
                                <select name="user_id" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-rose-500 outline-none">
                                    <option value="">Usuario...</option>
                                    {% for u in users %}
                                        <option value="{{ u.id }}">{{ u.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN</label>
                                <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-rose-500 outline-none">
                            </div>
                        </div>

                        <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2 mt-2">
                            <i class="fa-solid fa-file-signature"></i> Registrar Salida Controlada
                        </button>
                    </form>
                </div>

                <!-- Bitácora de Medicamentos Controlados -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                    <div class="flex justify-between items-center mb-4 border-b pb-3">
                        <div>
                            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                                <i class="fa-solid fa-book-medical text-rose-600"></i> Bitácora de Medicamentos Controlados
                            </h2>
                            <p class="text-xs text-slate-500">Histórico exclusivo para auditoría de narcóticos y psicotrópicos.</p>
                        </div>
                        <button onclick="window.print()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition flex items-center gap-1.5 no-print">
                            <i class="fa-solid fa-print"></i> Imprimir Libro
                        </button>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left text-slate-600">
                            <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                <tr>
                                    <th class="p-2.5">Fecha/Hora</th>
                                    <th class="p-2.5">Medicamento</th>
                                    <th class="p-2.5">Paciente</th>
                                    <th class="p-2.5">No. Receta</th>
                                    <th class="p-2.5 text-center">Cant.</th>
                                    <th class="p-2.5">Médico / Responsable</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for log in controlled_logs %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2.5 font-mono text-slate-500">{{ log.timestamp.strftime('%d/%m/%Y %H:%M') }}</td>
                                    <td class="p-2.5 font-bold text-slate-900">{{ log.item_name }}</td>
                                    <td class="p-2.5 font-medium text-slate-800">{{ log.patient_name }}</td>
                                    <td class="p-2.5 font-mono text-rose-700 font-bold bg-rose-50 rounded px-1.5 py-0.5">{{ log.prescription_num }}</td>
                                    <td class="p-2.5 text-center font-bold text-slate-900">{{ log.quantity }}</td>
                                    <td class="p-2.5">
                                        <span class="block text-slate-800 font-medium">{{ log.doctor_name or 'N/E' }}</span>
                                        <span class="block text-[10px] text-slate-400">Entregó: {{ log.user_name }}</span>
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="6" class="p-6 text-center text-slate-400 italic">No hay registros en la bitácora de medicamentos controlados.</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
"""

HTML_VIEW_BITACORA = """
        {% elif view == 'bitacora' %}
        <div class="space-y-6">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 no-print">
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

            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4 border-b pb-3 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora e Histórico de Auditoría
                        </h2>
                        <p class="text-xs text-slate-500">Consulte los movimientos registrados filtrando por fecha o tipo de operación.</p>
                    </div>
                    <button onclick="window.print()" class="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white font-bold rounded-xl text-xs transition flex items-center gap-2 no-print shadow-sm">
                        <i class="fa-solid fa-print text-sm"></i> Imprimir Bitácora
                    </button>
                </div>

                <form action="/bitacora" method="GET" class="grid grid-cols-1 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-6 bg-slate-50 p-4 rounded-xl border border-slate-200 no-print">
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
"""

HTML_VIEW_USUARIOS = """
        {% elif view == 'usuarios' %}
        {% if not is_admin %}
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 max-w-md mx-auto text-center">
            <div class="w-16 h-16 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center text-2xl mx-auto mb-4">
                <i class="fa-solid fa-lock"></i>
            </div>
            <h2 class="text-lg font-bold text-slate-900">Acceso Restringido a Administrador</h2>
            <p class="text-xs text-slate-500 mt-1 mb-6">Ingrese la contraseña del Administrador para acceder a la gestión de usuarios y contraseñas.</p>

            <form action="/auth_admin" method="POST" class="space-y-4">
                <input type="password" name="admin_pin" required placeholder="Contraseña de Administrador" class="w-full p-3 border rounded-xl text-center text-lg tracking-widest focus:ring-2 focus:ring-blue-500 outline-none">
                <button type="submit" class="w-full bg-blue-600 hover:bg
