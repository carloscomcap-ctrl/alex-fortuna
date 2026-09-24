import os
import io
import re
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file
)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd


import time

# =========================================================
# APLICACIÓN
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dinamicas-alex-2027-super-secret-key-prod"
)

# Seguridad de cookies de sesión
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # Máximo 10 MB

# Control de intentos de inicio de sesión (Protección Fuerza Bruta)
login_attempts = {}

def get_client_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"

def check_login_rate_limit(ip):
    now = time.time()
    attempts = login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < 900]  # Ventana de 15 min
    login_attempts[ip] = attempts
    return len(attempts) < 5

def record_failed_login(ip):
    now = time.time()
    attempts = login_attempts.get(ip, [])
    attempts.append(now)
    login_attempts[ip] = attempts

def reset_login_attempts(ip):
    login_attempts.pop(ip, None)

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# =========================================================
# BASE DE DATOS
# =========================================================

db_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///dinamicas_alex_27.db"
)

if db_url.startswith("postgres://"):
    db_url = db_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================================================
# ADMINISTRADOR
# =========================================================

ADMIN_USER = os.environ.get(
    "ADMIN_USER",
    "admin"
)

ADMIN_PASSWORD_HASH = generate_password_hash(
    os.environ.get(
        "ADMIN_PASSWORD",
        "cambiar123"
    )
)


# =========================================================
# MODELO DE SORTEO
# =========================================================

class Sorteo(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nombre = db.Column(
        db.String(120),
        nullable=False
    )

    loteria = db.Column(
        db.String(100),
        nullable=False
    )

    fecha = db.Column(
        db.String(30),
        nullable=False
    )

    horario = db.Column(
        db.String(30),
        nullable=False
    )

    valor = db.Column(
        db.Integer,
        default=0
    )

    premio_mayor = db.Column(
        db.String(50),
        default="$320.000"
    )

    premio_primeras = db.Column(
        db.String(50),
        default="$50.000"
    )

    premio_medio = db.Column(
        db.String(50),
        default="$50.000"
    )

    estado = db.Column(
        db.String(20),
        default="ACTIVO"
    )

    ventas = db.relationship(
        "Venta",
        backref="sorteo",
        lazy=True
    )


# =========================================================
# MODELO DE VENTA
# =========================================================

class Venta(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    telefono = db.Column(
        db.String(30),
        nullable=False,
        index=True
    )

    nombre = db.Column(
        db.String(120),
        nullable=False
    )

    numero = db.Column(
        db.String(20),
        nullable=False
    )

    loteria = db.Column(
        db.String(100),
        nullable=False
    )

    fecha = db.Column(
        db.String(30),
        nullable=False
    )

    valor = db.Column(
        db.Integer,
        default=0
    )

    estado = db.Column(
        db.String(20),
        default="PENDIENTE"
    )

    # Relaciona la venta con un sorteo.
    sorteo_id = db.Column(
        db.Integer,
        db.ForeignKey("sorteo.id"),
        nullable=True,
        index=True
    )


# =========================================================
# MODELO DE AJUSTES DEL SISTEMA (MEDIOS DE PAGO)
# =========================================================

class Ajuste(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    clave = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    valor = db.Column(
        db.Text,
        nullable=True
    )


# =========================================================
# MODELO DE GANADORES HISTÓRICOS (MURO DE GANADORES)
# =========================================================

class GanadorHistorico(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sorteo_nombre = db.Column(
        db.String(120),
        nullable=False,
        default="Dinámica Oficial"
    )

    loteria = db.Column(
        db.String(100),
        nullable=False
    )

    fecha = db.Column(
        db.String(30),
        nullable=False
    )

    numero = db.Column(
        db.String(10),
        nullable=False
    )

    nombre = db.Column(
        db.String(120),
        nullable=False
    )

    categoria = db.Column(
        db.String(100),
        nullable=False
    )

    premio = db.Column(
        db.String(50),
        nullable=True,
        default="$320.000"
    )

    cifras_sorteo = db.Column(
        db.String(10),
        nullable=True
    )

    creado_en = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


# =========================================================
# CREAR TABLAS Y COMPATIBILIDAD CON BASE EXISTENTE
# =========================================================

with app.app_context():

    db.create_all()

    try:
        inspector = db.inspect(db.engine)
        columnas_venta = [
            c["name"]
            for c in inspector.get_columns("venta")
        ]

        if "sorteo_id" not in columnas_venta:
            with db.engine.begin() as connection:
                if db.engine.dialect.name == "postgresql":
                    connection.exec_driver_sql(
                        'ALTER TABLE venta ADD COLUMN sorteo_id INTEGER'
                    )
                    connection.exec_driver_sql(
                        'CREATE INDEX IF NOT EXISTS ix_venta_sorteo_id ON venta (sorteo_id)'
                    )
                else:
                    connection.exec_driver_sql(
                        'ALTER TABLE venta ADD COLUMN sorteo_id INTEGER'
                    )

        # Migrar columnas de premios en Sorteo si no existen
        columnas_sorteo = [
            c["name"]
            for c in inspector.get_columns("sorteo")
        ]
        with db.engine.begin() as connection:
            if "premio_mayor" not in columnas_sorteo:
                connection.exec_driver_sql("ALTER TABLE sorteo ADD COLUMN premio_mayor VARCHAR(50) DEFAULT '$320.000'")
            if "premio_primeras" not in columnas_sorteo:
                connection.exec_driver_sql("ALTER TABLE sorteo ADD COLUMN premio_primeras VARCHAR(50) DEFAULT '$50.000'")
            if "premio_medio" not in columnas_sorteo:
                connection.exec_driver_sql("ALTER TABLE sorteo ADD COLUMN premio_medio VARCHAR(50) DEFAULT '$50.000'")

    except Exception:
        pass


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def clean_phone(value):
    """
    Deja solamente números en el teléfono.

    Ejemplo:
    +57 300 123 4567
    se convierte en:
    573001234567
    """

    return re.sub(
        r"\D",
        "",
        str(value or "")
    )


def mask_phone(value):
    """
    Oculta los últimos dígitos del teléfono con asteriscos para proteger la privacidad.
    Ejemplo:
    3101234567 -> 310 123 ****
    573101234567 -> 310 123 ****
    """
    if not value:
        return ""
    digits = re.sub(r"\D", "", str(value))
    if digits.startswith("57") and len(digits) == 12:
        digits = digits[2:]
    
    if len(digits) >= 10:
        return f"{digits[:3]} {digits[3:6]} ****"
    elif len(digits) >= 7:
        return f"{digits[:3]} {digits[3:6]} {'*' * (len(digits)-6)}"
    elif len(digits) > 3:
        return f"{digits[:3]} {'*' * (len(digits)-3)}"
    return "****"


@app.template_filter("mask_phone")
def mask_phone_filter(value):
    return mask_phone(value)


def parse_precio(texto):
    """
    Extrae el valor numérico entero de cadenas con formato de moneda.
    Ejemplo: '$320.000' -> 320000, '$50.000' -> 50000
    """
    if not texto:
        return 0
    limpio = re.sub(r"[^\d]", "", str(texto))
    return int(limpio) if limpio else 0


def required_admin():
    return session.get("admin") is True


def obtener_datos_pago():
    """
    Retorna un diccionario con los números de medios de pago configurados.
    Si no existen en BD, devuelve valores predeterminados.
    """
    defaults = {
        "nequi": "310 123 4567",
        "daviplata": "310 123 4567",
        "bancolombia": "Ahorros / A la mano",
        "titular": "Dinámicas Alex"
    }
    try:
        ajustes = Ajuste.query.all()
        datos = dict(defaults)
        for a in ajustes:
            if a.clave in datos and a.valor:
                datos[a.clave] = a.valor
        return datos
    except Exception:
        return defaults


# =========================================================
# PÁGINA PRINCIPAL
# =========================================================

@app.route("/")
def home():

    sorteos_activos = (
        Sorteo.query
        .filter_by(estado="ACTIVO")
        .order_by(Sorteo.id.desc())
        .all()
    )

    ganadores_recientes = (
        GanadorHistorico.query
        .order_by(GanadorHistorico.id.desc())
        .limit(12)
        .all()
    )

    medios_pago = obtener_datos_pago()

    return render_template(
        "index.html",
        sorteos_activos=sorteos_activos,
        ganadores_recientes=ganadores_recientes,
        medios_pago=medios_pago
    )


# =========================================================
# TABLA VISUAL DE NÚMEROS (00 AL 99)
# =========================================================

@app.route("/tabla/<int:id>")
def ver_tabla(id):

    sorteo = db.session.get(Sorteo, id)

    if not sorteo:
        flash("El sorteo solicitado no existe.", "error")
        return redirect(url_for("home"))

    # Estructura del 00 al 99
    mapa_numeros = {}
    for i in range(100):
        num_str = f"{i:02d}"
        mapa_numeros[num_str] = {
            "numero": num_str,
            "estado": "LIBRE",
            "cliente": None,
            "telefono": None,
            "venta_id": None
        }

    libres = 100
    apartados = 0
    pagados = 0

    ventas_sorteo = Venta.query.filter(
        (Venta.sorteo_id == sorteo.id) |
        ((Venta.sorteo_id == None) & (Venta.loteria == sorteo.loteria) & (Venta.fecha == sorteo.fecha))
    ).all()

    for venta in ventas_sorteo:
        num_str = str(venta.numero).strip().zfill(2)
        if num_str in mapa_numeros:
            estado = (venta.estado or "PENDIENTE").upper()
            if mapa_numeros[num_str]["estado"] == "LIBRE":
                libres -= 1

            if estado == "PAGADO":
                pagados += 1
            else:
                apartados += 1

            mapa_numeros[num_str]["estado"] = estado
            mapa_numeros[num_str]["cliente"] = venta.nombre
            mapa_numeros[num_str]["telefono"] = venta.telefono
            mapa_numeros[num_str]["venta_id"] = venta.id

    recaudado = pagados * (sorteo.valor or 0)
    por_recaudar = apartados * (sorteo.valor or 0)
    medios_pago = obtener_datos_pago()

    # Construir lista ordenada de participantes (00 al 99)
    participantes = []
    for i in range(100):
        num_str = f"{i:02d}"
        item = mapa_numeros[num_str]
        if item["estado"] != "LIBRE":
            participantes.append({
                "numero": num_str,
                "cliente": item["cliente"] or "Anónimo",
                "telefono_oculto": mask_phone(item["telefono"]),
                "telefono_raw": item["telefono"],
                "estado": item["estado"],
                "venta_id": item["venta_id"]
            })

    # Consultar ganadores históricos asociados a esta dinámica
    ganadores_sorteo = GanadorHistorico.query.filter(
        (GanadorHistorico.loteria == sorteo.loteria) &
        (GanadorHistorico.fecha == sorteo.fecha)
    ).all()

    return render_template(
        "tabla.html",
        sorteo=sorteo,
        mapa_numeros=mapa_numeros,
        participantes=participantes,
        ganadores_sorteo=ganadores_sorteo,
        libres=libres,
        apartados=apartados,
        pagados=pagados,
        recaudado=recaudado,
        por_recaudar=por_recaudar,
        medios_pago=medios_pago
    )



# =========================================================
# CONSULTAR NÚMEROS
# =========================================================

@app.post("/consultar")
def consultar():

    telefono = clean_phone(
        request.form.get("telefono")
    )

    ventas = (
        Venta.query
        .filter_by(telefono=telefono)
        .order_by(
            Venta.fecha.desc(),
            Venta.numero
        )
        .all()
    )

    return render_template(
        "resultado.html",
        telefono=telefono,
        ventas=ventas
    )


# =========================================================
# LOGIN ADMINISTRADOR
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        ip = get_client_ip()
        if not check_login_rate_limit(ip):
            flash(
                "⛔ Demasiados intentos fallidos. Por motivos de seguridad, espera 15 minutos antes de intentar de nuevo.",
                "error"
            )
            return render_template("login.html")

        user = request.form.get(
            "usuario",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            user == ADMIN_USER
            and check_password_hash(
                ADMIN_PASSWORD_HASH,
                password
            )
        ):

            session.clear()
            session["admin"] = True
            reset_login_attempts(ip)

            return redirect(
                url_for("admin")
            )

        record_failed_login(ip)

        flash(
            "Usuario o contraseña incorrectos.",
            "error"
        )

    return render_template(
        "login.html"
    )


# =========================================================
# CERRAR SESIÓN
# =========================================================

@app.get("/admin/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# PANEL ADMINISTRATIVO
# =========================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin():

    if not required_admin():

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        try:

            telefono = clean_phone(
                request.form.get("telefono")
            )

            nombre = request.form.get(
                "nombre",
                ""
            ).strip()

            numero = request.form.get(
                "numero",
                ""
            ).strip()

            loteria = request.form.get(
                "loteria",
                ""
            ).strip()

            fecha = request.form.get(
                "fecha",
                ""
            ).strip()

            valor = int(
                request.form.get(
                    "valor"
                ) or 0
            )

            estado = request.form.get(
                "estado",
                "PENDIENTE"
            ).upper()

            sorteo_id = request.form.get(
                "sorteo_id",
                ""
            ).strip()


            # =================================================
            # COMPROBAR DATOS OBLIGATORIOS
            # =================================================

            if not telefono:
                raise ValueError(
                    "Debes ingresar un teléfono."
                )

            if not nombre:
                raise ValueError(
                    "Debes ingresar el nombre."
                )

            if not numero:
                raise ValueError(
                    "Debes ingresar el número."
                )

            # Validar que el número sea de 2 cifras (00 al 99)
            numero_limpio = numero.strip()
            if not numero_limpio.isdigit() or len(numero_limpio) > 2:
                raise ValueError(
                    "En Dinámicas Alex 2027 las rifas son del 00 al 99. "
                    "El número ingresado debe ser de máximo 2 cifras (ej: 05, 27, 99)."
                )

            # Normalizar a exactamente 2 dígitos (ej: 7 -> 07)
            numero = f"{int(numero_limpio):02d}"

            if not loteria:
                raise ValueError(
                    "Debes seleccionar una lotería."
                )

            if not fecha:
                raise ValueError(
                    "Debes seleccionar una fecha."
                )


            # =================================================
            # VALIDAR SORTEO
            # =================================================

            sorteo = None

            if sorteo_id:

                sorteo = db.session.get(
                    Sorteo,
                    int(sorteo_id)
                )

                if not sorteo:
                    raise ValueError(
                        "El sorteo seleccionado no existe."
                    )

                if sorteo.estado != "ACTIVO":
                    raise ValueError(
                        "El sorteo seleccionado está cerrado."
                    )


            # Si no se seleccionó sorteo explícito, pero hay un sorteo ACTIVO con la misma lotería y fecha, vincularlo automáticamente
            if not sorteo:
                sorteo = Sorteo.query.filter_by(
                    loteria=loteria,
                    fecha=fecha,
                    estado="ACTIVO"
                ).first()

            # =================================================
            # COMPROBAR DUPLICADO ESTRICTO
            # =================================================

            numero_int_str = str(int(numero))

            if sorteo:
                existente = Venta.query.filter(
                    Venta.sorteo_id == sorteo.id,
                    (Venta.numero == numero) | (Venta.numero == numero_int_str)
                ).first()

                if not existente:
                    existente = Venta.query.filter(
                        Venta.loteria == sorteo.loteria,
                        Venta.fecha == sorteo.fecha,
                        (Venta.numero == numero) | (Venta.numero == numero_int_str)
                    ).first()
            else:
                existente = Venta.query.filter(
                    Venta.loteria == loteria,
                    Venta.fecha == fecha,
                    (Venta.numero == numero) | (Venta.numero == numero_int_str)
                ).first()

            if existente:
                estado_lbl = "PAGADO 🟢" if existente.estado == "PAGADO" else "APARTADO 🟡"
                flash(
                    f"⛔ ERROR: El número #{numero} YA ESTÁ OCUPADO ({estado_lbl}) por {existente.nombre} (Tel: {existente.telefono}) en {existente.loteria} ({existente.fecha}). No se puede volver a vender.",
                    "error"
                )

            else:

                venta = Venta(
                    telefono=telefono,
                    nombre=nombre,
                    numero=numero,
                    loteria=loteria,
                    fecha=fecha,
                    valor=valor,
                    estado=estado,
                    sorteo_id=(sorteo.id if sorteo else None)
                )

                db.session.add(venta)
                db.session.commit()

                flash("✅ Venta registrada correctamente.", "ok")


        except Exception as error:

            db.session.rollback()

            flash(
                "No se pudo guardar: "
                + str(error),
                "error"
            )


    ventas = (
        Venta.query
        .order_by(
            Venta.id.desc()
        )
        .all()
    )

    sorteos = (
        Sorteo.query
        .order_by(
            Sorteo.id.desc()
        )
        .all()
    )

    sorteos_activos = [
        s for s in sorteos
        if s.estado == "ACTIVO"
    ]

    medios_pago = obtener_datos_pago()

    ganadores_muro = (
        GanadorHistorico.query
        .order_by(GanadorHistorico.id.desc())
        .limit(30)
        .all()
    )

    # Finanzas y métricas en vivo
    total_recaudado = sum(v.valor or 0 for v in ventas if v.estado == "PAGADO")
    total_por_recaudar = sum(v.valor or 0 for v in ventas if v.estado == "PENDIENTE")
    boletas_pagadas = sum(1 for v in ventas if v.estado == "PAGADO")
    boletas_apartadas = sum(1 for v in ventas if v.estado == "PENDIENTE")

    # =========================================================
    # BALANCE FINANCIERO Y RENTABILIDAD POR SORTEO (PRIVADO)
    # =========================================================
    sorteos_con_balance = []
    gran_total_premios = 0
    gran_total_capacidad = 0
    gran_total_ganancia_maxima = 0

    for s in sorteos:
        # Ventas correspondientes a este sorteo
        ventas_s = [
            v for v in ventas 
            if v.sorteo_id == s.id or (v.sorteo_id is None and v.loteria == s.loteria and v.fecha == s.fecha)
        ]

        pagadas_s = [v for v in ventas_s if v.estado == "PAGADO"]
        apartadas_s = [v for v in ventas_s if v.estado == "PENDIENTE"]

        num_pagadas = len(pagadas_s)
        num_apartadas = len(apartadas_s)
        num_libres = max(0, 100 - (num_pagadas + num_apartadas))

        val_boleta = s.valor or 0
        capacidad_tabla = 100 * val_boleta  # Si se llena la tabla de 100 números

        recaudado_s = sum(v.valor or val_boleta for v in pagadas_s)
        por_recaudar_s = sum(v.valor or val_boleta for v in apartadas_s)
        proyectado_s = recaudado_s + por_recaudar_s

        costo_mayor = parse_precio(s.premio_mayor)
        costo_primeras = parse_precio(s.premio_primeras)
        costo_medio = parse_precio(s.premio_medio)
        total_premios = costo_mayor + costo_primeras + costo_medio

        # Ganancia neta real (lo cobrado menos el costo total de los premios)
        ganancia_neta_actual = recaudado_s - total_premios

        # Ganancia neta si se cobran los apartados
        ganancia_con_apartados = proyectado_s - total_premios

        # Ganancia neta máxima posible (si se vende la tabla completa de 100 números)
        ganancia_neta_maxima = capacidad_tabla - total_premios

        # Punto de equilibrio: cuántas boletas hay que vender como mínimo para pagar los premios
        boletas_equilibrio = 0
        if val_boleta > 0 and total_premios > 0:
            boletas_equilibrio = total_premios // val_boleta
            if total_premios % val_boleta != 0:
                boletas_equilibrio += 1

        # Porcentaje de cobertura de premios con las ventas pagadas actuales
        porcentaje_cobertura = 0
        if total_premios > 0:
            porcentaje_cobertura = min(100, int((recaudado_s / total_premios) * 100))
        elif recaudado_s > 0:
            porcentaje_cobertura = 100

        # Boletas que faltan para alcanzar el punto de equilibrio
        boletas_para_equilibrio = max(0, boletas_equilibrio - num_pagadas)

        gran_total_premios += total_premios
        gran_total_capacidad += capacidad_tabla
        gran_total_ganancia_maxima += ganancia_neta_maxima

        sorteos_con_balance.append({
            "sorteo": s,
            "num_pagadas": num_pagadas,
            "num_apartadas": num_apartadas,
            "num_libres": num_libres,
            "val_boleta": val_boleta,
            "capacidad_tabla": capacidad_tabla,
            "recaudado": recaudado_s,
            "por_recaudar": por_recaudar_s,
            "proyectado": proyectado_s,
            "costo_mayor": costo_mayor,
            "costo_primeras": costo_primeras,
            "costo_medio": costo_medio,
            "total_premios": total_premios,
            "ganancia_neta_actual": ganancia_neta_actual,
            "ganancia_con_apartados": ganancia_con_apartados,
            "ganancia_neta_maxima": ganancia_neta_maxima,
            "boletas_equilibrio": boletas_equilibrio,
            "boletas_para_equilibrio": boletas_para_equilibrio,
            "porcentaje_cobertura": porcentaje_cobertura
        })

    finanzas = {
        "recaudado": total_recaudado,
        "por_recaudar": total_por_recaudar,
        "boletas_pagadas": boletas_pagadas,
        "boletas_apartadas": boletas_apartadas,
        "total_ventas": len(ventas),
        "gran_total_premios": gran_total_premios,
        "gran_total_capacidad": gran_total_capacidad,
        "gran_total_ganancia_maxima": gran_total_ganancia_maxima,
        "ganancia_neta_global": total_recaudado - gran_total_premios
    }

    return render_template(
        "admin.html",
        ventas=ventas,
        sorteos=sorteos,
        sorteos_activos=sorteos_activos,
        sorteos_con_balance=sorteos_con_balance,
        medios_pago=medios_pago,
        ganadores_muro=ganadores_muro,
        finanzas=finanzas
    )


# =========================================================
# COMPROBANTE DIGITAL OFICIAL DE BOLETA
# =========================================================

@app.route("/comprobante/<int:id>")
def ver_comprobante(id):

    venta = db.session.get(Venta, id)

    if not venta:
        flash("El comprobante solicitado no existe.", "error")
        return redirect(url_for("home"))

    sorteo = venta.sorteo
    if not sorteo:
        sorteo = Sorteo.query.filter_by(
            loteria=venta.loteria,
            fecha=venta.fecha
        ).first()

    return render_template(
        "comprobante.html",
        venta=venta,
        sorteo=sorteo
    )


# =========================================================
# LIBERAR BOLETAS APARTADAS (PENDIENTES) DE UN SORTEO
# =========================================================

@app.post("/admin/sorteos/liberar-apartados/<int:id>")
def liberar_apartados_sorteo(id):

    if not required_admin():
        return redirect(url_for("login"))

    sorteo = db.session.get(Sorteo, id)
    if not sorteo:
        flash("El sorteo no existe.", "error")
        return redirect(url_for("admin"))

    pendientes = Venta.query.filter(
        ((Venta.sorteo_id == sorteo.id) |
         ((Venta.sorteo_id == None) & (Venta.loteria == sorteo.loteria) & (Venta.fecha == sorteo.fecha))) &
        (Venta.estado == "PENDIENTE")
    ).all()

    total_liberados = len(pendientes)
    for p in pendientes:
        db.session.delete(p)

    db.session.commit()
    flash(f"🧹 Se liberaron {total_liberados} boletas apartadas del sorteo '{sorteo.nombre}'. Los números ya están libres nuevamente.", "ok")
    return redirect(url_for("admin"))


# =========================================================
# CREAR SORTEO
# =========================================================

@app.post("/admin/sorteos/crear")
def crear_sorteo():

    if not required_admin():

        return redirect(
            url_for("login")
        )

    try:

        nombre = request.form.get(
            "nombre",
            ""
        ).strip()

        loteria_select = request.form.get(
            "loteria",
            ""
        ).strip()

        loteria_otra = request.form.get(
            "loteria_otra",
            ""
        ).strip()

        loteria = loteria_otra if (loteria_select == "OTRA" and loteria_otra) else loteria_select

        fecha = request.form.get(
            "fecha",
            ""
        ).strip()

        horario = request.form.get(
            "horario",
            ""
        ).strip()

        valor = int(
            request.form.get(
                "valor"
            ) or 0
        )

        premio_mayor = request.form.get(
            "premio_mayor",
            "$320.000"
        ).strip() or "$320.000"

        premio_primeras = request.form.get(
            "premio_primeras",
            "$50.000"
        ).strip() or "$50.000"

        premio_medio = request.form.get(
            "premio_medio",
            "$50.000"
        ).strip() or "$50.000"

        if not nombre:
            raise ValueError(
                "Debes ingresar el nombre del sorteo."
            )

        if not loteria:
            raise ValueError(
                "Debes seleccionar una lotería."
            )

        if not fecha:
            raise ValueError(
                "Debes seleccionar la fecha."
            )

        if not horario:
            raise ValueError(
                "Debes seleccionar el horario."
            )

        sorteo = Sorteo(
            nombre=nombre,
            loteria=loteria,
            fecha=fecha,
            horario=horario,
            valor=valor,
            premio_mayor=premio_mayor,
            premio_primeras=premio_primeras,
            premio_medio=premio_medio,
            estado="ACTIVO"
        )

        db.session.add(
            sorteo
        )

        db.session.commit()

        flash(
            "🎰 Sorteo creado correctamente.",
            "ok"
        )

    except Exception as error:

        db.session.rollback()

        flash(
            "No se pudo crear el sorteo: "
            + str(error),
            "error"
        )

    return redirect(
        url_for("admin")
    )


# =========================================================
# CERRAR / ABRIR SORTEO
# =========================================================

@app.post("/admin/sorteos/estado/<int:id>")
def cambiar_estado_sorteo(id):

    if not required_admin():

        return redirect(
            url_for("login")
        )

    sorteo = db.session.get(
        Sorteo,
        id
    )

    if sorteo:

        if sorteo.estado == "ACTIVO":
            sorteo.estado = "CERRADO"
            mensaje = "🔒 Sorteo cerrado."
        else:
            sorteo.estado = "ACTIVO"
            mensaje = "🟢 Sorteo activado."

        db.session.commit()

        flash(
            mensaje,
            "ok"
        )

    return redirect(
        url_for("admin")
    )


# =========================================================
# ELIMINAR SORTEO
# =========================================================

@app.post("/admin/sorteos/eliminar/<int:id>")
def eliminar_sorteo(id):

    if not required_admin():

        return redirect(
            url_for("login")
        )

    sorteo = db.session.get(
        Sorteo,
        id
    )

    if sorteo:

        ventas_asociadas = Venta.query.filter_by(
            sorteo_id=sorteo.id
        ).count()

        if ventas_asociadas > 0:

            flash(
                "⚠️ No puedes eliminar un sorteo que tiene ventas asociadas.",
                "error"
            )

            return redirect(
                url_for("admin")
            )

        db.session.delete(
            sorteo
        )

        db.session.commit()

        flash(
            "Sorteo eliminado correctamente.",
            "ok"
        )

    return redirect(
        url_for("admin")
    )


# =========================================================
# CAMBIAR ESTADO DE VENTA
# =========================================================

@app.post(
    "/admin/estado/<int:id>"
)
def cambiar_estado(id):

    if not required_admin():

        return redirect(
            url_for("login")
        )

    venta = db.session.get(
        Venta,
        id
    )

    if venta:

        if venta.estado == "PAGADO":
            venta.estado = "PENDIENTE"
        else:
            venta.estado = "PAGADO"

        db.session.commit()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ELIMINAR VENTA
# =========================================================

@app.post(
    "/admin/eliminar/<int:id>"
)
def eliminar(id):

    if not required_admin():

        return redirect(
            url_for("login")
        )

    venta = db.session.get(
        Venta,
        id
    )

    if venta:

        db.session.delete(
            venta
        )

        db.session.commit()

    return redirect(
        url_for("admin")
    )


# =========================================================
# IMPORTAR EXCEL
# =========================================================

@app.post("/admin/importar")
def importar():

    if not required_admin():

        return redirect(
            url_for("login")
        )

    archivo = request.files.get(
        "archivo"
    )

    if not archivo:

        flash(
            "Selecciona un archivo Excel.",
            "error"
        )

        return redirect(
            url_for("admin")
        )

    try:

        df = pd.read_excel(
            archivo
        )

        required = [
            "telefono",
            "nombre",
            "numero",
            "loteria",
            "fecha",
            "valor",
            "estado"
        ]

        missing = [
            columna
            for columna in required
            if columna not in df.columns
        ]

        if missing:

            raise ValueError(
                "Faltan columnas: "
                + ", ".join(missing)
            )

        count = 0
        duplicados = 0

        for _, row in df.iterrows():

            numero = str(
                row["numero"]
            ).replace(
                ".0",
                ""
            ).strip()

            loteria = str(
                row["loteria"]
            ).strip()

            existente = (
                Venta.query
                .filter_by(
                    numero=numero,
                    loteria=loteria
                )
                .first()
            )

            if existente:

                duplicados += 1
                continue

            venta = Venta(

                telefono=clean_phone(
                    row["telefono"]
                ),

                nombre=str(
                    row["nombre"]
                ).strip(),

                numero=numero,

                loteria=loteria,

                fecha=str(
                    row["fecha"]
                ).strip(),

                valor=(
                    int(
                        float(
                            row["valor"]
                        )
                    )
                    if str(
                        row["valor"]
                    ).strip()
                    else 0
                ),

                estado=str(
                    row["estado"]
                ).upper().strip()
            )

            db.session.add(
                venta
            )

            count += 1

        db.session.commit()

        if duplicados > 0:

            flash(
                f"✅ Se importaron {count} ventas. "
                f"⚠️ Se omitieron {duplicados} duplicadas.",
                "ok"
            )

        else:

            flash(
                f"✅ Se importaron {count} ventas.",
                "ok"
            )

    except Exception as error:

        db.session.rollback()

        flash(
            "Error al importar: "
            + str(error),
            "error"
        )

    return redirect(
        url_for("admin")
    )


# =========================================================
# EXPORTAR EXCEL
# =========================================================

@app.get("/admin/exportar")
def exportar():

    if not required_admin():

        return redirect(
            url_for("login")
        )

    ventas = (
        Venta.query
        .order_by(
            Venta.id
        )
        .all()
    )

    datos = []

    for venta in ventas:

        datos.append({

            "telefono": venta.telefono,

            "nombre": venta.nombre,

            "numero": venta.numero,

            "loteria": venta.loteria,

            "fecha": venta.fecha,

            "valor": venta.valor,

            "estado": venta.estado,

            "sorteo": (
                venta.sorteo.nombre
                if venta.sorteo
                else ""
            )
        })

    df = pd.DataFrame(
        datos
    )

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Ventas"
        )

    output.seek(0)

    return send_file(

        output,

        as_attachment=True,

        download_name=(
            "dinamicas_alex_2027_ventas.xlsx"
        ),

        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )


# =========================================================
# CONFIGURACIÓN DE MEDIOS DE PAGO (AJUSTES)
# =========================================================

@app.post("/admin/ajustes")
def guardar_ajustes():

    if not required_admin():
        return redirect(url_for("login"))

    try:
        campos = ["nequi", "daviplata", "bancolombia", "titular"]
        for campo in campos:
            valor = request.form.get(campo, "").strip()
            item = Ajuste.query.filter_by(clave=campo).first()
            if not item:
                item = Ajuste(clave=campo, valor=valor)
                db.session.add(item)
            else:
                item.valor = valor

        db.session.commit()
        flash("💳 Medios de pago actualizados correctamente.", "ok")

    except Exception as error:
        db.session.rollback()
        flash(f"Error al guardar ajustes: {str(error)}", "error")

    return redirect(url_for("admin"))


# =========================================================
# GESTIÓN DEL MURO DE GANADORES (PUBLICAR / ELIMINAR)
# =========================================================

@app.post("/admin/ganadores/publicar")
def publicar_ganador():

    if not required_admin():
        return {"error": "No autorizado"}, 401

    try:
        data = request.get_json() or {}
        sorteo_nombre = str(data.get("sorteo_nombre", "")).strip() or "Dinámica Oficial"
        loteria = str(data.get("loteria", "")).strip()
        fecha = str(data.get("fecha", "")).strip()
        numero = str(data.get("numero", "")).strip().zfill(2)
        nombre = str(data.get("nombre", "")).strip()
        categoria = str(data.get("categoria", "")).strip() or "Premio Ganador"
        premio = str(data.get("premio", "")).strip() or "$50.000"
        cifras_sorteo = str(data.get("cifras_sorteo", "")).strip()

        if not nombre or not numero:
            return {"error": "Faltan el nombre o el número del ganador."}, 400

        # Evitar registros duplicados idénticos en el muro
        existente = GanadorHistorico.query.filter_by(
            loteria=loteria,
            fecha=fecha,
            numero=numero,
            categoria=categoria
        ).first()

        if existente:
            return {
                "ok": True,
                "mensaje": "Este ganador ya se encuentra publicado en el Muro Oficial."
            }

        nuevo = GanadorHistorico(
            sorteo_nombre=sorteo_nombre,
            loteria=loteria,
            fecha=fecha,
            numero=numero,
            nombre=nombre,
            categoria=categoria,
            premio=premio,
            cifras_sorteo=cifras_sorteo
        )

        db.session.add(nuevo)
        db.session.commit()

        return {
            "ok": True,
            "mensaje": f"🏆 ¡{nombre} (#{numero}) publicado con éxito en el Muro!",
            "id": nuevo.id
        }

    except Exception as error:
        db.session.rollback()
        return {"error": str(error)}, 500


@app.post("/admin/ganadores/eliminar/<int:id>")
def eliminar_ganador_muro(id):

    if not required_admin():
        return redirect(url_for("login"))

    try:
        ganador = db.session.get(GanadorHistorico, id)
        if ganador:
            db.session.delete(ganador)
            db.session.commit()
            flash("🏆 Ganador retirado del Muro correctamente.", "ok")
    except Exception as error:
        db.session.rollback()
        flash(f"Error al retirar ganador: {str(error)}", "error")

    return redirect(url_for("admin"))


# =========================================================
# VERIFICAR GANADORES (POR 4 CIFRAS)
# =========================================================

@app.post("/admin/verificar-ganadores")
def verificar_ganadores():

    if not required_admin():
        return {"error": "No autorizado"}, 401

    data = request.get_json() or {}
    loteria = str(data.get("loteria", "")).strip()
    fecha = str(data.get("fecha", "")).strip()
    cifras = str(data.get("cifras", "")).strip()

    cifras = re.sub(r"\D", "", cifras)

    if len(cifras) < 4:
        return {
            "error": "Debes ingresar al menos 4 cifras del sorteo (ej: 5827)."
        }, 400

    ultimas_2 = cifras[-2:]
    primeras_2 = cifras[:2]
    medio_2 = cifras[1:3]

    consulta = Venta.query

    if loteria:
        consulta = consulta.filter_by(loteria=loteria)

    if fecha:
        consulta = consulta.filter_by(fecha=fecha)

    todas_ventas = consulta.all()

    def serialize_ventas(ventas_list, cat_label):
        resultado = []
        for v in ventas_list:
            sorteo_nombre = v.sorteo.nombre if v.sorteo else "Dinámica Oficial"
            premio_estimado = "$50.000"
            if v.sorteo:
                if "Mayor" in cat_label or "últimas" in cat_label.lower():
                    premio_estimado = v.sorteo.premio_mayor or "$320.000"
                elif "primeras" in cat_label.lower():
                    premio_estimado = v.sorteo.premio_primeras or "$50.000"
                else:
                    premio_estimado = v.sorteo.premio_medio or "$50.000"

            resultado.append({
                "id": v.id,
                "nombre": v.nombre,
                "telefono": v.telefono,
                "numero": v.numero,
                "loteria": v.loteria,
                "fecha": v.fecha,
                "valor": v.valor,
                "estado": v.estado,
                "sorteo_nombre": sorteo_nombre,
                "premio_estimado": premio_estimado
            })
        return resultado

    def buscar_por_numero(target_num, cat_label):
        matches = []
        target_int = int(target_num) if target_num.isdigit() else None
        for v in todas_ventas:
            num_clean = str(v.numero).strip()
            if num_clean == target_num or (target_int is not None and num_clean.isdigit() and int(num_clean) == target_int):
                matches.append(v)
        return serialize_ventas(matches, cat_label)

    return {
        "ok": True,
        "cifras": cifras,
        "loteria": loteria,
        "fecha": fecha,
        "ultimas_2": ultimas_2,
        "primeras_2": primeras_2,
        "medio_2": medio_2,
        "ganadores": {
            "ultimas": buscar_por_numero(ultimas_2, "Premio Mayor (Últimas 2)"),
            "primeras": buscar_por_numero(primeras_2, "Premio Secundario (Primeras 2)"),
            "medio": buscar_por_numero(medio_2, "Premio Secundario (Del Medio)")
        }
    }


# =========================================================
# PRUEBA DEL SERVICIO
# =========================================================

@app.get("/salud")
def salud():

    return {
        "ok": True,
        "servicio": "Dinámicas Alex 2027"
    }


# =========================================================
# EJECUTAR APLICACIÓN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
