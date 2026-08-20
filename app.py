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
    "sqlite:///alex_fortuna.db"
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

    # Nuevo: relaciona la venta con un sorteo.
    # Es nullable para conservar las ventas antiguas.
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

    # Si la base ya existía antes de agregar Sorteos,
    # agregamos sorteo_id a Venta sin borrar los datos.
    try:
        inspector = db.inspect(db.engine)
        columnas = [
            c["name"]
            for c in inspector.get_columns("venta")
        ]

        if "sorteo_id" not in columnas:
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

    except Exception:
        # Si la columna ya existe o la base no requiere cambios,
        # la aplicación continúa normalmente.
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

    return render_template(
        "index.html"
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
            "alex_fortuna_ventas.xlsx"
        ),

        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )


# =========================================================
# PRUEBA DEL SERVICIO
# =========================================================

@app.get("/salud")
def salud():

    return {
        "ok": True,
        "servicio": "Alex Fortuna"
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
