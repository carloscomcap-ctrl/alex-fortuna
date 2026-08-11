
import os, io, re
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","cambia-esta-clave-en-produccion")

db_url=os.environ.get("DATABASE_URL","sqlite:///alex_fortuna.db")
if db_url.startswith("postgres://"):
    db_url=db_url.replace("postgres://","postgresql://",1)
app.config["SQLALCHEMY_DATABASE_URI"]=db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
db=SQLAlchemy(app)

ADMIN_USER=os.environ.get("ADMIN_USER","admin")
ADMIN_PASSWORD_HASH=generate_password_hash(os.environ.get("ADMIN_PASSWORD","cambiar123"))

class Venta(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    telefono=db.Column(db.String(30),nullable=False,index=True)
    nombre=db.Column(db.String(120),nullable=False)
    numero=db.Column(db.String(20),nullable=False)
    loteria=db.Column(db.String(100),nullable=False)
    fecha=db.Column(db.String(30),nullable=False)
    valor=db.Column(db.Integer,default=0)
    estado=db.Column(db.String(20),default="PENDIENTE")

with app.app_context():
    db.create_all()

def clean_phone(v):
    return re.sub(r"\D","",str(v or ""))

@app.route("/")
def home():
    return render_template("index.html")

@app.post("/consultar")
def consultar():
    telefono=clean_phone(request.form.get("telefono"))
    ventas=Venta.query.filter_by(telefono=telefono).order_by(Venta.fecha.desc(),Venta.numero).all()
    return render_template("resultado.html",telefono=telefono,ventas=ventas)

@app.route("/admin/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        user=request.form.get("usuario","")
        password=request.form.get("password","")
        if user==ADMIN_USER and check_password_hash(ADMIN_PASSWORD_HASH,password):
            session["admin"]=True
            return redirect(url_for("admin"))
        flash("Usuario o contraseña incorrectos.","error")
    return render_template("login.html")

@app.get("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def required_admin():
    return session.get("admin") is True

@app.route("/admin",methods=["GET","POST"])
def admin():
    if not required_admin(): return redirect(url_for("login"))
    if request.method=="POST":
        try:
            v=Venta(
                telefono=clean_phone(request.form["telefono"]),
                nombre=request.form["nombre"].strip(),
                numero=request.form["numero"].strip(),
                loteria=request.form["loteria"].strip(),
                fecha=request.form["fecha"].strip(),
                valor=int(request.form.get("valor") or 0),
                estado=request.form.get("estado","PENDIENTE")
            )
            db.session.add(v); db.session.commit()
            flash("Venta registrada.","ok")
        except Exception as e:
            db.session.rollback(); flash("No se pudo guardar: "+str(e),"error")
    ventas=Venta.query.order_by(Venta.id.desc()).all()
    return render_template("admin.html",ventas=ventas)

@app.post("/admin/estado/<int:id>")
def cambiar_estado(id):
    if not required_admin(): return redirect(url_for("login"))
    v=db.session.get(Venta,id)
    if v:
        v.estado="PAGADO" if v.estado!="PAGADO" else "PENDIENTE"
        db.session.commit()
    return redirect(url_for("admin"))

@app.post("/admin/eliminar/<int:id>")
def eliminar(id):
    if not required_admin(): return redirect(url_for("login"))
    v=db.session.get(Venta,id)
    if v: db.session.delete(v); db.session.commit()
    return redirect(url_for("admin"))

@app.post("/admin/importar")
def importar():
    if not required_admin(): return redirect(url_for("login"))
    f=request.files.get("archivo")
    if not f:
        flash("Selecciona un Excel.","error"); return redirect(url_for("admin"))
    try:
        df=pd.read_excel(f)
        required=["telefono","nombre","numero","loteria","fecha","valor","estado"]
        missing=[c for c in required if c not in df.columns]
        if missing: raise ValueError("Faltan columnas: "+", ".join(missing))
        count=0
        for _,r in df.iterrows():
            db.session.add(Venta(
                telefono=clean_phone(r["telefono"]),
                nombre=str(r["nombre"]),
                numero=str(r["numero"]).replace(".0",""),
                loteria=str(r["loteria"]),
                fecha=str(r["fecha"]),
                valor=int(float(r["valor"])) if str(r["valor"]).strip() else 0,
                estado=str(r["estado"]).upper()
            ))
            count+=1
        db.session.commit(); flash(f"Se importaron {count} ventas.","ok")
    except Exception as e:
        db.session.rollback(); flash("Error al importar: "+str(e),"error")
    return redirect(url_for("admin"))

@app.get("/admin/exportar")
def exportar():
    if not required_admin(): return redirect(url_for("login"))
    ventas=Venta.query.order_by(Venta.id).all()
    df=pd.DataFrame([{
        "telefono":v.telefono,"nombre":v.nombre,"numero":v.numero,
        "loteria":v.loteria,"fecha":v.fecha,"valor":v.valor,"estado":v.estado
    } for v in ventas])
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer: df.to_excel(writer,index=False)
    out.seek(0)
    return send_file(out,as_attachment=True,download_name="alex_fortuna_ventas.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.get("/salud")
def salud(): return {"ok":True,"servicio":"Alex Fortuna"}

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
