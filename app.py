import os
from datetime import datetime, date, timedelta, timezone
import json
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "farmacia_secret_key_123")

# Configuración de Zona Horaria Local (UTC-6 para México / Hora Local)
LOCAL_TZ = timezone(timedelta(hours=-6))

def get_local_now():
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)

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

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=False)
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
    timestamp = db.Column(db.DateTime, default=get_local_now)
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
    timestamp = db.Column(db.DateTime, default=get_local_now)
    item_name = db.Column(db.String(150), nullable=False)
    patient_name = db.Column(db.String(150), nullable=False)
    prescription_num = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    doctor_name = db.Column(db.String(150), nullable=True)
    user_name = db.Column(db.String(100), nullable=False)

class CleaningLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=get_local_now)
    user_name = db.Column(db.String(100), nullable=False)
    anaqueles = db.Column(db.Boolean, default=False)
    cajones_unidosis = db.Column(db.Boolean, default=False)
    acomodo_bodega = db.Column(db.Boolean, default=False)
    carton = db.Column(db.Boolean, default=False)
    cajas_traslado = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(250), nullable=True)

# -----------------------------------------------------------------------------
# PLANTILLA HTML INTEGRADA
# -----------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farmacia Hospitalaria - Control de Inventario</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        @media print {
            header, nav, .no-print, button, form { display: none !important; }
            body { background-color: white !important; }
            .print-container { width: 100% !important; margin: 0 !important; padding: 0 !important; }
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
                    <p class="text-[11px] text-blue-200">Terminal Compartida & Surtido Multicarga</p>
                </div>
            </div>
            <nav class="flex flex-wrap gap-1 text-xs font-bold">
                <a href="/terminal" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'terminal' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-prescription-bottle-medical"></i> Surtido Múltiple
                </a>
                <a href="/alta_insumos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'alta_insumos' %}bg-emerald-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-emerald-100{% endif %}">
                    <i class="fa-solid fa-plus-circle"></i> Alta Insumos
                </a>
                <a href="/inventario" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'inventario' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-boxes-stacked"></i> Inventario
                </a>
                <a href="/controlados" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'controlados' %}bg-rose-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-rose-100{% endif %}">
                    <i class="fa-solid fa-capsules"></i> Controlados
                </a>
                <a href="/limpieza" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'limpieza' %}bg-teal-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-teal-100{% endif %}">
                    <i class="fa-solid fa-broom"></i> Limpieza
                </a>
                <a href="/bitacora" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'bitacora' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-clock-rotate-left"></i> Bitácora
                </a>
                <a href="/usuarios" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'usuarios' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-lock"></i> Usuarios
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

        <datalist id="patients_datalist">
            {% for p in patients %}
                <option value="{{ p.name }}">
            {% endfor %}
        </datalist>

        {% if view == 'terminal' %}
        <div class="space-y-6 max-w-5xl mx-auto">
            <!-- Selección de Personal -->
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-users text-blue-600"></i> Personal Responsable
                    </h2>
                    <p class="text-xs text-slate-500">Seleccione su usuario antes de procesar la solicitud.</p>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                    {% for u in users %}
                    <button type="button" onclick="selectUser('{{ u.id }}')" class="p-3 rounded-xl border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-400 transition text-center group flex flex-col items-center">
                        <div class="w-9 h-9 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm mb-1.5 group-hover:scale-110 transition">
                            <i class="fa-solid {% if 'Admin' in u.role or 'Farmacia' in u.role %}fa-user-shield{% elif 'Enfermer' in u.role %}fa-user-nurse{% else %}fa-user-doctor{% endif %}"></i>
                        </div>
                        <h4 class="font-bold text-slate-800 text-xs group-hover:text-blue-600 truncate w-full">{{ u.name }}</h4>
                        <span class="text-[10px] text-slate-500">{{ u.role }}</span>
                    </button>
                    {% endfor %}
                </div>
            </div>

            <!-- Formulario Principal de Surtido Múltiple -->
            <form action="/register_batch" method="POST" onsubmit="return validateBatchForm()" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-6">
                <input type="hidden" name="cart_data" id="cart_data_input">

                <div class="border-b pb-4 flex justify-between items-center">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-receipt text-blue-600"></i> Dispensación de Receta / Surtido a Paciente
                    </h2>
                    <span class="text-xs font-bold bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                        Múltiples Ítems Habilitado
                    </span>
                </div>

                <!-- Credenciales del Usuario -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Usuario Responsable</label>
                        <select name="user_id" id="userSelect" required class="w-full p-2.5 border rounded-xl text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                            <option value="">Seleccione Usuario...</option>
                            {% for u in users %}
                                <option value="{{ u.id }}">{{ u.name }} ({{ u.role }})</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">PIN / Contraseña</label>
                        <input type="password" name="pin" required placeholder="PIN de Seguridad" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>
                </div>

                <!-- Datos Paciente y Destino -->
                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                    <h3 class="text-xs font-bold text-blue-900 uppercase flex items-center gap-1.5">
                        <i class="fa-solid fa-bed-pulse"></i> Información del Paciente y Servicio
                    </h3>
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Nombre Completo del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" id="patient_name" placeholder="Ej. Juan Pérez" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-medium">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">No. Expediente / Cama</label>
                            <input type="text" name="patient_id" placeholder="Ej. EXP-9823 / Cama 4" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Servicio / Área</label>
                            <input type="text" name="service" placeholder="Ej. Urgencias / Hospitalización" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        </div>
                    </div>
                </div>

                <!-- Selector para Agregar Medicamentos al Carrito -->
                <div class="p-4 bg-indigo-50/40 rounded-xl border border-indigo-100 space-y-3">
                    <h3 class="text-xs font-bold text-indigo-900 uppercase flex items-center gap-1.5">
                        <i class="fa-solid fa-plus-circle"></i> Agregar Medicamentos a la Lista
                    </h3>
                    
                    <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                        <div class="md:col-span-5">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Buscar Medicamento / Lote</label>
                            <input list="items_list" id="temp_item" placeholder="Escriba o escanee código de barras..." class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-medium">
                            <datalist id="items_list">
                                {% for item in items %}
                                    <option value="[ID:{{ item.id }}] {{ item.code }} - {{ item.name }} (Lote: {{ item.lote or 'S/L' }})" data-name="{{ item.name }}" data-code="{{ item.code }}" data-lote="{{ item.lote or 'S/L' }}" data-stock-gen="{{ item.stock_general }}" data-stock-qx="{{ item.stock_quirofano }}">Gen: {{ item.stock_general }} | Qx: {{ item.stock_quirofano }} | {{ item.etiqueta }}</option>
                                {% endfor %}
                            </datalist>
                        </div>
                        <div class="md:col-span-2">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Tipo</label>
                            <select id="temp_type" class="w-full p-2 border rounded-lg text-xs bg-white outline-none">
                                <option value="Salida">Salida a Paciente</option>
                                <option value="Traspaso Qx">Traspaso a Quirófano</option>
                                <option value="Entrada">Entrada (Stock)</option>
                            </select>
                        </div>
                        <div class="md:col-span-2">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Origen</label>
                            <select id="temp_warehouse" class="w-full p-2 border rounded-lg text-xs bg-white outline-none">
                                <option value="Almacén General">Almacén General</option>
                                <option value="Quirófano">Quirófano</option>
                            </select>
                        </div>
                        <div class="md:col-span-1">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Cant.</label>
                            <input type="number" min="1" id="temp_quantity" value="1" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none text-center font-bold">
                        </div>
                        <div class="md:col-span-2">
                            <button type="button" onclick="addToCart()" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-3 rounded-lg text-xs transition flex items-center justify-center gap-1 shadow-sm">
                                <i class="fa-solid fa-cart-plus"></i> Agregar
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Tabla de Medicamentos a Dispensar -->
                <div>
                    <h3 class="text-xs font-bold text-slate-700 uppercase mb-2 flex items-center justify-between">
                        <span><i class="fa-solid fa-list-check text-blue-600"></i> Lista de Medicamentos a Dispensar</span>
                        <span id="cartCountBadge" class="text-[11px] font-semibold bg-slate-200 text-slate-700 px-2 py-0.5 rounded-full">0 ítems</span>
                    </h3>

                    <div class="overflow-x-auto border rounded-xl">
                        <table class="w-full text-xs text-left text-slate-600" id="cartTable">
                            <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                <tr>
                                    <th class="p-2.5">Medicamento / Lote</th>
                                    <th class="p-2.5">Tipo</th>
                                    <th class="p-2.5">Almacén</th>
                                    <th class="p-2.5 text-center">Cantidad</th>
                                    <th class="p-2.5 text-center">Acción</th>
                                </tr>
                            </thead>
                            <tbody id="cartTableBody" class="divide-y divide-slate-100">
                                <tr>
                                    <td colspan="5" class="p-6 text-center text-slate-400 italic" id="emptyCartRow">
                                        No se han agregado medicamentos a esta dispensación. Seleccione arriba y haga clic en "Agregar".
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Notas globales de la receta</label>
                    <input type="text" name="notes" placeholder="Observaciones generales para todo el surtido..." class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                </div>

                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2 text-sm">
                    <i class="fa-solid fa-check-double"></i> Procesar Surtido Completo
                </button>
            </form>
        </div>

        {% elif view == 'alta_insumos' %}
        <div class="space-y-6 max-w-xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-plus-circle text-emerald-600"></i> Dar de Alta Nuevo Medicamento / Lote
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
                        <i class="fa-solid fa-box-archive"></i> Registrar / Agregar Lote
                    </button>
                </form>
            </div>
        </div>

        {% elif view == 'inventario' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div class="flex flex-col md:flex-row justify-between items-center gap-4 mb-6 border-b pb-4">
                <div>
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-boxes-stacked text-blue-600"></i> Stock General e Inventario
                    </h2>
                    <p class="text-xs text-slate-500">Existencias independientes por lote. Alertas automáticas por caducidad.</p>
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
                                <span class="font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">Lote: {{ item.lote or 'S/L' }}</span>
                                <span class="block text-[10px] mt-1">
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
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        {% elif view == 'controlados' %}
        <div class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-file-prescription text-rose-600"></i> Surtir Medicamento Controlado
                    </h2>

                    <form action="/add_controlled" method="POST" class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Medicamento Controlado</label>
                            <input list="controlled_items_list" name="item_name" required placeholder="Escriba, escanee código o seleccione..." class="w-full p-2.5 border rounded-xl text-sm bg-rose-50 focus:bg-white focus:ring-2 focus:ring-rose-500 outline-none font-bold">
                            <datalist id="controlled_items_list">
                                {% for item in controlled_items %}
                                    <option value="{{ item.code }} - {{ item.name }} (Lote: {{ item.lote or 'S/L' }})">
                                {% endfor %}
                            </datalist>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" required placeholder="Seleccione o escriba el nombre..." class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-rose-500 outline-none font-medium">
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

                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 mb-4 border-b pb-3">
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

        {% elif view == 'limpieza' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-list-check text-teal-600"></i> Bitácora de Sanitización
                </h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-600">
                        <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                            <tr>
                                <th class="p-2.5">Fecha/Hora</th>
                                <th class="p-2.5">Responsable</th>
                                <th class="p-2.5 text-center">Anaqueles</th>
                                <th class="p-2.5 text-center">Cajones DU</th>
                                <th class="p-2.5 text-center">Bodega</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for log in cleaning_logs %}
                            <tr class="hover:bg-slate-50">
                                <td class="p-2.5 font-mono text-slate-500">{{ log.timestamp.strftime('%d/%m/%Y %H:%M') }}</td>
                                <td class="p-2.5 font-bold text-slate-900">{{ log.user_name }}</td>
                                <td class="p-2.5 text-center">{% if log.anaqueles %}✓{% else %}-{% endif %}</td>
                                <td class="p-2.5 text-center">{% if log.cajones_unidosis %}✓{% else %}-{% endif %}</td>
                                <td class="p-2.5 text-center">{% if log.acomodo_bodega %}✓{% else %}-{% endif %}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="5" class="p-6 text-center text-slate-400 italic">No hay actividades de limpieza registradas.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        {% elif view == 'bitacora' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4 border-b pb-3 flex justify-between items-center">
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora e Histórico de Auditoría
                    </h2>
                    <button onclick="window.print()" class="px-4 py-2 bg-slate-800 text-white font-bold rounded-xl text-xs">
                        <i class="fa-solid fa-print"></i> Imprimir Bitácora
                    </button>
                </div>

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
                                <td class="p-3 text-slate-600">{{ mov.service or 'N/A' }}</td>
                                <td class="p-3 font-medium text-slate-900">{{ mov.patient_name or '-' }}</td>
                                <td class="p-3 text-indigo-900 font-bold">{{ mov.user_name }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="7" class="p-8 text-center text-slate-400 italic">No hay movimientos.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        {% elif view == 'usuarios' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 max-w-2xl mx-auto">
            <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2">Personal Autorizado</h2>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {% for u in users %}
                <div class="p-3 rounded-xl border bg-slate-50 flex justify-between items-center">
                    <div>
                        <h4 class="font-bold text-slate-900 text-sm">{{ u.name }}</h4>
                        <p class="text-xs text-slate-500">{{ u.role }}</p>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </main>

    <script>
        let cart = [];

        function selectUser(id) {
            var elem = document.getElementById('userSelect');
            if(elem) elem.value = id;
        }

        function addToCart() {
            const itemInput = document.getElementById('temp_item');
            const itemSearchValue = itemInput.value.trim();
            const type = document.getElementById('temp_type').value;
            const warehouse = document.getElementById('temp_warehouse').value;
            const quantity = parseInt(document.getElementById('temp_quantity').value) || 1;

            if (!itemSearchValue) {
                alert('Por favor seleccione un medicamento.');
                return;
            }

            cart.push({
                item_search: itemSearchValue,
                type: type,
                warehouse: warehouse,
                quantity: quantity
            });

            itemInput.value = '';
            document.getElementById('temp_quantity').value = 1;
            renderCart();
        }

        function removeFromCart(index) {
            cart.splice(index, 1);
            renderCart();
        }

        function renderCart() {
            const tbody = document.getElementById('cartTableBody');
            const badge = document.getElementById('cartCountBadge');
            
            badge.innerText = cart.length + ' ítems';

            if (cart.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="p-6 text-center text-slate-400 italic">
                            No se han agregado medicamentos a esta dispensación. Seleccione arriba y haga clic en "Agregar".
                        </td>
                    </tr>
                `;
                return;
            }

            let html = '';
            cart.forEach((item, index) => {
                html += `
                    <tr class="hover:bg-slate-50">
                        <td class="p-2.5 font-bold text-slate-800">${item.item_search}</td>
                        <td class="p-2.5 font-medium text-xs">${item.type}</td>
                        <td class="p-2.5 text-xs text-slate-500">${item.warehouse}</td>
                        <td class="p-2.5 text-center font-bold text-sm text-slate-900">${item.quantity}</td>
                        <td class="p-2.5 text-center">
                            <button type="button" onclick="removeFromCart(${index})" class="px-2 py-1 bg-rose-100 hover:bg-rose-200 text-rose-700 font-bold rounded text-xs transition">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });

            tbody.innerHTML = html;
        }

        function validateBatchForm() {
            if (cart.length === 0) {
                alert('Debe agregar al menos un medicamento a la lista para dispensar.');
                return false;
            }
            document.getElementById('cart_data_input').value = JSON.stringify(cart);
            return true;
        }

        function filterInventory() {
            var input = document.getElementById("inventorySearch");
            var filter = input.value.toLowerCase();
            var rows = document.getElementsByClassName("inventory-row");
            for (var i = 0; i < rows.length; i++) {
                var text = rows[i].innerText.toLowerCase();
                rows[i].style.display = text.includes(filter) ? "" : "none";
            }
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
    items = Item.query.order_by(Item.name, Item.lote).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="terminal", items=items, users=users, patients=patients)

@app.route("/register_batch", methods=["POST"])
def register_batch():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    patient_name = request.form.get("patient_name", "").strip()
    patient_id = request.form.get("patient_id", "").strip()
    service = request.form.get("service", "").strip()
    notes = request.form.get("notes", "").strip()
    cart_json = request.form.get("cart_data", "[]")

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN o contraseña de usuario incorrecta.", "error")
        return redirect(url_for("terminal"))

    try:
        cart_items = json.loads(cart_json)
    except Exception:
        flash("Error al procesar la lista de medicamentos.", "error")
        return redirect(url_for("terminal"))

    if not cart_items or len(cart_items) == 0:
        flash("Debe agregar al menos un medicamento a la receta.", "error")
        return redirect(url_for("terminal"))

    if patient_name:
        existing_patient = Patient.query.filter_by(name=patient_name).first()
        if not existing_patient:
            new_p = Patient(name=patient_name)
            db.session.add(new_p)

    processed_count = 0

    for cart_item in cart_items:
        item_search = cart_item.get("item_search", "").strip()
        mov_type = cart_item.get("type")
        warehouse = cart_item.get("warehouse")
        quantity = int(cart_item.get("quantity", 1))

        item = None
        if item_search.startswith("[ID:") and "]" in item_search:
            try:
                item_id = int(item_search.split("[ID:")[1].split("]")[0])
                item = Item.query.get(item_id)
            except Exception:
                item = None

        if not item:
            clean_code = item_search.split(" - ")[0] if " - " in item_search else item_search
            item = Item.query.filter((Item.code == clean_code) | (Item.name.ilike(f"%{item_search}%"))).first()

        if not item:
            continue

        # Validaciones y actualización de stock
        if mov_type == "Entrada":
            if warehouse == "Almacén General":
                item.stock_general += quantity
            else:
                item.stock_quirofano += quantity

        elif mov_type == "Salida":
            if warehouse == "Almacén General":
                if item.stock_general < quantity:
                    flash(f"Stock insuficiente para '{item.name}' en Almacén General ({item.stock_general} disponibles).", "error")
                    db.session.rollback()
                    return redirect(url_for("terminal"))
                item.stock_general -= quantity
            else:
                if item.stock_quirofano < quantity:
                    flash(f"Stock insuficiente para '{item.name}' en Quirófano ({item.stock_quirofano} disponibles).", "error")
                    db.session.rollback()
                    return redirect(url_for("terminal"))
                item.stock_quirofano -= quantity

        elif mov_type == "Traspaso Qx":
            if item.stock_general < quantity:
                flash(f"Stock insuficiente para traspaso de '{item.name}'.", "error")
                db.session.rollback()
                return redirect(url_for("terminal"))
            item.stock_general -= quantity
            item.stock_quirofano += quantity

        mov = Movement(
            timestamp=get_local_now(),
            item_code=item.code,
            item_name=f"{item.name} (Lote: {item.lote or 'S/L'})",
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
        processed_count += 1

    db.session.commit()
    flash(f"Surtido de {processed_count} medicamento(s) registrado exitosamente para el paciente {patient_name or 'General'}.", "success")
    return redirect(url_for("terminal"))

@app.route("/alta_insumos")
def alta_insumos():
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="alta_insumos", users=users, patients=patients)

@app.route("/limpieza")
def limpieza():
    cleaning_logs = CleaningLog.query.order_by(CleaningLog.timestamp.desc()).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="limpieza", cleaning_logs=cleaning_logs, users=users, patients=patients)

@app.route("/inventario")
def inventario():
    items = Item.query.order_by(Item.name, Item.lote).all()
    patients = Patient.query.order_by(Patient.name).all()
    today_str = datetime.now(LOCAL_TZ).date().isoformat()
    warning_str = (datetime.now(LOCAL_TZ).date() + timedelta(days=30)).isoformat()
    return render_template_string(HTML_TEMPLATE, view="inventario", items=items, today_str=today_str, warning_str=warning_str, patients=patients)

@app.route("/controlados")
def controlados():
    controlled_items = Item.query.filter_by(etiqueta="Controlado").order_by(Item.name).all()
    controlled_logs = ControlledLog.query.order_by(ControlledLog.timestamp.desc()).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="controlados", controlled_items=controlled_items, controlled_logs=controlled_logs, users=users, patients=patients)

@app.route("/add_controlled", methods=["POST"])
def add_controlled():
    item_name = request.form.get("item_name", "").strip()
    patient_name = request.form.get("patient_name", "").strip()
    prescription_num = request.form.get("prescription_num", "").strip()
    quantity = int(request.form.get("quantity", 1))
    doctor_name = request.form.get("doctor_name", "").strip()
    user_id = request.form.get("user_id")
    pin = request.form.get("pin", "").strip()

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN de seguridad incorrecto.", "error")
        return redirect(url_for("controlados"))

    if patient_name:
        existing_patient = Patient.query.filter_by(name=patient_name).first()
        if not existing_patient:
            new_p = Patient(name=patient_name)
            db.session.add(new_p)

    new_log = ControlledLog(
        timestamp=get_local_now(),
        item_name=item_name,
        patient_name=patient_name,
        prescription_num=prescription_num,
        quantity=quantity,
        doctor_name=doctor_name,
        user_name=user.name
    )
    db.session.add(new_log)
    db.session.commit()

    flash(f"Salida controlada de '{item_name}' registrada bajo la receta {prescription_num}.", "success")
    return redirect(url_for("controlados"))

@app.route("/bitacora")
def bitacora():
    movements = Movement.query.order_by(Movement.timestamp.desc()).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="bitacora", movements=movements, patients=patients)

@app.route("/usuarios")
def usuarios():
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="usuarios", users=users, patients=patients)

@app.route("/add_item", methods=["POST"])
def add_item():
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    category = request.form.get("category")
    via_administracion = request.form.get("via_administracion")
    presentacion = request.form.get("presentacion")
    lote = request.form.get("lote", "").strip()
    caducidad = request.form.get("caducidad", "").strip()
    etiqueta = request.form.get("etiqueta", "Ninguna")
    unit = request.form.get("unit", "pza").strip()
    stock_general = int(request.form.get("stock_general", 0))

    try:
        new_item = Item(
            code=code, 
            name=name, 
            category=category, 
            via_administracion=via_administracion,
            presentacion=presentacion,
            lote=lote,
            caducidad=caducidad,
            etiqueta=etiqueta,
            unit=unit, 
            stock_general=stock_general, 
            stock_quirofano=0
        )
        db.session.add(new_item)
        db.session.commit()
        flash(f"Nuevo insumo/lote '{name}' registrado exitosamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al registrar: {str(e)}", "error")

    return redirect(url_for("alta_insumos"))

# -----------------------------------------------------------------------------
# INICIALIZACIÓN DE BASE DE DATOS
# -----------------------------------------------------------------------------

def seed_database():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            users_list = [
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678"),
                User(name="Dra. Sofia Ramos", role="Farmacéutico", pin="4321"),
                User(name="Hannia Martinez Salas", role="Enfermería Quirófano", pin="1234")
            ]
            db.session.add_all(users_list)

        if Item.query.count() == 0:
            items_list = [
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", via_administracion="Oral", presentacion="Tableta", lote="LOT-9821", caducidad="2027-12-31", etiqueta="Ninguna", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-4410", caducidad="2027-08-15", etiqueta="Alto Riesgo", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-1102", caducidad="2026-11-20", etiqueta="Controlado", stock_general=30, stock_quirofano=10)
            ]
            db.session.add_all(items_list)

        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
