from flask import Flask, render_template_string, request, redirect, url_for, flash
import datetime

app = Flask(__name__)
app.secret_key = "hospital_pharmacy_secret_key"

USERS = [
    {"username": "admin", "password": "1234", "name": "David Gonzalez Mendoza", "role": "Administrador"},
    {"username": "esteban", "password": "5678", "name": "Esteban Medina Fiesco", "role": "Farmacéutico"},
    {"username": "hannia", "password": "9876", "name": "Hannia Martinez Salas", "role": "Farmacéutico"},
    {"username": "patricia", "password": "1122", "name": "Patricia Manzano Leon", "role": "Farmacéutico"},
    {"username": "juan", "password": "1123", "name": "Juan Isai Maldonado Pelaez", "role": "Farmacéutico"},
    {"username": "maria", "password": "1124", "name": "Maria Fernanda Moran Sanchez", "role": "Farmacéutico"},
    {"username": "alfonso", "password": "1125", "name": "Alfonso Salvador Guzman Reyes", "role": "Farmacéutico"},
    {"username": "mabel", "password": "1126", "name": "Mabel Iris Morales Marin", "role": "Farmacéutico"},
    {"username": "victor", "password": "1127", "name": "Victor Silva Guani", "role": "Farmacéutico"},
    {"username": "carolina", "password": "1128", "name": "Carolina Perez Allende Perez", "role": "Farmacéutico"},
    {"username": "cintia", "password": "1129", "name": "Cintia Citlali Maximo Amador", "role": "Farmacéutico"},
    {"username": "antonio", "password": "1130", "name": "Antonio Jose Manuel", "role": "Farmacéutico"},
    {"username": "jessica", "password": "1131", "name": "Jessica Joseline Solano Tolentino", "role": "Farmacéutico"},
    {"username": "josue", "password": "1132", "name": "Josue Valdemar Estrada Arreola", "role": "Farmacéutico"},
    {"username": "brenda", "password": "1133", "name": "Brenda Toledano", "role": "Farmacéutico"}
]

WAREHOUSES = [
    "Farmacia Central",
    "Almacén General",
    "Subalmacén Quirófano",
    "Subalmacén Urgencias",
    "Farmacia Hospitalización"
]

CLINICAL_SERVICES = [
    "Cuarto piso",
    "Tercer piso",
    "Segundo piso",
    "Tercer anexo",
    "Quirófano",
    "Urgencias",
    "Choque",
    "Terapia intensiva",
    "Cunero patológico",
    "Cunero intermedio",
    "Pediatría",
    "Inhaloterapia",
    "Dirección medica",
    "Personal obregon",
    "Farmacia Central"
]

INVENTORY = [
    {
        "code": "7506358400408", 
        "name": "LINEZOLID", 
        "category": "Medicamento",
        "presentation": "2 mg / ml", 
        "via": "Intravenosa", 
        "lote": "100525", 
        "caducidad": "2027-01-04", 
        "min_stock": 5,
        "stocks": {
            "Farmacia Central": 6,
            "Almacén General": 0,
            "Subalmacén Quirófano": 0,
            "Subalmacén Urgencias": 0,
            "Farmacia Hospitalización": 0
        },
        "entradas_total": 7,
        "salidas_total": 1
    }
]

MOVEMENTS = [
    {
        "date": "2026-10-16", 
        "time": "13:52:45", 
        "code": "7506358400408", 
        "name": "LINEZOLID", 
        "category": "Medicamento",
        "type": "ENTRADA", 
        "qty": 7, 
        "service": "Ingreso a [Farmacia Central]", 
        "patient": "N/A", 
        "user": "Hannia Martinez Salas", 
        "reason": "Recepción inicial"
    },
    {
        "date": "2026-10-16", 
        "time": "13:55:28", 
        "code": "7506358400408", 
        "name": "LINEZOLID", 
        "category": "Medicamento",
        "type": "SALIDA", 
        "qty": 1, 
        "service": "Hospitalización (desde Farmacia Central)", 
        "patient": "1235 pens", 
        "user": "Hannia Martinez Salas", 
        "reason": "Surtido receta"
    }
]

@app.route("/", methods=["GET", "POST"])
@app.route("/terminal", methods=["GET", "POST"])
def terminal():
    if request.method == "POST":
        user_select = request.form.get("user_select", "").strip()
        password_input = request.form.get("password_input", "").strip()
        
        user_auth = next((u for u in USERS if u["username"] == user_select and u["password"] == password_input), None)
        if not user_auth:
            flash("⚠️ Autenticación fallida: Verifique el usuario seleccionado y la contraseña.", "danger")
            return redirect(url_for("terminal"))
        
        tipo_mov = request.form.get("tipo_mov", "SALIDA")
        codigo = request.form.get("codigo", "").strip()
        
        try:
            qty = int(request.form.get("qty", 1))
            if qty <= 0:
                raise ValueError
        except ValueError:
            flash("⚠️ La cantidad debe ser un número entero mayor a cero.", "danger")
            return redirect(url_for("terminal"))
            
        service_or_source = request.form.get("service", "Farmacia Central")
        patient = request.form.get("patient", "").strip() or "N/A"
        reason = request.form.get("reason", "").strip()
        
        if not codigo:
            flash("⚠️ Debe ingresar o escanear un código de barras.", "danger")
            return redirect(url_for("terminal"))

        item = next((i for i in INVENTORY if i["code"] == codigo), None)
        
        if not item:
            if tipo_mov != "ENTRADA":
                flash(f"⚠️ El código {codigo} no existe en inventario. Para darlo de alta debe seleccionar ENTRADA.", "danger")
                return redirect(url_for("terminal"))
            
            med_name = request.form.get("name", "").strip()
            if not med_name:
                flash("⚠️ Para registrar un ítem NUEVO debe colocar el Nombre.", "danger")
                return redirect(url_for("terminal"))
                
            category = request.form.get("category", "Medicamento")
            presentation = request.form.get("presentation", "").strip() or "General"
            via = request.form.get("via", "").strip() or "N/A"
            lote = request.form.get("lote", "").strip() or "LOT-N/A"
            caducidad = request.form.get("caducidad", "").strip() or "2028-12-31"
            
            try:
                min_stock = int(request.form.get("min_stock", 5))
            except ValueError:
                min_stock = 5
                
            item = {
                "code": codigo,
                "name": med_name.upper(),
                "category": category,
                "presentation": presentation,
                "via": via,
                "lote": lote,
                "caducidad": caducidad,
                "min_stock": min_stock,
                "stocks": {w: 0 for w in WAREHOUSES},
                "entradas_total": 0,
                "salidas_total": 0
            }
            INVENTORY.append(item)
        
        now = datetime.datetime.now()
        
        if tipo_mov == "ENTRADA":
            target_warehouse = request.form.get("target_warehouse", "Farmacia Central")
            item["stocks"][target_warehouse] += qty
            item["entradas_total"] += qty
            if not reason:
                reason = "Recepción de insumo"
                
            MOVEMENTS.append({
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "code": codigo,
                "name": item["name"],
                "category": item["category"],
                "type": "ENTRADA",
                "qty": qty,
                "service": f"Ingreso a [{target_warehouse}]",
                "patient": "N/A",
                "user": user_auth["name"],
                "reason": reason
            })
            
        elif tipo_mov == "SALIDA":
            source_wh = request.form.get("source_warehouse", "Farmacia Central")
            if item["stocks"][source_wh] < qty:
                flash(f"⚠️ Stock insuficiente en '{source_wh}'. Disponible: {item['stocks'][source_wh]} unidades.", "danger")
                return redirect(url_for("terminal"))
                
            item["stocks"][source_wh] -= qty
            item["salidas_total"] += qty
            if not reason:
                reason = "Surtido receta / servicio"
                
            MOVEMENTS.append({
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "code": codigo,
                "name": item["name"],
                "category": item["category"],
                "type": "SALIDA",
                "qty": qty,
                "service": f"{service_or_source} (desde {source_wh})",
                "patient": patient,
                "user": user_auth["name"],
                "reason": reason
            })
            
        elif tipo_mov == "TRASPASO":
            origin_wh = request.form.get("origin_warehouse", "Farmacia Central")
            dest_wh = request.form.get("dest_warehouse", "Subalmacén Quirófano")
            
            if origin_wh == dest_wh:
                flash("⚠️ El almacén de origen y destino no pueden ser iguales.", "danger")
                return redirect(url_for("terminal"))
                
            if item["stocks"][origin_wh] < qty:
                flash(f"⚠️ Stock insuficiente en origen ('{origin_wh}'). Disponible: {item['stocks'][origin_wh]} unidades.", "danger")
                return redirect(url_for("terminal"))
                
            item["stocks"][origin_wh] -= qty
            item["stocks"][dest_wh] += qty
            
            full_reason = f"Traspaso de [{origin_wh}] a [{dest_wh}]. {reason}".strip()
            MOVEMENTS.append({
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "code": codigo,
                "name": item["name"],
                "category": item["category"],
                "type": "TRASPASO",
                "qty": qty,
                "service": f"{origin_wh} ➔ {dest_wh}",
                "patient": "Traspaso Almacenes",
                "user": user_auth["name"],
                "reason": full_reason
            })
            
        flash(f"✅ ¡{tipo_mov} de {qty} unidad(es) de [{item['category']}] procesada y guardada exitosamente!", "success")
        return redirect(url_for("terminal"))
        
    return render_template_string(TERMINAL_TEMPLATE, users=USERS, warehouses=WAREHOUSES, services=CLINICAL_SERVICES)

@app.route("/inventory")
def inventory():
    search_query = request.args.get("q", "").strip().lower()
    cat_filter = request.args.get("category", "TODOS")
    
    filtered_inventory = []
    for item in INVENTORY:
        total_stock = sum(item["stocks"].values())
        item["current_stock"] = total_stock
        if total_stock <= 0:
            item["status"] = "AGOTADO"
        elif total_stock <= item["min_stock"]:
            item["status"] = "STOCK BAJO"
        else:
            item["status"] = "DISPONIBLE"
            
        match_cat = (cat_filter == "TODOS" or item["category"] == cat_filter)
        match_query = (not search_query or search_query in item["name"].lower() or search_query in item["code"].lower() or search_query in item["lote"].lower())
        
        if match_cat and match_query:
            filtered_inventory.append(item)
            
    return render_template_string(INVENTORY_TEMPLATE, inventory=filtered_inventory, warehouses=WAREHOUSES, search_query=search_query, current_category=cat_filter)

@app.route("/movements")
def movements():
    search_query = request.args.get("q", "").strip().lower()
    
    filtered_movements = []
    for m in MOVEMENTS:
        match_query = (not search_query or 
                       search_query in m["name"].lower() or 
                       search_query in m["code"].lower() or 
                       search_query in m.get("patient", "").lower() or 
                       search_query in m.get("user", "").lower() or
                       search_query in m.get("service", "").lower())
        if match_query:
            filtered_movements.append(m)
            
    return render_template_string(MOVEMENTS_TEMPLATE, movements=reversed(filtered_movements), search_query=search_query)

@app.route("/reporte")
def reporte():
    cat_filter = request.args.get("category", "TODOS")
    search_query = request.args.get("q", "").strip().lower()
    
    salidas_y_traspasos = [m for m in MOVEMENTS if m["type"] in ["SALIDA", "TRASPASO"]]
    
    if cat_filter != "TODOS":
        salidas_y_traspasos = [m for m in salidas_y_traspasos if m.get("category", "Medicamento") == cat_filter]
        
    if search_query:
        salidas_y_traspasos = [m for m in salidas_y_traspasos if search_query in m["name"].lower() or search_query in m["code"].lower() or search_query in m.get("patient", "").lower() or search_query in m.get("service", "").lower()]
        
    total_unidades = sum(m["qty"] for m in salidas_y_traspasos)
    return render_template_string(REPORTE_TEMPLATE, salidas=reversed(salidas_y_traspasos), total_salidas=total_unidades, current_category=cat_filter, search_query=search_query, datetime=datetime)

# --- PLANTILLAS HTML MODERNAS CON BUSCADORES Y PERSISTENCIA VISUAL ---

BASE_NAV = """
    <nav class="bg-gradient-to-r from-slate-900 via-blue-950 to-slate-900 text-white px-8 py-4 flex justify-between items-center shadow-xl border-b border-blue-900/50">
        <div class="flex items-center space-x-3">
            <div class="bg-blue-600 p-2 rounded-xl shadow-md text-xl">🏥</div>
            <div>
                <h1 class="text-lg font-black tracking-wider bg-gradient-to-r from-white to-blue-200 bg-clip-text text-transparent">FARMACIA HOSPITALARIA</h1>
                <p class="text-xs text-blue-400 font-medium">Sistema de Gestión Multialmacén y Auditoría</p>
            </div>
        </div>
        <div class="space-x-2 flex items-center text-sm font-semibold">
            <a href="/terminal" class="px-4 py-2 rounded-xl transition duration-200 flex items-center space-x-1 {% if request.path == '/terminal' or request.path == '/' %}bg-blue-600 text-white shadow-lg shadow-blue-600/30 font-bold{% else %}text-slate-300 hover:bg-slate-800 hover:text-white{% endif %}">
                <span>⚡</span><span>Terminal</span>
            </a>
            <a href="/inventory" class="px-4 py-2 rounded-xl transition duration-200 flex items-center space-x-1 {% if request.path == '/inventory' %}bg-blue-600 text-white shadow-lg shadow-blue-600/30 font-bold{% else %}text-slate-300 hover:bg-slate-800 hover:text-white{% endif %}">
                <span>📦</span><span>Inventario</span>
            </a>
            <a href="/movements" class="px-4 py-2 rounded-xl transition duration-200 flex items-center space-x-1 {% if request.path == '/movements' %}bg-blue-600 text-white shadow-lg shadow-blue-600/30 font-bold{% else %}text-slate-300 hover:bg-slate-800 hover:text-white{% endif %}">
                <span>📑</span><span>Movimientos</span>
            </a>
            <a href="/reporte" class="px-4 py-2 rounded-xl transition duration-200 flex items-center space-x-1 {% if request.path == '/reporte' %}bg-blue-600 text-white shadow-lg shadow-blue-600/30 font-bold{% else %}text-slate-300 hover:bg-slate-800 hover:text-white{% endif %}">
                <span>📊</span><span>Reporte Diario</span>
            </a>
        </div>
    </nav>
"""

TERMINAL_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Terminal de Captura - Sistema Hospitalario</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        function handleMovementType(val) {
            document.getElementById('div_entrada').style.display = (val === 'ENTRADA') ? 'block' : 'none';
            document.getElementById('div_salida').style.display = (val === 'SALIDA') ? 'block' : 'none';
            document.getElementById('div_traspaso').style.display = (val === 'TRASPASO') ? 'block' : 'none';
            document.getElementById('div_nuevo_med').style.display = (val === 'ENTRADA') ? 'block' : 'none';
        }
    </script>
</head>
<body class="bg-slate-50 min-h-screen font-sans">
    """ + BASE_NAV + """

    <div class="max-w-4xl mx-auto my-10 bg-white p-8 rounded-3xl shadow-2xl border border-slate-100">
        <div class="flex items-center space-x-4 mb-8 pb-6 border-b border-slate-100">
            <div class="bg-blue-100 p-3.5 rounded-2xl text-blue-600 text-2xl font-bold">⚡</div>
            <div>
                <h2 class="text-2xl font-black text-slate-900 tracking-tight">Terminal de Captura y Auditoría</h2>
                <p class="text-sm text-slate-500">Todo movimiento queda guardado en la bitácora con registro de usuario y contraseña.</p>
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="mb-6 p-4 rounded-2xl text-sm font-bold shadow-sm flex items-center space-x-3 {% if category == 'danger' %}bg-red-50 text-red-700 border border-red-200{% else %}bg-emerald-50 text-emerald-800 border border-emerald-200{% endif %}">
                <span>{% if category == 'danger' %}❌{% else %}✅{% endif %}</span>
                <span>{{ message }}</span>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <form method="POST" class="space-y-6">
            <div class="bg-gradient-to-br from-blue-50 to-indigo-50/50 p-6 rounded-2xl border border-blue-100 grid grid-cols-1 md:grid-cols-2 gap-5 shadow-sm">
                <div>
                    <label class="block text-xs font-black text-blue-900 uppercase tracking-wider mb-2">👤 Usuario Autorizado</label>
                    <select name="user_select" required class="w-full px-4 py-3 border border-blue-200 rounded-xl bg-white font-semibold text-slate-800 focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm">
                        {% for u in users %}
                            <option value="{{ u.username }}">{{ u.name }} ({{ u.role }})</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-black text-blue-900 uppercase tracking-wider mb-2">🔑 Contraseña de Verificación</label>
                    <input type="password" name="password_input" required placeholder="Ingrese clave..." class="w-full px-4 py-3 border border-blue-200 rounded-xl bg-white text-slate-800 focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm font-semibold">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                    <label class="block text-xs font-black text-slate-700 uppercase tracking-wider mb-2">Tipo de Movimiento</label>
                    <select name="tipo_mov" id="tipo_mov" onchange="handleMovementType(this.value)" class="w-full px-4 py-3.5 border border-slate-200 rounded-xl bg-white font-bold text-slate-900 focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm">
                        <option value="SALIDA">📤 SALIDA (Dispensación a Servicios)</option>
                        <option value="ENTRADA">📥 ENTRADA (Recepción / Alta)</option>
                        <option value="TRASPASO">🔄 TRASPASO ENTRE ALMACENES</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-black text-slate-700 uppercase tracking-wider mb-2">Código de Barras</label>
                    <input type="text" name="codigo" required autofocus placeholder="Escanee o escriba código..." class="w-full px-4 py-3.5 border border-slate-200 rounded-xl font-mono font-bold text-slate-900 focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm">
                </div>
                <div>
                    <label class="block text-xs font-black text-slate-700 uppercase tracking-wider mb-2">Cantidad de Unidades</label>
                    <input type="number" name="qty" value="1" min="1" required class="w-full px-4 py-3.5 border border-slate-200 rounded-xl font-bold text-slate-900 focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm">
                </div>

                <div id="div_entrada" style="display: none;">
                    <label class="block text-xs font-black text-emerald-800 uppercase tracking-wider mb-2">📥 Almacén de Recepción</label>
                    <select name="target_warehouse" class="w-full px-4 py-3.5 border border-emerald-200 rounded-xl bg-white font-bold text-emerald-950 shadow-sm">
                        {% for w in warehouses %}
                            <option value="{{ w }}">{{ w }}</option>
                        {% endfor %}
                    </select>
                </div>

                <div id="div_salida">
                    <label class="block text-xs font-black text-slate-700 uppercase tracking-wider mb-2">Servicio Clínico Destino</label>
                    <select name="service" class="w-full px-4 py-3 border border-slate-200 rounded-xl bg-white font-semibold text-slate-900 shadow-sm">
                        {% for s in services %}
                            <option value="{{ s }}">{{ s }}</option>
                        {% endfor %}
                    </select>
                    <label class="block text-xs font-bold text-slate-500 mt-2 mb-1">Descontar del Almacén:</label>
                    <select name="source_warehouse" class="w-full px-3 py-2 border border-slate-200 rounded-lg bg-white text-xs font-medium text-slate-700">
                        {% for w in warehouses %}
                            <option value="{{ w }}">{{ w }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>

            <div id="div_traspaso" style="display: none;" class="bg-gradient-to-br from-indigo-50 to-purple-50 p-6 rounded-2xl border border-indigo-100 grid grid-cols-1 md:grid-cols-2 gap-5 shadow-sm">
                <div>
                    <label class="block text-xs font-black text-indigo-900 uppercase tracking-wider mb-2">📤 Almacén Origen</label>
                    <select name="origin_warehouse" class="w-full px-4 py-3 border border-indigo-200 rounded-xl bg-white font-bold text-indigo-950 shadow-sm">
                        {% for w in warehouses %}
                            <option value="{{ w }}">{{ w }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-black text-indigo-900 uppercase tracking-wider mb-2">📥 Almacén Destino (Ej. Quirófano)</label>
                    <select name="dest_warehouse" class="w-full px-4 py-3 border border-indigo-200 rounded-xl bg-white font-bold text-indigo-950 shadow-sm">
                        {% for w in warehouses %}
                            <option value="{{ w }}">{{ w }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>

            <div id="div_nuevo_med" style="display: none;" class="bg-gradient-to-br from-amber-50 to-orange-50/50 p-6 rounded-2xl border border-amber-200 space-y-4 shadow-sm">
                <p class="text-xs font-black text-amber-900 uppercase tracking-wider flex items-center">
                    <span class="mr-2">📝</span> ALTA DE NUEVO ÍTEM EN EL CATÁLOGO:
                </p>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-amber-900 mb-1">Clasificación:</label>
                        <select name="category" class="w-full px-3 py-2.5 border border-amber-300 rounded-xl bg-white text-sm font-bold text-slate-900">
                            <option value="Medicamento">💊 Medicamento</option>
                            <option value="Material">🩹 Material de Curación / Insumo</option>
                        </select>
                    </div>
                    <div class="md:col-span-2">
                        <label class="block text-xs font-bold text-amber-900 mb-1">Nombre del Ítem:</label>
                        <input type="text" name="name" placeholder="Ej. PARACETAMOL 500 MG o GUANTES" class="w-full px-3 py-2.5 border border-amber-300 rounded-xl bg-white text-sm font-semibold text-slate-900">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-amber-900 mb-1">Presentación:</label>
                        <input type="text" name="presentation" placeholder="Ej. Caja con 20 tabletas" class="w-full px-3 py-2.5 border border-amber-300 rounded-xl bg-white text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-amber-900 mb-1">Vía de Administración:</label>
                        <input type="text" name="via" placeholder="Ej. Oral / Tópico" class="w-full px-3 py-2.5 border border-amber-300 rounded-xl bg-white text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-amber-900 mb-1">Lote y Caducidad:</label>
                        <div class="grid grid-cols-2 gap-2">
                            <input type="text" name="lote" placeholder="Lote" class="px-2 py-2.5 border border-amber-300 rounded-xl bg-white text-xs">
                            <input type="date" name="caducidad" value="2028-12-31" class="px-2 py-2.5 border border-amber-300 rounded-xl bg-white text-xs">
                        </div>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                    <label class="block text-xs font-black text-slate-700 uppercase tracking-wider mb-2">Paciente / No. Expediente (Opcional)</label>
                    <input type="text" name="patient" placeholder="Ej. EXP-10023 o N/A" class="w-full px-4 py-3 border border-slate-200 rounded-xl focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm">
                </div>
                <div>
                    <label class="block text-xs font-black text-slate-700 uppercase tracking-wider mb-2">Motivo / Observaciones</label>
                    <input type="text" name="reason" placeholder="Ej. Surtido receta ordinaria" class="w-full px-4 py-3 border border-slate-200 rounded-xl focus:ring-4 focus:ring-blue-500/20 focus:border-blue-600 outline-none transition shadow-sm">
                </div>
            </div>

            <button type="submit" class="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white py-4 rounded-2xl font-black text-base shadow-xl shadow-blue-600/30 transition duration-200 flex items-center justify-center space-x-2">
                <span>🚀</span><span>REGISTRAR Y GUARDAR MOVIMIENTO</span>
            </button>
        </form>
    </div>
</body>
</html>
"""

INVENTORY_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Inventario Multialmacén - Sistema Hospitalario</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 min-h-screen font-sans">
    """ + BASE_NAV + """

    <div class="max-w-7xl mx-auto my-10 bg-white p-8 rounded-3xl shadow-2xl border border-slate-100">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 pb-6 border-b border-slate-100 gap-4">
            <div>
                <h2 class="text-2xl font-black text-slate-900 tracking-tight">📦 Control de Inventario y Almacenes</h2>
                <p class="text-sm text-slate-500">Busque medicamentos, insumos, códigos o lotes en tiempo real.</p>
            </div>
            
            <form method="GET" action="/inventory" class="flex items-center space-x-2 w-full md:w-auto">
                <input type="hidden" name="category" value="{{ current_category }}">
                <input type="text" name="q" value="{{ search_query }}" placeholder="🔍 Buscar medicamento, insumo o lote..." class="px-4 py-2.5 border border-slate-300 rounded-xl text-sm w-full md:w-80 focus:ring-2 focus:ring-blue-500 outline-none shadow-sm">
                <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2.5 rounded-xl font-bold text-sm shadow transition">Buscar</button>
                {% if search_query %}
                    <a href="/inventory?category={{ current_category }}" class="bg-slate-200 hover:bg-slate-300 text-slate-700 px-3 py-2.5 rounded-xl font-bold text-sm transition">Limpiar</a>
                {% endif %}
            </form>
        </div>

        <div class="mb-6 flex space-x-2">
            <a href="/inventory?q={{ search_query }}&category=TODOS" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if current_category == 'TODOS' %}bg-blue-600 text-white shadow-md{% else %}bg-slate-100 text-slate-700 hover:bg-slate-200{% endif %}">Todos los Insumos</a>
            <a href="/inventory?q={{ search_query }}&category=Medicamento" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if current_category == 'Medicamento' %}bg-blue-600 text-white shadow-md{% else %}bg-slate-100 text-slate-700 hover:bg-slate-200{% endif %}">💊 Medicamentos</a>
            <a href="/inventory?q={{ search_query }}&category=Material" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if current_category == 'Material' %}bg-blue-600 text-white shadow-md{% else %}bg-slate-100 text-slate-700 hover:bg-slate-200{% endif %}">🩹 Material de Curación</a>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm">
            <table class="w-full border-collapse text-sm text-left">
                <thead class="bg-slate-900 text-white uppercase text-xs tracking-wider">
                    <tr>
                        <th class="p-4 border-b border-slate-800">Código</th>
                        <th class="p-4 border-b border-slate-800">Clasificación</th>
                        <th class="p-4 border-b border-slate-800">Medicamento / Material</th>
                        <th class="p-4 border-b border-slate-800">Presentación</th>
                        <th class="p-4 border-b border-slate-800">Lote / Cad.</th>
                        {% for w in warehouses %}
                            <th class="p-4 border-b border-slate-800 text-center bg-slate-800/80">{{ w }}</th>
                        {% endfor %}
                        <th class="p-4 border-b border-slate-800 text-right bg-blue-950">Stock Total</th>
                        <th class="p-4 border-b border-slate-800 text-center">Estatus</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 font-medium">
                    {% for item in inventory %}
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="p-4 font-mono font-bold text-slate-700">{{ item.code }}</td>
                        <td class="p-4">
                            {% if item.category == 'Medicamento' %}
                                <span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-xs font-bold">💊 Medicamento</span>
                            {% else %}
                                <span class="bg-purple-100 text-purple-800 px-3 py-1 rounded-full text-xs font-bold">🩹 Material</span>
                            {% endif %}
                        </td>
                        <td class="p-4 font-black text-slate-900">{{ item.name }}</td>
                        <td class="p-4 text-slate-600 text-xs">{{ item.presentation }}<br>{{ item.via }}</td>
                        <td class="p-4 text-slate-600 text-xs font-mono">{{ item.lote }}<br>{{ item.caducidad }}</td>
                        
                        {% for w in warehouses %}
                            <td class="p-4 text-center font-bold text-slate-800">{{ item.stocks[w] }}</td>
                        {% endfor %}
                        
                        <td class="p-4 text-right font-black text-base text-blue-900">{{ item.current_stock }}</td>
                        <td class="p-4 text-center font-bold text-xs">
                            {% if item.status == 'DISPONIBLE' %}
                                <span class="bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full">DISPONIBLE</span>
                            {% elif item.status == 'STOCK BAJO' %}
                                <span class="bg-amber-100 text-amber-800 px-3 py-1 rounded-full">STOCK BAJO</span>
                            {% else %}
                                <span class="bg-red-100 text-red-800 px-3 py-1 rounded-full">AGOTADO</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="12" class="p-8 text-center text-slate-400 font-semibold">No se encontraron resultados para su búsqueda.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

MOVEMENTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Historial de Movimientos - Sistema Hospitalario</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 min-h-screen font-sans">
    """ + BASE_NAV + """

    <div class="max-w-7xl mx-auto my-10 bg-white p-8 rounded-3xl shadow-2xl border border-slate-100">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 pb-6 border-b border-slate-100 gap-4">
            <div>
                <h2 class="text-2xl font-black text-slate-900 tracking-tight">📑 Bitácora General de Movimientos y Auditoría</h2>
                <p class="text-sm text-slate-500">Busque por paciente, expediente, medicamento, usuario o servicio clínico.</p>
            </div>
            
            <form method="GET" action="/movements" class="flex items-center space-x-2 w-full md:w-auto">
                <input type="text" name="q" value="{{ search_query }}" placeholder="🔍 Buscar por paciente, medicamento..." class="px-4 py-2.5 border border-slate-300 rounded-xl text-sm w-full md:w-80 focus:ring-2 focus:ring-blue-500 outline-none shadow-sm">
                <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2.5 rounded-xl font-bold text-sm shadow transition">Buscar</button>
                {% if search_query %}
                    <a href="/movements" class="bg-slate-200 hover:bg-slate-300 text-slate-700 px-3 py-2.5 rounded-xl font-bold text-sm transition">Limpiar</a>
                {% endif %}
            </form>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm">
            <table class="w-full border-collapse text-sm text-left">
                <thead class="bg-slate-900 text-white uppercase text-xs tracking-wider">
                    <tr>
                        <th class="p-4 border-b border-slate-800">Fecha / Hora</th>
                        <th class="p-4 border-b border-slate-800">Código</th>
                        <th class="p-4 border-b border-slate-800">Clasificación</th>
                        <th class="p-4 border-b border-slate-800">Medicamento / Material</th>
                        <th class="p-4 border-b border-slate-800 text-center">Tipo</th>
                        <th class="p-4 border-b border-slate-800 text-right">Cant.</th>
                        <th class="p-4 border-b border-slate-800">Servicio / Destino</th>
                        <th class="p-4 border-b border-slate-800">Paciente / Expediente</th>
                        <th class="p-4 border-b border-slate-800">Responsable</th>
                        <th class="p-4 border-b border-slate-800">Observaciones</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 font-medium">
                    {% for m in movements %}
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="p-4 font-mono text-xs text-slate-500">{{ m.date }} {{ m.time }}</td>
                        <td class="p-4 font-mono font-semibold text-slate-700">{{ m.code }}</td>
                        <td class="p-4">
                            {% if m.category == 'Medicamento' %}
                                <span class="bg-blue-100 text-blue-800 px-2.5 py-0.5 rounded-full text-xs font-bold">💊 Medicamento</span>
                            {% else %}
                                <span class="bg-purple-100 text-purple-800 px-2.5 py-0.5 rounded-full text-xs font-bold">🩹 Material</span>
                            {% endif %}
                        </td>
                        <td class="p-4 font-black text-slate-900">{{ m.name }}</td>
                        <td class="p-4 text-center font-bold text-xs">
                            {% if m.type == 'ENTRADA' %}
                                <span class="bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full">ENTRADA</span>
                            {% elif m.type == 'TRASPASO' %}
                                <span class="bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full">TRASPASO</span>
                            {% else %}
                                <span class="bg-red-100 text-red-800 px-3 py-1 rounded-full">SALIDA</span>
                            {% endif %}
                        </td>
                        <td class="p-4 text-right font-black text-slate-900">{{ m.qty }}</td>
                        <td class="p-4 text-slate-700 text-xs font-semibold">{{ m.service }}</td>
                        <td class="p-4 text-slate-800 text-xs font-bold bg-amber-50/50 rounded">{{ m.patient }}</td>
                        <td class="p-4 font-bold text-blue-900 text-xs">{{ m.user }}</td>
                        <td class="p-4 text-slate-500 text-xs">{{ m.reason }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="10" class="p-8 text-center text-slate-400 font-semibold">No se encontraron movimientos registrados con ese criterio.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

REPORTE_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Reporte Diario - Sistema Hospitalario</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 min-h-screen font-sans">
    <div class="print:hidden">
        """ + BASE_NAV + """
    </div>

    <div class="max-w-7xl mx-auto my-10 bg-white p-8 rounded-3xl shadow-2xl border border-slate-100">
        <div class="flex justify-between items-center mb-6 border-b border-slate-100 pb-6">
            <div>
                <h2 class="text-2xl font-black text-slate-900 tracking-tight flex items-center">
                    <span class="mr-3">📊</span> Reporte Diario Filtrado de Salidas y Traspasos
                </h2>
                <p class="text-sm text-slate-500">Filtre por clasificación de insumos y busque pacientes o medicamentos para auditorías precisas.</p>
            </div>
            <button onclick="window.print()" class="bg-slate-900 hover:bg-slate-800 text-white px-5 py-3 rounded-2xl font-bold text-sm shadow-xl transition print:hidden flex items-center space-x-2">
                <span>🖨️</span><span>Imprimir Reporte</span>
            </button>
        </div>

        <div class="mb-8 p-6 bg-slate-50 rounded-2xl border border-slate-200 flex flex-wrap items-center justify-between gap-4 print:hidden">
            <div class="flex items-center space-x-3">
                <span class="text-sm font-black text-slate-700 uppercase tracking-wider">Clasificación:</span>
                <div class="flex space-x-2">
                    <a href="/reporte?category=TODOS&q={{ search_query }}" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if current_category == 'TODOS' %}bg-blue-600 text-white shadow-md{% else %}bg-white text-slate-700 border border-slate-200 hover:bg-slate-100{% endif %}">Todos</a>
                    <a href="/reporte?category=Medicamento&q={{ search_query }}" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if current_category == 'Medicamento' %}bg-blue-600 text-white shadow-md{% else %}bg-white text-slate-700 border border-slate-200 hover:bg-slate-100{% endif %}">💊 Medicamentos</a>
                    <a href="/reporte?category=Material&q={{ search_query }}" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if current_category == 'Material' %}bg-blue-600 text-white shadow-md{% else %}bg-white text-slate-700 border border-slate-200 hover:bg-slate-100{% endif %}">🩹 Material</a>
                </div>
            </div>

            <form method="GET" action="/reporte" class="flex items-center space-x-2">
                <input type="hidden" name="category" value="{{ current_category }}">
                <input type="text" name="q" value="{{ search_query }}" placeholder="🔍 Filtrar por paciente o insumo..." class="px-3 py-2 border border-slate-300 rounded-xl text-xs w-64 focus:ring-2 focus:ring-blue-500 outline-none">
                <button type="submit" class="bg-blue-600 text-white px-3 py-2 rounded-xl font-bold text-xs">Filtrar</button>
                {% if search_query %}
                    <a href="/reporte?category={{ current_category }}" class="bg-slate-200 text-slate-700 px-3 py-2 rounded-xl font-bold text-xs">Limpiar</a>
                {% endif %}
            </form>
        </div>

        <div class="mb-8 bg-gradient-to-br from-blue-50 to-indigo-50/50 p-6 rounded-2xl border border-blue-100 flex justify-between items-center shadow-sm">
            <div>
                <p class="text-xs font-black text-blue-900 uppercase tracking-wider">Total Unidades Salientes / Traspasadas ({{ current_category }}):</p>
                <p class="text-3xl font-black text-blue-950 mt-1">{{ total_salidas }} unidades</p>
            </div>
            <p class="text-xs font-bold text-slate-500">Emisión: {{ datetime.datetime.now().strftime("%Y-%m-%d %H:%M") }}</p>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-slate-200 shadow-sm">
            <table class="w-full border-collapse text-sm text-left">
                <thead class="bg-slate-900 text-white uppercase text-xs tracking-wider">
                    <tr>
                        <th class="p-4 border-b border-slate-800">Fecha / Hora</th>
                        <th class="p-4 border-b border-slate-800">Código</th>
                        <th class="p-4 border-b border-slate-800">Clasificación</th>
                        <th class="p-4 border-b border-slate-800">Medicamento / Material</th>
                        <th class="p-4 border-b border-slate-800 text-center">Tipo</th>
                        <th class="p-4 border-b border-slate-800 text-right">Cant.</th>
                        <th class="p-4 border-b border-slate-800">Servicio / Destino</th>
                        <th class="p-4 border-b border-slate-800">Paciente</th>
                        <th class="p-4 border-b border-slate-800">Responsable</th>
                        <th class="p-4 border-b border-slate-800">Observaciones</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 font-medium">
                    {% for m in salidas %}
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="p-4 font-mono text-xs text-slate-500">{{ m.date }} {{ m.time }}</td>
                        <td class="p-4 font-mono font-semibold text-slate-700">{{ m.code }}</td>
                        <td class="p-4">
                            {% if m.category == 'Medicamento' %}
                                <span class="bg-blue-100 text-blue-800 px-2.5 py-0.5 rounded-full text-xs font-bold">💊 Medicamento</span>
                            {% else %}
                                <span class="bg-purple-100 text-purple-800 px-2.5 py-0.5 rounded-full text-xs font-bold">🩹 Material</span>
                            {% endif %}
                        </td>
                        <td class="p-4 font-black text-slate-900">{{ m.name }}</td>
                        <td class="p-4 text-center font-bold text-xs">
                            {% if m.type == 'TRASPASO' %}
                                <span class="bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full">TRASPASO</span>
                            {% else %}
                                <span class="bg-red-100 text-red-800 px-3 py-1 rounded-full">SALIDA</span>
                            {% endif %}
                        </td>
                        <td class="p-4 text-right font-black text-slate-900">-{{ m.qty }}</td>
                        <td class="p-4 text-slate-700 text-xs font-semibold">{{ m.service }}</td>
                        <td class="p-4 text-slate-800 text-xs font-bold bg-amber-50/50 rounded">{{ m.patient }}</td>
                        <td class="p-4 font-bold text-blue-900 text-xs">{{ m.user }}</td>
                        <td class="p-4 text-slate-500 text-xs">{{ m.reason }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="10" class="p-8 text-center text-slate-400 font-semibold">No se encontraron registros de salidas o traspasos con ese criterio.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, port=5000)
