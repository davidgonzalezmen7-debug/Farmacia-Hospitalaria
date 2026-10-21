import os
from datetime import datetime, date, timedelta, timezone
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
# PLANTILLA HTML INTEGRADA Y UNIFICADA
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
            <nav class="flex flex-wrap gap-1 text-xs font-bold">
                <a href="/terminal" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'terminal' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-pen-to-square"></i> Surtido
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
                <a href="/etiquetas" class="px-2.5 py-2 rounded-xl transition flex items-center gap-1.5 {% if view == 'etiquetas' %}bg-blue-600 text-white shadow{% else %}bg-white/10 hover:bg-white/20 text-blue-100{% endif %}">
                    <i class="fa-solid fa-tags"></i> Etiquetas
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
        <div class="space-y-6 max-w-4xl mx-auto">
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

            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
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
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Insumo / Medicamento (Buscador con Lote)</label>
                        <input list="items_list" name="item_search" required placeholder="Escriba o escanee código de barras..." class="w-full p-2.5 border rounded-xl text-sm bg-blue-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none font-medium">
                        <datalist id="items_list">
                            {% for item in items %}
                                <option value="[ID:{{ item.id }}] {{ item.code }} - {{ item.name }} (Lote: {{ item.lote or 'S/L' }})">Gen: {{ item.stock_general }} | Qx: {{ item.stock_quirofano }} | {{ item.etiqueta }}</option>
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
                                <input type="text" list="patients_datalist" name="patient_name" placeholder="Seleccione o escriba el paciente..." class="w-full p-2 border rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-medium">
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

        {% elif view == 'limpieza' %}
        <div class="space-y-6">
            <div class="bg-gradient-to-br from-teal-900 to-slate-900 text-white p-6 rounded-2xl shadow-md border border-teal-800">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4 border-b border-teal-700/50 pb-3">
                    <div>
                        <h2 class="text-base font-extrabold flex items-center gap-2 text-teal-300">
                            <i class="fa-solid fa-calendar-week text-xl"></i> Rol de Limpieza Semanal Automático
                        </h2>
                        <p class="text-xs text-teal-100/80">Semana Número {{ current_week }} del Año | Asignación rotativa de actividades (Sin Administradores).</p>
                    </div>
                    <span class="px-3 py-1 bg-teal-500/20 text-teal-200 border border-teal-400/30 rounded-full text-xs font-bold">
                        Rotación Activa
                    </span>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                    {% for item in weekly_schedule %}
                    <div class="bg-white/10 backdrop-blur-sm p-3.5 rounded-xl border border-white/10 hover:bg-white/15 transition">
                        <div class="flex items-center gap-2 mb-1.5">
                            <div class="w-7 h-7 rounded-full bg-teal-500/30 text-teal-200 flex items-center justify-center text-xs font-bold">
                                <i class="fa-solid fa-user"></i>
                            </div>
                            <h4 class="font-bold text-xs text-white truncate">{{ item.user.name }}</h4>
                        </div>
                        <p class="text-[10px] text-teal-200 uppercase font-semibold mb-2">{{ item.user.role }}</p>
                        <div class="p-2 bg-teal-950/60 rounded-lg border border-teal-500/30 text-center">
                            <span class="text-xs font-extrabold text-teal-300 block">{{ item.task }}</span>
                        </div>
                    </div>
                    {% else %}
                    <p class="text-xs text-teal-200 italic col-span-full">No hay usuarios operativos registrados para asignar en el rol.</p>
                    {% endfor %}
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-broom text-teal-600"></i> Registrar Limpieza Realizada
                    </h2>

                    <form action="/add_cleaning" method="POST" class="space-y-4">
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Usuario</label>
                                <select name="user_id" required class="w-full p-2.5 border rounded-xl text-xs bg-slate-50 focus:bg-white focus:ring-2 focus:ring-teal-500 outline-none">
                                    <option value="">Seleccione...</option>
                                    {% for u in users %}
                                        <option value="{{ u.id }}">{{ u.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN</label>
                                <input type="password" name="pin" required placeholder="PIN" class="w-full p-2.5 border rounded-xl text-xs focus:ring-2 focus:ring-teal-500 outline-none">
                            </div>
                        </div>

                        <div class="bg-teal-50/60 p-4 rounded-xl border border-teal-100 space-y-3">
                            <h3 class="text-xs font-bold text-teal-900 uppercase border-b border-teal-200 pb-1">
                                Parámetros Ejecutados
                            </h3>

                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer hover:text-teal-900">
                                <input type="checkbox" name="anaqueles" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500 border-slate-300">
                                <span>🧹 Limpieza de Anaqueles</span>
                            </label>

                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer hover:text-teal-900">
                                <input type="checkbox" name="cajones_unidosis" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500 border-slate-300">
                                <span>🗄️ Limpieza de Cajones de Unidosis</span>
                            </label>

                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer hover:text-teal-900">
                                <input type="checkbox" name="acomodo_bodega" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500 border-slate-300">
                                <span>📦 Acomodo de Bodega</span>
                            </label>

                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer hover:text-teal-900">
                                <input type="checkbox" name="carton" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500 border-slate-300">
                                <span>♻️ Gestión / Retiro de Cartón</span>
                            </label>

                            <label class="flex items-center gap-2.5 text-xs font-medium text-slate-700 cursor-pointer hover:text-teal-900">
                                <input type="checkbox" name="cajas_traslado" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500 border-slate-300">
                                <span>🚚 Limpieza de Cajas de Traslado</span>
                            </label>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Notas / Observaciones</label>
                            <input type="text" name="notes" placeholder="Ej. Se sanitizó con solución desinfectante..." class="w-full p-2.5 border rounded-xl text-xs focus:ring-2 focus:ring-teal-500 outline-none">
                        </div>

                        <button type="submit" class="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2">
                            <i class="fa-solid fa-clipboard-check"></i> Guardar Registro
                        </button>
                    </form>
                </div>

                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                    <div class="flex justify-between items-center mb-4 border-b pb-3">
                        <div>
                            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                                <i class="fa-solid fa-list-check text-teal-600"></i> Bitácora de Sanitización
                            </h2>
                            <p class="text-xs text-slate-500">Histórico para auditoría normativa.</p>
                        </div>
                        <button onclick="window.print()" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition flex items-center gap-1.5 no-print">
                            <i class="fa-solid fa-print"></i> Imprimir Bitácora
                        </button>
                    </div>

                    <form action="/limpieza" method="GET" class="flex gap-2 mb-4 bg-teal-50/50 p-3 rounded-xl border border-teal-100 no-print items-end">
                        <div class="flex-1">
                            <label class="block text-[11px] font-bold text-teal-900 uppercase mb-1">Filtrar por Día</label>
                            <input type="date" name="filter_date" value="{{ selected_date }}" class="w-full p-2 border rounded-lg text-xs bg-white font-bold outline-none">
                        </div>
                        <button type="submit" class="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white font-bold rounded-lg text-xs transition">
                            <i class="fa-solid fa-filter"></i> Filtrar
                        </button>
                        <a href="/limpieza" class="px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-lg text-xs transition">
                            Ver Todos
                        </a>
                    </form>

                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left text-slate-600">
                            <thead class="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                                <tr>
                                    <th class="p-2.5">Fecha/Hora</th>
                                    <th class="p-2.5">Responsable</th>
                                    <th class="p-2.5 text-center">Anaqueles</th>
                                    <th class="p-2.5 text-center">Cajones DU</th>
                                    <th class="p-2.5 text-center">Bodega</th>
                                    <th class="p-2.5 text-center">Cartón</th>
                                    <th class="p-2.5 text-center">Cajas Traslado</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for log in cleaning_logs %}
                                <tr class="hover:bg-slate-50">
                                    <td class="p-2.5 font-mono text-slate-500">{{ log.timestamp.strftime('%d/%m/%Y %H:%M') }}</td>
                                    <td class="p-2.5 font-bold text-slate-900">
                                        {{ log.user_name }}
                                        {% if log.notes %}
                                            <span class="block text-[10px] text-slate-400 font-normal italic">{{ log.notes }}</span>
                                        {% endif %}
                                    </td>
                                    <td class="p-2.5 text-center">
                                        {% if log.anaqueles %}<span class="text-emerald-600 text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}
                                    </td>
                                    <td class="p-2.5 text-center">
                                        {% if log.cajones_unidosis %}<span class="text-emerald-600 text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}
                                    </td>
                                    <td class="p-2.5 text-center">
                                        {% if log.acomodo_bodega %}<span class="text-emerald-600 text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}
                                    </td>
                                    <td class="p-2.5 text-center">
                                        {% if log.carton %}<span class="text-emerald-600 text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}
                                    </td>
                                    <td class="p-2.5 text-center">
                                        {% if log.cajas_traslado %}<span class="text-emerald-600 text-sm">✓</span>{% else %}<span class="text-slate-300">-</span>{% endif %}
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="7" class="p-6 text-center text-slate-400 italic">No hay actividades de limpieza registradas.</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
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

        {% elif view == 'controlados' %}
        <div class="space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-1">
                    <h2 class="text-base font-bold text-slate-900 mb-4 border-b pb-2 flex items-center gap-2">
                        <i class="fa-solid fa-file-prescription text-rose-600"></i> Surtir Medicamento Controlado
                    </h2>

                    <form action="/add_controlled" method="POST" class="space-y-3">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Medicamento Controlado (Buscador/Código)</label>
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

                    <form action="/controlados" method="GET" class="flex gap-2 mb-4 bg-rose-50 p-3 rounded-xl border border-rose-100 no-print items-end">
                        <div class="flex-1">
                            <label class="block text-[11px] font-bold text-rose-900 uppercase mb-1">Filtrar por Día</label>
                            <input type="date" name="filter_date" value="{{ selected_date }}" class="w-full p-2 border rounded-lg text-xs bg-white font-bold outline-none">
                        </div>
                        <button type="submit" class="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded-lg text-xs transition">
                            <i class="fa-solid fa-filter"></i> Filtrar Día
                        </button>
                        <a href="/controlados" class="px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold rounded-lg text-xs transition">
                            Ver Todos
                        </a>
                    </form>

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
                                    <th class="p-2.5 text-center no-print">Acción</th>
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
                                    <td class="p-2.5 text-center no-print">
                                        <button onclick="openEditControlledModal('{{ log.id }}', '{{ log.patient_name }}', '{{ log.prescription_num }}', '{{ log.quantity }}', '{{ log.doctor_name or '' }}')" class="px-2 py-1 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded text-[10px] transition shadow-sm">
                                            <i class="fa-solid fa-pen"></i> Editar
                                        </button>
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="7" class="p-6 text-center text-slate-400 italic">No hay registros en la bitácora de medicamentos controlados.</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div id="editControlledModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden flex items-center justify-center p-4 z-50">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100">
                <div class="flex justify-between items-center mb-4 border-b pb-2">
                    <h3 class="font-bold text-base text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-pen-to-square text-amber-500"></i> Editar Registro Controlado
                    </h3>
                    <button onclick="closeEditControlledModal()" class="text-slate-400 hover:text-slate-600 text-lg">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>

                <form action="/update_controlled" method="POST" class="space-y-3">
                    <input type="hidden" name="log_id" id="edit_log_id">

                    <div class="p-3 bg-amber-50 rounded-xl border border-amber-200">
                        <label class="block text-xs font-bold text-amber-900 uppercase mb-1">🔒 PIN Administrador</label>
                        <input type="password" name="admin_pin" required placeholder="Ingrese PIN de Admin" class="w-full p-2 border rounded-lg text-xs bg-white font-bold outline-none">
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre del Paciente</label>
                        <input type="text" name="patient_name" id="edit_patient_name" required class="w-full p-2 border rounded-xl text-xs font-bold">
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">No. Receta / Folio</label>
                        <input type="text" name="prescription_num" id="edit_prescription_num" required class="w-full p-2 border rounded-xl text-xs font-mono font-bold">
                    </div>

                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Cantidad</label>
                            <input type="number" min="1" name="quantity" id="edit_quantity" required class="w-full p-2 border rounded-xl text-xs font-bold">
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Médico Prescriptor</label>
                            <input type="text" name="doctor_name" id="edit_doctor_name" class="w-full p-2 border rounded-xl text-xs">
                        </div>
                    </div>

                    <div class="flex gap-2 pt-3">
                        <button type="button" onclick="closeEditControlledModal()" class="w-1/2 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs transition">Cancelar</button>
                        <button type="submit" class="w-1/2 py-2 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-xl text-xs transition">Guardar Cambios</button>
                    </div>
                </form>
            </div>
        </div>

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
                    <input type="hidden" name="user_id" id="form_user_id">
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Nombre Completo</label>
                        <input type="text" name="name" id="form_user_name" required placeholder="Ej. Dr. Juan Pérez" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">Rol / Cargo</label>
                        <select name="role" id="form_user_role" required class="w-full p-2.5 border rounded-xl text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none">
                            <option value="Enfermería Quirófano">Enfermería Quirófano</option>
                            <option value="Enfermería Urgencias">Enfermería Urgencias</option>
                            <option value="Médico Anestesiólogo">Médico Anestesiólogo</option>
                            <option value="Farmacéutico">Farmacéutico</option>
                            <option value="Administrador">Administrador</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-600 uppercase mb-1">PIN / Contraseña de Seguridad</label>
                        <input type="password" name="pin" id="form_user_pin" required placeholder="••••" class="w-full p-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    </div>

                    <div class="flex gap-2">
                        <button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition duration-200 flex items-center justify-center gap-2">
                            <i class="fa-solid fa-user-check"></i> Guardar Usuario
                        </button>
                        <button type="button" onclick="resetUserForm()" class="bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold px-3 rounded-xl text-xs">
                            Limpiar
                        </button>
                    </div>
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
                            <span class="text-[10px] text-slate-400">PIN: ••••</span>
                        </div>
                        <button onclick="editUser('{{ u.id }}', '{{ u.name }}', '{{ u.role }}')" class="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-lg text-xs font-bold transition flex items-center gap-1">
                            <i class="fa-solid fa-user-pen"></i> Editar
                        </button>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        {% endif %}

        {% elif view == 'etiquetas' %}
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

        function openEditModal(id, code, name, category, via, presentacion, lote, caducidad, unit, general, quirofano, etiqueta) {
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
            document.getElementById('edit_etiqueta').value = etiqueta || 'Ninguna';
            document.getElementById('editModal').classList.remove('hidden');
        }

        function closeEditModal() {
            document.getElementById('editModal').classList.add('hidden');
        }

        function openEditControlledModal(id, patient, prescription, quantity, doctor) {
            document.getElementById('edit_log_id').value = id;
            document.getElementById('edit_patient_name').value = patient;
            document.getElementById('edit_prescription_num').value = prescription;
            document.getElementById('edit_quantity').value = quantity;
            document.getElementById('edit_doctor_name').value = doctor;
            document.getElementById('editControlledModal').classList.remove('hidden');
        }

        function closeEditControlledModal() {
            document.getElementById('editControlledModal').classList.add('hidden');
        }

        function editUser(id, name, role) {
            document.getElementById('form_user_id').value = id;
            document.getElementById('form_user_name').value = name;
            document.getElementById('form_user_role').value = role;
            document.getElementById('form_user_pin').value = '';
            document.getElementById('form_user_name').focus();
        }

        function resetUserForm() {
            document.getElementById('form_user_id').value = '';
            document.getElementById('form_user_name').value = '';
            document.getElementById('form_user_role').value = 'Enfermería Quirófano';
            document.getElementById('form_user_pin').value = '';
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

@app.route("/alta_insumos")
def alta_insumos():
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="alta_insumos", users=users, patients=patients)

@app.route("/limpieza")
def limpieza():
    filter_date = request.args.get("filter_date", "").strip()
    query = CleaningLog.query

    if filter_date:
        try:
            target_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
            query = query.filter(db.func.date(CleaningLog.timestamp) == target_date)
        except ValueError:
            pass

    cleaning_logs = query.order_by(CleaningLog.timestamp.desc()).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()

    current_week = datetime.now(LOCAL_TZ).isocalendar()[1]
    non_admin_users = [u for u in users if "admin" not in u.role.lower()]
    
    tasks = [
        "🧹 Limpieza de Anaqueles",
        "🗄️ Cajones de Unidosis",
        "📦 Acomodo de Bodega",
        "♻️ Gestión de Cartón",
        "🚚 Cajas de Traslado"
    ]

    weekly_schedule = []
    if non_admin_users:
        for idx, user in enumerate(non_admin_users):
            task_idx = (idx + current_week) % len(tasks)
            weekly_schedule.append({
                "user": user,
                "task": tasks[task_idx]
            })

    return render_template_string(
        HTML_TEMPLATE,
        view="limpieza",
        cleaning_logs=cleaning_logs,
        users=users,
        patients=patients,
        selected_date=filter_date,
        weekly_schedule=weekly_schedule,
        current_week=current_week
    )

@app.route("/add_cleaning", methods=["POST"])
def add_cleaning():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin", "").strip()
    anaqueles = 'anaqueles' in request.form
    cajones_unidosis = 'cajones_unidosis' in request.form
    acomodo_bodega = 'acomodo_bodega' in request.form
    carton = 'carton' in request.form
    cajas_traslado = 'cajas_traslado' in request.form
    notes = request.form.get("notes", "").strip()

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN de seguridad incorrecto.", "error")
        return redirect(url_for("limpieza"))

    new_log = CleaningLog(
        timestamp=get_local_now(),
        user_name=user.name,
        anaqueles=anaqueles,
        cajones_unidosis=cajones_unidosis,
        acomodo_bodega=acomodo_bodega,
        carton=carton,
        cajas_traslado=cajas_traslado,
        notes=notes
    )
    db.session.add(new_log)
    db.session.commit()

    flash("Registro de limpieza y sanitización guardado correctamente.", "success")
    return redirect(url_for("limpieza"))

@app.route("/inventario")
def inventario():
    items = Item.query.order_by(Item.name, Item.lote).all()
    patients = Patient.query.order_by(Patient.name).all()
    today_str = datetime.now(LOCAL_TZ).date().isoformat()
    warning_str = (datetime.now(LOCAL_TZ).date() + timedelta(days=30)).isoformat()
    return render_template_string(HTML_TEMPLATE, view="inventario", items=items, today_str=today_str, warning_str=warning_str, patients=patients)

@app.route("/controlados")
def controlados():
    filter_date = request.args.get("filter_date", "").strip()
    query = ControlledLog.query

    if filter_date:
        try:
            target_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
            query = query.filter(db.func.date(ControlledLog.timestamp) == target_date)
        except ValueError:
            pass

    controlled_items = Item.query.filter_by(etiqueta="Controlado").order_by(Item.name).all()
    controlled_logs = query.order_by(ControlledLog.timestamp.desc()).all()
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()

    return render_template_string(
        HTML_TEMPLATE, 
        view="controlados", 
        controlled_items=controlled_items, 
        controlled_logs=controlled_logs, 
        users=users, 
        patients=patients,
        selected_date=filter_date
    )

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

@app.route("/update_controlled", methods=["POST"])
def update_controlled():
    admin_pin = request.form.get("admin_pin")
    admin_user = User.query.filter_by(role="Administrador").first()

    if admin_pin != "5678" and (not admin_user or admin_user.pin != admin_pin):
        flash("❌ Acceso denegado: PIN de Administrador incorrecto.", "error")
        return redirect(url_for("controlados"))

    log_id = request.form.get("log_id")
    log = ControlledLog.query.get(log_id)
    if not log:
        flash("Registro no encontrado.", "error")
        return redirect(url_for("controlados"))

    log.patient_name = request.form.get("patient_name", "").strip()
    log.prescription_num = request.form.get("prescription_num", "").strip()
    log.quantity = int(request.form.get("quantity", 1))
    log.doctor_name = request.form.get("doctor_name", "").strip()

    db.session.commit()
    flash(f"✅ Registro de bitácora modificado correctamente por el Administrador.", "success")
    return redirect(url_for("controlados"))

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
    patients = Patient.query.order_by(Patient.name).all()

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
        total_traspasos=total_traspasos,
        patients=patients
    )

@app.route("/usuarios")
def usuarios():
    users = User.query.order_by(User.name).all()
    patients = Patient.query.order_by(Patient.name).all()
    is_admin = request.args.get("admin") == "true"
    return render_template_string(HTML_TEMPLATE, view="usuarios", users=users, is_admin=is_admin, patients=patients)

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
    etiqueta = request.form.get("etiqueta", "Ninguna")
    unit = request.form.get("unit", "pza").strip()
    stock_general = int(request.form.get("stock_general", 0))

    try:
        existing_item = Item.query.filter_by(code=code, lote=lote).first()

        if existing_item:
            existing_item.stock_general += stock_general
            if caducidad:
                existing_item.caducidad = caducidad
            if etiqueta and etiqueta != "Ninguna":
                existing_item.etiqueta = etiqueta
            flash(f"Se sumaron {stock_general} {unit} al lote existente '{lote or 'S/L'}' del código {code}.", "success")
        else:
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
            flash(f"Nuevo lote registrado exitosamente para '{name}' (Código: {code}, Lote: '{lote or 'S/L'}').", "success")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Error al registrar el lote: {str(e)}", "error")

    return redirect(url_for("alta_insumos"))

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
    item.etiqueta = request.form.get("etiqueta", "Ninguna")
    item.unit = request.form.get("unit", "pza").strip()
    item.stock_general = int(request.form.get("stock_general", 0))
    item.stock_quirofano = int(request.form.get("stock_quirofano", 0))

    db.session.commit()
    flash(f"✅ Insumo '{item.name}' actualizado correctamente por el Administrador.", "success")
    return redirect(url_for("inventario"))

@app.route("/save_user", methods=["POST"])
def save_user():
    user_id = request.form.get("user_id")
    name = request.form.get("name", "").strip()
    role = request.form.get("role")
    pin = request.form.get("pin", "").strip()

    if not name or not pin:
        flash("Complete todos los campos requeridos.", "error")
        return redirect(url_for("usuarios", admin="true"))

    if user_id:
        user = User.query.get(user_id)
        if user:
            user.name = name
            user.role = role
            user.pin = pin
            flash(f"Usuario {name} actualizado con éxito por el Administrador.", "success")
    else:
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
    patients = Patient.query.order_by(Patient.name).all()
    return render_template_string(HTML_TEMPLATE, view="etiquetas", patients=patients)

@app.route("/register", methods=["POST"])
def register_movement():
    user_id = request.form.get("user_id")
    pin = request.form.get("pin")
    item_search = request.form.get("item_search", "").strip()
    mov_type = request.form.get("type")
    warehouse = request.form.get("warehouse")
    quantity = int(request.form.get("quantity", 1))
    service = request.form.get("service")
    patient_name = request.form.get("patient_name", "").strip()
    patient_id = request.form.get("patient_id")
    notes = request.form.get("notes")

    user = User.query.get(user_id)
    if not user or user.pin != pin:
        flash("PIN o contraseña de usuario incorrecta.", "error")
        return redirect(url_for("terminal"))

    if patient_name:
        existing_patient = Patient.query.filter_by(name=patient_name).first()
        if not existing_patient:
            new_p = Patient(name=patient_name)
            db.session.add(new_p)

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
        flash("Insumo o lote no encontrado. Seleccione una opción válida del buscador.", "error")
        return redirect(url_for("terminal"))

    if mov_type == "Entrada":
        if warehouse == "Almacén General":
            item.stock_general += quantity
        else:
            item.stock_quirofano += quantity

    elif mov_type == "Salida":
        if warehouse == "Almacén General":
            if item.stock_general < quantity:
                flash(f"Stock insuficiente en Almacén General ({item.stock_general} disponibles en el lote '{item.lote or 'S/L'}').", "error")
                return redirect(url_for("terminal"))
            item.stock_general -= quantity
        else:
            if item.stock_quirofano < quantity:
                flash(f"Stock insuficiente en Quirófano ({item.stock_quirofano} disponibles en el lote '{item.lote or 'S/L'}').", "error")
                return redirect(url_for("terminal"))
            item.stock_quirofano -= quantity

    elif mov_type == "Traspaso Qx":
        if item.stock_general < quantity:
            flash(f"Stock insuficiente en Almacén General ({item.stock_general} disponibles) para el traspaso.", "error")
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
    db.session.commit()

    flash(f"Movimiento de '{item.name}' (Lote: {item.lote or 'S/L'}) guardado exitosamente.", "success")
    return redirect(url_for("terminal"))

# -----------------------------------------------------------------------------
# DATOS SEMILLA E INICIALIZACIÓN DE MIGRACIONES AUTOMÁTICAS
# -----------------------------------------------------------------------------

def seed_database():
    with app.app_context():
        db.create_all()

        try:
            db.session.execute(text("ALTER TABLE item DROP CONSTRAINT IF EXISTS item_code_key;"))
            db.session.execute(text("DROP INDEX IF EXISTS item_code_key;"))
            
            db.session.execute(text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS patient_name VARCHAR(150);"))
            db.session.execute(text("ALTER TABLE movement ADD COLUMN IF NOT EXISTS patient_id VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS via_administracion VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS presentacion VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS lote VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS caducidad VARCHAR(20);"))
            db.session.execute(text("ALTER TABLE item ADD COLUMN IF NOT EXISTS etiqueta VARCHAR(50);"))
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
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", via_administracion="Oral", presentacion="Tableta", lote="LOT-9821", caducidad="2027-12-31", etiqueta="Ninguna", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-4410", caducidad="2027-08-15", etiqueta="Alto Riesgo", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", via_administracion="Intravenosa", presentacion="Ampolleta", lote="LOT-1102", caducidad="2026-11-20", etiqueta="Controlado", stock_general=30, stock_quirofano=10),
                Item(code="MAT-001", name="Jeringa 10ml c/Aguja", category="Material Curación", via_administracion="N/A", presentacion="Otro", lote="LOT-0012", caducidad="2028-05-01", etiqueta="Ninguna", stock_general=300, stock_quirofano=50),
                Item(code="MAT-002", name="Equipo Venoclisis Normogotero", category="Material Curación", via_administracion="N/A", presentacion="Otro", lote="LOT-0099", caducidad="2028-01-10", etiqueta="Ninguna", stock_general=100, stock_quirofano=25)
            ]
            db.session.add_all(items_list)

        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
