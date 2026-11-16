import re
from werkzeug.security import generate_password_hash
import os
import uuid
import pymysql
import boto3
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, abort
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

BUCKET = os.environ["S3_BUCKET"]
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

def get_db():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )

def es_imagen_mime(tipo_mime, nombre):
    if tipo_mime and tipo_mime.startswith("image/"):
        return True
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    return ext in ["jpg", "jpeg", "png", "gif", "webp"]

def puede_ver(estado, autor_id):
    if estado == "publicada":
        return True
    return session.get("rol") == "moderador" or session.get("user_id") == autor_id

def guardar_adjunto(archivo, entrada_id):
    nombre = secure_filename(archivo.filename)
    if not nombre:
        return None
    clave = f"uploads/{uuid.uuid4().hex}_{nombre}"
    tipo_mime = archivo.mimetype or "application/octet-stream"

    s3.upload_fileobj(
        archivo.stream,
        BUCKET,
        clave,
        ExtraArgs={"ContentType": tipo_mime},
    )

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Si se está editando y ya tenía adjunto, reemplazamos el registro
            cur.execute("DELETE FROM adjuntos WHERE entrada_id = %s", (entrada_id,))
            cur.execute(
                "INSERT INTO adjuntos (entrada_id, nombre_original, clave_s3, tipo_mime) "
                "VALUES (%s, %s, %s, %s)",
                (entrada_id, nombre, clave, tipo_mime),
            )
            return cur.lastrowid
    finally:
        conn.close()

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    cat = request.args.get("categoria", "").strip()
    autor = request.args.get("autor", "").strip()

    sql = """
        SELECT e.id, e.titulo, e.contenido, e.creado_en AS fecha, e.estado,
               u.nombre AS autor_nombre, u.usuario AS autor_user,
               c.nombre AS categoria,
               a.id AS adjunto_id, a.nombre_original AS archivo_nombre, a.tipo_mime
        FROM entradas e
        JOIN usuarios u ON u.id = e.autor_id
        JOIN categorias c ON c.id = e.categoria_id
        LEFT JOIN adjuntos a ON a.entrada_id = e.id
        WHERE e.estado = 'publicada'
    """
    params = []
    if q:
        sql += " AND (e.titulo LIKE %s OR e.contenido LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if cat:
        sql += " AND c.nombre = %s"
        params.append(cat)
    if autor:
        sql += " AND u.usuario = %s"
        params.append(autor)

    sql += " ORDER BY e.creado_en DESC"

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            resultados = cur.fetchall()

            for r in resultados:
                if r["adjunto_id"]:
                    r["archivo_url"] = url_for("descargar_adjunto", adjunto_id=r["adjunto_id"])
                    r["es_imagen"] = es_imagen_mime(r["tipo_mime"], r["archivo_nombre"] or "")
                else:
                    r["archivo_url"] = None
                    r["es_imagen"] = False

            cur.execute("SELECT nombre FROM categorias ORDER BY nombre")
            categorias = [row["nombre"] for row in cur.fetchall()]

            cur.execute("SELECT usuario AS username, nombre FROM usuarios WHERE rol = 'autor' ORDER BY nombre")
            autores = cur.fetchall()
    finally:
        conn.close()

    return render_template("index.html", entradas=resultados, categorias=categorias, autores=autores, q=q, cat=cat, autor=autor)

@app.route("/entrada/<int:id>")
def ver_entrada(id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id, e.titulo, e.contenido, e.creado_en AS fecha, e.estado, e.autor_id,
                       u.nombre AS autor_nombre, c.nombre AS categoria,
                       a.id AS adjunto_id, a.nombre_original AS archivo_nombre, a.tipo_mime
                FROM entradas e
                JOIN usuarios u ON u.id = e.autor_id
                JOIN categorias c ON c.id = e.categoria_id
                LEFT JOIN adjuntos a ON a.entrada_id = e.id
                WHERE e.id = %s
            """, (id,))
            entrada = cur.fetchone()
    finally:
        conn.close()

    if not entrada:
        flash("La publicación solicitada no existe.", "danger")
        return redirect(url_for("index"))

    if not puede_ver(entrada["estado"], entrada["autor_id"]):
        flash("Acceso restringido: Esta publicación es un borrador privado o fue retirada.", "warning")
        return redirect(url_for("index"))

    if entrada["adjunto_id"]:
        entrada["archivo_url"] = url_for("descargar_adjunto", adjunto_id=entrada["adjunto_id"])
        entrada["es_imagen"] = es_imagen_mime(entrada["tipo_mime"], entrada["archivo_nombre"] or "")
    else:
        entrada["archivo_url"] = None
        entrada["es_imagen"] = False

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.contenido, c.creado_en AS fecha, u.nombre AS autor_nombre, u.rol AS autor_rol
                FROM comentarios c
                JOIN usuarios u ON u.id = c.usuario_id
                WHERE c.entrada_id = %s
                ORDER BY c.creado_en ASC
            """, (id,))
            comentarios = cur.fetchall()
    finally:
        conn.close()

    return render_template("post.html", entrada=entrada, comentarios=comentarios)

@app.route("/entrada/<int:id>/comentar", methods=["POST"])
def comentar_entrada(id):
    texto = request.form.get("comentario", "").strip()
    if not texto:
        flash("Escribe un comentario antes de publicar.", "warning")
        return redirect(url_for("ver_entrada", id=id) + "#comentarios")

    if not session.get("user_id"):
        session["comentario_pendiente"] = {"entrada_id": id, "contenido": texto}
        flash("Inicia sesión o crea una cuenta nueva para que tu comentario se publique automáticamente.", "info")
        return redirect(url_for("login"))

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO comentarios (entrada_id, usuario_id, contenido) VALUES (%s, %s, %s)",
                (id, session["user_id"], texto),
            )
    finally:
        conn.close()

    flash("¡Tu comentario ha sido publicado!", "success")
    return redirect(url_for("ver_entrada", id=id) + "#comentarios")

@app.route("/archivo/<int:adjunto_id>")
def descargar_adjunto(adjunto_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.clave_s3, a.nombre_original, a.tipo_mime, e.estado, e.autor_id "
                "FROM adjuntos a JOIN entradas e ON e.id = a.entrada_id WHERE a.id = %s",
                (adjunto_id,),
            )
            fila = cur.fetchone()
    finally:
        conn.close()

    if not fila or not puede_ver(fila["estado"], fila["autor_id"]):
        abort(404)

    forzar_descarga = request.args.get("download") == "1"
    disposicion = "attachment" if forzar_descarga else "inline"
    objeto = s3.get_object(Bucket=BUCKET, Key=fila["clave_s3"])
    return Response(
        objeto["Body"].iter_chunks(chunk_size=8192),
        content_type=fila["tipo_mime"] or "application/octet-stream",
        headers={"Content-Disposition": f'{disposicion}; filename="{fila["nombre_original"]}"'},
    )

@app.route("/panel")
def panel():
    if not session.get("user_id"):
        flash("Inicia sesión para acceder a tu panel de gestión.", "warning")
        return redirect(url_for("login"))

    conn = get_db()
    try:
        with conn.cursor() as cur:
            base_sql = """
                SELECT e.id, e.titulo, e.estado, e.creado_en AS fecha,
                       u.nombre AS autor_nombre, c.nombre AS categoria,
                       a.nombre_original AS archivo_nombre
                FROM entradas e
                JOIN usuarios u ON u.id = e.autor_id
                JOIN categorias c ON c.id = e.categoria_id
                LEFT JOIN adjuntos a ON a.entrada_id = e.id
            """
            if session.get("rol") == "moderador":
                cur.execute(base_sql + " ORDER BY e.creado_en DESC")
            else:
                cur.execute(base_sql + " WHERE e.autor_id = %s ORDER BY e.creado_en DESC", (session["user_id"],))
            mis_entradas = cur.fetchall()
    finally:
        conn.close()

    return render_template("panel.html", entradas=mis_entradas)

@app.route("/nueva", methods=["GET", "POST"])
@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editor(id=None):
    if not session.get("user_id"):
        flash("Debes iniciar sesión para redactar entradas.", "warning")
        return redirect(url_for("login"))

    conn = get_db()
    entrada = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nombre FROM categorias ORDER BY nombre")
            categorias_db = cur.fetchall()

            if id:
                cur.execute("""
                    SELECT e.*, a.nombre_original AS archivo_nombre
                    FROM entradas e
                    LEFT JOIN adjuntos a ON a.entrada_id = e.id
                    WHERE e.id = %s
                """, (id,))
                entrada = cur.fetchone()
                if not entrada or (entrada["autor_id"] != session["user_id"] and session.get("rol") != "moderador"):
                    flash("No tienes permiso para modificar esta publicación.", "danger")
                    destino_comentario = procesar_comentario_pendiente(user["id"])
            return redirect(destino_comentario or url_for("panel"))

        if request.method == "POST":
            titulo = request.form.get("titulo", "").strip()
            contenido = request.form.get("contenido", "").strip()
            categoria_id = request.form.get("categoria_id", "").strip()
            estado = request.form.get("estado", "borrador")
            archivo = request.files.get("archivo")

            if not titulo or not contenido or not categoria_id:
                flash("Error de validación: El título, la categoría y el contenido son obligatorios.", "danger")
                return render_template("editor.html", entrada=entrada, categorias=categorias_db)

            with conn.cursor() as cur:
                if id:
                    cur.execute("""
                        UPDATE entradas
                        SET titulo=%s, contenido=%s, categoria_id=%s, estado=%s
                        WHERE id=%s
                    """, (titulo, contenido, int(categoria_id), estado, id))
                    entrada_id = id
                    flash("Publicación actualizada correctamente en RDS.", "success")
                else:
                    cur.execute("""
                        INSERT INTO entradas (titulo, contenido, autor_id, categoria_id, estado)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (titulo, contenido, session["user_id"], int(categoria_id), estado))
                    entrada_id = cur.lastrowid
                    flash(f"Entrada guardada en RDS como '{estado}'.", "success")

            if archivo and archivo.filename:
                try:
                    guardar_adjunto(archivo, entrada_id)
                except Exception as e:
                    flash(f"Entrada guardada, pero hubo un error al subir el archivo a S3: {str(e)}", "warning")

            return redirect(url_for("panel"))
    finally:
        conn.close()

    return render_template("editor.html", entrada=entrada, categorias=categorias_db)

@app.route("/moderar/<int:id>/<accion>", methods=["POST"])
def moderar(id, accion):
    if session.get("rol") != "moderador":
        flash("Operación no permitida: Se requiere perfil de moderador.", "danger")
        return redirect(url_for("index"))

    nuevo_estado = "retirada" if accion == "retirar" else "publicada"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE entradas SET estado = %s WHERE id = %s", (nuevo_estado, id))
    finally:
        conn.close()

    flash(f"Estado cambiado a '{nuevo_estado}' para la entrada #{id}.", "info")
    return redirect(url_for("panel"))

def procesar_comentario_pendiente(user_id):
    pendiente = session.pop("comentario_pendiente", None)
    if pendiente and pendiente.get("entrada_id") and pendiente.get("contenido"):
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO comentarios (entrada_id, usuario_id, contenido) VALUES (%s, %s, %s)",
                    (pendiente["entrada_id"], user_id, pendiente["contenido"]),
                )
        finally:
            conn.close()
        flash("¡Bienvenido! Tu comentario pendiente fue publicado automáticamente.", "success")
        return url_for("ver_entrada", id=pendiente["entrada_id"]) + "#comentarios"
    return None

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM usuarios WHERE usuario = %s", (username,))
                user = cur.fetchone()
        finally:
            conn.close()

        # Soporta contraseñas en texto plano o con hash (por si schema.sql usa generate_password_hash)
        valido = False
        if user:
            campo_pass = user.get("password_hash") or user.get("password") or ""
            if campo_pass.startswith(("scrypt:", "pbkdf2:")):
                valido = check_password_hash(campo_pass, password)
            else:
                valido = (campo_pass == password)

        if valido:
            session["user_id"] = user["id"]
            session["username"] = user["usuario"]
            session["nombre"] = user["nombre"]
            session["rol"] = user["rol"]
            flash(f"Sesión iniciada como {user['nombre']} ({user['rol']}).", "success")
            return redirect(url_for("panel"))
        else:
            flash("Credenciales incorrectas. Verifica tu usuario y contraseña.", "danger")

    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if session.get("user_id"):
        return redirect(url_for("panel"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirmar = request.form.get("confirmar", "").strip()

        if not nombre or not username or not password:
            flash("Todos los campos son obligatorios.", "danger")
            return render_template("registro.html")

        if " " in username:
            flash("El nombre de usuario no puede contener espacios.", "danger")
            return render_template("registro.html")

        if (
            len(password) < 8
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"\d", password)
        ):
            flash("La contraseña debe tener al menos 8 caracteres e incluir mayúsculas, minúsculas y números.", "danger")
            return render_template("registro.html")

        if password != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("registro.html")

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM usuarios WHERE usuario = %s", (username,))
                if cur.fetchone():
                    flash("Ese nombre de usuario ya está ocupado. Elige otro.", "warning")
                    return render_template("registro.html")

                phash = generate_password_hash(password)
                cur.execute(
                    "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s, %s, %s, 'autor')",
                    (nombre, username, phash)
                )
                nuevo_id = cur.lastrowid
        finally:
            conn.close()

        session["user_id"] = nuevo_id
        session["nombre"] = nombre
        session["usuario"] = username
        session["rol"] = "autor"

        destino_comentario = procesar_comentario_pendiente(nuevo_id)
        if destino_comentario:
            return redirect(destino_comentario)

        flash("Cuenta creada exitosamente. ¡Bienvenido a CloudBlog!", "success")
        return redirect(url_for("panel"))

    return render_template("registro.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
