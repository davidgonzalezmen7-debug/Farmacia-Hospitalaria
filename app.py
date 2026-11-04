import os
from datetime import datetime, date, timedelta, timezone
import json
import io
from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy

# Dependencias para generación de PDF y Reportes
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

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
    code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    via_administracion = db.Column(db.String(50), nullable=True)
    presentacion = db.Column(db.String(50), nullable=True)
    lote = db.Column(db.String(50), nullable=True)
    caducidad = db.Column(db.String(20), nullable=True) # Formato YYYY-MM-DD
    etiqueta = db.Column(db.String(50), default="Ninguna")
    stock_general = db.Column(db.Integer, default=0)
    stock_quirofano = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default="pza")

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=get_local_now)
    item_code = db.Column(db.String(50), nullable=True)
    item_name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    warehouse = db.Column(db.String(50), nullable=False)
    service = db.Column(db.String(100), nullable=True)
    patient_name = db.Column(db.String(150), nullable=True)
    patient_id = db.Column(db.String(50), nullable=True)
    room = db.Column(db.String(50), nullable=True)
    shift = db.Column(db.String(50), nullable=True) # Matutino, Vespertino, Nocturno A, Nocturno B
    is_cost_cargo = db.Column(db.Boolean, default=False)
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
    dia_semana = db.Column(db.String(20), nullable=True) # Lunes, Martes, etc.
    turno = db.Column(db.String(20), nullable=True) # Matutino, Vespertino, Nocturno
    anaqueles = db.Column(db.Boolean, default=False)
    pasillos = db.Column(db.Boolean, default=False)
    desecho_carton = db.Column(db.Boolean, default=False)
    refrigerador = db.Column(db.Boolean, default=False)
    cajas_traslado = db.Column(db.Boolean, default=False)
    acomodo_medicamento = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(350), nullable=True)

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
            @page {
                size: portrait;
                margin: 10mm;
            }
            body, html {
                width: 100% !important;
                background-color: white !important;
            }
            header, nav, .no-print, button, form { 
                display: none !important; 
            }
            .print-container {
                display: block !important;
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
            }
        }
    </style>
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 font-sans">
    <header class="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 text-white shadow-lg sticky top-0 z-40 no-print">
        <div class="max-w-7xl mx-auto px-4 py-3 flex flex-col md:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-3">
                <div class="bg-blue-600 p-2.5 rounded-xl shadow-inner">
                    <i class="fa-solid fa-hospital-user text-2xl text-white"></i>
                </div>
                <div>
                    <h1 class="text-xl font-extrabold tracking-tight">Farmacia Hospitalaria</h1>
                    <p class="text-[11px] text-blue-200">Terminal Compartida & Control Integral</p>
                </div>
            </div>
            <nav class="flex flex-wrap gap-1 text-xs font-bold">
                <a href="/terminal?view=terminal" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'terminal' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-prescription-bottle-medical"></i> Surtido Múltiple
                </a>
                <a href="/terminal?view=costos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'costos' %}bg-emerald-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-emerald-100{% endif %}">
                    <i class="fa-solid fa-file-invoice-dollar"></i> Cargo Costos
                </a>
                <a href="/terminal?view=etiquetas" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'etiquetas' %}bg-purple-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-purple-100{% endif %}">
                    <i class="fa-solid fa-tags"></i> Generar Etiquetas
                </a>
                <a href="/terminal?view=alta_insumos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'alta_insumos' %}bg-emerald-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-emerald-100{% endif %}">
                    <i class="fa-solid fa-plus-circle"></i> Alta Insumos
                </a>
                <a href="/terminal?view=inventario" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'inventario' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-boxes-stacked"></i> Inventario
                </a>
                <a href="/terminal?view=controlados" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'controlados' %}bg-rose-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-rose-100{% endif %}">
                    <i class="fa-solid fa-capsules"></i> Controlados
                </a>
                <a href="/terminal?view=limpieza" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'limpieza' %}bg-teal-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-teal-100{% endif %}">
                    <i class="fa-solid fa-broom"></i> Limpieza (Check-list)
                </a>
                <a href="/terminal?view=bitacora" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'bitacora' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-clock-rotate-left"></i> Bitácora
                </a>
                <a href="/terminal?view=usuarios" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'usuarios' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
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

        <datalist id="items_list">
            {% for item in items %}
                <option value="{{ item.name }} (Lote: {{ item.lote or 'S/L' }})">Stock Gen: {{ item.stock_general }} | Qx: {{ item.stock_quirofano }} | {{ item.etiqueta }}</option>
            {% endfor %}
        </datalist>

        {% if view == 'costos' %}
        <!-- ==================== PESTAÑA: CARGO DE MATERIAL PARA COSTOS (MÚLTIPLE CON BUSCADOR) ==================== -->
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="border-b pb-4 mb-4 flex justify-between items-center">
                    <div>
                        <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-file-invoice-dollar text-emerald-600"></i> Cargo Múltiple de Material para Costos
                        </h2>
                        <p class="text-xs text-slate-500">Agregue varios insumos a la lista de cargo para un paciente y regístrelos en un solo movimiento por turno.</p>
                    </div>
                </div>

                <form action="/add_cost_cargo_batch" method="POST" onsubmit="return validateCostosBatch()" class="space-y-4">
                    <input type="hidden" name="cart_costos_data" id="cart_costos_data_input">

                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" id="costos_patient_name" required placeholder="Ej. Ana Gómez" class="w-full p-2 border rounded-xl text-xs focus:ring-2 focus:ring-emerald-500 outline-none bg-white">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Habitación / Cama</label>
                            <input type="text" name="room" id="costos_room" required placeholder="Ej. Hab. 302" class="w-full p-2 border rounded-xl text-xs focus:ring-2 focus:ring-emerald-500 outline-none bg-white">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">No. de Expediente</label>
                            <input type="text" name="patient_id" id="costos_patient_id" required placeholder="Ej. EXP-1092" class="w-full p-2 border rounded-xl text-xs focus:ring-2 focus:ring-emerald-500 outline-none bg-white">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Turno de Atención</label>
                            <select name="shift" required class="w-full p-2 border rounded-xl text-xs focus:ring-2 focus:ring-emerald-500 outline-none bg-white font-bold text-slate-700">
                                <option value="Matutino">☀️ Turno Matutino</option>
                                <option value="Vespertino">⛅ Turno Vespertino</option>
                                <option value="Nocturno A">🌙 Turno Nocturno A</option>
                                <option value="Nocturno B">🌌 Turno Nocturno B</option>
                            </select>
                        </div>
                    </div>

                    <!-- Buscador y selección de insumos para cargo -->
                    <div class="p-4 bg-emerald-50/60 rounded-xl border border-emerald-200 space-y-3">
                        <h3 class="text-xs font-bold text-emerald-900 uppercase flex items-center gap-1.5">
                            <i class="fa-solid fa-magnifying-glass"></i> Buscador y Selección de Insumos / Materiales
                        </h3>
                        <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                            <div class="md:col-span-5">
                                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Buscar Insumo / Medicamento</label>
                                <input list="items_list" id="costos_temp_item" placeholder="Escriba para filtrar en el inventario..." class="w-full p-2 border rounded-lg text-xs bg-white outline-none font-medium">
                            </div>
                            <div class="md:col-span-3">
                                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Almacén de Origen</label>
                                <select id="costos_temp_warehouse" class="w-full p-2 border rounded-lg text-xs bg-white outline-none">
                                    <option value="Almacén General">Almacén General</option>
                                    <option value="Quirófano">Quirófano</option>
                                </select>
                            </div>
                            <div class="md:col-span-2">
                                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Cantidad</label>
                                <input type="number" min="1" id="costos_temp_qty" value="1" class="w-full p-2 border rounded-lg text-xs bg-white text-center font-bold outline-none">
                            </div>
                            <div class="md:col-span-2">
                                <button type="button" onclick="addCostosCartItem()" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-2 rounded-lg text-xs transition flex items-center justify-center gap-1 shadow-sm">
                                    <i class="fa-solid fa-plus"></i> Agregar
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Tabla de ítems en el carrito de costos -->
                    <div>
                        <h3 class="text-xs font-bold text-slate-700 uppercase mb-2 flex items-center justify-between">
                            <span><i class="fa-solid fa-list-check text-emerald-600"></i> Insumos Seleccionados para Cargo</span>
                            <span id="costosCartCountBadge" class="text-[11px] font-semibold bg-slate-200 text-slate-700 px-2 py-0.5 rounded-full">0 ítems</span>
                        </h3>
                        <div class="overflow-x-auto border rounded-xl bg-white">
                            <table class="w-full text-xs text-left text-slate-600">
                                <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                    <tr>
                                        <th class="p-2.5">Insumo / Lote</th>
                                        <th class="p-2.5">Almacén</th>
                                        <th class="p-2.5 text-center">Cantidad</th>
                                        <th class="p-2.5 text-center">Acción</th>
                                    </tr>
                                </thead>
                                <tbody id="costosCartTableBody" class="divide-y divide-slate-100">
                                    <tr>
                                        <td colspan="4" class="p-6 text-center text-slate-400 italic">
                                            No hay insumos agregados al cargo. Utilice el buscador superior para agregar materiales.
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Usuario Responsable</label>
                            <select name="user_id" required class="w-full p-2.5 border rounded-xl text-xs bg-white">
                                <option value="">Seleccionar Usuario...</option>
                                {% for u in users %}
                                    <option value="{{ u.id }}">{{ u.name }} ({{ u.role }})</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">PIN de Validación</label>
                            <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-xs bg-white">
                        </div>
                    </div>

                    <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl transition shadow flex items-center justify-center gap-2 text-xs">
                        <i class="fa-solid fa-check-circle"></i> Registrar Cargo Múltiple de Material
                    </button>
                </form>
            </div>

            <!-- Ventanas / Tablas de Movimientos por Turno (Con opción de imprimir por turno) -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                <!-- Turno Matutino -->
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-amber-200">
                    <h3 class="text-sm font-bold text-amber-800 flex items-center justify-between border-b pb-3 mb-3">
                        <span><i class="fa-solid fa-sun text-amber-500 mr-2"></i> Movimientos - Turno Matutino</span>
                        <div class="flex items-center gap-2">
                            <span class="bg-amber-100 text-amber-800 text-[10px] px-2.5 py-0.5 rounded-full font-bold">{{ matutino_cargos|length }} registros</span>
                            <a href="/imprimir_turno_pdf?shift=Matutino" target="_blank" class="px-2.5 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[11px] font-bold shadow transition flex items-center gap-1">
                                <i class="fa-solid fa-print"></i> Imprimir Turno
                            </a>
                        </div>
                    </h3>
                    <div class="overflow-x-auto max-h-72">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-amber-50 text-amber-900 sticky top-0">
                                <tr>
                                    <th class="p-2">Paciente / Exp.</th>
                                    <th class="p-2">Habitación</th>
                                    <th class="p-2">Insumo</th>
                                    <th class="p-2 text-center">Cant.</th>
                                    <th class="p-2">Hora</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for c in matutino_cargos %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2 font-medium">{{ c.patient_name }}<br><span class="text-[10px] text-slate-400">Exp: {{ c.patient_id }}</span></td>
                                    <td class="p-2">{{ c.room }}</td>
                                    <td class="p-2">{{ c.item_name }}</td>
                                    <td class="p-2 text-center font-bold text-emerald-600">{{ c.quantity }}</td>
                                    <td class="p-2 text-[10px] text-slate-400">{{ c.timestamp.strftime('%H:%M') }}</td>
                                </tr>
                                {% else %}
                                <tr><td colspan="5" class="p-4 text-center text-slate-400 text-xs">Sin cargos en turno matutino.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Turno Vespertino -->
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-orange-200">
                    <h3 class="text-sm font-bold text-orange-800 flex items-center justify-between border-b pb-3 mb-3">
                        <span><i class="fa-solid fa-cloud-sun text-orange-500 mr-2"></i> Movimientos - Turno Vespertino</span>
                        <div class="flex items-center gap-2">
                            <span class="bg-orange-100 text-orange-800 text-[10px] px-2.5 py-0.5 rounded-full font-bold">{{ vespertino_cargos|length }} registros</span>
                            <a href="/imprimir_turno_pdf?shift=Vespertino" target="_blank" class="px-2.5 py-1 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-[11px] font-bold shadow transition flex items-center gap-1">
                                <i class="fa-solid fa-print"></i> Imprimir Turno
                            </a>
                        </div>
                    </h3>
                    <div class="overflow-x-auto max-h-72">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-orange-50 text-orange-900 sticky top-0">
                                <tr>
                                    <th class="p-2">Paciente / Exp.</th>
                                    <th class="p-2">Habitación</th>
                                    <th class="p-2">Insumo</th>
                                    <th class="p-2 text-center">Cant.</th>
                                    <th class="p-2">Hora</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for c in vespertino_cargos %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2 font-medium">{{ c.patient_name }}<br><span class="text-[10px] text-slate-400">Exp: {{ c.patient_id }}</span></td>
                                    <td class="p-2">{{ c.room }}</td>
                                    <td class="p-2">{{ c.item_name }}</td>
                                    <td class="p-2 text-center font-bold text-emerald-600">{{ c.quantity }}</td>
                                    <td class="p-2 text-[10px] text-slate-400">{{ c.timestamp.strftime('%H:%M') }}</td>
                                </tr>
                                {% else %}
                                <tr><td colspan="5" class="p-4 text-center text-slate-400 text-xs">Sin cargos en turno vespertino.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Turno Nocturno A -->
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-indigo-200">
                    <h3 class="text-sm font-bold text-indigo-800 flex items-center justify-between border-b pb-3 mb-3">
                        <span><i class="fa-solid fa-moon text-indigo-500 mr-2"></i> Movimientos - Turno Nocturno A</span>
                        <div class="flex items-center gap-2">
                            <span class="bg-indigo-100 text-indigo-800 text-[10px] px-2.5 py-0.5 rounded-full font-bold">{{ nocturno_a_cargos|length }} registros</span>
                            <a href="/imprimir_turno_pdf?shift=Nocturno A" target="_blank" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[11px] font-bold shadow transition flex items-center gap-1">
                                <i class="fa-solid fa-print"></i> Imprimir Turno
                            </a>
                        </div>
                    </h3>
                    <div class="overflow-x-auto max-h-72">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-indigo-50 text-indigo-900 sticky top-0">
                                <tr>
                                    <th class="p-2">Paciente / Exp.</th>
                                    <th class="p-2">Habitación</th>
                                    <th class="p-2">Insumo</th>
                                    <th class="p-2 text-center">Cant.</th>
                                    <th class="p-2">Hora</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for c in nocturno_a_cargos %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2 font-medium">{{ c.patient_name }}<br><span class="text-[10px] text-slate-400">Exp: {{ c.patient_id }}</span></td>
                                    <td class="p-2">{{ c.room }}</td>
                                    <td class="p-2">{{ c.item_name }}</td>
                                    <td class="p-2 text-center font-bold text-emerald-600">{{ c.quantity }}</td>
                                    <td class="p-2 text-[10px] text-slate-400">{{ c.timestamp.strftime('%H:%M') }}</td>
                                </tr>
                                {% else %}
                                <tr><td colspan="5" class="p-4 text-center text-slate-400 text-xs">Sin cargos en turno nocturno A.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Turno Nocturno B -->
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-purple-200">
                    <h3 class="text-sm font-bold text-purple-800 flex items-center justify-between border-b pb-3 mb-3">
                        <span><i class="fa-solid fa-star text-purple-500 mr-2"></i> Movimientos - Turno Nocturno B</span>
                        <div class="flex items-center gap-2">
                            <span class="bg-purple-100 text-purple-800 text-[10px] px-2.5 py-0.5 rounded-full font-bold">{{ nocturno_b_cargos|length }} registros</span>
                            <a href="/imprimir_turno_pdf?shift=Nocturno B" target="_blank" class="px-2.5 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-[11px] font-bold shadow transition flex items-center gap-1">
                                <i class="fa-solid fa-print"></i> Imprimir Turno
                            </a>
                        </div>
                    </h3>
                    <div class="overflow-x-auto max-h-72">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-purple-50 text-purple-900 sticky top-0">
                                <tr>
                                    <th class="p-2">Paciente / Exp.</th>
                                    <th class="p-2">Habitación</th>
                                    <th class="p-2">Insumo</th>
                                    <th class="p-2 text-center">Cant.</th>
                                    <th class="p-2">Hora</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for c in nocturno_b_cargos %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2 font-medium">{{ c.patient_name }}<br><span class="text-[10px] text-slate-400">Exp: {{ c.patient_id }}</span></td>
                                    <td class="p-2">{{ c.room }}</td>
                                    <td class="p-2">{{ c.item_name }}</td>
                                    <td class="p-2 text-center font-bold text-emerald-600">{{ c.quantity }}</td>
                                    <td class="p-2 text-[10px] text-slate-400">{{ c.timestamp.strftime('%H:%M') }}</td>
                                </tr>
                                {% else %}
                                <tr><td colspan="5" class="p-4 text-center text-slate-400 text-xs">Sin cargos en turno nocturno B.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

            </div>
        </div>

        {% elif view == 'terminal' %}
        <div class="space-y-6 max-w-5xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-users text-blue-600"></i> Personal Responsable
                    </h2>
                    <p class="text-xs text-slate-500">Haga clic sobre su nombre para cargarlo en el formulario.</p>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                    {% for u in users %}
                    <button type="button" onclick="selectUser('{{ u.id }}', '{{ u.name }}')" class="p-3 rounded-xl border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-400 transition text-center group flex flex-col items-center">
                        <div class="w-9 h-9 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm mb-1.5 group-hover:scale-110 transition">
                            <i class="fa-solid {% if 'Admin' in u.role or 'Farmacia' in u.role %}fa-user-shield{% elif 'Enfermer' in u.role %}fa-user-nurse{% else %}fa-user-doctor{% endif %}"></i>
                        </div>
                        <h4 class="font-bold text-slate-800 text-xs group-hover:text-blue-600 truncate w-full">{{ u.name }}</h4>
                        <span class="text-[10px] text-slate-500">{{ u.role }}</span>
                    </button>
                    {% endfor %}
                </div>
            </div>

            <form action="/register_batch" method="POST" onsubmit="return validateBatchForm()" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-6">
                <input type="hidden" name="cart_data" id="cart_data_input">

                <div class="border-b pb-4 flex justify-between items-center">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-receipt text-blue-600"></i> Dispensación de Receta / Surtido a Paciente
                    </h2>
                    <span class="text-xs font-bold bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                        Surtido Multicarga Habilitado
                    </span>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Usuario Responsable</label>
                        <select name="user_id" id="userSelect" required onchange="updateSelectedUserName()" class="w-full p-2.5 border rounded-xl text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                            <option value="">Seleccione Usuario...</option>
                            {% for u in users %}
                                <option value="{{ u.id }}" data-name="{{ u.name }}">{{ u.name }} ({{ u.role }})</option>
                            {% endfor %}
                        </select>
                        <input type="hidden" name="user_name_hidden" id="user_name_hidden">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">PIN / Contraseña</label>
                        <input type="password" name="pin" required placeholder="PIN de Seguridad" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>
                </div>

                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                    <h3 class="text-xs font-bold text-blue-900 uppercase flex items-center gap-1.5">
                        <i class="fa-solid fa-bed-pulse"></i> Información del Paciente y Servicio
                    </h3>
                    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" id="patient_name" placeholder="Ej. Juan Pérez" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-medium">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Fecha de Nacimiento</label>
                            <input type="text" name="patient_fnac" id="patient_fnac" placeholder="Ej. 14/07/1967" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Habitación / Cama / UCI</label>
                            <input type="text" name="patient_id" id="patient_id" placeholder="Ej. UCI-5" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Servicio / Área</label>
                            <input type="text" name="service" id="service_area" placeholder="Ej. Urgencias" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        </div>
                    </div>
                </div>

                <div class="p-4 bg-indigo-50/40 rounded-xl border border-indigo-100 space-y-3">
                    <h3 class="text-xs font-bold text-indigo-900 uppercase flex items-center gap-1.5">
                        <i class="fa-solid fa-plus-circle"></i> Agregar Medicamentos al Surtido
                    </h3>
                    
                    <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                        <div class="md:col-span-4">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Medicamento / Lote</label>
                            <input list="items_list" id="temp_item" placeholder="Buscar medicamento..." class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-medium">
                        </div>
                        <div class="md:col-span-2">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Vía Admin.</label>
                            <input type="text" id="temp_via" placeholder="Ej. ORAL" class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-bold uppercase">
                        </div>
                        <div class="md:col-span-2">
                            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Tipo</label>
                            <select id="temp_type" class="w-full p-2 border rounded-lg text-xs bg-white outline-none">
                                <option value="Salida">Salida a Paciente</option>
                                <option value="Traspaso Qx">Traspaso a Quirófano</option>
                                <option value="Entrada">Entrada (Stock)</option>
                            </select>
                        </div>
                        <div class="md:col-span-1">
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
                            <button type="button" onclick="addToCart()" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-2 rounded-lg text-xs transition flex items-center justify-center gap-1 shadow-sm">
                                <i class="fa-solid fa-cart-plus"></i> Agregar
                            </button>
                        </div>
                    </div>
                </div>

                <div>
                    <h3 class="text-xs font-bold text-slate-700 uppercase mb-2 flex items-center justify-between">
                        <span><i class="fa-solid fa-list-check text-blue-600"></i> Medicamentos en la Lista de Surtido</span>
                        <span id="cartCountBadge" class="text-[11px] font-semibold bg-slate-200 text-slate-700 px-2 py-0.5 rounded-full">0 ítems</span>
                    </h3>

                    <div class="overflow-x-auto border rounded-xl">
                        <table class="w-full text-xs text-left text-slate-600" id="cartTable">
                            <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                <tr>
                                    <th class="p-2.5">Medicamento / Lote</th>
                                    <th class="p-2.5">Vía</th>
                                    <th class="p-2.5">Tipo</th>
                                    <th class="p-2.5">Almacén</th>
                                    <th class="p-2.5 text-center">Cantidad</th>
                                    <th class="p-2.5 text-center">Acción</th>
                                </tr>
                            </thead>
                            <tbody id="cartTableBody" class="divide-y divide-slate-100">
                                <tr>
                                    <td colspan="6" class="p-6 text-center text-slate-400 italic">
                                        No hay medicamentos agregados al surtido.
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Notas u Observaciones</label>
                    <input type="text" name="notes" placeholder="Observaciones sobre la dispensación..." class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                </div>

                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2 text-sm">
                    <i class="fa-solid fa-check-double"></i> Procesar Surtido Completo, Guardar y Generar Etiquetas
                </button>
            </form>
        </div>

        {% elif view == 'etiquetas' %}
        <div class="space-y-6 max-w-5xl mx-auto">
            <form action="/save_patient_from_label" method="POST" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 no-print">
                <div class="border-b pb-3 mb-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                    <div>
                        <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-tags text-purple-600"></i> Generador de Etiquetas Térmicas (51 x 25 mm)
                        </h2>
                        <p class="text-xs text-slate-500">Seleccione el formato y complete los datos para generar la etiqueta térmica exacta.</p>
                    </div>
                    <div class="flex gap-2 w-full sm:w-auto">
                        <button type="submit" class="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow transition flex items-center justify-center gap-1.5">
                            <i class="fa-solid fa-user-plus"></i> Guardar Paciente
                        </button>
                        <button type="button" onclick="downloadPdfLabel()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow transition flex items-center justify-center gap-2">
                            <i class="fa-solid fa-file-pdf"></i> Descargar PDF Exacto (51x25 mm)
                        </button>
                    </div>
                </div>

                <div class="mb-4 flex gap-4 bg-purple-50 p-3 rounded-xl border border-purple-200">
                    <label class="flex items-center gap-2 font-bold text-xs text-purple-900 cursor-pointer">
                        <input type="radio" name="format_type" value="horizontal1" checked onchange="toggleLabelFormat()" class="text-purple-600">
                        <span>🏷️ Formato 1: Etiqueta Con Paciente</span>
                    </label>
                    <label class="flex items-center gap-2 font-bold text-xs text-purple-900 cursor-pointer">
                        <input type="radio" name="format_type" value="horizontal2" onchange="toggleLabelFormat()" class="text-purple-600">
                        <span>🏷️ Formato 2: Etiqueta Unidosis (Sin Paciente)</span>
                    </label>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Paciente (Solo Formato 1)</label>
                            <input type="text" id="lbl_patient" name="patient_name" list="patients_datalist" placeholder="Ej. Ventura Carlos Petronilo" oninput="updateLabelPreview()" required class="w-full p-2 border rounded-lg text-xs bg-slate-50 font-medium outline-none">
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Fecha de Nacimiento</label>
                                <input type="text" id="lbl_fnac" placeholder="Ej. 14/07/1967" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Habitación / UCI</label>
                                <input type="text" id="lbl_habitacion" placeholder="Ej. UCI-5" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 outline-none">
                            </div>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Medicamento / Denominación</label>
                            <input list="items_list" id="lbl_item" placeholder="Seleccione o escriba medicamento..." oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 font-bold outline-none">
                        </div>
                    </div>

                    <div class="space-y-3">
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Vía de Administración</label>
                                <input type="text" id="lbl_via" placeholder="Ej. ORAL" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 outline-none font-bold">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Dosis / Cantidad</label>
                                <input type="text" id="lbl_dosis_cant" placeholder="Ej. 1 pza" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 outline-none font-bold">
                            </div>
                        </div>
                        <div class="grid grid-cols-3 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Lote</label>
                                <input type="text" id="lbl_lote" placeholder="Ej. SJ2544" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 text-center outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Folio</label>
                                <input type="text" id="lbl_folio" placeholder="Ej. 71" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 text-center outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Caducidad</label>
                                <input type="text" id="lbl_cad" placeholder="Ej. 10/01/2027" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 text-center outline-none">
                            </div>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Responsable / Preparó</label>
                            <input type="text" id="lbl_user" placeholder="Ej. GODINEZ RUIZ" oninput="updateLabelPreview()" class="w-full p-2 border rounded-lg text-xs bg-slate-50 outline-none">
                        </div>
                    </div>
                </div>
            </form>

            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 text-center space-y-4">
                <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 no-print">Previsualización Térmica (51 mm × 25 mm)</h3>
                
                <!-- FORMATO 1: 51x25 mm -->
                <div id="previewHoriz1" class="printable-label w-[385px] h-[188px] mx-auto bg-white border border-slate-400 rounded p-1 text-left shadow-md flex flex-col justify-between font-mono text-slate-900 overflow-hidden" style="box-sizing: border-box;">
                    <div class="flex justify-between items-center border-b border-black pb-0.5">
                        <div class="overflow-hidden pr-1">
                            <div class="font-black text-[9px] uppercase leading-none truncate" id="v1_patient">VENTURA CARLOS PETRONILO</div>
                            <div class="text-[7.5px] text-slate-700 leading-tight">F.N: <span id="v1_fnac" class="font-bold">14/07/1967</span> | Hab: <span id="v1_habitacion" class="font-bold">UCI-5</span></div>
                        </div>
                        <div class="text-right flex items-center gap-1 border border-black px-1 py-0.5 bg-slate-50 shrink-0">
                            <span class="font-extrabold text-[10px] tracking-tighter text-blue-900 leading-none">HD</span>
                            <div class="text-[6px] leading-none font-bold uppercase text-slate-800">
                                Hosp.<br>Obregón
                            </div>
                        </div>
                    </div>

                    <div class="text-center bg-slate-100 border border-slate-300 py-0.5 px-0.5">
                        <div class="font-black text-[8.5px] tracking-tight text-blue-900 uppercase truncate" id="v1_item">ACETATO DE METILPREDNISOLONA 40 MG</div>
                    </div>

                    <div class="grid grid-cols-2 text-[7.5px] font-bold border-t border-b border-black py-0.5 px-0.5">
                        <div class="truncate">Vía: <span id="v1_via" class="uppercase">ORAL</span></div>
                        <div class="text-right">Dosis: <span id="v1_dosis_cant">1 pza</span></div>
                    </div>

                    <div class="flex justify-between text-[7px] text-slate-800 pt-0.5">
                        <span>Folio: <strong id="v1_folio">--</strong></span>
                        <span>Prep: <span id="v1_user" class="uppercase">--</span></span>
                        <span>Hora: <span id="v1_hora">--:--</span></span>
                    </div>
                </div>

                <!-- FORMATO 2: 51x25 mm Unidosis -->
                <div id="previewHoriz2" class="printable-label hidden w-[385px] h-[188px] mx-auto bg-white border border-slate-400 rounded p-1 text-left shadow-md flex flex-col justify-between font-mono text-slate-900 overflow-hidden" style="box-sizing: border-box;">
                    <div class="flex justify-between items-center border-b border-black pb-0.5">
                        <span class="font-bold text-[7.5px] uppercase text-slate-700">UNIDOSIS HOSPITALARIA</span>
                        <div class="text-right flex items-center gap-1 border border-black px-1 py-0.5 bg-slate-50 shrink-0">
                            <span class="font-extrabold text-[10px] tracking-tighter text-blue-900 leading-none">HD</span>
                            <div class="text-[6px] leading-none font-bold uppercase text-slate-800">
                                Hosp.<br>Obregón
                            </div>
                        </div>
                    </div>

                    <div>
                        <div class="font-black text-[9px] uppercase text-blue-900 truncate" id="h2_item">PARACETAMOL</div>
                    </div>

                    <div class="grid grid-cols-4 gap-0.5 text-[7px] border-t border-b border-slate-400 py-0.5 bg-slate-50 px-0.5 text-center">
                        <div>Dosis:<br><strong id="h2_dosis_cant" class="text-[7.5px]">500 mg</strong></div>
                        <div>Forma:<br><strong id="h2_forma" class="text-[7.5px]">Tab</strong></div>
                        <div>Lote:<br><strong id="h2_lote" class="text-[7.5px]">SJ2544</strong></div>
                        <div>Vig:<br><strong id="h2_cad" class="text-[7.5px]">10/01/27</strong></div>
                    </div>

                    <div class="flex justify-between text-[7px] text-slate-800 pt-0.5">
                        <span>Vía: <strong id="h2_via" class="uppercase">Oral</strong></span>
                        <span>Folio: <strong id="h2_folio">--</strong></span>
                        <span>Prep: <strong id="h2_user" class="uppercase">--</strong></span>
                    </div>
                </div>

                <div class="no-print pt-2 flex justify-center gap-3">
                    <button onclick="downloadPdfLabel()" class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl text-xs shadow-md transition flex items-center gap-2">
                        <i class="fa-solid fa-file-pdf"></i> Descargar PDF Exacto de 51 x 25 mm
                    </button>
                    <button onclick="window.print()" class="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-xl text-xs shadow-md transition flex items-center gap-2">
                        <i class="fa-solid fa-print"></i> Imprimir Vía Navegador
                    </button>
                </div>
            </div>
        </div>

        {% elif view == 'inventario' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="flex flex-col md:flex-row justify-between items-center gap-4 mb-6 border-b pb-4">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-boxes-stacked text-blue-600"></i> Inventario y Existencias
                        </h2>
                        <p class="text-xs text-slate-500">Modificación de parámetros y eliminación de insumos mediante PIN de Administrador.</p>
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
                                <th class="p-3">Etiqueta</th>
                                <th class="p-3">Lote / Caducidad</th>
                                <th class="p-3 text-center">General</th>
                                <th class="p-3 text-center">Quirófano</th>
                                <th class="p-3 text-center">Acciones Admin</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for item in items %}
                            <tr class="hover:bg-slate-50 transition inventory-row">
                                <td class="p-3 font-mono text-xs font-bold text-blue-900">{{ item.code }}</td>
                                <td class="p-3 font-bold text-slate-900">
                                    {{ item.name }}
                                    <span class="block text-[11px] text-slate-400 font-normal">Vía: {{ item.via_administracion or 'N/A' }} | Forma: {{ item.presentacion or 'N/A' }}</span>
                                </td>
                                <td class="p-3">
                                    <span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                                        {{ item.category }}
                                    </span>
                                </td>
                                <td class="p-3">
                                    {% if item.etiqueta == 'Medicamento de alto Riesgo(MAR)' or item.etiqueta == 'Alto Riesgo' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800">🔴 {{ item.etiqueta }}</span>
                                    {% elif item.etiqueta == 'Controlado' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800">🟣 Controlado</span>
                                    {% elif item.etiqueta == 'Antibiótico' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">🟡 Antibiótico</span>
                                    {% elif item.etiqueta == 'Alto costo' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">💰 Alto Costo</span>
                                    {% elif item.etiqueta == 'Autorizado' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">✅ Autorizado</span>
                                    {% elif item.etiqueta == 'Ginecología' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-pink-100 text-pink-800">🌸 Ginecología</span>
                                    {% elif item.etiqueta == 'Anestesia' %}
                                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-800">💉 Anestesia</span>
                                    {% else %}
                                        <span class="text-slate-400 text-xs">-</span>
                                    {% endif %}
                                </td>
                                <td class="p-3 text-xs text-slate-600">
                                    <span class="font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">Lote: {{ item.lote or 'S/L' }}</span>
                                    <span class="block text-[10px] mt-0.5">
                                        {% if item.caducidad %}
                                            {% if item.caducidad < today_str_inv %}
                                                <span class="text-rose-700 font-extrabold bg-rose-100 px-1 rounded">⚠️ Caducado ({{ item.caducidad }})</span>
                                            {% elif item.caducidad <= warning_str %}
                                                <span class="text-amber-700 font-extrabold bg-amber-100 px-1 rounded">⏰ Por Caducar ({{ item.caducidad }})</span>
                                            {% else %}
                                                <span class="text-slate-500">Cad: {{ item.caducidad }}</span>
                                            {% endif %}
                                        {% else %}
                                            <span class="text-slate-400">Cad: S/F</span>
                                        {% endif %}
                                    </span>
                                </td>
                                <td class="p-3 text-center font-bold text-emerald-800">{{ item.stock_general }} {{ item.unit }}</td>
                                <td class="p-3 text-center font-bold text-blue-800">{{ item.stock_quirofano }} {{ item.unit }}</td>
                                <td class="p-3 text-center flex items-center justify-center gap-1">
                                    <button onclick="openEditItemModal('{{ item.id }}', '{{ item.code }}', '{{ item.name }}', '{{ item.category }}', '{{ item.via_administracion or '' }}', '{{ item.presentacion or '' }}', '{{ item.etiqueta or 'Ninguna' }}', '{{ item.lote or '' }}', '{{ item.caducidad or '' }}', '{{ item.stock_general }}', '{{ item.stock_quirofano }}')" class="px-2 py-1 bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold rounded text-xs transition" title="Modificar">
                                        <i class="fa-solid fa-pen"></i>
                                    </button>
                                    <button onclick="openDeleteItemModal('{{ item.id }}', '{{ item.name }}')" class="px-2 py-1 bg-rose-100 hover:bg-rose-200 text-rose-700 font-bold rounded text-xs transition" title="Eliminar Insumo">
                                        <i class="fa-solid fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div id="editModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border space-y-4 max-h-[90vh] overflow-y-auto">
                <div class="flex justify-between items-center border-b pb-2">
                    <h3 class="font-bold text-slate-900 text-base" id="modalItemTitle">Edición de Parámetros de Inventario</h3>
                    <button onclick="closeModal()" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
                </div>
                
                <form action="/update_item" method="POST" class="space-y-3">
                    <input type="hidden" name="item_id" id="modal_item_id">

                    <div class="bg-amber-50 p-3 rounded-xl border border-amber-200 text-xs">
                        <label class="block font-bold text-amber-900 uppercase mb-1"><i class="fa-solid fa-shield-halved"></i> PIN del Administrador (Requerido)</label>
                        <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-2 border rounded-lg text-center font-bold tracking-widest text-sm outline-none bg-white">
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Código / Clave</label>
                            <input type="text" name="code" id="modal_code" required class="w-full p-2 border rounded-xl text-xs font-mono">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre / Descripción</label>
                            <input type="text" name="name" id="modal_name" required class="w-full p-2 border rounded-xl text-xs font-bold">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Categoría</label>
                            <select name="category" id="modal_category" required class="w-full p-2 border rounded-xl text-xs bg-slate-50">
                                <option value="Medicamento">Medicamento</option>
                                <option value="Material Curación">Material Curación</option>
                                <option value="Solución / Inyectable">Solución / Inyectable</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Etiqueta Especial</label>
                            <select name="etiqueta" id="modal_etiqueta" class="w-full p-2 border rounded-xl text-xs font-bold">
                                <option value="Ninguna">Ninguna</option>
                                <option value="Medicamento de alto Riesgo(MAR)">🔴 Medicamento de alto Riesgo(MAR)</option>
                                <option value="Controlado">🟣 Controlado</option>
                                <option value="Antibiótico">🟡 Antibiótico</option>
                                <option value="Alto costo">💰 Alto costo</option>
                                <option value="Autorizado">✅ Autorizado</option>
                                <option value="Ginecología">🌸 Ginecología</option>
                                <option value="Anestesia">💉 Anestesia</option>
                            </select>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Vía Administración</label>
                            <input type="text" name="via_administracion" id="modal_via" placeholder="Ej. Oral / IV" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Forma Farmacéutica</label>
                            <input type="text" name="presentacion" id="modal_presentacion" placeholder="Ej. Tableta / Ampolleta" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Lote</label>
                            <input type="text" name="lote" id="modal_lote" class="w-full p-2 border rounded-xl text-xs font-medium">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Fecha Caducidad</label>
                            <input type="date" name="caducidad" id="modal_caducidad" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3 bg-slate-50 p-3 rounded-xl border">
                        <div>
                            <label class="block text-xs font-bold text-emerald-800 uppercase mb-1">Stock General</label>
                            <input type="number" name="stock_general" id="modal_stock_general" required class="w-full p-2 border rounded-xl text-xs font-bold text-center">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-blue-800 uppercase mb-1">Stock Quirófano</label>
                            <input type="number" name="stock_quirofano" id="modal_stock_quirofano" required class="w-full p-2 border rounded-xl text-xs font-bold text-center">
                        </div>
                    </div>

                    <button type="submit" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-bold py-2.5 rounded-xl transition shadow">
                        Autorizar y Guardar Cambios
                    </button>
                </form>
            </div>
        </div>

        <!-- MODAL ELIMINAR INSUMO -->
        <div id="deleteItemModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border space-y-4">
                <div class="flex justify-between items-center border-b pb-2">
                    <h3 class="font-bold text-slate-900 text-base text-rose-600">Eliminar Insumo del Inventario</h3>
                    <button onclick="closeDeleteItemModal()" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
                </div>
                <p class="text-xs text-slate-600">¿Está seguro de eliminar el insumo <strong id="delete_item_name_lbl" class="text-slate-900"></strong>? Ingrese el PIN de Administrador para confirmar:</p>
                <form action="/delete_item" method="POST" class="space-y-3">
                    <input type="hidden" name="item_id" id="modal_delete_item_id">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN del Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-2.5 border rounded-xl text-center text-lg font-bold tracking-widest outline-none">
                    </div>
                    <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-bold py-2.5 rounded-xl transition">
                        Eliminar Insumo Definitivamente
                    </button>
                </form>
            </div>
        </div>

        {% elif view == 'lote_etiquetas' %}
        <div class="space-y-6 max-w-4xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 no-print flex flex-col md:flex-row justify-between items-center gap-4">
                <div>
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-tags text-purple-600"></i> Lote de Etiquetas Generadas ({{ batch_labels|length }} ítems)
                    </h2>
                    <p class="text-xs text-slate-500">Paciente: <strong class="text-slate-800">{{ patient_name }}</strong> | Habitación: <strong class="text-slate-800">{{ habitacion }}</strong></p>
                </div>
                <div class="flex gap-2">
                    <a href="/imprimir_lote_pdf?patient={{ patient_name }}&fnac={{ fnac }}&habitacion={{ habitacion }}&user={{ user_name }}&items={{ items_json }}" target="_blank" class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow transition flex items-center gap-2">
                        <i class="fa-solid fa-file-pdf"></i> Descargar PDF Masivo (51x25 mm)
                    </a>
                    <button onclick="window.print()" class="px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold shadow transition flex items-center gap-2">
                        <i class="fa-solid fa-print"></i> Imprimir Todas
                    </button>
                    <a href="/terminal?view=terminal" class="px-4 py-2.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-xl text-xs font-bold transition">
                        Volver a Terminal
                    </a>
                </div>
            </div>

            <div class="space-y-6 text-center">
                <p class="text-xs font-bold text-slate-400 uppercase tracking-widest no-print">Previsualización Continua (Cada recuadro es una etiqueta independiente de 51 x 25 mm)</p>
                
                <div class="space-y-4">
                    {% for lbl in batch_labels %}
                    <div class="printable-label w-[385px] h-[188px] mx-auto bg-white border border-slate-400 rounded p-1 text-left shadow-md flex flex-col justify-between font-mono text-slate-900 overflow-hidden" style="box-sizing: border-box;">
                        <div class="flex justify-between items-center border-b border-black pb-0.5">
                            <div class="overflow-hidden pr-1">
                                <div class="font-black text-[9px] uppercase leading-none truncate">{{ patient_name }}</div>
                                <div class="text-[7.5px] text-slate-700 leading-tight">F.N: <span class="font-bold">{{ fnac }}</span> | Hab: <span class="font-bold">{{ habitacion }}</span></div>
                            </div>
                            <div class="text-right flex items-center gap-1 border border-black px-1 py-0.5 bg-slate-50 shrink-0">
                                <span class="font-extrabold text-[10px] tracking-tighter text-blue-900 leading-none">HD</span>
                                <div class="text-[6px] leading-none font-bold uppercase text-slate-800">
                                    Hosp.<br>Obregón
                                </div>
                            </div>
                        </div>

                        <div class="text-center bg-slate-100 border border-slate-300 py-0.5 px-0.5">
                            <div class="font-black text-[8.5px] tracking-tight text-blue-900 uppercase truncate">{{ lbl.name }}</div>
                        </div>

                        <div class="grid grid-cols-2 text-[7.5px] font-bold border-t border-b border-black py-0.5 px-0.5">
                            <div class="truncate">Vía: <span class="uppercase">{{ lbl.via }}</span></div>
                            <div class="text-right">Dosis: <span>{{ lbl.quantity }} pza(s)</span></div>
                        </div>

                        <div class="flex justify-between text-[7px] text-slate-800 pt-0.5">
                            <span>Folio: <strong>--</strong></span>
                            <span>Prep: <span class="uppercase">{{ user_name }}</span></span>
                            <span>Hora: <span>{{ current_time }}</span></span>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>

        {% elif view == 'alta_insumos' %}
        <div class="space-y-6 max-w-xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-plus-circle text-emerald-600"></i> Registrar Nuevo Insumo / Medicamento
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
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Vía de Administración</label>
                            <input type="text" name="via_administracion" placeholder="Ej. Oral / Intravenosa" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Forma Farmacéutica</label>
                            <input type="text" name="presentacion" placeholder="Ej. Tableta / Ampolleta" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Categoría</label>
                        <select name="category" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 outline-none">
                            <option value="Medicamento">Medicamento</option>
                            <option value="Material Curación">Material Curación</option>
                            <option value="Solución / Inyectable">Solución / Inyectable</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Etiqueta Especial</label>
                        <select name="etiqueta" class="w-full p-2.5 border rounded-xl text-sm bg-amber-50 font-bold outline-none">
                            <option value="Ninguna">Ninguna</option>
                            <option value="Medicamento de alto Riesgo(MAR)">🔴 Medicamento de alto Riesgo (MAR)</option>
                            <option value="Controlado">🟣 Medicamento Controlado</option>
                            <option value="Antibiótico">🟡 Antibiótico</option>
                            <option value="Alto costo">💰 Alto costo</option>
                            <option value="Autorizado">✅ Autorizado</option>
                            <option value="Ginecología">🌸 Ginecología</option>
                            <option value="Anestesia">💉 Anestesia</option>
                        </select>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Lote</label>
                            <input type="text" name="lote" placeholder="LOT-2026-X" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Fecha Caducidad</label>
                            <input type="date" name="caducidad" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Unidad</label>
                            <input type="text" name="unit" required value="pza" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Stock Inicial</label>
                            <input type="number" min="0" name="stock_general" required value="50" class="w-full p-2.5 border rounded-xl text-sm outline-none font-bold">
                        </div>
                    </div>

                    <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2 mt-4">
                        <i class="fa-solid fa-box-archive"></i> Registrar Medicamento
                    </button>
                </form>
            </div>
        </div>

        {% elif view == 'limpieza' %}
        <!-- ==================== PESTAÑA: CHECK-LIST LIMPIEZA / FORMATO FAR-FTO-19-01 ==================== -->
        <div class="space-y-6">
            <div class="bg-gradient-to-r from-teal-900 to-slate-900 text-white p-6 rounded-2xl shadow-md border border-teal-800">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                            <span class="bg-white/20 text-white text-[10px] font-mono px-2 py-0.5 rounded font-bold">FAR-FTO-19-01</span>
                            <span class="text-xs text-teal-300 font-bold">HOSPITAL OBREGÓN</span>
                        </div>
                        <h2 class="text-base font-bold flex items-center gap-2">
                            <i class="fa-solid fa-clipboard-check text-teal-400"></i> Check List Limpieza Farmacia / Almacén
                        </h2>
                        <p class="text-xs text-teal-200">Objetivo: Asegurar la limpieza de la Farmacia para brindar un conservación óptima de los medicamentos. Marque con una "✓" como área limpia.</p>
                    </div>
                </div>
            </div>

            <!-- Formulario de Registro Diario Check-list -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h3 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-broom text-teal-600"></i> Registrar Verificación Diaria
                    </h3>

                    <form action="/add_cleaning" method="POST" class="space-y-3">
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Día</label>
                                <select name="dia_semana" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 outline-none font-bold">
                                    <option value="Lunes">Lunes</option>
                                    <option value="Martes">Martes</option>
                                    <option value="Miércoles">Miércoles</option>
                                    <option value="Jueves">Jueves</option>
                                    <option value="Viernes">Viernes</option>
                                    <option value="Sábado">Sábado</option>
                                    <option value="Domingo">Domingo</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Turno</label>
                                <select name="turno" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 outline-none font-bold">
                                    <option value="Matutino">Matutino (M)</option>
                                    <option value="Vespertino">Vespertino (V)</option>
                                    <option value="Nocturno">Nocturno (N)</option>
                                </select>
                            </div>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Responsable</label>
                                <select name="user_id" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 outline-none">
                                    <option value="">Seleccione...</option>
                                    {% for u in users %}
                                        <option value="{{ u.id }}">{{ u.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN</label>
                                <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-xs outline-none">
                            </div>
                        </div>

                        <div class="bg-teal-50/60 p-4 rounded-xl border border-teal-100 space-y-2.5">
                            <h4 class="text-xs font-bold text-teal-900 uppercase border-b border-teal-200 pb-1">
                                Áreas de Limpieza (Formato Oficial)
                            </h4>

                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer">
                                <input type="checkbox" name="anaqueles" class="w-4 h-4 text-teal-600 rounded">
                                <span>Anaqueles</span>
                            </label>
                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer">
                                <input type="checkbox" name="pasillos" class="w-4 h-4 text-teal-600 rounded">
                                <span>Pasillos</span>
                            </label>
                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer">
                                <input type="checkbox" name="desecho_carton" class="w-4 h-4 text-teal-600 rounded">
                                <span>Desecho de cartón</span>
                            </label>
                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer">
                                <input type="checkbox" name="refrigerador" class="w-4 h-4 text-teal-600 rounded">
                                <span>Refrigerador</span>
                            </label>
                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer">
                                <input type="checkbox" name="cajas_traslado" class="w-4 h-4 text-teal-600 rounded">
                                <span>Cajas de traslado</span>
                            </label>
                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer">
                                <input type="checkbox" name="acomodo_medicamento" class="w-4 h-4 text-teal-600 rounded">
                                <span>Acomodo de medicamento</span>
                            </label>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Observaciones / Incidencias</label>
                            <textarea name="notes" rows="2" placeholder="Indique incidencias en el servicio y cómo lo solucionó..." class="w-full p-2 border rounded-xl text-xs outline-none bg-slate-50"></textarea>
                        </div>

                        <button type="submit" class="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-3 rounded-xl shadow-md transition flex items-center justify-center gap-2">
                            <i class="fa-solid fa-clipboard-check"></i> Registrar en Formato Oficial
                        </button>
                    </form>
                </div>

                <!-- Tabla de Bitácora Estilo Check-list Institucional -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2 space-y-4">
                    <div class="flex justify-between items-center border-b pb-3">
                        <div>
                            <h3 class="text-base font-bold text-slate-900 flex items-center gap-2">
                                <i class="fa-solid fa-table text-teal-600"></i> Bitácora Institucional de Limpieza
                            </h3>
                            <p class="text-[11px] text-slate-500">Registro histórico basado en formato FAR-FTO-19-01</p>
                        </div>
                        <button onclick="window.print()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold no-print">
                            <i class="fa-solid fa-print"></i> Imprimir Formato
                        </button>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left text-slate-700 border border-slate-300">
                            <thead class="bg-teal-50 text-teal-900 uppercase text-[10px] border-b border-slate-300">
                                <tr>
                                    <th class="p-2 border-r border-slate-300">Día / Turno</th>
                                    <th class="p-2 text-center border-r border-slate-300">Anaqueles</th>
                                    <th class="p-2 text-center border-r border-slate-300">Pasillos</th>
                                    <th class="p-2 text-center border-r border-slate-300">Cartón</th>
                                    <th class="p-2 text-center border-r border-slate-300">Refrigerador</th>
                                    <th class="p-2 text-center border-r border-slate-300">Cajas</th>
                                    <th class="p-2 text-center border-r border-slate-300">Acomodo</th>
                                    <th class="p-2 border-r border-slate-300">Responsable</th>
                                    <th class="p-2">Observaciones</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-200">
                                {% for log in cleaning_logs %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2 border-r border-slate-200 font-bold">
                                        {{ log.dia_semana or 'Día' }} <span class="bg-teal-100 text-teal-800 px-1.5 py-0.5 rounded text-[10px]">{{ log.turno or 'M' }}</span>
                                        <span class="block text-[9px] text-slate-400 font-mono">{{ log.timestamp.strftime('%d/%m/%Y') if log.timestamp else '' }}</span>
                                    </td>
                                    <td class="p-2 text-center border-r border-slate-200">{% if log.anaqueles %}<span class="text-emerald-600 font-extrabold text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}</td>
                                    <td class="p-2 text-center border-r border-slate-200">{% if log.pasillos %}<span class="text-emerald-600 font-extrabold text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}</td>
                                    <td class="p-2 text-center border-r border-slate-200">{% if log.desecho_carton %}<span class="text-emerald-600 font-extrabold text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}</td>
                                    <td class="p-2 text-center border-r border-slate-200">{% if log.refrigerador %}<span class="text-emerald-600 font-extrabold text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}</td>
                                    <td class="p-2 text-center border-r border-slate-200">{% if log.cajas_traslado %}<span class="text-emerald-600 font-extrabold text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}</td>
                                    <td class="p-2 text-center border-r border-slate-200">{% if log.acomodo_medicamento %}<span class="text-emerald-600 font-extrabold text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}</td>
                                    <td class="p-2 border-r border-slate-200 font-bold text-slate-800">{{ log.user_name }}</td>
                                    <td class="p-2 text-[11px] text-slate-600">{{ log.notes or '-' }}</td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="9" class="p-6 text-center text-slate-400 italic">
                                        No hay registros de limpieza en el formato institucional.
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        {% elif view == 'bitacora' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4 border-b pb-3 flex justify-between items-center">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora e Histórico de Surtido
                        </h2>
                        <p class="text-xs text-slate-500">Reversión, cancelación y eliminación de registros requieren PIN de Administrador.</p>
                    </div>
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
                                <th class="p-3">Medicamento</th>
                                <th class="p-3 text-center">Cant.</th>
                                <th class="p-3">Paciente / Área</th>
                                <th class="p-3">Responsable</th>
                                <th class="p-3 text-center">Acciones Admin</th>
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
                                <td class="p-3 font-medium text-slate-900">{{ mov.patient_name or mov.service or '-' }}</td>
                                <td class="p-3 text-indigo-900 font-bold">{{ mov.user_name }}</td>
                                <td class="p-3 text-center flex items-center justify-center gap-1.5">
                                    <button onclick="revertMovementModal('{{ mov.id }}')" class="px-2 py-1 bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold rounded text-[11px]" title="Revertir y devolver stock">
                                        <i class="fa-solid fa-rotate-left"></i> Revertir
                                    </button>
                                    <button onclick="deleteMovementModal('{{ mov.id }}')" class="px-2 py-1 bg-rose-100 hover:bg-rose-200 text-rose-700 font-bold rounded text-[11px]" title="Eliminar registro">
                                        <i class="fa-solid fa-trash"></i> Eliminar
                                    </button>
                                </td>
                            </tr>
                            {% else %}
                            <tr><td colspan="7" class="p-8 text-center text-slate-400 italic">No hay movimientos.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- MODAL REVERTIR SURTIDO -->
        <div id="revertModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border space-y-4">
                <div class="flex justify-between items-center border-b pb-2">
                    <h3 class="font-bold text-slate-900 text-base">Reversión (Devolver Stock)</h3>
                    <button onclick="closeRevertModal()" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
                </div>
                <p class="text-xs text-slate-600">Ingrese el PIN del Administrador para revertir este surtido y reingresar el stock a farmacia.</p>
                <form action="/revert_movement" method="POST" class="space-y-3">
                    <input type="hidden" name="movement_id" id="modal_movement_id">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN del Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-2.5 border rounded-xl text-center text-lg font-bold tracking-widest outline-none">
                    </div>
                    <button type="submit" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-bold py-2.5 rounded-xl transition">
                        Confirmar Reversión
                    </button>
                </form>
            </div>
        </div>

        <!-- MODAL ELIMINAR MOVIMIENTO BITÁCORA -->
        <div id="deleteMovModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border space-y-4">
                <div class="flex justify-between items-center border-b pb-2">
                    <h3 class="font-bold text-slate-900 text-base text-rose-600">Eliminar Registro de Bitácora</h3>
                    <button onclick="closeDeleteMovementModal()" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
                </div>
                <p class="text-xs text-slate-600">Esta acción borrará permanentemente el registro de la bitácora sin modificar existencias. Ingrese el PIN de Administrador:</p>
                <form action="/delete_movement" method="POST" class="space-y-3">
                    <input type="hidden" name="movement_id" id="modal_delete_mov_id">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN del Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-2.5 border rounded-xl text-center text-lg font-bold tracking-widest outline-none">
                    </div>
                    <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-bold py-2.5 rounded-xl transition">
                        Eliminar Definitivamente
                    </button>
                </form>
            </div>
        </div>

        {% elif view == 'controlados' %}
        <div class="space-y-6">
            {% if is_admin_controlled %}
            <div class="bg-gradient-to-r from-purple-900 via-indigo-900 to-slate-900 p-6 rounded-2xl shadow-md text-white space-y-4">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 border-b border-purple-800 pb-3">
                    <div>
                        <h2 class="text-base font-bold flex items-center gap-2">
                            <i class="fa-solid fa-scale-balanced text-purple-300"></i> Módulo de Arqueo y Conciliación Diaria de Controlados (Admin)
                        </h2>
                        <p class="text-xs text-purple-200">Cotejo diario entre las salidas surtidas y lo registrado en la bitácora de controlados para la fecha de hoy ({{ today_str }})</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="bg-purple-600 px-3 py-1.5 rounded-xl text-xs font-mono font-bold shadow">
                            {{ controlled_reconciliation | length }} Fármacos Monitoreados
                        </span>
                        <a href="/terminal?view=controlados" class="bg-white/20 hover:bg-white/30 text-white px-3 py-1.5 rounded-xl text-xs font-bold transition">Cerrar Arqueo</a>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {% for rec in controlled_reconciliation %}
                    <div class="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-purple-700/50 space-y-3">
                        <div class="flex justify-between items-start">
                            <h4 class="font-bold text-sm text-white truncate max-w-[200px]" title="{{ rec.item.name }}">{{ rec.item.name }}</h4>
                            {% if rec.status == 'Conciliado' %}
                                <span class="bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full text-[10px] font-extrabold flex items-center gap-1">
                                    <i class="fa-solid fa-circle-check"></i> Conciliado (Cuadrado)
                                </span>
                            {% else %}
                                <span class="bg-rose-500/20 text-rose-300 border border-rose-500/40 px-2 py-0.5 rounded-full text-[10px] font-extrabold flex items-center gap-1">
                                    <i class="fa-solid fa-triangle-exclamation"></i> Discrepancia
                                </span>
                            {% endif %}
                        </div>

                        <div class="grid grid-cols-3 gap-1.5 text-xs bg-black/20 p-2.5 rounded-lg border border-purple-900/40 text-center">
                            <div>
                                <span class="text-[9px] text-purple-300 block">Stock Actual:</span>
                                <strong class="text-xs text-emerald-300 font-mono">{{ rec.current_stock }} pzas</strong>
                            </div>
                            <div>
                                <span class="text-[9px] text-purple-300 block">Surtidas Hoy:</span>
                                <strong class="text-xs text-white font-mono">{{ rec.dispensed_today }} pzas</strong>
                            </div>
                            <div>
                                <span class="text-[9px] text-purple-300 block">Bitácora Hoy:</span>
                                <strong class="text-xs text-amber-300 font-mono">{{ rec.logged_today }} pzas</strong>
                            </div>
                        </div>

                        <div class="text-[11px] text-purple-200 flex justify-between">
                            <span>Lote: <strong class="text-white">{{ rec.item.lote or 'S/L' }}</strong></span>
                            <span>Estado: <strong class="{% if rec.status == 'Conciliado' %}text-emerald-300{% else %}text-rose-300{% endif %}">{{ rec.status }}</strong></span>
                        </div>
                    </div>
                    {% else %}
                    <div class="col-span-full text-center text-purple-300 italic py-3 text-xs">
                        No hay medicamentos controlados registrados en el inventario para cotejar.
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% else %}
            <div class="bg-purple-900/10 border border-purple-200 p-4 rounded-2xl flex flex-col sm:flex-row justify-between items-center gap-3 no-print">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center font-bold">
                        <i class="fa-solid fa-shield-halved"></i>
                    </div>
                    <div>
                        <h4 class="font-bold text-purple-900 text-xs">Módulo de Arqueo y Conciliación Diaria Protegido</h4>
                        <p class="text-[11px] text-slate-500">Esta herramienta analítica es exclusiva para el Administrador.</p>
                    </div>
                </div>
                <button onclick="openUnlockArqueoModal()" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-xl text-xs shadow transition flex items-center gap-1.5">
                    <i class="fa-solid fa-lock-open"></i> Desbloquear Arqueo Diario (Admin)
                </button>
            </div>
            {% endif %}

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-file-prescription text-rose-600"></i> Surtir Medicamento Controlado
                    </h2>

                    <form action="/add_controlled" method="POST" class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Medicamento Controlado</label>
                            <input list="controlled_items_list" name="item_name" required placeholder="Escriba o busque..." class="w-full p-2.5 border rounded-xl text-sm bg-rose-50 focus:bg-white focus:ring-2 focus:ring-rose-500 outline-none font-bold">
                            <datalist id="controlled_items_list">
                                {% for item in controlled_items %}
                                    <option value="{{ item.name }} (Lote: {{ item.lote or 'S/L' }})">
                                {% endfor %}
                            </datalist>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" required placeholder="Nombre del paciente..." class="w-full p-2.5 border rounded-xl text-sm outline-none font-medium">
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">No. Receta / Folio Controlado</label>
                            <input type="text" name="prescription_num" required placeholder="Ej. REC-2026-9901" class="w-full p-2.5 border rounded-xl text-sm font-mono outline-none">
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Cantidad</label>
                                <input type="number" min="1" value="1" name="quantity" required class="w-full p-2.5 border rounded-xl text-sm outline-none">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Médico Prescriptor</label>
                                <input type="text" name="doctor_name" placeholder="Ej. Dr. Ramírez" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                            </div>
                        </div>

                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Usuario</label>
                                <select name="user_id" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 outline-none">
                                    <option value="">Seleccione...</option>
                                    {% for u in users %}
                                        <option value="{{ u.id }}">{{ u.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN</label>
                                <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                            </div>
                        </div>

                        <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2 mt-2">
                            <i class="fa-solid fa-file-signature"></i> Registrar Salida Controlada
                        </button>
                    </form>
                </div>

                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                    <div class="flex justify-between items-center mb-4 border-b pb-3">
                        <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-book-medical text-rose-600"></i> Bitácora de Medicamentos Controlados
                        </h2>
                        <button onclick="window.print()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold no-print">
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
                                    <th class="p-2.5 text-center">Acción Admin</th>
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
                                    <td class="p-2.5 text-center">
                                        <button onclick="deleteControlledModal('{{ log.id }}')" class="px-2 py-1 bg-rose-100 hover:bg-rose-200 text-rose-700 font-bold rounded text-[11px]" title="Eliminar registro controlado">
                                            <i class="fa-solid fa-trash"></i> Eliminar
                                        </button>
                                    </td>
                                </tr>
                                {% else %}
                                <tr><td colspan="7" class="p-6 text-center text-slate-400 italic">No hay registros controlados.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- MODAL DESBLOQUEAR ARQUEO CONTROLADOS -->
        <div id="unlockArqueoModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border space-y-4">
                <div class="flex justify-between items-center border-b pb-2">
                    <h3 class="font-bold text-slate-900 text-base">Autorización de Administrador</h3>
                    <button onclick="closeUnlockArqueoModal()" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
                </div>
                <p class="text-xs text-slate-600">Ingrese el PIN del Administrador para visualizar el módulo de arqueo y conciliación diaria de controlados.</p>
                <form action="/auth_admin_controlled" method="POST" class="space-y-3">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN del Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-2.5 border rounded-xl text-center text-lg font-bold tracking-widest outline-none">
                    </div>
                    <button type="submit" class="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-2.5 rounded-xl transition">
                        Desbloquear Módulo
                    </button>
                </form>
            </div>
        </div>

        <!-- MODAL ELIMINAR REGISTRO CONTROLADO -->
        <div id="deleteControlledModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border space-y-4">
                <div class="flex justify-between items-center border-b pb-2">
                    <h3 class="font-bold text-slate-900 text-base text-rose-600">Eliminar Registro Controlado</h3>
                    <button onclick="closeDeleteControlledModal()" class="text-slate-400 hover:text-slate-600 text-lg">&times;</button>
                </div>
                <p class="text-xs text-slate-600">Esta acción borrará permanentemente el registro de la bitácora controlada. Ingrese el PIN de Administrador:</p>
                <form action="/delete_controlled" method="POST" class="space-y-3">
                    <input type="hidden" name="log_id" id="modal_delete_controlled_id">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN del Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-2.5 border rounded-xl text-center text-lg font-bold tracking-widest outline-none">
                    </div>
                    <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-bold py-2.5 rounded-xl transition">
                        Eliminar Definitivamente
                    </button>
                </form>
            </div>
        </div>

        {% elif view == 'usuarios' %}
        {% if not is_admin %}
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 max-w-md mx-auto text-center space-y-4">
            <div class="w-16 h-16 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center text-2xl mx-auto">
                <i class="fa-solid fa-user-lock"></i>
            </div>
            <h2 class="text-lg font-bold text-slate-900">Acceso Exclusivo de Administrador</h2>
            <p class="text-xs text-slate-500">Solo el Administrador puede agregar, editar usuarios y modificar PINs de acceso.</p>

            <form action="/auth_admin_users" method="POST" class="space-y-3">
                <input type="password" name="admin_pin" required placeholder="PIN de Administrador" class="w-full p-3 border rounded-xl text-center text-lg font-bold tracking-widest outline-none focus:ring-2 focus:ring-blue-500">
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition">
                    Desbloquear Administración
                </button>
            </form>
        </div>
        {% else %}
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-user-plus text-blue-600"></i> Crear / Modificar Usuario
                </h2>
                <form action="/save_user" method="POST" class="space-y-3">
                    <input type="hidden" name="user_id" id="edit_user_id">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre Completo</label>
                        <input type="text" name="name" id="edit_user_name" required placeholder="Ej. Carlos Mendoza" class="w-full p-2.5 border rounded-xl text-sm outline-none">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Rol / Puesto</label>
                        <select name="role" id="edit_user_role" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 outline-none">
                            <option value="Farmacéutico">Farmacéutico</option>
                            <option value="Enfermería Quirófano">Enfermería Quirófano</option>
                            <option value="Técnico de Farmacia">Técnico de Farmacia</option>
                            <option value="Administrador">Administrador</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN / Contraseña</label>
                        <input type="password" name="pin" id="edit_user_pin" required placeholder="PIN de 4 dígitos" class="w-full p-2.5 border rounded-xl text-sm outline-none font-mono">
                    </div>
                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition">
                        Guardar Usuario / PIN
                    </button>
                </form>
            </div>

            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-users-gear text-blue-600"></i> Personal Registrado
                </h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {% for u in users %}
                    <div class="p-4 rounded-xl border bg-slate-50 flex justify-between items-center">
                        <div>
                            <h4 class="font-bold text-slate-900 text-sm">{{ u.name }}</h4>
                            <p class="text-xs text-slate-500">{{ u.role }}</p>
                            <p class="text-[10px] text-blue-600 font-mono mt-1">PIN: ••••</p>
                        </div>
                        <button onclick="editUser('{{ u.id }}', '{{ u.name }}', '{{ u.role }}', '{{ u.pin }}')" class="px-2.5 py-1 bg-blue-100 hover:bg-blue-200 text-blue-800 font-bold rounded-lg text-xs transition">
                            <i class="fa-solid fa-pen"></i> Editar PIN
                        </button>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        {% endif %}
        {% endif %}
    </main>

    <script>
        let cart = [];
        let costosCart = [];

        function selectUser(id, name) {
            var elem = document.getElementById('userSelect');
            if(elem) elem.value = id;
            document.getElementById('user_name_hidden').value = name;
        }

        function updateSelectedUserName() {
            var select = document.getElementById('userSelect');
            var opt = select.options[select.selectedIndex];
            var name = opt.getAttribute('data-name') || '';
            document.getElementById('user_name_hidden').value = name;
        }

        function addToCart() {
            const itemInput = document.getElementById('temp_item');
            const itemSearchValue = itemInput.value.trim();
            const viaInput = document.getElementById('temp_via').value.trim() || 'ORAL';
            const type = document.getElementById('temp_type').value;
            const warehouse = document.getElementById('temp_warehouse').value;
            const quantity = parseInt(document.getElementById('temp_quantity').value) || 1;

            if (!itemSearchValue) {
                alert('Por favor seleccione un medicamento.');
                return;
            }

            cart.push({
                item_search: itemSearchValue,
                via: viaInput,
                type: type,
                warehouse: warehouse,
                quantity: quantity
            });

            itemInput.value = '';
            document.getElementById('temp_via').value = '';
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
                        <td colspan="6" class="p-6 text-center text-slate-400 italic">
                            No hay medicamentos agregados al surtido.
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
                        <td class="p-2.5 font-semibold uppercase text-xs">${item.via}</td>
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

        // Funciones para el Carrito de Cargo Costos Múltiple
        function addCostosCartItem() {
            const itemInput = document.getElementById('costos_temp_item');
            const itemVal = itemInput.value.trim();
            const warehouse = document.getElementById('costos_temp_warehouse').value;
            const quantity = parseInt(document.getElementById('costos_temp_qty').value) || 1;

            if (!itemVal) {
                alert('Por favor seleccione o escriba un insumo.');
                return;
            }

            costosCart.push({
                item_search: itemVal,
                warehouse: warehouse,
                quantity: quantity
            });

            itemInput.value = '';
            document.getElementById('costos_temp_qty').value = 1;
            renderCostosCart();
        }

        function removeCostosCartItem(index) {
            costosCart.splice(index, 1);
            renderCostosCart();
        }

        function renderCostosCart() {
            const tbody = document.getElementById('costosCartTableBody');
            const badge = document.getElementById('costosCartCountBadge');
            badge.innerText = costosCart.length + ' ítems';

            if (costosCart.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" class="p-6 text-center text-slate-400 italic">
                            No hay insumos agregados al cargo. Utilice el buscador superior para agregar materiales.
                        </td>
                    </tr>
                `;
                return;
            }

            let html = '';
            costosCart.forEach((item, index) => {
                html += `
                    <tr class="hover:bg-slate-50">
                        <td class="p-2.5 font-bold text-slate-800">${item.item_search}</td>
                        <td class="p-2.5 text-xs text-slate-600">${item.warehouse}</td>
                        <td class="p-2.5 text-center font-bold text-sm text-emerald-700">${item.quantity}</td>
                        <td class="p-2.5 text-center">
                            <button type="button" onclick="removeCostosCartItem(${index})" class="px-2 py-1 bg-rose-100 hover:bg-rose-200 text-rose-700 font-bold rounded text-xs transition">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function validateCostosBatch() {
            if (costosCart.length === 0) {
                alert('Debe agregar al menos un insumo al cargo de costos.');
                return false;
            }
            document.getElementById('cart_costos_data_input').value = JSON.stringify(costosCart);
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

        function toggleLabelFormat() {
            const formatType = document.querySelector('input[name="format_type"]:checked').value;
            const h1Preview = document.getElementById('previewHoriz1');
            const h2Preview = document.getElementById('previewHoriz2');

            if (formatType === 'horizontal1') {
                h1Preview.classList.remove('hidden');
                h2Preview.classList.add('hidden');
            } else {
                h1Preview.classList.add('hidden');
                h2Preview.classList.remove('hidden');
            }
        }

        function updateLabelPreview() {
            const pName = document.getElementById('lbl_patient').value.trim();
            const pFnac = document.getElementById('lbl_fnac').value.trim();
            const pHab = document.getElementById('lbl_habitacion').value.trim();
            const pItem = document.getElementById('lbl_item').value.trim();
            const pVia = document.getElementById('lbl_via').value.trim();
            const pDosisCant = document.getElementById('lbl_dosis_cant').value.trim();
            const pLote = document.getElementById('lbl_lote').value.trim();
            const pFolio = document.getElementById('lbl_folio').value.trim();
            const pCad = document.getElementById('lbl_cad').value.trim();
            const pUser = document.getElementById('lbl_user').value.trim();

            const timeNow = new Date().toLocaleTimeString('es-MX', {hour: '2-digit', minute:'2-digit'});

            document.getElementById('v1_patient').innerText = pName || 'VENTURA CARLOS PETRONILO';
            document.getElementById('v1_fnac').innerText = pFnac || '14/07/1967';
            document.getElementById('v1_habitacion').innerText = pHab || 'UCI-5';
            document.getElementById('v1_item').innerText = pItem || 'ACETATO DE METILPREDNISOLONA 40 MG';
            document.getElementById('v1_via').innerText = pVia || 'ORAL';
            document.getElementById('v1_hora').innerText = timeNow;
            document.getElementById('v1_dosis_cant').innerText = pDosisCant || '1 pza';
            document.getElementById('v1_folio').innerText = pFolio || '--';
            document.getElementById('v1_user').innerText = pUser || '--';

            document.getElementById('h2_item').innerText = pItem || 'PARACETAMOL';
            document.getElementById('h2_dosis_cant').innerText = pDosisCant || '500 mg';
            document.getElementById('h2_forma').innerText = pVia || 'Tab';
            document.getElementById('h2_lote').innerText = pLote || 'SJ2544';
            document.getElementById('h2_via').innerText = pVia || 'Oral';
            document.getElementById('h2_folio').innerText = pFolio || '--';
            document.getElementById('h2_cad').innerText = pCad || '10/01/27';
            document.getElementById('h2_user').innerText = pUser || '--';
        }

        function downloadPdfLabel() {
            const formatType = document.querySelector('input[name="format_type"]:checked').value;
            const patient = encodeURIComponent(document.getElementById('lbl_patient').value.trim());
            const fnac = encodeURIComponent(document.getElementById('lbl_fnac').value.trim());
            const habitacion = encodeURIComponent(document.getElementById('lbl_habitacion').value.trim());
            const item = encodeURIComponent(document.getElementById('lbl_item').value.trim());
            const via = encodeURIComponent(document.getElementById('lbl_via').value.trim());
            const dosis_cant = encodeURIComponent(document.getElementById('lbl_dosis_cant').value.trim());
            const lote = encodeURIComponent(document.getElementById('lbl_lote').value.trim());
            const folio = encodeURIComponent(document.getElementById('lbl_folio').value.trim());
            const cad = encodeURIComponent(document.getElementById('lbl_cad').value.trim());
            const user = encodeURIComponent(document.getElementById('lbl_user').value.trim());

            const url = `/imprimir_etiqueta_pdf?format_type=${formatType}&patient=${patient}&fnac=${fnac}&habitacion=${habitacion}&item=${item}&via=${via}&dosis_cant=${dosis_cant}&lote=${lote}&folio=${folio}&cad=${cad}&user=${user}`;
            window.open(url, '_blank');
        }

        function loadParamsFromURL() {
            const urlParams = new URLSearchParams(window.location.search);
            if(urlParams.has('patient') || urlParams.has('item')) {
                if(urlParams.get('patient')) document.getElementById('lbl_patient').value = urlParams.get('patient');
                if(urlParams.get('fnac')) document.getElementById('lbl_fnac').value = urlParams.get('fnac');
                if(urlParams.get('item')) document.getElementById('lbl_item').value = urlParams.get('item');
                if(urlParams.get('via')) document.getElementById('lbl_via').value = urlParams.get('via');
                if(urlParams.get('qty')) document.getElementById('lbl_dosis_cant').value = urlParams.get('qty') + ' pza';
                if(urlParams.get('user')) document.getElementById('lbl_user').value = urlParams.get('user');
                if(urlParams.get('habitacion')) document.getElementById('lbl_habitacion').value = urlParams.get('habitacion');
                updateLabelPreview();
            }
        }

        function openEditItemModal(id, code, name, category, via, pres, etiq, lote, cad, gen, qx) {
            document.getElementById('modal_item_id').value = id;
            document.getElementById('modal_code').value = code;
            document.getElementById('modal_name').value = name;
            document.getElementById('modal_category').value = category;
            document.getElementById('modal_via').value = via;
            document.getElementById('modal_presentacion').value = pres;
            document.getElementById('modal_etiqueta').value = etiq;
            document.getElementById('modal_lote').value = lote;
            document.getElementById('modal_caducidad').value = cad;
            document.getElementById('modal_stock_general').value = gen;
            document.getElementById('modal_stock_quirofano').value = qx;
            document.getElementById('modalItemTitle').innerText = 'Modificar Parámetros: ' + name;
            document.getElementById('editModal').classList.remove('hidden');
        }

        function closeModal() {
            document.getElementById('editModal').classList.add('hidden');
        }

        function openDeleteItemModal(id, name) {
            document.getElementById('modal_delete_item_id').value = id;
            document.getElementById('delete_item_name_lbl').innerText = name;
            document.getElementById('deleteItemModal').classList.remove('hidden');
        }

        function closeDeleteItemModal() {
            document.getElementById('deleteItemModal').classList.add('hidden');
        }

        function revertMovementModal(id) {
            document.getElementById('modal_movement_id').value = id;
            document.getElementById('revertModal').classList.remove('hidden');
        }

        function closeRevertModal() {
            document.getElementById('revertModal').classList.add('hidden');
        }

        function deleteMovementModal(id) {
            document.getElementById('modal_delete_mov_id').value = id;
            document.getElementById('deleteMovModal').classList.remove('hidden');
        }

        function closeDeleteMovementModal() {
            document.getElementById('deleteMovModal').classList.add('hidden');
        }

        function openUnlockArqueoModal() {
            document.getElementById('unlockArqueoModal').classList.remove('hidden');
        }

        function closeUnlockArqueoModal() {
            document.getElementById('unlockArqueoModal').classList.add('hidden');
        }

        function deleteControlledModal(id) {
            document.getElementById('modal_delete_controlled_id').value = id;
            document.getElementById('deleteControlledModal').classList.remove('hidden');
        }

        function closeDeleteControlledModal() {
            document.getElementById('deleteControlledModal').classList.add('hidden');
        }

        function editUser(id, name, role, pin) {
            document.getElementById('edit_user_id').value = id;
            document.getElementById('edit_user_name').value = name;
            document.getElementById('edit_user_role').value = role;
            document.getElementById('edit_user_pin').value = pin;
        }

        window.onload = function() {
            updateLabelPreview();
            loadParamsFromURL();
        };
    </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# RUTAS DE PDF MASIVO, ETIQUETAS Y REPORTES DE TURNO
# -----------------------------------------------------------------------------

@app.route("/imprimir_turno_pdf")
def imprimir_turno_pdf():
    shift = request.args.get("shift", "Matutino").strip()
    cargos = Movement.query.filter_by(is_cost_cargo=True, shift=shift).order_by(Movement.timestamp.desc()).all()
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Encabezado del Reporte Institucional
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, height - 20 * mm, "HOSPITAL OBREGÓN - FARMACIA HOSPITALARIA")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, height - 26 * mm, f"REPORTE DE CARGOS A COSTOS - TURNO: {shift.upper()}")
    
    fecha_actual = datetime.now(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, height - 32 * mm, f"Fecha de emisión: {fecha_actual}")
    
    c.setLineWidth(1)
    c.line(20 * mm, height - 35 * mm, width - 20 * mm, height - 35 * mm)

    # Tabla de Contenido
    y = height - 45 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "Paciente / Expediente")
    c.drawString(70 * mm, y, "Habitación")
    c.drawString(95 * mm, y, "Insumo / Material")
    c.drawString(160 * mm, y, "Cant.")
    c.drawString(178 * mm, y, "Hora")
    
    y -= 6 * mm
    c.setLineWidth(0.5)
    c.line(20 * mm, y + 4 * mm, width - 20 * mm, y + 4 * mm)

    c.setFont("Helvetica", 9)
    for cgo in cargos:
        if y < 25 * mm:  # Salto de página automático si se llena
            c.showPage()
            y = height - 25 * mm
        
        patient_info = f"{cgo.patient_name} (Exp: {cgo.patient_id})"
        c.drawString(20 * mm, y, patient_info[:32])
        c.drawString(70 * mm, y, str(cgo.room or "-")[:15])
        c.drawString(95 * mm, y, str(cgo.item_name)[:35])
        c.drawRightString(168 * mm, y, str(cgo.quantity))
        c.drawString(178 * mm, y, cgo.timestamp.strftime('%H:%M') if cgo.timestamp else "--:--")
        
        y -= 7 * mm

    if not cargos:
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(20 * mm, y, "No hay registros de cargos para este turno.")

    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        mimetype="application/pdf",
        download_name=f"reporte_cargos_{shift.lower().replace(' ', '_')}.pdf"
    )

@app.route("/imprimir_lote_pdf")
def imprimir_lote_pdf():
    patient = request.args.get("patient", "PACIENTE").strip().upper()
    fnac = request.args.get("fnac", "").strip()
    habitacion = request.args.get("habitacion", "").strip()
    user_name = request.args.get("user", "").strip().upper()
    items_json = request.args.get("items", "[]")

    try:
        items_list = json.loads(items_json)
    except Exception:
        items_list = []

    width = 51 * mm
    height = 25 * mm

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    hora = datetime.now(LOCAL_TZ).strftime("%H:%M")

    for idx, lbl in enumerate(items_list):
        item_name = lbl.get("name", "").upper()
        via = lbl.get("via", "ORAL").upper()
        qty = lbl.get("quantity", 1)

        c.setLineWidth(0.5)
        c.rect(1*mm, 1*mm, 49*mm, 23*mm)

        c.setFont("Helvetica-Bold", 7)
        c.drawString(2*mm, 21.5*mm, patient[:26])
        
        c.setFont("Helvetica", 6)
        c.drawString(2*mm, 18.5*mm, f"F.N: {fnac} | Hab: {habitacion}")

        c.rect(38*mm, 18*mm, 11*mm, 5*mm)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(38.5*mm, 19.5*mm, "HD")
        c.setFont("Helvetica", 4)
        c.drawString(43.5*mm, 21*mm, "Hosp.")
        c.drawString(43.5*mm, 19*mm, "Obregón")

        c.line(1*mm, 17.5*mm, 50*mm, 17.5*mm)

        c.setFillColor(HexColor("#F1F5F9"))
        c.rect(1.5*mm, 11.5*mm, 48*mm, 5*mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#000000"))
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(25.5*mm, 13*mm, item_name[:35])

        c.line(1*mm, 11*mm, 50*mm, 11*mm)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(2*mm, 8*mm, f"Vía: {via}")
        c.drawRightString(49*mm, 8*mm, f"Dosis: {qty} pza(s)")
        c.line(1*mm, 6.5*mm, 50*mm, 6.5*mm)

        c.setFont("Helvetica", 5.5)
        c.drawString(2*mm, 3*mm, "Folio: --")
        c.drawCentredString(25.5*mm, 3*mm, f"Prep: {user_name[:12]}")
        c.drawRightString(49*mm, 3*mm, f"Hora: {hora}")

        c.showPage()

    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=False,
        mimetype="application/pdf",
        download_name="lote_etiquetas_51x25.pdf"
    )

# -----------------------------------------------------------------------------
# RESTO DE RUTAS DE LA APLICACIÓN
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("terminal", view="costos"))

@app.route("/terminal")
def terminal():
    view = request.args.get("view", "costos")
    items = Item.query.order_by(Item.name, Item.lote).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()

    # Filtros de cargos por turno (cargo de material para costos)
    matutino_cargos = Movement.query.filter_by(is_cost_cargo=True, shift="Matutino").order_by(Movement.timestamp.desc()).all()
    vespertino_cargos = Movement.query.filter_by(is_cost_cargo=True, shift="Vespertino").order_by(Movement.timestamp.desc()).all()
    nocturno_a_cargos = Movement.query.filter_by(is_cost_cargo=True, shift="Nocturno A").order_by(Movement.timestamp.desc()).all()
    nocturno_b_cargos = Movement.query.filter_by(is_cost_cargo=True, shift="Nocturno B").order_by(Movement.timestamp.desc()).all()

    controlled_items = Item.query.filter_by(etiqueta="Controlado").order_by(Item.name).all()
    controlled_logs = ControlledLog.query.order_by(ControlledLog.timestamp.desc()).all()
    cleaning_logs = CleaningLog.query.order_by(CleaningLog.timestamp.desc()).all()

    is_admin_controlled = request.args.get("admin_arqueo") == "true"
    today_date = datetime.now(LOCAL_TZ).date()
    today_str = today_date.strftime('%d/%m/%Y')
    warning_str = (datetime.now(LOCAL_TZ).date() + timedelta(days=30)).isoformat()
    today_iso = today_date.isoformat()

    controlled_reconciliation = []
    if is_admin_controlled:
        for item in controlled_items:
            current_stock = (item.stock_general or 0) + (item.stock_quirofano or 0)
            dispensed_today = sum(
                mov.quantity for mov in Movement.query.filter(Movement.type == 'Salida').all()
                if item.name.lower() in mov.item_name.lower() and mov.timestamp.date() == today_date
            )
            logged_today = sum(
                log.quantity for log in controlled_logs
                if item.name.lower() in log.item_name.lower() and log.timestamp.date() == today_date
            )
            status = "Conciliado" if dispensed_today == logged_today else "Discrepancia"
            controlled_reconciliation.append({
                'item': item,
                'current_stock': current_stock,
                'dispensed_today': dispensed_today,
                'logged_today': logged_today,
                'status': status
            })

    movements = Movement.query.order_by(Movement.timestamp.desc()).all()
    is_admin = request.args.get("admin") == "true"

    return render_template_string(
        HTML_TEMPLATE,
        view=view,
        items=items,
        users=users,
        patients=patients,
        matutino_cargos=matutino_cargos,
        vespertino_cargos=vespertino_cargos,
        nocturno_a_cargos=nocturno_a_cargos,
        nocturno_b_cargos=nocturno_b_cargos,
        controlled_items=controlled_items,
        controlled_logs=controlled_logs,
        cleaning_logs=cleaning_logs,
        is_admin_controlled=is_admin_controlled,
        today_str=today_str,
        today_str_inv=today_iso,
        warning_str=warning_str,
        controlled_reconciliation=controlled_reconciliation,
        movements=movements,
        is_admin=is_admin
    )

@app.route("/add_cost_cargo_batch", methods=["POST"])
def add_cost_cargo_batch():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    user = User.query.get(user_id)

    if not user or user.pin != pin:
        flash("PIN o usuario incorrecto.", "error")
        return redirect(url_for("terminal", view="costos"))

    patient_name = request.form.get("patient_name", "").strip()
    room = request.form.get("room", "").strip()
    patient_id = request.form.get("patient_id", "").strip()
    shift = request.form.get("shift")
    cart_json = request.form.get("cart_costos_data", "[]")

    try:
        cart_items = json.loads(cart_json)
    except Exception:
        cart_items = []

    if not cart_items:
        flash("Debe agregar al menos un insumo al cargo.", "error")
        return redirect(url_for("terminal", view="costos"))

    if patient_name and not Patient.query.filter_by(name=patient_name).first():
        db.session.add(Patient(name=patient_name))

    for cart_item in cart_items:
        raw_search = cart_item.get("item_search", "").strip()
        item_search = raw_search.split(" (Lote:")[0].strip() if " (Lote:" in raw_search else raw_search
        warehouse = cart_item.get("warehouse", "Almacén General")
        quantity = int(cart_item.get("quantity", 1))

        item = Item.query.filter(Item.name.ilike(f"%{item_search}%")).first()
        if not item:
            continue

        if warehouse == "Quirófano":
            if item.stock_quirofano < quantity:
                flash(f"Stock insuficiente en Quirófano para '{item.name}' (Disponible: {item.stock_quirofano}).", "error")
                db.session.rollback()
                return redirect(url_for("terminal", view="costos"))
            item.stock_quirofano -= quantity
        else:
            if item.stock_general < quantity:
                flash(f"Stock insuficiente en Almacén General para '{item.name}' (Disponible: {item.stock_general}).", "error")
                db.session.rollback()
                return redirect(url_for("terminal", view="costos"))
            item.stock_general -= quantity

        mov = Movement(
            timestamp=get_local_now(),
            item_code=item.code,
            item_name=f"{item.name} (Lote: {item.lote or 'S/L'})",
            type="Salida (Costos)",
            quantity=quantity,
            warehouse=warehouse,
            user_name=user.name,
            patient_name=patient_name,
            patient_id=patient_id,
            room=room,
            shift=shift,
            is_cost_cargo=True
        )
        db.session.add(mov)

    db.session.commit()
    flash(f"Cargo múltiple registrado correctamente para {patient_name} en Turno {shift}.", "success")
    return redirect(url_for("terminal", view="costos"))

@app.route("/etiquetas")
def etiquetas():
    return redirect(url_for("terminal", view="etiquetas"))

@app.route("/save_patient_from_label", methods=["POST"])
def save_patient_from_label():
    patient_name = request.form.get("patient_name", "").strip()
    if patient_name:
        existing = Patient.query.filter_by(name=patient_name).first()
        if not existing:
            new_p = Patient(name=patient_name)
            db.session.add(new_p)
            db.session.commit()
            flash(f"Paciente '{patient_name}' guardado exitosamente en el catálogo.", "success")
        else:
            flash(f"El paciente '{patient_name}' ya se encontraba registrado.", "success")
    else:
        flash("Por favor ingrese un nombre de paciente válido.", "error")
    return redirect(url_for("terminal", view="etiquetas"))

@app.route("/register_batch", methods=["POST"])
def register_batch():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    patient_name = request.form.get("patient_name", "").strip() or "PACIENTE GENERAL"
    patient_fnac = request.form.get("patient_fnac", "").strip() or "S/F"
    patient_id = request.form.get("patient_id", "").strip() or "S/H"
    service = request.form.get("service", "").strip()
    notes = request.form.get("notes", "").strip()
    cart_json = request.form.get("cart_data", "[]")

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN o contraseña de usuario incorrecta.", "error")
        return redirect(url_for("terminal", view="terminal"))

    try:
        cart_items = json.loads(cart_json)
    except Exception:
        flash("Error al procesar la lista de medicamentos.", "error")
        return redirect(url_for("terminal", view="terminal"))

    if not cart_items or len(cart_items) == 0:
        flash("Debe agregar al menos un medicamento a la receta.", "error")
        return redirect(url_for("terminal", view="terminal"))

    if patient_name and patient_name != "PACIENTE GENERAL":
        existing_patient = Patient.query.filter_by(name=patient_name).first()
        if not existing_patient:
            new_p = Patient(name=patient_name)
            db.session.add(new_p)

    batch_labels = []

    for cart_item in cart_items:
        raw_search = cart_item.get("item_search", "").strip()
        item_search = raw_search.split(" (Lote:")[0].strip() if " (Lote:" in raw_search else raw_search
        
        via_admin = cart_item.get("via", "ORAL")
        mov_type = cart_item.get("type")
        warehouse = cart_item.get("warehouse")
        quantity = int(cart_item.get("quantity", 1))

        item = Item.query.filter(Item.name.ilike(f"%{item_search}%")).first()
        if not item:
            continue

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
                    return redirect(url_for("terminal", view="terminal"))
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
                return redirect(url_for("terminal", view="terminal"))
            item.stock_general -= quantity
            item.stock_quirofano += quantity

        mov = Movement(
            timestamp=get_local_now(),
            item_code=item.code,
            item_name=f"{item.name} (Lote: {item.lote or 'S/L'}) [Vía: {via_admin}]",
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
        
        batch_labels.append({
            "name": item.name,
            "via": via_admin,
            "quantity": quantity
        })

    db.session.commit()
    
    items = Item.query.order_by(Item.name, Item.lote).all()
    patients = Patient.query.order_by(Patient.name).all()
    users = User.query.order_by(User.name).all()
    current_time = datetime.now(LOCAL_TZ).strftime("%H:%M")

    return render_template_string(
        HTML_TEMPLATE,
        view="lote_etiquetas",
        batch_labels=batch_labels,
        patient_name=patient_name,
        fnac=patient_fnac,
        habitacion=patient_id,
        user_name=user.name,
        current_time=current_time,
        items_json=json.dumps(batch_labels),
        items=items,
        patients=patients,
        users=users
    )

@app.route("/update_item", methods=["POST"])
def update_item():
    admin_pin = request.form.get("admin_pin", "").strip()
    admin_user = User.query.filter_by(role="Administrador").first()

    if admin_pin not in ["5678", "1234"] and (not admin_user or admin_user.pin != admin_pin):
        flash("PIN de Administrador incorrecto. Modificación no autorizada.", "error")
        return redirect(url_for("terminal", view="inventario"))

    item_id = request.form.get("item_id")
    item = Item.query.get(item_id)
    if item:
        item.code = request.form.get("code", item.code).strip().upper()
        item.name = request.form.get("name", item.name).strip()
        item.category = request.form.get("category", item.category)
        item.via_administracion = request.form.get("via_administracion", item.via_administracion)
        item.presentacion = request.form.get("presentacion", item.presentacion)
        item.etiqueta = request.form.get("etiqueta", item.etiqueta)
        item.lote = request.form.get("lote", item.lote).strip()
        item.caducidad = request.form.get("caducidad", item.caducidad).strip()
        item.stock_general = int(request.form.get("stock_general", item.stock_general))
        item.stock_quirofano = int(request.form.get("stock_quirofano", item.stock_quirofano))
        
        db.session.commit()
        flash(f"Parámetros e inventario de '{item.name}' actualizados con éxito por el Administrador.", "success")
    
    return redirect(url_for("terminal", view="inventario"))

@app.route("/delete_item", methods=["POST"])
def delete_item():
    admin_pin = request.form.get("admin_pin", "").strip()
    admin_user = User.query.filter_by(role="Administrador").first()

    if admin_pin not in ["5678", "1234"] and (not admin_user or admin_user.pin != admin_pin):
        flash("PIN de Administrador incorrecto. Eliminación no autorizada.", "error")
        return redirect(url_for("terminal", view="inventario"))

    item_id = request.form.get("item_id")
    item = Item.query.get(item_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Insumo eliminado exitosamente del inventario.", "success")
    return redirect(url_for("terminal", view="inventario"))

@app.route("/add_cleaning", methods=["POST"])
def add_cleaning():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    dia_semana = request.form.get("dia_semana", "Lunes")
    turno = request.form.get("turno", "Matutino")
    anaqueles = 'anaqueles' in request.form
    pasillos = 'pasillos' in request.form
    desecho_carton = 'desecho_carton' in request.form
    refrigerador = 'refrigerador' in request.form
    cajas_traslado = 'cajas_traslado' in request.form
    acomodo_medicamento = 'acomodo_medicamento' in request.form
    notes = request.form.get("notes")

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN o usuario incorrecto.", "error")
        return redirect(url_for("terminal", view="limpieza"))

    log = CleaningLog(
        timestamp=get_local_now(),
        user_name=user.name,
        dia_semana=dia_semana,
        turno=turno,
        anaqueles=anaqueles,
        pasillos=pasillos,
        desecho_carton=desecho_carton,
        refrigerador=refrigerador,
        cajas_traslado=cajas_traslado,
        acomodo_medicamento=acomodo_medicamento,
        notes=notes
    )
    db.session.add(log)
    db.session.commit()
    flash("Verificación de limpieza guardada correctamente en el formato institucional.", "success")
    return redirect(url_for("terminal", view="limpieza"))

@app.route("/revert_movement", methods=["POST"])
def revert_movement():
    mov_id = request.form.get("movement_id")
    admin_pin = request.form.get("admin_pin", "").strip()

    admin_user = User.query.filter_by(role="Administrador").first()
    if admin_pin not in ["5678", "1234"] and (not admin_user or admin_user.pin != admin_pin):
        flash("PIN de Administrador incorrecto. Se requiere autorización.", "error")
        return redirect(url_for("terminal", view="bitacora"))

    mov = Movement.query.get(mov_id)
    if mov:
        clean_name = mov.item_name.split(" (Lote:")[0] if " (Lote:" in mov.item_name else mov.item_name
        item = Item.query.filter((Item.code == mov.item_code) | (Item.name == clean_name)).first()

        if item:
            if mov.type == "Salida" or mov.type == "Salida (Costos)":
                if mov.warehouse == "Almacén General":
                    item.stock_general += mov.quantity
                else:
                    item.stock_quirofano += mov.quantity
            elif mov.type == "Entrada":
                if mov.warehouse == "Almacén General":
                    item.stock_general -= mov.quantity
                else:
                    item.stock_quirofano -= mov.quantity

        db.session.delete(mov)
        db.session.commit()
        flash("Surtido revertido exitosamente y existencias devueltas.", "success")

    return redirect(url_for("terminal", view="bitacora"))

@app.route("/delete_movement", methods=["POST"])
def delete_movement():
    mov_id = request.form.get("movement_id")
    admin_pin = request.form.get("admin_pin", "").strip()

    admin_user = User.query.filter_by(role="Administrador").first()
    if admin_pin not in ["5678", "1234"] and (not admin_user or admin_user.pin != admin_pin):
        flash("PIN de Administrador incorrecto. Eliminación no autorizada.", "error")
        return redirect(url_for("terminal", view="bitacora"))

    mov = Movement.query.get(mov_id)
    if mov:
        db.session.delete(mov)
        db.session.commit()
        flash("Registro de bitácora eliminado correctamente.", "success")
    return redirect(url_for("terminal", view="bitacora"))

@app.route("/auth_admin_users", methods=["POST"])
def auth_admin_users():
    admin_pin = request.form.get("admin_pin", "").strip()
    admin_user = User.query.filter_by(role="Administrador").first()

    if admin_pin in ["5678", "1234"] or (admin_user and admin_user.pin == admin_pin):
        flash("Acceso concedido a la gestión de usuarios.", "success")
        return redirect(url_for("terminal", view="usuarios", admin="true"))
    else:
        flash("PIN de Administrador incorrecto.", "error")
        return redirect(url_for("terminal", view="usuarios"))

@app.route("/save_user", methods=["POST"])
def save_user():
    user_id = request.form.get("user_id")
    name = request.form.get("name", "").strip()
    role = request.form.get("role")
    pin = request.form.get("pin", "").strip()

    if user_id:
        u = User.query.get(user_id)
        if u:
            u.name = name
            u.role = role
            u.pin = pin
            flash(f"Usuario '{name}' actualizado correctamente.", "success")
    else:
        new_u = User(name=name, role=role, pin=pin)
        db.session.add(new_u)
        flash(f"Nuevo usuario '{name}' creado exitosamente.", "success")

    db.session.commit()
    return redirect(url_for("terminal", view="usuarios", admin="true"))

@app.route("/add_item", methods=["POST"])
def add_item():
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    via_administracion = request.form.get("via_administracion", "").strip()
    presentacion = request.form.get("presentacion", "").strip()
    category = request.form.get("category")
    lote = request.form.get("lote", "").strip()
    caducidad = request.form.get("caducidad", "").strip()
    etiqueta = request.form.get("etiqueta", "Ninguna")
    unit = request.form.get("unit", "pza").strip()
    stock_general = int(request.form.get("stock_general", 0))

    try:
        new_item = Item(
            code=code, 
            name=name,
            via_administracion=via_administracion,
            presentacion=presentacion,
            category=category, 
            lote=lote,
            caducidad=caducidad,
            etiqueta=etiqueta,
            unit=unit, 
            stock_general=stock_general, 
            stock_quirofano=0
        )
        db.session.add(new_item)
        db.session.commit()
        flash(f"Nuevo insumo '{name}' registrado exitosamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al registrar: {str(e)}", "error")

    return redirect(url_for("terminal", view="alta_insumos"))

@app.route("/auth_admin_controlled", methods=["POST"])
def auth_admin_controlled():
    admin_pin = request.form.get("admin_pin", "").strip()
    admin_user = User.query.filter_by(role="Administrador").first()

    if admin_pin in ["5678", "1234"] or (admin_user and admin_user.pin == admin_pin):
        flash("Acceso concedido al módulo de arqueo y conciliación diaria.", "success")
        return redirect(url_for("terminal", view="controlados", admin_arqueo="true"))
    else:
        flash("PIN de Administrador incorrecto.", "error")
        return redirect(url_for("terminal", view="controlados"))

@app.route("/add_controlled", methods=["POST"])
def add_controlled():
    raw_item_name = request.form.get("item_name", "").strip()
    item_name = raw_item_name.split(" (Lote:")[0].strip() if " (Lote:" in raw_item_name else raw_item_name
    
    patient_name = request.form.get("patient_name", "").strip()
    prescription_num = request.form.get("prescription_num", "").strip()
    quantity = int(request.form.get("quantity", 1))
    doctor_name = request.form.get("doctor_name", "").strip()
    user_id = request.form.get("user_id")
    pin = request.form.get("pin", "").strip()

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN de seguridad incorrecto.", "error")
        return redirect(url_for("terminal", view="controlados"))

    item = Item.query.filter(Item.name.ilike(f"%{item_name}%"), Item.etiqueta == "Controlado").first()
    if item:
        if item.stock_general >= quantity:
            item.stock_general -= quantity
        elif item.stock_quirofano >= quantity:
            item.stock_quirofano -= quantity
        else:
            flash(f"Stock insuficiente para el medicamento controlado '{item.name}'.", "error")
            return redirect(url_for("terminal", view="controlados"))

    if patient_name:
        existing_patient = Patient.query.filter_by(name=patient_name).first()
        if not existing_patient:
            new_p = Patient(name=patient_name)
            db.session.add(new_p)

    new_log = ControlledLog(
        timestamp=get_local_now(),
        item_name=raw_item_name,
        patient_name=patient_name,
        prescription_num=prescription_num,
        quantity=quantity,
        doctor_name=doctor_name,
        user_name=user.name
    )
    db.session.add(new_log)
    db.session.commit()

    flash(f"Salida controlada de '{raw_item_name}' registrada, inventario descontado y bitácora actualizada.", "success")
    return redirect(url_for("terminal", view="controlados"))

@app.route("/delete_controlled", methods=["POST"])
def delete_controlled():
    log_id = request.form.get("log_id")
    admin_pin = request.form.get("admin_pin", "").strip()

    admin_user = User.query.filter_by(role="Administrador").first()
    if admin_pin not in ["5678", "1234"] and (not admin_user or admin_user.pin != admin_pin):
        flash("PIN de Administrador incorrecto. Eliminación no autorizada.", "error")
        return redirect(url_for("terminal", view="controlados"))

    log_item = ControlledLog.query.get(log_id)
    if log_item:
        db.session.delete(log_item)
        db.session.commit()
        flash("Registro controlado eliminado correctamente de la bitácora.", "success")
    return redirect(url_for("terminal", view="controlados"))

# -----------------------------------------------------------------------------
# INICIALIZACIÓN DE BASE DE DATOS Y AUTO-MIGRACIÓN
# -----------------------------------------------------------------------------

def seed_database():
    with app.app_context():
        db.create_all()
        
        # Bloque automático de seguridad para añadir columnas faltantes en PostgreSQL / SQLite
        try:
            db.session.execute(db.text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS room VARCHAR(50);"))
            db.session.execute(db.text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS shift VARCHAR(50);"))
            db.session.execute(db.text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS is_cost_cargo BOOLEAN DEFAULT FALSE;"))
            db.session.execute(db.text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS item_code VARCHAR(50);"))
            
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS dia_semana VARCHAR(20);"))
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS turno VARCHAR(20);"))
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS pasillos BOOLEAN DEFAULT FALSE;"))
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS desecho_carton BOOLEAN DEFAULT FALSE;"))
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS refrigerador BOOLEAN DEFAULT FALSE;"))
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS cajas_traslado BOOLEAN DEFAULT FALSE;"))
            db.session.execute(db.text("ALTER TABLE cleaning_log ADD COLUMN IF NOT EXISTS acomodo_medicamento BOOLEAN DEFAULT FALSE;"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Nota de actualización de esquema:", e)

        if User.query.count() == 0:
            users_list = [
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678"),
                User(name="Alfonso Salvador Guzman Reyes", role="Farmacéutico", pin="1234"),
                User(name="Dra. Sofia Ramos", role="Farmacéutico", pin="4321"),
                User(name="Hannia Martinez Salas", role="Enfermería Quirófano", pin="1122")
            ]
            db.session.add_all(users_list)

        if Item.query.count() == 0:
            items_list = [
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", via_administracion="Oral", presentacion="Tableta", lote="LOT-9821", caducidad="2027-12-31", etiqueta="Ninguna", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-4410", caducidad="2027-08-15", etiqueta="Medicamento de alto Riesgo(MAR)", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-1102", caducidad="2026-11-20", etiqueta="Controlado", stock_general=30, stock_quirofano=10)
            ]
            db.session.add_all(items_list)

        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
