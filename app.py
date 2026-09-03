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


# =========================================================
# APLICACIÓN
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "cambia-esta-clave-en-produccion"
)


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


def required_admin():
    return session.get("admin") is True


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

    return render_template(
        "index.html",
        sorteos_activos=sorteos_activos
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

    for venta in sorteo.ventas:
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

    return render_template(
        "tabla.html",
        sorteo=sorteo,
        mapa_numeros=mapa_numeros,
        libres=libres,
        apartados=apartados,
        pagados=pagados,
        recaudado=recaudado,
        por_recaudar=por_recaudar
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

        user = request.form.get(
            "usuario",
            ""
        )

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

            session["admin"] = True

            return redirect(
                url_for("admin")
            )

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


            # =================================================
            # COMPROBAR DUPLICADO
            # =================================================

            consulta = Venta.query.filter_by(
                numero=numero,
                loteria=loteria
            )

            if sorteo:
                consulta = consulta.filter_by(
                    sorteo_id=sorteo.id
                )

            else:
                # Las ventas antiguas sin sorteo mantienen
                # la regla anterior de número + lotería.
                consulta = consulta.filter_by(
                    sorteo_id=None
                )

            existente = consulta.first()


            if existente:

                flash(
                    f"⚠️ El número {numero} "
                    f"ya está registrado para "
                    f"{loteria} en este sorteo.",
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

                    sorteo_id=(
                        sorteo.id
                        if sorteo
                        else None
                    )
                )

                db.session.add(
                    venta
                )

                db.session.commit()

                flash(
                    "✅ Venta registrada correctamente.",
                    "ok"
                )


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

    return render_template(
        "admin.html",
        ventas=ventas,
        sorteos=sorteos,
        sorteos_activos=sorteos_activos
    )


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

        loteria = request.form.get(
            "loteria",
            ""
        ).strip()

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

    def serialize_ventas(ventas_list):
        return [
            {
                "id": v.id,
                "nombre": v.nombre,
                "telefono": v.telefono,
                "numero": v.numero,
                "loteria": v.loteria,
                "fecha": v.fecha,
                "valor": v.valor,
                "estado": v.estado
            }
            for v in ventas_list
        ]

    def buscar_por_numero(target_num):
        matches = []
        target_int = int(target_num) if target_num.isdigit() else None
        for v in todas_ventas:
            num_clean = str(v.numero).strip()
            if num_clean == target_num or (target_int is not None and num_clean.isdigit() and int(num_clean) == target_int):
                matches.append(v)
        return serialize_ventas(matches)

    return {
        "ok": True,
        "cifras": cifras,
        "ultimas_2": ultimas_2,
        "primeras_2": primeras_2,
        "medio_2": medio_2,
        "ganadores": {
            "ultimas": buscar_por_numero(ultimas_2),
            "primeras": buscar_por_numero(primeras_2),
            "medio": buscar_por_numero(medio_2)
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
