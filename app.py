import os
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "farmacia_secret_key_123")

# Configuración de Base de Datos (Adaptada para PostgreSQL / psycopg2)
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
    role = db.Column(db.String(50), nullable=False)  # Administrador / Personal
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
    id = db.Column(db.Integer, primary_primary=True, primary_key=True)
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
# PLANTILLA HTML INTEGRADA
# -----------------------------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farmacia Hospitalaria - Control e Inventario</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen text-gray-800">
    
    <!-- Encabezado y Navegación -->
    <header class="bg-blue-900 text-white shadow-md">
        <div class="max-w-7xl mx-auto p-4 flex flex-col md:flex-row justify-between items-center gap-4">
            <div>
                <h1 class="text-2xl font-bold">🏥 Farmacia Hospitalaria</h1>
                <p class="text-xs text-blue-200">Terminal Compartida de Captura e Inventario Multi-Almacén</p>
            </div>
            
            <nav class="flex gap-2 text-sm font-semibold">
                <a href="/terminal{% if is_admin %}?admin=true{% endif %}" class="px-3 py-1.5 rounded bg-blue-800 hover:bg-blue-700">📋 Captura</a>
                <a href="/etiquetas" class="px-3 py-1.5 rounded bg-blue-800 hover:bg-blue-700">🏷️ Etiquetas DU</a>
            </nav>
        </div>
    </header>

    <div class="max-w-7xl mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        <!-- Mensajes Flash -->
        <div class="lg:col-span-3">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="p-4 mb-2 text-sm rounded-lg {% if category == 'error' %}bg-red-100 text-red-800 border border-red-300{% else %}bg-green-100 text-green-800 border border-green-300{% endif %}">
                    {{ message }}
                  </div>
                {% endfor %}
              {% endif %}
            {% endwith %}
        </div>

        {% if view == 'terminal' %}
        <!-- FORMULARIO DE CAPTURA COMPARTIDO -->
        <div class="bg-white p-6 rounded-xl shadow-md border border-gray-200 lg:col-span-1">
            <h2 class="text-lg font-bold text-blue-900 mb-4 border-b pb-2">📋 Registrar Movimiento</h2>
            <form action="/register" method="POST" class="space-y-4">
                
                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase">Personal / Usuario Autorizado</label>
                    <select name="user_id" required class="w-full mt-1 p-2 border rounded-md text-sm bg-gray-50">
                        <option value="">Seleccione Personal...</option>
                        {% for user in users %}
                            <option value="{{ user.id }}">{{ user.name }} ({{ user.role }})</option>
                        {% endfor %}
                    </select>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase">PIN de Verificación</label>
                    <input type="password" name="pin" required placeholder="Ingrese PIN personal" class="w-full mt-1 p-2 border rounded-md text-sm">
                </div>

                <!-- BUSCADOR INTERACTIVO DE INSUMO -->
                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase">Insumo / Medicamento (Buscador)</label>
                    <input list="items_list" name="item_search" required placeholder="Escriba nombre, clave o escanee código..." class="w-full mt-1 p-2 border rounded-md text-sm bg-blue-50 focus:bg-white border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <datalist id="items_list">
                        {% for item in items %}
                            <option value="{{ item.code }} - {{ item.name }}">General: {{ item.stock_general }} | Qx: {{ item.stock_quirofano }}</option>
                        {% endfor %}
                    </datalist>
                    <span class="text-[10px] text-gray-500">Escanee el código de barras o busque por descripción.</span>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase">Tipo de Movimiento</label>
                    <select name="type" required class="w-full mt-1 p-2 border rounded-md text-sm bg-gray-50">
                        <option value="Salida">Salida a Servicio / Paciente</option>
                        <option value="Traspaso Qx">Traspaso a Quirófano</option>
                        <option value="Entrada">Entrada (Abastecimiento)</option>
                    </select>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase">Almacén Origen/Destino</label>
                    <select name="warehouse" required class="w-full mt-1 p-2 border rounded-md text-sm bg-gray-50">
                        <option value="Almacén General">Almacén General</option>
                        <option value="Quirófano">Subalmacén Quirófano</option>
                    </select>
                </div>

                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 uppercase">Cantidad</label>
                        <input type="number" min="1" name="quantity" required value="1" class="w-full mt-1 p-2 border rounded-md text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 uppercase">Servicio / Cama</label>
                        <input type="text" name="service" placeholder="Ej. Urgencias / Cama 4" class="w-full mt-1 p-2 border rounded-md text-sm">
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-gray-600 uppercase">Notas adicionales</label>
                    <input type="text" name="notes" placeholder="Observaciones..." class="w-full mt-1 p-2 border rounded-md text-sm">
                </div>

                <button type="submit" class="w-full bg-blue-800 hover:bg-blue-900 text-white font-bold py-2.5 rounded-md transition duration-200">
                    Registrar Movimiento
                </button>
            </form>
        </div>

        <!-- VISTA DE EXISTENCIAS Y REPORTE RESTRINGIDO -->
        <div class="space-y-6 lg:col-span-2">
            
            <!-- Existencias Generales -->
            <div class="bg-white p-6 rounded-xl shadow-md border border-gray-200">
                <h2 class="text-lg font-bold text-blue-900 mb-4 border-b pb-2">📦 Existencias en Almacén</h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-sm text-left text-gray-600">
                        <thead class="text-xs text-gray-700 uppercase bg-gray-50 border-b">
                            <tr>
                                <th class="p-2">Código</th>
                                <th class="p-2">Descripción</th>
                                <th class="p-2">Categoría</th>
                                <th class="p-2 text-center">Almacén General</th>
                                <th class="p-2 text-center">Quirófano</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for item in items %}
                            <tr class="border-b hover:bg-gray-50">
                                <td class="p-2 font-mono text-xs font-bold text-blue-900">{{ item.code }}</td>
                                <td class="p-2 font-medium text-gray-900">{{ item.name }}</td>
                                <td class="p-2">
                                    <span class="px-2 py-0.5 rounded-full text-xs font-semibold {% if item.category == 'Medicamento' %}bg-purple-100 text-purple-800{% else %}bg-amber-100 text-amber-800{% endif %}">
                                        {{ item.category }}
                                    </span>
                                </td>
                                <td class="p-2 text-center font-bold">{{ item.stock_general }} {{ item.unit }}</td>
                                <td class="p-2 text-center font-bold">{{ item.stock_quirofano }} {{ item.unit }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- BITÁCORA Y REPORTE RESTRINGIDO PARA ADMINISTRADOR -->
            <div class="bg-white p-6 rounded-xl shadow-md border border-gray-200">
                <div class="flex justify-between items-center mb-4 border-b pb-2">
                    <h2 class="text-lg font-bold text-blue-900">🔒 Bitácora de Movimientos y Reporte Diario</h2>
                </div>

                {% if is_admin %}
                <div class="overflow-x-auto">
                    <table class="w-full text-xs text-left text-gray-600">
                        <thead class="text-xs text-gray-700 uppercase bg-gray-50 border-b">
                            <tr>
                                <th class="p-2">Fecha/Hora</th>
                                <th class="p-2">Tipo</th>
                                <th class="p-2">Insumo</th>
                                <th class="p-2 text-center">Cant.</th>
                                <th class="p-2">Servicio</th>
                                <th class="p-2">Responsable</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for mov in movements %}
                            <tr class="border-b hover:bg-gray-50">
                                <td class="p-2 text-gray-500">{{ mov.timestamp.strftime('%d/%m %H:%M') }}</td>
                                <td class="p-2 font-semibold">{{ mov.type }}</td>
                                <td class="p-2 font-medium text-gray-800">{{ mov.item_name }}</td>
                                <td class="p-2 text-center font-bold">{{ mov.quantity }}</td>
                                <td class="p-2 text-gray-500">{{ mov.service or 'N/A' }}</td>
                                <td class="p-2 font-semibold text-gray-700">{{ mov.user_name }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="p-6 text-center bg-gray-50 rounded-lg border border-dashed border-gray-300">
                    <p class="text-sm text-gray-500">🔒 <strong>Acceso Restringido:</strong> La bitácora y reporte diario solo son visibles para el personal con rol de <strong>Administrador / Farmacia Titular</strong> al autenticarse.</p>
                </div>
                {% endif %}
            </div>

        </div>

        {% elif view == 'etiquetas' %}
        <!-- PESTAÑA GENERACIÓN DE ETIQUETAS DU -->
        <div class="bg-white p-6 rounded-xl shadow-md border border-gray-200 lg:col-span-3">
            <h2 class="text-xl font-bold text-blue-900 mb-2">🏷️ Módulo de Etiquetas de Dosis Unitaria</h2>
            <p class="text-sm text-gray-600 mb-6">Sección para generación e impresión estandarizada de etiquetas.</p>
            
            <div class="p-8 border-2 border-dashed border-blue-200 rounded-lg text-center bg-blue-50">
                <p class="text-gray-700 font-semibold mb-2">📄 Plantilla Integrada</p>
                <p class="text-xs text-gray-500 max-w-md mx-auto">Próximamente podrás seleccionar cualquier medicamento del catálogo e imprimir sus etiquetas en formato estándar de Dosis Unitaria.</p>
            </div>
        </div>
        {% endif %}

    </div>
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
    
    # Comprobar estado de administrador
    is_admin = request.args.get("admin") == "true"
    
    return render_template_string(HTML_TEMPLATE, view="terminal", items=items, users=users, movements=movements, is_admin=is_admin)

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
        flash("❌ PIN o Contraseña incorrectos.", "error")
        return redirect(url_for("terminal"))

    # Buscar insumo por clave/código
    item_code = item_search.split(" - ")[0] if " - " in item_search else item_search
    item = Item.query.filter((Item.code == item_code) | (Item.name.ilike(f"%{item_search}%"))).first()

    if not item:
        flash("❌ Insumo no encontrado. Seleccione una opción válida del buscador.", "error")
        return redirect(url_for("terminal"))

    # Procesar Lógica de Inventario
    if mov_type == "Entrada":
        if warehouse == "Almacén General":
            item.stock_general += quantity
        else:
            item.stock_quirofano += quantity

    elif mov_type == "Salida":
        if warehouse == "Almacén General":
            if item.stock_general < quantity:
                flash(f"❌ Stock insuficiente en Almacén General ({item.stock_general} disponibles).", "error")
                return redirect(url_for("terminal"))
            item.stock_general -= quantity
        else:
            if item.stock_quirofano < quantity:
                flash(f"❌ Stock insuficiente en Quirófano ({item.stock_quirofano} disponibles).", "error")
                return redirect(url_for("terminal"))
            item.stock_quirofano -= quantity

    elif mov_type == "Traspaso Qx":
        if item.stock_general < quantity:
            flash("❌ Stock insuficiente en Almacén General para el traspaso.", "error")
            return redirect(url_for("terminal"))
        item.stock_general -= quantity
        item.stock_quirofano += quantity

    # Registrar en Bitácora
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

    # Si quien registra es Administrador, mantenemos la vista activa
    is_admin_param = "?admin=true" if user.role == "Administrador" else ""
    flash("✅ Movimiento registrado correctamente.", "success")
    return redirect(url_for("terminal") + is_admin_param)

# -----------------------------------------------------------------------------
# INICIALIZACIÓN DE DATOS SEMILLA (PERSONAL E INVENTARIO)
# -----------------------------------------------------------------------------

def seed_database():
    with app.app_context():
        db.create_all()
        
        # Restauración y Población de Personal
        if User.query.count() == 0:
            users_list = [
                User(name="David Gonzalez Mendoza", role="Administrador", pin="5678"),
                User(name="Hannia Martinez Salas", role="Enfermera Quirófano", pin="1234"),
                User(name="Carlos Rivera López", role="Enfermero Urgencias", pin="1111"),
                User(name="Dra. María Elena Castro", role="Anestesióloga", pin="2222"),
                User(name="Dra. Sofia Ramos", role="Farmacia Titular", pin="4321")
            ]
            db.session.add_all(users_list)

        # Inventario de Muestra
        if Item.query.count() == 0:
            items_list = [
                Item(code="MED-001", name="Paracetamol 500mg Tab", category="Medicamento", stock_general=150, stock_quirofano=20),
                Item(code="MED-002", name="Propofol 200mg/20ml Amp", category="Medicamento", stock_general=40, stock_quirofano=15),
                Item(code="MED-003", name="Fentanilo 0.5mg/10ml Amp", category="Medicamento", stock_general=30, stock_quirofano=10),
                Item(code="MAT-001", name="Jeringa 10ml c/Aguja", category="Material", stock_general=300, stock_quirofano=50),
                Item(code="MAT-002", name="Equipo de Venoclisis Normogotero", category="Material", stock_general=100, stock_quirofano=25)
            ]
            db.session.add_all(items_list)

        db.session.commit()

seed_database()

if __name__ == "__main__":
    app.run(debug=True)
