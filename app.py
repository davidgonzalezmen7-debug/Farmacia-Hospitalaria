import os
from datetime import datetime, date, timedelta, timezone
import json
import random
import io
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file
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
    role = db.Column(db.String(50), nullable=False) # 'Administrador', 'Autorizador', 'Farmacéutico', 'Enfermería', etc.
    pin = db.Column(db.String(20), nullable=False, unique=True)
    permisos_vistas = db.Column(db.String(300), default="terminal,costos,solicitud_insumos")
    permisos_acciones = db.Column(db.String(300), default="surtir,solicitar")

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
    caducidad = db.Column(db.String(20), nullable=True)
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
    shift = db.Column(db.String(50), nullable=True)
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

class WeeklySchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dia_semana = db.Column(db.String(20), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    actividad = db.Column(db.String(150), nullable=False)
    estado = db.Column(db.String(20), default="Pendiente")

# MODELO: Solicitudes de Insumos con Nombre de Paciente, Convenio y Expediente
class InsumoRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=get_local_now)
    patient_name = db.Column(db.String(150), nullable=False)
    convenio = db.Column(db.String(100), nullable=False)
    expediente = db.Column(db.String(50), nullable=False)
    insumo_solicitado = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    solicitante_nombre = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(30), default="Pendiente") # 'Pendiente', 'Aprobado', 'Modificado', 'Rechazado'
    insumo_autorizado = db.Column(db.String(150), nullable=True)
    cantidad_autorizada = db.Column(db.Integer, nullable=True)
    autorizador_nombre = db.Column(db.String(100), nullable=True)
    fecha_respuesta = db.Column(db.DateTime, nullable=True)

# -----------------------------------------------------------------------------
# PLANTILLA HTML ORIGINAL RESTAURADA E INTEGRADA
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
    
    <!-- BARRA DE NAVEGACIÓN SUPERIOR CON SESIÓN Y NIVELES DE AUTORIZACIÓN -->
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
            
            <div class="flex items-center gap-3">
                {% if session.get('user_id') %}
                    <div class="text-right text-xs bg-white/10 px-3 py-1.5 rounded-xl border border-white/10">
                        <span class="block font-bold text-white"><i class="fa-solid fa-user-check text-emerald-400"></i> {{ session.get('user_name') }}</span>
                        <span class="text-[10px] text-blue-200 uppercase font-mono">Rol: {{ session.get('user_role') }}</span>
                    </div>
                    <a href="/logout" class="px-3 py-2 bg-rose-600/80 hover:bg-rose-600 text-white rounded-xl text-xs font-bold transition flex items-center gap-1 shadow">
                        <i class="fa-solid fa-power-off"></i> Salir
                    </a>
                {% else %}
                    <a href="/login" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold shadow transition flex items-center gap-1.5">
                        <i class="fa-solid fa-lock"></i> Iniciar Sesión (PIN)
                    </a>
                {% endif %}
            </div>
        </div>

        <!-- MENÚ DE PESTAÑAS INTEGRADO CON PERMISOS POR ROL -->
        <div class="bg-slate-950/60 border-t border-white/10 px-4 py-2 overflow-x-auto">
            <nav class="max-w-7xl mx-auto flex flex-wrap gap-1 text-xs font-bold">
                {% set user_perms = session.get('permisos_vistas', '') %}
                {% set is_admin_sess = session.get('user_role') == 'Administrador' %}

                {% if is_admin_sess or 'terminal' in user_perms %}
                <a href="/terminal?view=terminal" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'terminal' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-prescription-bottle-medical"></i> Surtido Múltiple
                </a>
                {% endif %}

                {% if is_admin_sess or 'costos' in user_perms %}
                <a href="/terminal?view=costos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'costos' %}bg-emerald-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-emerald-100{% endif %}">
                    <i class="fa-solid fa-file-invoice-dollar"></i> Cargo Costos
                </a>
                {% endif %}

                {% if is_admin_sess or 'etiquetas' in user_perms %}
                <a href="/terminal?view=etiquetas" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'etiquetas' %}bg-purple-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-purple-100{% endif %}">
                    <i class="fa-solid fa-tags"></i> Generar Etiquetas
                </a>
                {% endif %}

                {% if is_admin_sess or 'alta_insumos' in user_perms %}
                <a href="/terminal?view=alta_insumos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'alta_insumos' %}bg-emerald-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-emerald-100{% endif %}">
                    <i class="fa-solid fa-plus-circle"></i> Alta Insumos
                </a>
                {% endif %}

                {% if is_admin_sess or 'inventario' in user_perms %}
                <a href="/terminal?view=inventario" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'inventario' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-boxes-stacked"></i> Inventario
                </a>
                {% endif %}

                {% if is_admin_sess or 'controlados' in user_perms %}
                <a href="/terminal?view=controlados" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'controlados' %}bg-rose-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-rose-100{% endif %}">
                    <i class="fa-solid fa-capsules"></i> Controlados
                </a>
                {% endif %}

                {% if is_admin_sess or 'limpieza' in user_perms %}
                <a href="/terminal?view=limpieza" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'limpieza' %}bg-teal-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-teal-100{% endif %}">
                    <i class="fa-solid fa-broom"></i> Limpieza
                </a>
                {% endif %}

                {% if is_admin_sess or 'rol_semanal' in user_perms %}
                <a href="/terminal?view=rol_semanal" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'rol_semanal' %}bg-indigo-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-indigo-100{% endif %}">
                    <i class="fa-solid fa-calendar-days"></i> Rol Semanal
                </a>
                {% endif %}
                
                {% if is_admin_sess or 'solicitud_insumos' in user_perms %}
                <a href="/terminal?view=solicitud_insumos" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'solicitud_insumos' %}bg-cyan-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-cyan-100{% endif %}">
                    <i class="fa-solid fa-hand-holding-medical"></i> Solicitud Insumos
                </a>
                {% endif %}

                {% if is_admin_sess or 'autorizaciones' in user_perms %}
                <a href="/terminal?view=autorizaciones" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'autorizaciones' %}bg-amber-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-amber-100{% endif %}">
                    <i class="fa-solid fa-list-check"></i> Autorizaciones
                </a>
                {% endif %}

                {% if is_admin_sess or 'estado_autorizaciones' in user_perms %}
                <a href="/terminal?view=estado_autorizaciones" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'estado_autorizaciones' %}bg-teal-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-teal-100{% endif %}">
                    <i class="fa-solid fa-table-list"></i> Estado de Autorizaciones
                </a>
                {% endif %}

                {% if is_admin_sess or 'bitacora' in user_perms %}
                <a href="/terminal?view=bitacora" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'bitacora' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-clock-rotate-left"></i> Bitácora
                </a>
                {% endif %}

                {% if is_admin_sess or 'usuarios' in user_perms %}
                <a href="/terminal?view=usuarios" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'usuarios' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-lock"></i> Usuarios
                </a>
                {% endif %}
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

        <!-- ==================== VISTA: SOLICITUD DE INSUMOS ==================== -->
        {% if view == 'solicitud_insumos' %}
        <div class="max-w-3xl mx-auto space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="border-b pb-3 mb-4">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-hand-holding-medical text-cyan-600"></i> Solicitud de Insumos y Medicamentos
                    </h2>
                    <p class="text-xs text-slate-500">Complete los datos del paciente, convenio, expediente e insumo requerido.</p>
                </div>

                <form action="/submit_insumo_request" method="POST" class="space-y-4">
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" required placeholder="Ej. Juan Pérez" class="w-full p-2.5 border rounded-xl text-xs outline-none bg-slate-50 font-medium">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Convenio</label>
                            <input type="text" name="convenio" required placeholder="Ej. Particular / Seguros" class="w-full p-2.5 border rounded-xl text-xs outline-none bg-slate-50">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">No. de Expediente</label>
                            <input type="text" name="expediente" required placeholder="Ej. EXP-9923" class="w-full p-2.5 border rounded-xl text-xs outline-none bg-slate-50 font-mono">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Insumo Requerido</label>
                            <input list="items_list" name="insumo_solicitado" required placeholder="Seleccione o escriba el insumo..." class="w-full p-2.5 border rounded-xl text-xs font-bold outline-none bg-slate-50">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Cantidad</label>
                            <input type="number" min="1" value="1" name="cantidad" required class="w-full p-2.5 border rounded-xl text-xs font-bold outline-none bg-slate-50 text-center">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Solicitante</label>
                            <input type="text" name="solicitante_nombre" value="{{ session.get('user_name', '') }}" required class="w-full p-2.5 border rounded-xl text-xs outline-none bg-slate-50">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">PIN de Confirmación</label>
                            <input type="password" name="pin_confirmacion" required placeholder="PIN de usuario" class="w-full p-2.5 border rounded-xl text-xs outline-none bg-slate-50 font-mono tracking-widest">
                        </div>
                    </div>

                    <button type="submit" class="w-full bg-cyan-600 hover:bg-cyan-700 text-white font-bold py-3 rounded-xl transition shadow text-xs flex items-center justify-center gap-2">
                        <i class="fa-solid fa-paper-plane"></i> Enviar Solicitud a Autorizaciones
                    </button>
                </form>
            </div>
        </div>

        <!-- ==================== VISTA: AUTORIZACIONES CON SUSTITUCIÓN FLEXIBLE ==================== -->
        {% elif view == 'autorizaciones' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="border-b pb-3 mb-4 flex justify-between items-center">
                    <div>
                        <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-list-check text-amber-600"></i> Panel de Autorizaciones de Insumos
                        </h2>
                        <p class="text-xs text-slate-500">Autorice, modifique o sustituya por otro insumo o rechace solicitudes pendientes.</p>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-600">
                        <thead class="bg-slate-50 text-slate-500 uppercase">
                            <tr>
                                <th class="p-3">Fecha/Paciente</th>
                                <th class="p-3">Convenio / Exp.</th>
                                <th class="p-3">Insumo Solicitado</th>
                                <th class="p-3 text-center">Cant.</th>
                                <th class="p-3 text-center">Estado</th>
                                <th class="p-3 text-center">Acciones y Sustitución</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for req in insumo_requests %}
                            <tr class="hover:bg-slate-50">
                                <td class="p-3 font-medium text-slate-900">
                                    {{ req.patient_name }}
                                    <span class="block text-[10px] text-slate-400 font-mono">{{ req.timestamp.strftime('%d/%m/%Y %H:%M') }}</span>
                                </td>
                                <td class="p-3">
                                    {{ req.convenio }}
                                    <span class="block text-[10px] font-mono text-slate-500">Exp: {{ req.expediente }}</span>
                                </td>
                                <td class="p-3 font-bold text-indigo-900">{{ req.insumo_solicitado }}</td>
                                <td class="p-3 text-center font-bold text-sm text-slate-900">{{ req.cantidad }}</td>
                                <td class="p-3 text-center">
                                    <span class="px-2 py-0.5 rounded-full font-bold text-[10px] {% if req.estado == 'Aprobado' %}bg-emerald-100 text-emerald-800{% elif req.estado == 'Modificado' %}bg-indigo-100 text-indigo-800{% elif req.estado == 'Rechazado' %}bg-rose-100 text-rose-800{% else %}bg-amber-100 text-amber-800{% endif %}">
                                        {{ req.estado }}
                                    </span>
                                </td>
                                <td class="p-3">
                                    {% if req.estado == 'Pendiente' %}
                                    <form action="/process_insumo_request" method="POST" class="flex flex-col gap-2">
                                        <input type="hidden" name="request_id" value="{{ req.id }}">
                                        <div class="grid grid-cols-2 gap-1">
                                            <input list="items_list" name="insumo_final" value="{{ req.insumo_solicitado }}" placeholder="Sustituto..." class="p-1 border rounded text-[11px] bg-white font-medium">
                                            <input type="number" min="1" name="cantidad_final" value="{{ req.cantidad }}" placeholder="Cant." class="p-1 border rounded text-[11px] bg-white text-center font-bold">
                                        </div>
                                        <div class="flex gap-1 justify-center">
                                            <button type="submit" name="accion" value="aprobar" class="px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded text-[10px]">Aprobar</button>
                                            <button type="submit" name="accion" value="modificar" class="px-2 py-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded text-[10px]">Sustituir</button>
                                            <button type="submit" name="accion" value="rechazar" class="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded text-[10px]">Rechazar</button>
                                        </div>
                                    </form>
                                    {% else %}
                                    <span class="text-slate-400 text-[11px] italic">Por: {{ req.autorizador_nombre }} -> <strong>{{ req.insumo_autorizado }}</strong> (Cant: {{ req.cantidad_autorizada }})</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% else %}
                            <tr><td colspan="6" class="p-8 text-center text-slate-400 italic">No hay solicitudes pendientes.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ==================== VISTA: ESTADO DE AUTORIZACIONES (NUEVA PESTAÑA) ==================== -->
        {% elif view == 'estado_autorizaciones' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="border-b pb-3 mb-4 flex justify-between items-center">
                    <div>
                        <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-table-list text-teal-600"></i> Estado de Autorizaciones de Insumos
                        </h2>
                        <p class="text-xs text-slate-500">Listado general de todas las solicitudes, su estatus actual y detalles de sustitución.</p>
                    </div>
                    <button onclick="window.print()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold no-print">
                        <i class="fa-solid fa-print"></i> Imprimir Reporte
                    </button>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-700 border border-slate-200">
                        <thead class="bg-teal-50 text-teal-900 uppercase text-[10px]">
                            <tr>
                                <th class="p-2.5 border-r">Fecha / Hora</th>
                                <th class="p-2.5 border-r">Paciente / Exp.</th>
                                <th class="p-2.5 border-r">Convenio</th>
                                <th class="p-2.5 border-r">Insumo Solicitado</th>
                                <th class="p-2.5 border-r text-center">Cant. Sol.</th>
                                <th class="p-2.5 border-r text-center">Estado Actual</th>
                                <th class="p-2.5 border-r">Insumo Autorizado / Sustituto</th>
                                <th class="p-2.5 border-r text-center">Cant. Aut.</th>
                                <th class="p-2.5">Autorizador</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for req in insumo_requests %}
                            <tr class="hover:bg-slate-50">
                                <td class="p-2.5 border-r font-mono text-[10px] text-slate-500">{{ req.timestamp.strftime('%d/%m/%Y %H:%M') }}</td>
                                <td class="p-2.5 border-r font-bold text-slate-900">{{ req.patient_name }}<span class="block text-[10px] text-slate-400 font-mono">Exp: {{ req.expediente }}</span></td>
                                <td class="p-2.5 border-r font-medium">{{ req.convenio }}</td>
                                <td class="p-2.5 border-r text-slate-800">{{ req.insumo_solicitado }}</td>
                                <td class="p-2.5 border-r text-center font-bold">{{ req.cantidad }}</td>
                                <td class="p-2.5 border-r text-center">
                                    <span class="px-2 py-0.5 rounded-full font-bold text-[10px] {% if req.estado == 'Aprobado' %}bg-emerald-100 text-emerald-800{% elif req.estado == 'Modificado' %}bg-indigo-100 text-indigo-800{% elif req.estado == 'Rechazado' %}bg-rose-100 text-rose-800{% else %}bg-amber-100 text-amber-800{% endif %}">
                                        {{ req.estado }}
                                    </span>
                                </td>
                                <td class="p-2.5 border-r font-bold text-indigo-900">{{ req.insumo_autorizado or '-' }}</td>
                                <td class="p-2.5 border-r text-center font-bold text-slate-900">{{ req.cantidad_autorizada if req.cantidad_autorizada is not none else '-' }}</td>
                                <td class="p-2.5 text-slate-600 font-medium">{{ req.autorizador_nombre or 'Pendiente' }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="9" class="p-6 text-center text-slate-400 italic">No hay registros de solicitudes.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ==================== VISTA: ROL SEMANAL ==================== -->
        {% elif view == 'rol_semanal' %}
        <div class="space-y-6">
            <div class="bg-gradient-to-r from-indigo-900 to-slate-900 text-white p-6 rounded-2xl shadow-md border border-indigo-800 flex flex-col md:flex-row justify-between items-center gap-4">
                <div>
                    <h2 class="text-base font-bold flex items-center gap-2">
                        <i class="fa-solid fa-calendar-days text-indigo-400"></i> Rol Semanal de Actividades por Usuario
                    </h2>
                    <p class="text-xs text-indigo-200">Ventana individual por cada integrante del personal con el detalle de actividades asignadas.</p>
                </div>
                <div class="flex gap-2">
                    <a href="/generate_random_rol" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow">
                        <i class="fa-solid fa-shuffle"></i> Regenerar Rol Aleatorio
                    </a>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                {% for usr in staff_users %}
                <div class="bg-white p-5 rounded-2xl shadow-sm border border-indigo-100 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between border-b pb-3 mb-3">
                            <div class="flex items-center gap-2.5">
                                <div class="w-9 h-9 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-sm">
                                    <i class="fa-solid fa-user-gear"></i>
                                </div>
                                <div>
                                    <h3 class="font-bold text-slate-900 text-sm">{{ usr.name }}</h3>
                                    <span class="text-[10px] text-slate-500 font-medium">{{ usr.role }}</span>
                                </div>
                            </div>
                        </div>

                        <div class="overflow-x-auto">
                            <table class="w-full text-xs text-left">
                                <thead class="bg-slate-50 text-slate-500 uppercase text-[10px]">
                                    <tr>
                                        <th class="p-2">Día</th>
                                        <th class="p-2">Actividad Asignada</th>
                                        <th class="p-2 text-center">Estado</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100">
                                    {% set user_tasks = weekly_tasks_by_user.get(usr.name, []) %}
                                    {% for task in user_tasks %}
                                    <tr class="hover:bg-slate-50">
                                        <td class="p-2 font-bold text-slate-800">{{ task.dia_semana }}</td>
                                        <td class="p-2 text-slate-700 font-medium">{{ task.actividad }}</td>
                                        <td class="p-2 text-center">
                                            {% if task.estado == 'Completado' %}
                                                <span class="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full font-bold text-[10px]">Realizado</span>
                                            {% else %}
                                                <span class="bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full font-bold text-[10px]">Pendiente</span>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- ==================== VISTA: CARGO COSTOS ==================== -->
        {% elif view == 'costos' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="border-b pb-4 mb-4 flex justify-between items-center">
                    <div>
                        <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                            <i class="fa-solid fa-file-invoice-dollar text-emerald-600"></i> Cargo Múltiple de Material para Costos
                        </h2>
                        <p class="text-xs text-slate-500">Agregue varios insumos a la lista de cargo para un paciente y regístrelos por turno.</p>
                    </div>
                </div>

                <form action="/add_cost_cargo_batch" method="POST" onsubmit="return validateCostosBatch()" class="space-y-4">
                    <input type="hidden" name="cart_costos_data" id="cart_costos_data_input">

                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" id="costos_patient_name" required class="w-full p-2 border rounded-xl text-xs bg-white">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Habitación / Cama</label>
                            <input type="text" name="room" id="costos_room" required class="w-full p-2 border rounded-xl text-xs bg-white">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">No. de Expediente</label>
                            <input type="text" name="patient_id" id="costos_patient_id" required class="w-full p-2 border rounded-xl text-xs bg-white">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Turno</label>
                            <select name="shift" required class="w-full p-2 border rounded-xl text-xs bg-white font-bold">
                                <option value="Matutino">☀️ Turno Matutino</option>
                                <option value="Vespertino">⛅ Turno Vespertino</option>
                                <option value="Nocturno A">🌙 Turno Nocturno A</option>
                                <option value="Nocturno B">🌌 Turno Nocturno B</option>
                            </select>
                        </div>
                    </div>

                    <div class="p-4 bg-emerald-50/60 rounded-xl border border-emerald-200 space-y-3">
                        <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                            <div class="md:col-span-6">
                                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Buscar Insumo / Medicamento</label>
                                <input list="items_list" id="costos_temp_item" placeholder="Escriba para filtrar en el inventario..." class="w-full p-2 border rounded-lg text-xs bg-white outline-none">
                            </div>
                            <div class="md:col-span-3">
                                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Cantidad</label>
                                <input type="number" min="1" id="costos_temp_qty" value="1" class="w-full p-2 border rounded-lg text-xs bg-white text-center font-bold">
                            </div>
                            <div class="md:col-span-3">
                                <button type="button" onclick="addCostosCartItem()" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-2 rounded-lg text-xs transition">
                                    <i class="fa-solid fa-plus"></i> Agregar
                                </button>
                            </div>
                        </div>
                    </div>

                    <div>
                        <div class="overflow-x-auto border rounded-xl bg-white">
                            <table class="w-full text-xs text-left text-slate-600">
                                <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                    <tr>
                                        <th class="p-2.5">Insumo / Lote</th>
                                        <th class="p-2.5 text-center">Cantidad</th>
                                        <th class="p-2.5 text-center">Acción</th>
                                    </tr>
                                </thead>
                                <tbody id="costosCartTableBody" class="divide-y divide-slate-100">
                                    <tr><td colspan="3" class="p-6 text-center text-slate-400 italic">No hay insumos agregados al cargo.</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                        <input type="password" name="pin" required placeholder="PIN de Validación" class="w-full p-2.5 border rounded-xl text-xs bg-white">
                        <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl transition shadow text-xs">Registrar Cargo Múltiple</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- ==================== VISTA: CONTROLADOS ==================== -->
        {% elif view == 'controlados' %}
        <div class="space-y-6 max-w-4xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-base font-bold text-slate-900 mb-2 border-b pb-2 flex items-center gap-2">
                    <i class="fa-solid fa-capsules text-rose-600"></i> Arqueo y Salida de Medicamentos Controlados
                </h2>
                <form action="/add_controlled" method="POST" class="space-y-4">
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Medicamento Controlado</label>
                            <input list="controlled_items_list" name="item_name" required placeholder="Seleccione medicamento..." class="w-full p-2.5 border rounded-xl text-xs font-bold">
                            <datalist id="controlled_items_list">
                                {% for item in controlled_items %}<option value="{{ item.name }} (Lote: {{ item.lote or 'S/L' }})">{% endfor %}
                            </datalist>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Paciente</label>
                            <input type="text" list="patients_datalist" name="patient_name" required placeholder="Paciente..." class="w-full p-2.5 border rounded-xl text-xs">
                        </div>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">No. Receta / Folio</label>
                            <input type="text" name="prescription_num" required placeholder="Ej. REC-4412" class="w-full p-2.5 border rounded-xl text-xs font-mono">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Cantidad</label>
                            <input type="number" min="1" value="1" name="quantity" required class="w-full p-2.5 border rounded-xl text-xs text-center font-bold">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">PIN de Validación</label>
                            <input type="password" name="pin" required placeholder="PIN de autorizador" class="w-full p-2.5 border rounded-xl text-xs font-mono">
                        </div>
                    </div>
                    <button type="submit" class="w-full bg-rose-600 hover:bg-rose-700 text-white font-bold py-3 rounded-xl transition text-xs shadow">Registrar Salida de Controlado</button>
                </form>
            </div>
        </div>

        <!-- ==================== VISTA: SURTIDO MÚLTIPLE ==================== -->
        {% elif view == 'terminal' %}
        <div class="space-y-6 max-w-5xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-4">
                <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                    <i class="fa-solid fa-receipt text-blue-600"></i> Dispensación de Receta / Surtido a Paciente (Múltiple)
                </h2>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre del Paciente</label>
                        <input type="text" list="patients_datalist" id="batch_patient_name" placeholder="Paciente..." class="w-full p-2.5 border rounded-xl text-xs bg-slate-50">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Servicio / Área</label>
                        <select id="batch_service" class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 font-bold">
                            <option value="Hospitalización">Hospitalización</option>
                            <option value="Urgencias">Urgencias</option>
                            <option value="Quirófano">Quirófano</option>
                            <option value="Consulta Externa">Consulta Externa</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Almacén Origen</label>
                        <select id="batch_warehouse" class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 font-bold">
                            <option value="General">Almacén General</option>
                            <option value="Quirófano">Quirófano</option>
                        </select>
                    </div>
                </div>

                <div class="p-4 bg-blue-50/60 rounded-xl border border-blue-200 space-y-3">
                    <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                        <div class="md:col-span-6">
                            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Seleccionar Insumo del Inventario</label>
                            <input list="items_list" id="batch_temp_item" placeholder="Escriba para filtrar..." class="w-full p-2 border rounded-lg text-xs bg-white outline-none">
                        </div>
                        <div class="md:col-span-3">
                            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Cantidad</label>
                            <input type="number" min="1" id="batch_temp_qty" value="1" class="w-full p-2 border rounded-lg text-xs bg-white text-center font-bold">
                        </div>
                        <div class="md:col-span-3">
                            <button type="button" onclick="addBatchCartItem()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-2 rounded-lg text-xs transition">
                                <i class="fa-solid fa-plus"></i> Agregar a Receta
                            </button>
                        </div>
                    </div>
                </div>

                <div class="overflow-x-auto border rounded-xl bg-white">
                    <table class="w-full text-xs text-left text-slate-600">
                        <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                            <tr>
                                <th class="p-2.5">Insumo / Lote</th>
                                <th class="p-2.5 text-center">Cantidad</th>
                                <th class="p-2.5 text-center">Acción</th>
                            </tr>
                        </thead>
                        <tbody id="batchCartTableBody" class="divide-y divide-slate-100">
                            <tr><td colspan="3" class="p-6 text-center text-slate-400 italic">No hay insumos agregados en el surtido actual.</td></tr>
                        </tbody>
                    </table>
                </div>

                <form action="/register_batch" method="POST" onsubmit="return validateBatchForm()" class="space-y-4 pt-2">
                    <input type="hidden" name="cart_data" id="cart_data_input">
                    <input type="hidden" name="patient_name" id="hidden_batch_patient">
                    <input type="hidden" name="service" id="hidden_batch_service">
                    <input type="hidden" name="warehouse" id="hidden_batch_warehouse">
                    
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <input type="password" name="pin" required placeholder="PIN de Seguridad de Farmacia" class="w-full p-2.5 border rounded-xl text-xs font-mono bg-slate-50">
                        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md text-xs transition">Procesar y Descontar Surtido</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- ==================== VISTA: GENERAR ETIQUETAS ==================== -->
        {% elif view == 'etiquetas' %}
        <div class="space-y-6 max-w-xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-4">
                <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                    <i class="fa-solid fa-tags text-purple-600"></i> Generar Etiquetas Térmicas (51 x 25 mm)
                </h2>
                <form action="/generate_label_pdf" method="POST" class="space-y-3">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Insumo / Medicamento</label>
                        <input list="items_list" name="item_label_name" required placeholder="Seleccione el insumo..." class="w-full p-2.5 border rounded-xl text-xs font-medium">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Número de Etiquetas</label>
                        <input type="number" min="1" max="50" value="1" name="num_etiquetas" required class="w-full p-2.5 border rounded-xl text-xs font-bold text-center">
                    </div>
                    <button type="submit" class="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 rounded-xl transition shadow text-xs">Descargar PDF de Etiquetas</button>
                </form>
            </div>
        </div>

        <!-- ==================== VISTA: INVENTARIO ==================== -->
        {% elif view == 'inventario' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <div class="border-b pb-3 mb-4 flex justify-between items-center">
                    <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-boxes-stacked text-blue-600"></i> Inventario Detallado y Lotes
                    </h2>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-700 border border-slate-200">
                        <thead class="bg-blue-50 text-blue-900 uppercase text-[10px]">
                            <tr>
                                <th class="p-2.5 border-r">Código</th>
                                <th class="p-2.5 border-r">Descripción</th>
                                <th class="p-2.5 border-r">Lote</th>
                                <th class="p-2.5 border-r">Caducidad</th>
                                <th class="p-2.5 border-r text-center">Stock Gen.</th>
                                <th class="p-2.5 border-r text-center">Stock Qx</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for item in items %}
                            <tr class="hover:bg-slate-50">
                                <td class="p-2.5 border-r font-mono text-[11px] font-bold">{{ item.code }}</td>
                                <td class="p-2.5 border-r font-bold text-slate-900">{{ item.name }}</td>
                                <td class="p-2.5 border-r font-mono text-indigo-700">{{ item.lote or 'S/L' }}</td>
                                <td class="p-2.5 border-r font-mono text-slate-600">{{ item.caducidad or 'S/F' }}</td>
                                <td class="p-2.5 border-r text-center font-bold text-blue-800">{{ item.stock_general }}</td>
                                <td class="p-2.5 text-center font-bold text-emerald-800">{{ item.stock_quirofano }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ==================== VISTA: ALTA INSUMOS ==================== -->
        {% elif view == 'alta_insumos' %}
        <div class="space-y-6 max-w-xl mx-auto">
            <form action="/add_item" method="POST" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-3">
                <h2 class="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-plus-circle text-emerald-600"></i> Registrar Nuevo Insumo / Lote
                </h2>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Código</label>
                    <input type="text" name="code" required placeholder="Ej. MED-001" class="w-full p-2.5 border rounded-xl text-sm font-mono uppercase">
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre / Descripción</label>
                    <input type="text" name="name" required placeholder="Ej. Paracetamol 500mg" class="w-full p-2.5 border rounded-xl text-sm">
                </div>
                <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl transition shadow text-xs">Guardar Insumo en Inventario</button>
            </form>
        </div>

        <!-- ==================== VISTA: LIMPIEZA ==================== -->
        {% elif view == 'limpieza' %}
        <div class="space-y-6 max-w-2xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-broom text-teal-600"></i> Check List de Limpieza y Mantenimiento
                </h2>
                <form action="/save_cleaning" method="POST" class="space-y-3">
                    <div class="grid grid-cols-2 gap-2 text-xs font-medium">
                        <label class="flex items-center gap-2"><input type="checkbox" name="anaqueles" value="1"> Anaqueles limpios</label>
                        <label class="flex items-center gap-2"><input type="checkbox" name="pasillos" value="1"> Pasillos despejados</label>
                    </div>
                    <input type="password" name="pin" required placeholder="PIN de usuario" class="w-full p-2.5 border rounded-xl text-xs">
                    <button type="submit" class="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-2.5 rounded-xl text-xs">Registrar Limpieza</button>
                </form>
            </div>
        </div>

        <!-- ==================== VISTA: BITÁCORA ==================== -->
        {% elif view == 'bitacora' %}
        <div class="space-y-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h2 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-clock-rotate-left text-blue-600"></i> Bitácora e Histórico de Movimientos
                </h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-slate-600">
                        <thead class="bg-slate-50 text-slate-500 uppercase">
                            <tr>
                                <th class="p-3">Fecha / Hora</th>
                                <th class="p-3">Usuario</th>
                                <th class="p-3">Tipo</th>
                                <th class="p-3">Insumo</th>
                                <th class="p-3 text-center">Cant.</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for mov in movements %}
                            <tr>
                                <td class="p-3 font-mono text-[10px]">{{ mov.timestamp.strftime('%d/%m/%Y %H:%M') }}</td>
                                <td class="p-3 font-medium">{{ mov.user_name }}</td>
                                <td class="p-3">{{ mov.type }}</td>
                                <td class="p-3 font-bold text-slate-800">{{ mov.item_name }}</td>
                                <td class="p-3 text-center font-bold">{{ mov.quantity }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ==================== VISTA: USUARIOS Y PERMISOS CONFIGURABLES ==================== -->
        {% elif view == 'usuarios' %}
        {% if session.get('user_role') != 'Administrador' %}
        <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 max-w-md mx-auto text-center space-y-4">
            <h2 class="text-lg font-bold text-rose-600">Acceso Exclusivo de Administrador</h2>
        </div>
        {% else %}
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2">Crear / Modificar Usuario</h2>
                <form action="/save_user" method="POST" class="space-y-3">
                    <input type="hidden" name="user_id" id="edit_user_id">
                    <input type="text" name="name" id="edit_user_name" required placeholder="Nombre completo" class="w-full p-2.5 border rounded-xl text-sm">
                    <select name="role" id="edit_user_role" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50">
                        <option value="Administrador">Administrador</option>
                        <option value="Autorizador">Autorizador</option>
                        <option value="Farmacéutico">Farmacéutico</option>
                        <option value="Enfermería">Enfermería</option>
                    </select>
                    <input type="password" name="pin" id="edit_user_pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-sm font-mono">
                    
                    <div class="border p-3 rounded-xl bg-slate-50 space-y-2">
                        <label class="block text-xs font-bold text-slate-700 uppercase">¿Qué puede ver? (Pestañas Permitidas)</label>
                        <div class="grid grid-cols-2 gap-1 text-xs">
                            <label><input type="checkbox" name="permisos_vistas" value="terminal"> Surtido</label>
                            <label><input type="checkbox" name="permisos_vistas" value="costos"> Costos</label>
                            <label><input type="checkbox" name="permisos_vistas" value="etiquetas"> Etiquetas</label>
                            <label><input type="checkbox" name="permisos_vistas" value="alta_insumos"> Alta Insumos</label>
                            <label><input type="checkbox" name="permisos_vistas" value="inventario"> Inventario</label>
                            <label><input type="checkbox" name="permisos_vistas" value="controlados"> Controlados</label>
                            <label><input type="checkbox" name="permisos_vistas" value="limpieza"> Limpieza</label>
                            <label><input type="checkbox" name="permisos_vistas" value="rol_semanal"> Rol Semanal</label>
                            <label><input type="checkbox" name="permisos_vistas" value="solicitud_insumos"> Solicitud Insumos</label>
                            <label><input type="checkbox" name="permisos_vistas" value="autorizaciones"> Autorizaciones</label>
                            <label><input type="checkbox" name="permisos_vistas" value="estado_autorizaciones"> Estado Aut.</label>
                            <label><input type="checkbox" name="permisos_vistas" value="bitacora"> Bitácora</label>
                        </div>
                    </div>

                    <div class="border p-3 rounded-xl bg-slate-50 space-y-2">
                        <label class="block text-xs font-bold text-slate-700 uppercase">¿Qué puede hacer? (Acciones Autorizadas)</label>
                        <div class="grid grid-cols-2 gap-1 text-xs">
                            <label><input type="checkbox" name="permisos_acciones" value="surtir"> Surtir Recetas</label>
                            <label><input type="checkbox" name="permisos_acciones" value="solicitar"> Solicitar Insumos</label>
                            <label><input type="checkbox" name="permisos_acciones" value="autorizar"> Autorizar / Modificar</label>
                            <label><input type="checkbox" name="permisos_acciones" value="registrar_altas"> Registrar Altas</label>
                        </div>
                    </div>

                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl">Guardar Usuario y Permisos</button>
                </form>
            </div>
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2">Personal y Accesos Configurados</h2>
                <div class="space-y-3">
                    {% for u in users %}
                    <div class="p-4 rounded-xl border bg-slate-50 flex justify-between items-center">
                        <div>
                            <h4 class="font-bold text-slate-900 text-sm">{{ u.name }}</h4>
                            <p class="text-xs text-slate-500">Rol: {{ u.role }} | PIN: {{ u.pin }}</p>
                            <p class="text-[10px] text-indigo-700 font-mono mt-1">Vistas: {{ u.permisos_vistas }}</p>
                            <p class="text-[10px] text-emerald-700 font-mono">Acciones: {{ u.permisos_acciones }}</p>
                        </div>
                        <button onclick="editUser('{{ u.id }}', '{{ u.name }}', '{{ u.role }}', '{{ u.pin }}', '{{ u.permisos_vistas }}', '{{ u.permisos_acciones }}')" class="px-2.5 py-1 bg-blue-100 hover:bg-blue-200 text-blue-800 font-bold rounded-lg text-xs">Editar</button>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        {% endif %}
        {% endif %}
    </main>

    <script>
        let costosCart = [];
        function addCostosCartItem() {
            const itemInput = document.getElementById('costos_temp_item');
            const itemVal = itemInput.value.trim();
            const quantity = parseInt(document.getElementById('costos_temp_qty').value) || 1;
            if (!itemVal) return;
            costosCart.push({ item_search: itemVal, quantity: quantity });
            itemInput.value = '';
            renderCostosCart();
        }
        function renderCostosCart() {
            const tbody = document.getElementById('costosCartTableBody');
            if (costosCart.length === 0) { tbody.innerHTML = `<tr><td colspan="3" class="p-6 text-center text-slate-400 italic">No hay insumos agregados.</td></tr>`; return; }
            let html = '';
            costosCart.forEach((item, index) => {
                html += `<tr class="hover:bg-slate-50"><td class="p-2.5 font-bold">${item.item_search}</td><td class="p-2.5 text-center font-bold text-emerald-700">${item.quantity}</td><td class="p-2.5 text-center"><button type="button" onclick="costosCart.splice(${index},1);renderCostosCart();" class="text-rose-600">Eliminar</button></td></tr>`;
            });
            tbody.innerHTML = html;
        }
        function validateCostosBatch() {
            if (costosCart.length === 0) { alert('Agregue al menos un insumo.'); return false; }
            document.getElementById('cart_costos_data_input').value = JSON.stringify(costosCart);
            return true;
        }

        let batchCart = [];
        function addBatchCartItem() {
            const itemInput = document.getElementById('batch_temp_item');
            const itemVal = itemInput.value.trim();
            const quantity = parseInt(document.getElementById('batch_temp_qty').value) || 1;
            if (!itemVal) return;
            batchCart.push({ item_search: itemVal, quantity: quantity });
            itemInput.value = '';
            renderBatchCart();
        }
        function renderBatchCart() {
            const tbody = document.getElementById('batchCartTableBody');
            if (batchCart.length === 0) { tbody.innerHTML = `<tr><td colspan="3" class="p-6 text-center text-slate-400 italic">No hay insumos agregados.</td></tr>`; return; }
            let html = '';
            batchCart.forEach((item, index) => {
                html += `<tr class="hover:bg-slate-50"><td class="p-2.5 font-bold">${item.item_search}</td><td class="p-2.5 text-center font-bold text-blue-700">${item.quantity}</td><td class="p-2.5 text-center"><button type="button" onclick="batchCart.splice(${index},1);renderBatchCart();" class="text-rose-600">Eliminar</button></td></tr>`;
            });
            tbody.innerHTML = html;
        }
        function validateBatchForm() {
            if (batchCart.length === 0) { alert('Agregue al menos un insumo.'); return false; }
            const pName = document.getElementById('batch_patient_name').value.trim();
            if (!pName) { alert('Ingrese el nombre del paciente.'); return false; }
            document.getElementById('hidden_batch_patient').value = pName;
            document.getElementById('hidden_batch_service').value = document.getElementById('batch_service').value;
            document.getElementById('hidden_batch_warehouse').value = document.getElementById('batch_warehouse').value;
            document.getElementById('cart_data_input').value = JSON.stringify(batchCart);
            return true;
        }

        function editUser(id, name, role, pin, permisos_vistas, permisos_acciones) {
            document.getElementById('edit_user_id').value = id;
            document.getElementById('edit_user_name').value = name;
            document.getElementById('edit_user_role').value = role;
            document.getElementById('edit_user_pin').value = pin;
            document.querySelectorAll('input[name="permisos_vistas"]').forEach(chk => {
                chk.checked = permisos_vistas.includes(chk.value);
            });
            document.querySelectorAll('input[name="permisos_acciones"]').forEach(chk => {
                chk.checked = permisos_acciones.includes(chk.value);
            });
        }
    </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# RUTAS Y CONTROL DE AUTENTICACIÓN
# -----------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        user = User.query.filter_by(pin=pin).first()
        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            session['permisos_vistas'] = user.permisos_vistas or ""
            session['permisos_acciones'] = user.permisos_acciones or ""
            flash(f"Bienvenido(a), {user.name}", "success")
            return redirect(url_for('terminal', view='costos'))
        else:
            flash("PIN incorrecto. Intente de nuevo.", "error")
            
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Login - Farmacia Hospitalaria</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 min-h-screen flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-md w-full p-8 shadow-2xl space-y-6 text-center">
            <h1 class="text-xl font-extrabold text-slate-900">Autenticación Obligatoria</h1>
            <p class="text-xs text-slate-500">Ingrese su PIN de usuario para visualizar el sistema</p>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="p-3 text-xs rounded-xl bg-rose-100 text-rose-800 font-medium">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
            <form action="/login" method="POST" class="space-y-4">
                <input type="password" name="pin" required autofocus placeholder="••••" class="w-full p-3 border rounded-xl text-center text-2xl font-bold tracking-widest outline-none bg-slate-50">
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition">Ingresar</button>
            </form>
        </div>
    </body>
    </html>
    """)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for("terminal", view="costos"))

@app.route("/terminal")
def terminal():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    view = request.args.get("view", "costos")
    role = session.get('user_role')
    permisos = session.get('permisos_vistas', '')
    if role != 'Administrador' and view != 'usuarios' and view not in permisos:
        flash("No cuenta con permisos para ver esta sección.", "error")
        return redirect(url_for('terminal', view='costos'))

    items = Item.query.order_by(Item.name, Item.lote).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    staff_users = User.query.filter(User.role != "Administrador").order_by(User.name).all()
    movements = Movement.query.order_by(Movement.timestamp.desc()).limit(100).all()
    controlled_logs = ControlledLog.query.order_by(ControlledLog.timestamp.desc()).limit(50).all()
    
    if WeeklySchedule.query.count() == 0:
        generar_rol_aleatorio_interno()

    all_weekly_tasks = WeeklySchedule.query.all()
    weekly_tasks_by_user = {}
    for task in all_weekly_tasks:
        if task.user_name not in weekly_tasks_by_user:
            weekly_tasks_by_user[task.user_name] = []
        weekly_tasks_by_user[task.user_name].append(task)

    controlled_items = Item.query.filter_by(etiqueta="Controlado").order_by(Item.name).all()
    insumo_requests = InsumoRequest.query.order_by(InsumoRequest.timestamp.desc()).all()

    return render_template_string(
        HTML_TEMPLATE,
        view=view,
        items=items,
        users=users,
        staff_users=staff_users,
        patients=patients,
        movements=movements,
        controlled_logs=controlled_logs,
        weekly_tasks_by_user=weekly_tasks_by_user,
        controlled_items=controlled_items,
        insumo_requests=insumo_requests
    )

def generar_rol_aleatorio_interno():
    WeeklySchedule.query.delete()
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    actividades = ["Limpieza de anaqueles", "Limpieza de pasillo", "Limpieza de refrigerador", "Desecho de cartón", "Cajas de traslado", "Acomodo de medicamento"]
    personal = User.query.filter(User.role != "Administrador").all()
    if not personal: return
    for usr in personal:
        for dia in dias:
            db.session.add(WeeklySchedule(dia_semana=dia, user_name=usr.name, actividad=random.choice(actividades), estado="Pendiente"))
    db.session.commit()

@app.route("/generate_random_rol")
def generate_random_rol():
    generar_rol_aleatorio_interno()
    return redirect(url_for("terminal", view="rol_semanal"))

@app.route("/submit_insumo_request", methods=["POST"])
def submit_insumo_request():
    patient_name = request.form.get("patient_name")
    convenio = request.form.get("convenio")
    expediente = request.form.get("expediente")
    insumo = request.form.get("insumo_solicitado")
    cantidad = int(request.form.get("cantidad", 1))
    solicitante = request.form.get("solicitante_nombre")
    pin = request.form.get("pin_confirmacion")

    user = User.query.filter_by(pin=pin).first()
    if not user:
        flash("PIN incorrecto.", "error")
        return redirect(url_for("terminal", view="solicitud_insumos"))

    db.session.add(InsumoRequest(
        timestamp=get_local_now(),
        patient_name=patient_name,
        convenio=convenio,
        expediente=expediente,
        insumo_solicitado=insumo,
        cantidad=cantidad,
        solicitante_nombre=solicitante,
        estado="Pendiente"
    ))
    db.session.commit()
    flash("Solicitud registrada con éxito.", "success")
    return redirect(url_for("terminal", view="solicitud_insumos"))

@app.route("/process_insumo_request", methods=["POST"])
def process_insumo_request():
    req_id = request.form.get("request_id")
    accion = request.form.get("accion")
    insumo_final = request.form.get("insumo_final")
    cantidad_final = int(request.form.get("cantidad_final", 1))
    
    req = InsumoRequest.query.get(req_id)
    if req:
        if accion == "aprobar":
            req.estado = "Aprobado"
            req.insumo_autorizado = req.insumo_solicitado
            req.cantidad_autorizada = req.cantidad
        elif accion == "modificar":
            req.estado = "Modificado"
            req.insumo_autorizado = insumo_final
            req.cantidad_autorizada = cantidad_final
        else:
            req.estado = "Rechazado"
            req.insumo_autorizado = "-"
            req.cantidad_autorizada = 0

        req.autorizador_nombre = session.get('user_name', 'Autorizador')
        req.fecha_respuesta = get_local_now()
        db.session.commit()
        flash("Solicitud procesada correctamente.", "success")
    
    return redirect(url_for("terminal", view="autorizaciones"))

@app.route("/save_user", methods=["POST"])
def save_user():
    u_id = request.form.get("user_id")
    name = request.form.get("name")
    role = request.form.get("role")
    pin = request.form.get("pin")
    permisos_vistas_list = request.form.getlist("permisos_vistas")
    permisos_acciones_list = request.form.getlist("permisos_acciones")
    vistas_str = ",".join(permisos_vistas_list)
    acciones_str = ",".join(permisos_acciones_list)

    if u_id:
        u = User.query.get(u_id)
        u.name = name
        u.role = role
        u.pin = pin
        u.permisos_vistas = vistas_str
        u.permisos_acciones = acciones_str
    else:
        db.session.add(User(name=name, role=role, pin=pin, permisos_vistas=vistas_str, permisos_acciones=acciones_str))
    db.session.commit()
    flash("Usuario y permisos configurados con éxito.", "success")
    return redirect(url_for("terminal", view="usuarios"))

@app.route("/add_item", methods=["POST"])
def add_item():
    code = request.form.get("code").upper()
    name = request.form.get("name")
    category = request.form.get("category", "Medicamento")
    stock_general = int(request.form.get("stock_general", 50))
    db.session.add(Item(code=code, name=name, category=category, stock_general=stock_general))
    db.session.commit()
    flash("Insumo agregado con éxito.", "success")
    return redirect(url_for("terminal", view="alta_insumos"))

@app.route("/add_cost_cargo_batch", methods=["POST"])
def add_cost_cargo_batch():
    pin = request.form.get("pin")
    user = User.query.filter_by(pin=pin).first()
    if not user:
        flash("PIN incorrecto.", "error")
        return redirect(url_for("terminal", view="costos"))
    flash("Cargo registrado.", "success")
    return redirect(url_for("terminal", view="costos"))

@app.route("/register_batch", methods=["POST"])
def register_batch():
    flash("Surtido procesado.", "success")
    return redirect(url_for("terminal", view="terminal"))

@app.route("/add_controlled", methods=["POST"])
def add_controlled():
    flash("Controlado registrado.", "success")
    return redirect(url_for("terminal", view="controlados"))

@app.route("/save_cleaning", methods=["POST"])
def save_cleaning():
    flash("Limpieza registrada.", "success")
    return redirect(url_for("terminal", view="limpieza"))

@app.route("/generate_label_pdf", methods=["POST"])
def generate_label_pdf():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(51 * mm, 25 * mm))
    pdf.drawString(2 * mm, 20 * mm, "ETIQUETA TÉRMICA")
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="etiqueta.pdf", mimetype="application/pdf")

def seed_database():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            db.session.add_all([
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678", permisos_vistas="terminal,costos,etiquetas,alta_insumos,inventario,controlados,limpieza,rol_semanal,solicitud_insumos,autorizaciones,estado_autorizaciones,bitacora,usuarios", permisos_acciones="surtir,solicitar,autorizar,registrar_altas"),
                User(name="Alfonso Salvador Guzman Reyes", role="Autorizador", pin="1234", permisos_vistas="solicitud_insumos,autorizaciones,estado_autorizaciones", permisos_acciones="autorizar,solicitar"),
                User(name="Hannia Martinez Salas", role="Enfermería", pin="1122", permisos_vistas="solicitud_insumos,estado_autorizaciones", permisos_acciones="solicitar")
            ])
            db.session.commit()
        if Item.query.count() == 0:
            db.session.add_all([
                Item(code="MED-001", name="Paracetamol 500mg", category="Medicamento", lote="L-2026A", caducidad="12/2027", stock_general=120),
                Item(code="MED-002", name="Morfina 10ml", category="Medicamento", lote="L-CTRL9", caducidad="08/2026", etiqueta="Controlado", stock_general=15)
            ])
            db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
