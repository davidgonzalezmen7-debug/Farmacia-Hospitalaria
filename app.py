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
    dia_semana = db.Column(db.String(20), nullable=True)
    turno = db.Column(db.String(20), nullable=True)
    anaqueles = db.Column(db.Boolean, default=False)
    pasillos = db.Column(db.Boolean, default=False)
    desecho_carton = db.Column(db.Boolean, default=False)
    refrigerador = db.Column(db.Boolean, default=False)
    cajas_traslado = db.Column(db.Boolean, default=False)
    acomodo_medicamento = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(350), nullable=True)

class WeeklyCleaningSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semana_inicio = db.Column(db.String(20), nullable=False)
    dia_semana = db.Column(db.String(20), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    actividad = db.Column(db.String(100), nullable=False)
    completado = db.Column(db.Boolean, default=False)

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
            @page { size: portrait; margin: 10mm; }
            body, html { width: 100% !important; background-color: white !important; }
            header, nav, .no-print, button, form { display: none !important; }
            .print-container { display: block !important; width: 100% !important; margin: 0 !important; padding: 0 !important; }
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
                    <i class="fa-solid fa-prescription-bottle-medical"></i> Surtido
                </a>
                <a href="/terminal?view=costos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'costos' %}bg-emerald-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-emerald-100{% endif %}">
                    <i class="fa-solid fa-file-invoice-dollar"></i> Costos
                </a>
                <a href="/terminal?view=etiquetas" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'etiquetas' %}bg-purple-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-purple-100{% endif %}">
                    <i class="fa-solid fa-tags"></i> Etiquetas
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
                    <i class="fa-solid fa-broom"></i> Check-list
                </a>
                <a href="/terminal?view=rol_semanal" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'rol_semanal' %}bg-cyan-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-cyan-100{% endif %}">
                    <i class="fa-solid fa-calendar-days"></i> Rol Semanal
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
        <!-- ==================== PESTAÑA: CARGO DE MATERIAL PARA COSTOS ==================== -->
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
                                    <tr><td colspan="4" class="p-6 text-center text-slate-400 italic">No hay insumos agregados al cargo.</td></tr>
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

            <!-- Tablas de turnos de costos -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Matutino -->
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-amber-200">
                    <h3 class="text-sm font-bold text-amber-800 flex items-center justify-between border-b pb-3 mb-3">
                        <span><i class="fa-solid fa-sun text-amber-500 mr-2"></i> Matutino</span>
                        <a href="/imprimir_turno_pdf?shift=Matutino" target="_blank" class="px-2.5 py-1 bg-amber-600 text-white rounded-lg text-[11px] font-bold shadow"><i class="fa-solid fa-print"></i> Imprimir</a>
                    </h3>
                    <div class="overflow-x-auto max-h-72">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-amber-50 text-amber-900 sticky top-0">
                                <tr><th class="p-2">Paciente</th><th class="p-2">Hab.</th><th class="p-2">Insumo</th><th class="p-2 text-center">Cant.</th></tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for c in matutino_cargos %}
                                <tr class="hover:bg-slate-50"><td class="p-2 font-medium">{{ c.patient_name }}</td><td class="p-2">{{ c.room }}</td><td class="p-2">{{ c.item_name }}</td><td class="p-2 text-center font-bold text-emerald-600">{{ c.quantity }}</td></tr>
                                {% else %}
                                <tr><td colspan="4" class="p-4 text-center text-slate-400 text-xs">Sin cargos.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
                <!-- Vespertino -->
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-orange-200">
                    <h3 class="text-sm font-bold text-orange-800 flex items-center justify-between border-b pb-3 mb-3">
                        <span><i class="fa-solid fa-cloud-sun text-orange-500 mr-2"></i> Vespertino</span>
                        <a href="/imprimir_turno_pdf?shift=Vespertino" target="_blank" class="px-2.5 py-1 bg-orange-600 text-white rounded-lg text-[11px] font-bold shadow"><i class="fa-solid fa-print"></i> Imprimir</a>
                    </h3>
                    <div class="overflow-x-auto max-h-72">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-orange-50 text-orange-900 sticky top-0">
                                <tr><th class="p-2">Paciente</th><th class="p-2">Hab.</th><th class="p-2">Insumo</th><th class="p-2 text-center">Cant.</th></tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for c in vespertino_cargos %}
                                <tr class="hover:bg-slate-50"><td class="p-2 font-medium">{{ c.patient_name }}</td><td class="p-2">{{ c.room }}</td><td class="p-2">{{ c.item_name }}</td><td class="p-2 text-center font-bold text-emerald-600">{{ c.quantity }}</td></tr>
                                {% else %}
                                <tr><td colspan="4" class="p-4 text-center text-slate-400 text-xs">Sin cargos.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        {% elif view == 'terminal' %}
        <!-- ==================== PESTAÑA: SURTIDO MÚLTIPLE ==================== -->
        <div class="space-y-6 max-w-5xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="mb-4">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2"><i class="fa-solid fa-users text-blue-600"></i> Personal Responsable</h2>
                    <p class="text-xs text-slate-500">Haga clic sobre su nombre para seleccionarlo.</p>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                    {% for u in users %}
                    <button type="button" onclick="selectUser('{{ u.id }}', '{{ u.name }}')" class="p-3 rounded-xl border border-slate-200 bg-slate-50 hover:bg-blue-50 transition text-center flex flex-col items-center">
                        <div class="w-9 h-9 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm mb-1.5"><i class="fa-solid fa-user-doctor"></i></div>
                        <h4 class="font-bold text-slate-800 text-xs truncate w-full">{{ u.name }}</h4>
                        <span class="text-[10px] text-slate-500">{{ u.role }}</span>
                    </button>
                    {% endfor %}
                </div>
            </div>

            <form action="/register_batch" method="POST" onsubmit="return validateBatchForm()" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-6">
                <input type="hidden" name="cart_data" id="cart_data_input">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Usuario Responsable</label>
                        <select name="user_id" id="userSelect" required onchange="updateSelectedUserName()" class="w-full p-2.5 border rounded-xl text-sm bg-white">
                            <option value="">Seleccione Usuario...</option>
                            {% for u in users %}
                                <option value="{{ u.id }}" data-name="{{ u.name }}">{{ u.name }} ({{ u.role }})</option>
                            {% endfor %}
                        </select>
                        <input type="hidden" name="user_name_hidden" id="user_name_hidden">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">PIN / Contraseña</label>
                        <input type="password" name="pin" required placeholder="PIN de Seguridad" class="w-full p-2.5 border rounded-xl text-sm bg-white">
                    </div>
                </div>

                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                    <h3 class="text-xs font-bold text-blue-900 uppercase flex items-center gap-1.5"><i class="fa-solid fa-bed-pulse"></i> Información del Paciente</h3>
                    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                        <input type="text" list="patients_datalist" name="patient_name" id="patient_name" placeholder="Nombre Paciente" class="w-full p-2 border rounded-lg text-xs bg-white">
                        <input type="text" name="patient_fnac" placeholder="F. Nacimiento" class="w-full p-2 border rounded-lg text-xs bg-white">
                        <input type="text" name="patient_id" placeholder="Habitación / Cama" class="w-full p-2 border rounded-lg text-xs bg-white">
                        <input type="text" name="service" placeholder="Servicio" class="w-full p-2 border rounded-lg text-xs bg-white">
                    </div>
                </div>

                <div class="p-4 bg-indigo-50/40 rounded-xl border border-indigo-100 space-y-3">
                    <h3 class="text-xs font-bold text-indigo-900 uppercase flex items-center gap-1.5"><i class="fa-solid fa-plus-circle"></i> Agregar Medicamentos</h3>
                    <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                        <input list="items_list" id="temp_item" placeholder="Buscar medicamento..." class="md:col-span-4 p-2 border rounded-lg text-xs bg-white">
                        <input type="text" id="temp_via" placeholder="Vía (Ej. ORAL)" class="md:col-span-2 p-2 border rounded-lg text-xs bg-white uppercase font-bold">
                        <select id="temp_type" class="md:col-span-2 p-2 border rounded-lg text-xs bg-white">
                            <option value="Salida">Salida</option>
                            <option value="Traspaso Qx">Traspaso Qx</option>
                            <option value="Entrada">Entrada</option>
                        </select>
                        <select id="temp_warehouse" class="md:col-span-1 p-2 border rounded-lg text-xs bg-white">
                            <option value="Almacén General">General</option>
                            <option value="Quirófano">Quirófano</option>
                        </select>
                        <input type="number" min="1" id="temp_quantity" value="1" class="md:col-span-1 p-2 border rounded-lg text-xs bg-white text-center font-bold">
                        <button type="button" onclick="addToCart()" class="md:col-span-2 bg-indigo-600 text-white font-bold py-2 rounded-lg text-xs flex items-center justify-center gap-1"><i class="fa-solid fa-cart-plus"></i> Agregar</button>
                    </div>
                </div>

                <div class="overflow-x-auto border rounded-xl">
                    <table class="w-full text-xs text-left text-slate-600">
                        <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                            <tr><th class="p-2.5">Medicamento</th><th class="p-2.5">Vía</th><th class="p-2.5">Tipo</th><th class="p-2.5 text-center">Cant.</th><th class="p-2.5 text-center">Acción</th></tr>
                        </thead>
                        <tbody id="cartTableBody" class="divide-y divide-slate-100">
                            <tr><td colspan="5" class="p-6 text-center text-slate-400 italic">No hay medicamentos en la lista.</td></tr>
                        </tbody>
                    </table>
                </div>

                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl shadow-md transition flex items-center justify-center gap-2 text-sm">
                    <i class="fa-solid fa-check-double"></i> Procesar Surtido Completo y Generar Etiquetas
                </button>
            </form>
        </div>

        {% elif view == 'rol_semanal' %}
        <!-- ==================== PESTAÑA: ROL SEMANAL DE LIMPIEZA ==================== -->
        <div class="space-y-6">
            <div class="bg-gradient-to-r from-cyan-900 to-slate-900 text-white p-6 rounded-2xl shadow-md border border-cyan-800">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                            <span class="bg-white/20 text-white text-[10px] font-mono px-2 py-0.5 rounded font-bold">ROL ROTATIVO</span>
                            <span class="text-xs text-cyan-300 font-bold">HOSPITAL OBREGÓN</span>
                        </div>
                        <h2 class="text-base font-bold flex items-center gap-2">
                            <i class="fa-solid fa-calendar-days text-cyan-400"></i> Rol Semanal de Limpieza y Orden
                        </h2>
                        <p class="text-xs text-cyan-200">Asignación semanal rotativa: Una actividad por día (Anaqueles, Refrigerador, Desecho de cartón, Pasillos, Cajas de traslado y Acomodo de medicamentos) para todo el personal.</p>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Formulario para asignar o autogenerar rol semanal -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1 space-y-4">
                    <h3 class="text-base font-bold text-slate-900 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-plus-circle text-cyan-600"></i> Configurar Rol Semanal
                    </h3>
                    
                    <form action="/generate_weekly_schedule" method="POST" class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Semana que inicia (Lunes)</label>
                            <input type="date" name="semana_inicio" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 outline-none">
                        </div>
                        <button type="submit" class="w-full bg-cyan-600 hover:bg-cyan-700 text-white font-bold py-3 rounded-xl shadow-md transition flex items-center justify-center gap-2 text-xs">
                            <i class="fa-solid fa-rotate"></i> Autogenerar / Asignar Rotación Semanal
                        </button>
                    </form>

                    <div class="border-t pt-3">
                        <h4 class="text-xs font-bold text-slate-700 uppercase mb-2">Actividades Consideradas:</h4>
                        <ul class="text-[11px] text-slate-600 space-y-1 list-disc pl-4 font-medium">
                            <li>Anaqueles</li>
                            <li>Refrigerador</li>
                            <li>Desecho de cartón</li>
                            <li>Pasillos</li>
                            <li>Cajas de traslado</li>
                            <li>Acomodo de medicamentos</li>
                        </ul>
                    </div>
                </div>

                <!-- Tabla del Rol Semanal Activo -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2 space-y-4">
                    <div class="flex justify-between items-center border-b pb-3">
                        <div>
                            <h3 class="text-base font-bold text-slate-900 flex items-center gap-2">
                                <i class="fa-solid fa-table text-cyan-600"></i> Calendario de Actividades por Día
                            </h3>
                            <p class="text-[11px] text-slate-500">Rotación activa para el personal de farmacia y limpieza</p>
                        </div>
                        <button onclick="window.print()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold no-print">
                            <i class="fa-solid fa-print"></i> Imprimir Rol
                        </button>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left text-slate-700 border border-slate-300">
                            <thead class="bg-cyan-50 text-cyan-900 uppercase text-[10px] border-b border-slate-300">
                                <tr>
                                    <th class="p-2.5 border-r border-slate-300">Día de la Semana</th>
                                    <th class="p-2.5 border-r border-slate-300">Actividad Asignada</th>
                                    <th class="p-2.5 border-r border-slate-300">Responsable</th>
                                    <th class="p-2.5 text-center">Estado</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-200">
                                {% for sch in weekly_schedules %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2.5 border-r border-slate-200 font-bold text-cyan-900">{{ sch.dia_semana }}</td>
                                    <td class="p-2.5 border-r border-slate-200 font-semibold text-slate-800"><i class="fa-solid fa-check text-cyan-600 mr-1"></i> {{ sch.actividad }}</td>
                                    <td class="p-2.5 border-r border-slate-200 font-bold text-slate-900">{{ sch.user_name }}</td>
                                    <td class="p-2.5 text-center">
                                        {% if sch.completado %}
                                            <span class="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full font-bold text-[10px]">Completado</span>
                                        {% else %}
                                            <form action="/toggle_weekly_schedule" method="POST" class="inline">
                                                <input type="hidden" name="schedule_id" value="{{ sch.id }}">
                                                <button type="submit" class="bg-slate-100 hover:bg-emerald-100 text-slate-700 hover:text-emerald-800 px-2.5 py-1 rounded-lg font-bold transition text-[10px]">Pendiente (Marcar)</button>
                                            </form>
                                        {% endif %}
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="4" class="p-6 text-center text-slate-400 italic">
                                        No hay rol semanal generado. Haga clic en "Autogenerar / Asignar Rotación Semanal".
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        {% elif view == 'limpieza' %}
        <!-- ==================== PESTAÑA: CHECK-LIST LIMPIEZA ==================== -->
        <div class="space-y-6">
            <div class="bg-gradient-to-r from-teal-900 to-slate-900 text-white p-6 rounded-2xl shadow-md border border-teal-800">
                <h2 class="text-base font-bold flex items-center gap-2"><i class="fa-solid fa-clipboard-check text-teal-400"></i> Check List Limpieza Farmacia (FAR-FTO-19-01)</h2>
                <p class="text-xs text-teal-200">Verificación diaria de áreas limpias.</p>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <form action="/add_cleaning" method="POST" class="space-y-3">
                        <div class="grid grid-cols-2 gap-2">
                            <select name="dia_semana" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 font-bold">
                                <option value="Lunes">Lunes</option><option value="Martes">Martes</option><option value="Miércoles">Miércoles</option><option value="Jueves">Jueves</option><option value="Viernes">Viernes</option><option value="Sábado">Sábado</option><option value="Domingo">Domingo</option>
                            </select>
                            <select name="turno" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 font-bold">
                                <option value="Matutino">Matutino</option><option value="Vespertino">Vespertino</option><option value="Nocturno">Nocturno</option>
                            </select>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <select name="user_id" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50">
                                <option value="">Responsable...</option>
                                {% for u in users %}<option value="{{ u.id }}">{{ u.name }}</option>{% endfor %}
                            </select>
                            <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-xs">
                        </div>
                        <div class="bg-teal-50/60 p-4 rounded-xl border border-teal-100 space-y-2">
                            <label class="flex items-center gap-2 text-xs"><input type="checkbox" name="anaqueles"> Anaqueles</label>
                            <label class="flex items-center gap-2 text-xs"><input type="checkbox" name="pasillos"> Pasillos</label>
                            <label class="flex items-center gap-2 text-xs"><input type="checkbox" name="desecho_carton"> Desecho de cartón</label>
                            <label class="flex items-center gap-2 text-xs"><input type="checkbox" name="refrigerador"> Refrigerador</label>
                            <label class="flex items-center gap-2 text-xs"><input type="checkbox" name="cajas_traslado"> Cajas de traslado</label>
                            <label class="flex items-center gap-2 text-xs"><input type="checkbox" name="acomodo_medicamento"> Acomodo de medicamento</label>
                        </div>
                        <textarea name="notes" rows="2" placeholder="Observaciones..." class="w-full p-2 border rounded-xl text-xs bg-slate-50"></textarea>
                        <button type="submit" class="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-3 rounded-xl transition text-xs">Registrar Verificación</button>
                    </form>
                </div>
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2 overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-700 border border-slate-300">
                        <thead class="bg-teal-50 text-teal-900 uppercase text-[10px]">
                            <tr><th class="p-2 border">Día/Turno</th><th class="p-2 text-center border">Anaqueles</th><th class="p-2 text-center border">Pasillos</th><th class="p-2 text-center border">Cartón</th><th class="p-2 text-center border">Refrig.</th><th class="p-2 text-center border">Cajas</th><th class="p-2 text-center border">Acomodo</th><th class="p-2 border">Resp.</th></tr>
                        </thead>
                        <tbody class="divide-y divide-slate-200">
                            {% for log in cleaning_logs %}
                            <tr>
                                <td class="p-2 border font-bold">{{ log.dia_semana }} ({{ log.turno }})</td>
                                <td class="p-2 text-center border">{% if log.anaqueles %}✓{% else %}-{% endif %}</td>
                                <td class="p-2 text-center border">{% if log.pasillos %}✓{% else %}-{% endif %}</td>
                                <td class="p-2 text-center border">{% if log.desecho_carton %}✓{% else %}-{% endif %}</td>
                                <td class="p-2 text-center border">{% if log.refrigerador %}✓{% else %}-{% endif %}</td>
                                <td class="p-2 text-center border">{% if log.cajas_traslado %}✓{% else %}-{% endif %}</td>
                                <td class="p-2 text-center border">{% if log.acomodo_medicamento %}✓{% else %}-{% endif %}</td>
                                <td class="p-2 border font-bold">{{ log.user_name }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="8" class="p-6 text-center text-slate-400 italic">Sin registros de limpieza.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        {% elif view == 'inventario' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <h2 class="text-lg font-bold text-slate-900 mb-4"><i class="fa-solid fa-boxes-stacked text-blue-600"></i> Inventario</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left text-slate-600">
                    <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                        <tr><th class="p-3">Código</th><th class="p-3">Descripción</th><th class="p-3">Categoría</th><th class="p-3 text-center">General</th><th class="p-3 text-center">Quirófano</th></tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {% for item in items %}
                        <tr class="hover:bg-slate-50">
                            <td class="p-3 font-mono text-xs font-bold">{{ item.code }}</td>
                            <td class="p-3 font-bold text-slate-900">{{ item.name }}</td>
                            <td class="p-3">{{ item.category }}</td>
                            <td class="p-3 text-center font-bold text-emerald-800">{{ item.stock_general }}</td>
                            <td class="p-3 text-center font-bold text-blue-800">{{ item.stock_quirofano }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        {% elif view == 'bitacora' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <h2 class="text-lg font-bold text-slate-900 mb-4"><i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora de Movimientos</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-xs text-left text-slate-600">
                    <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                        <tr><th class="p-3">Fecha/Hora</th><th class="p-3">Tipo</th><th class="p-3">Medicamento</th><th class="p-3 text-center">Cant.</th><th class="p-3">Paciente</th><th class="p-3">Responsable</th></tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {% for mov in movements %}
                        <tr>
                            <td class="p-3 font-mono text-slate-500">{{ mov.timestamp.strftime('%d/%m/%Y %H:%M') }}</td>
                            <td class="p-3 font-bold uppercase">{{ mov.type }}</td>
                            <td class="p-3 font-bold text-slate-900">{{ mov.item_name }}</td>
                            <td class="p-3 text-center font-bold">{{ mov.quantity }}</td>
                            <td class="p-3">{{ mov.patient_name or '-' }}</td>
                            <td class="p-3 text-indigo-900 font-bold">{{ mov.user_name }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        {% elif view == 'usuarios' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 max-w-xl mx-auto">
            <h2 class="text-base font-bold text-slate-900 mb-4"><i class="fa-solid fa-users-gear text-blue-600"></i> Personal Registrado</h2>
            <div class="space-y-3">
                {% for u in users %}
                <div class="p-3 rounded-xl border bg-slate-50 flex justify-between items-center text-xs">
                    <div><strong class="text-slate-900">{{ u.name }}</strong> <span class="text-slate-500">({{ u.role }})</span></div>
                    <span class="font-mono text-blue-600 font-bold">PIN: ••••</span>
                </div>
                {% endfor %}
            </div>
        </div>

        {% elif view == 'alta_insumos' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 max-w-xl mx-auto">
            <h2 class="text-base font-bold text-slate-900 mb-4"><i class="fa-solid fa-plus-circle text-emerald-600"></i> Registrar Insumo</h2>
            <form action="/add_item" method="POST" class="space-y-3 text-xs">
                <input type="text" name="code" required placeholder="Código" class="w-full p-2.5 border rounded-xl">
                <input type="text" name="name" required placeholder="Nombre / Descripción" class="w-full p-2.5 border rounded-xl">
                <select name="category" required class="w-full p-2.5 border rounded-xl bg-slate-50">
                    <option value="Medicamento">Medicamento</option><option value="Material Curación">Material Curación</option>
                </select>
                <input type="number" min="0" name="stock_general" required value="50" placeholder="Stock Inicial" class="w-full p-2.5 border rounded-xl font-bold">
                <button type="submit" class="w-full bg-emerald-600 text-white font-bold py-3 rounded-xl shadow">Registrar</button>
            </form>
        </div>

        {% elif view == 'controlados' %}
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 max-w-2xl mx-auto">
            <h2 class="text-base font-bold text-slate-900 mb-4"><i class="fa-solid fa-capsules text-rose-600"></i> Surtir Controlado</h2>
            <form action="/add_controlled" method="POST" class="space-y-3 text-xs">
                <input list="controlled_items_list" name="item_name" required placeholder="Medicamento Controlado..." class="w-full p-2.5 border rounded-xl font-bold">
                <datalist id="controlled_items_list">
                    {% for item in controlled_items %}<option value="{{ item.name }} (Lote: {{ item.lote or 'S/L' }})">{% endfor %}
                </datalist>
                <input type="text" name="patient_name" required placeholder="Paciente" class="w-full p-2.5 border rounded-xl">
                <input type="text" name="prescription_num" required placeholder="No. Receta" class="w-full p-2.5 border rounded-xl">
                <input type="number" min="1" value="1" name="quantity" required class="w-full p-2.5 border rounded-xl">
                <select name="user_id" required class="w-full p-2.5 border rounded-xl bg-slate-50">
                    <option value="">Responsable...</option>{% for u in users %}<option value="{{ u.id }}">{{ u.name }}</option>{% endfor %}
                </select>
                <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl">
                <button type="submit" class="w-full bg-rose-600 text-white font-bold py-3 rounded-xl shadow">Registrar Salida Controlada</button>
            </form>
        </div>
        {% endif %}
    </main>

    <script>
        let cart = [];
        let costosCart = [];
        function selectUser(id, name) { document.getElementById('userSelect').value = id; document.getElementById('user_name_hidden').value = name; }
        function updateSelectedUserName() {
            var select = document.getElementById('userSelect');
            document.getElementById('user_name_hidden').value = select.options[select.selectedIndex].getAttribute('data-name') || '';
        }
        function addToCart() {
            const item = document.getElementById('temp_item').value.trim();
            const via = document.getElementById('temp_via').value.trim() || 'ORAL';
            const type = document.getElementById('temp_type').value;
            const wh = document.getElementById('temp_warehouse').value;
            const qty = parseInt(document.getElementById('temp_quantity').value) || 1;
            if (!item) { alert('Seleccione medicamento.'); return; }
            cart.push({item_search: item, via, type, warehouse: wh, quantity: qty});
            document.getElementById('temp_item').value = '';
            renderCart();
        }
        function renderCart() {
            const tbody = document.getElementById('cartTableBody');
            if (cart.length === 0) { tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-slate-400 italic">No hay medicamentos.</td></tr>`; return; }
            let html = '';
            cart.forEach((i, idx) => {
                html += `<tr class="hover:bg-slate-50"><td class="p-2.5 font-bold">${i.item_search}</td><td class="p-2.5 uppercase">${i.via}</td><td class="p-2.5">${i.type}</td><td class="p-2.5 text-center font-bold">${i.quantity}</td><td class="p-2.5 text-center"><button type="button" onclick="cart.splice(${idx},1);renderCart()" class="text-rose-600 font-bold">X</button></td></tr>`;
            });
            tbody.innerHTML = html;
        }
        function validateBatchForm() {
            if (cart.length === 0) { alert('Agregue al menos un medicamento.'); return false; }
            document.getElementById('cart_data_input').value = JSON.stringify(cart);
            return true;
        }
        function addCostosCartItem() {
            const item = document.getElementById('costos_temp_item').value.trim();
            const wh = document.getElementById('costos_temp_warehouse').value;
            const qty = parseInt(document.getElementById('costos_temp_qty').value) || 1;
            if (!item) { alert('Seleccione insumo.'); return; }
            costosCart.push({item_search: item, warehouse: wh, quantity: qty});
            document.getElementById('costos_temp_item').value = '';
            renderCostosCart();
        }
        function renderCostosCart() {
            const tbody = document.getElementById('costosCartTableBody');
            if (costosCart.length === 0) { tbody.innerHTML = `<tr><td colspan="4" class="p-6 text-center text-slate-400 italic">No hay insumos.</td></tr>`; return; }
            let html = '';
            costosCart.forEach((i, idx) => {
                html += `<tr class="hover:bg-slate-50"><td class="p-2.5 font-bold">${i.item_search}</td><td class="p-2.5">${i.warehouse}</td><td class="p-2.5 text-center font-bold text-emerald-700">${i.quantity}</td><td class="p-2.5 text-center"><button type="button" onclick="costosCart.splice(${idx},1);renderCostosCart()" class="text-rose-600 font-bold">X</button></td></tr>`;
            });
            tbody.innerHTML = html;
        }
        function validateCostosBatch() {
            if (costosCart.length === 0) { alert('Agregue al menos un insumo.'); return false; }
            document.getElementById('cart_costos_data_input').value = JSON.stringify(costosCart);
            return true;
        }
    </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# RUTAS DE REPORTES Y ROL SEMANAL
# -----------------------------------------------------------------------------

@app.route("/imprimir_turno_pdf")
def imprimir_turno_pdf():
    shift = request.args.get("shift", "Matutino").strip()
    cargos = Movement.query.filter_by(is_cost_cargo=True, shift=shift).order_by(Movement.timestamp.desc()).all()
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, height - 20 * mm, "HOSPITAL OBREGÓN - FARMACIA HOSPITALARIA")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, height - 26 * mm, f"REPORTE DE CARGOS A COSTOS - TURNO: {shift.upper()}")
    
    y = height - 40 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "Paciente / Expediente")
    c.drawString(70 * mm, y, "Habitación")
    c.drawString(95 * mm, y, "Insumo / Material")
    c.drawString(160 * mm, y, "Cant.")
    
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for cgo in cargos:
        if y < 25 * mm:
            c.showPage()
            y = height - 25 * mm
        c.drawString(20 * mm, y, f"{cgo.patient_name} (Exp: {cgo.patient_id})"[:32])
        c.drawString(70 * mm, y, str(cgo.room or "-")[:15])
        c.drawString(95 * mm, y, str(cgo.item_name)[:35])
        c.drawRightString(168 * mm, y, str(cgo.quantity))
        y -= 7 * mm

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=False, mimetype="application/pdf", download_name=f"reporte_cargos_{shift.lower()}.pdf")

@app.route("/")
def index():
    return redirect(url_for("terminal", view="costos"))

@app.route("/terminal")
def terminal():
    view = request.args.get("view", "costos")
    items = Item.query.order_by(Item.name, Item.lote).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()

    matutino_cargos = Movement.query.filter_by(is_cost_cargo=True, shift="Matutino").order_by(Movement.timestamp.desc()).all()
    vespertino_cargos = Movement.query.filter_by(is_cost_cargo=True, shift="Vespertino").order_by(Movement.timestamp.desc()).all()
    
    controlled_items = Item.query.filter_by(etiqueta="Controlado").order_by(Item.name).all()
    cleaning_logs = CleaningLog.query.order_by(CleaningLog.timestamp.desc()).all()
    weekly_schedules = WeeklyCleaningSchedule.query.order_by(WeeklyCleaningSchedule.id).all()
    movements = Movement.query.order_by(Movement.timestamp.desc()).all()

    return render_template_string(
        HTML_TEMPLATE,
        view=view,
        items=items,
        users=users,
        patients=patients,
        matutino_cargos=matutino_cargos,
        vespertino_cargos=vespertino_cargos,
        controlled_items=controlled_items,
        cleaning_logs=cleaning_logs,
        weekly_schedules=weekly_schedules,
        movements=movements
    )

@app.route("/generate_weekly_schedule", methods=["POST"])
def generate_weekly_schedule():
    semana_inicio = request.form.get("semana_inicio", str(date.today()))
    
    WeeklyCleaningSchedule.query.delete()
    
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    actividades = [
        "Anaqueles",
        "Refrigerador",
        "Desecho de cartón",
        "Pasillos",
        "Cajas de traslado",
        "Acomodo de medicamentos"
    ]
    
    users = User.query.all()
    user_names = [u.name for u in users] if users else ["Personal General"]
    
    for idx, dia in enumerate(dias):
        actividad = actividades[idx % len(actividades)]
        user_name = user_names[idx % len(user_names)]
        
        sch = WeeklyCleaningSchedule(
            semana_inicio=semana_inicio,
            dia_semana=dia,
            user_name=user_name,
            actividad=actividad,
            completado=False
        )
        db.session.add(sch)
    
    db.session.commit()
    flash("Rol semanal de limpieza generado y rotado exitosamente.", "success")
    return redirect(url_for("terminal", view="rol_semanal"))

@app.route("/toggle_weekly_schedule", methods=["POST"])
def toggle_weekly_schedule():
    schedule_id = request.form.get("schedule_id")
    sch = WeeklyCleaningSchedule.query.get(schedule_id)
    if sch:
        sch.completado = not sch.completado
        db.session.commit()
        flash(f"Estado de la actividad '{sch.actividad}' actualizado.", "success")
    return redirect(url_for("terminal", view="rol_semanal"))

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
                flash(f"Stock insuficiente en Quirófano para '{item.name}'.", "error")
                db.session.rollback()
                return redirect(url_for("terminal", view="costos"))
            item.stock_quirofano -= quantity
        else:
            if item.stock_general < quantity:
                flash(f"Stock insuficiente en Almacén General para '{item.name}'.", "error")
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
    flash(f"Cargo múltiple registrado correctamente para {patient_name}.", "success")
    return redirect(url_for("terminal", view="costos"))

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
        flash("PIN incorrecto.", "error")
        return redirect(url_for("terminal", view="terminal"))

    try:
        cart_items = json.loads(cart_json)
    except Exception:
        cart_items = []

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

        if mov_type == "Salida":
            if warehouse == "Almacén General":
                item.stock_general -= quantity
            else:
                item.stock_quirofano -= quantity

        mov = Movement(
            timestamp=get_local_now(),
            item_code=item.code,
            item_name=f"{item.name} [Vía: {via_admin}]",
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
    flash("Surtido procesado correctamente.", "success")
    return redirect(url_for("terminal", view="terminal"))

@app.route("/add_cleaning", methods=["POST"])
def add_cleaning():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    dia_semana = request.form.get("dia_semana", "Lunes")
    turno = request.form.get("turno", "Matutino")
    
    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN incorrecto.", "error")
        return redirect(url_for("terminal", view="limpieza"))

    log = CleaningLog(
        timestamp=get_local_now(),
        user_name=user.name,
        dia_semana=dia_semana,
        turno=turno,
        anaqueles='anaqueles' in request.form,
        pasillos='pasillos' in request.form,
        desecho_carton='desecho_carton' in request.form,
        refrigerador='refrigerador' in request.form,
        cajas_traslado='cajas_traslado' in request.form,
        acomodo_medicamento='acomodo_medicamento' in request.form,
        notes=request.form.get("notes")
    )
    db.session.add(log)
    db.session.commit()
    flash("Verificación guardada.", "success")
    return redirect(url_for("terminal", view="limpieza"))

@app.route("/add_item", methods=["POST"])
def add_item():
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    category = request.form.get("category")
    stock_general = int(request.form.get("stock_general", 0))

    new_item = Item(code=code, name=name, category=category, stock_general=stock_general, stock_quirofano=0)
    db.session.add(new_item)
    db.session.commit()
    flash(f"Insumo '{name}' registrado.", "success")
    return redirect(url_for("terminal", view="alta_insumos"))

@app.route("/add_controlled", methods=["POST"])
def add_controlled():
    raw_item_name = request.form.get("item_name", "").strip()
    item_name = raw_item_name.split(" (Lote:")[0].strip() if " (Lote:" in raw_item_name else raw_item_name
    patient_name = request.form.get("patient_name", "").strip()
    prescription_num = request.form.get("prescription_num", "").strip()
    quantity = int(request.form.get("quantity", 1))
    user_id = request.form.get("user_id")
    pin = request.form.get("pin", "").strip()

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN incorrecto.", "error")
        return redirect(url_for("terminal", view="controlados"))

    item = Item.query.filter(Item.name.ilike(f"%{item_name}%"), Item.etiqueta == "Controlado").first()
    if item:
        item.stock_general -= quantity

    new_log = ControlledLog(
        timestamp=get_local_now(),
        item_name=raw_item_name,
        patient_name=patient_name,
        prescription_num=prescription_num,
        quantity=quantity,
        user_name=user.name
    )
    db.session.add(new_log)
    db.session.commit()
    flash("Salida controlada registrada.", "success")
    return redirect(url_for("terminal", view="controlados"))

def seed_database():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            users_list = [
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678"),
                User(name="Alfonso Salvador Guzman Reyes", role="Farmacéutico", pin="1234"),
                User(name="Dra. Sofia Ramos", role="Farmacéutico", pin="4321"),
                User(name="Hannia Martinez Salas", role="Enfermería Quirófano", pin="1122"),
                User(name="Personal de Limpieza", role="Personal de Limpieza", pin="0000")
            ]
            db.session.add_all(users_list)
        if Item.query.count() == 0:
            items_list = [
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", etiqueta="Controlado", stock_general=30, stock_quirofano=10)
            ]
            db.session.add_all(items_list)
        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
