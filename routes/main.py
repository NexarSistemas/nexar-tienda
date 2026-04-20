from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
from pathlib import Path

import database as db
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from services.license_storage import cargar_licencia, guardar_licencia
from services.license_sdk import get_current_hwid, get_license_product, validate_license_key
from services.runtime_config import app_data_dir
from services.supabase_license_api import (
    create_license_request,
    generate_activation_id,
    is_configured as supabase_configured,
)
from services.update_checker import download_release_asset, get_cached_update_info

main_bp = Blueprint("main", __name__)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = app_data_dir()
BACKUP_DIR = DATA_DIR / "respaldo"
UPDATE_DIR = DATA_DIR / "updates"
CHANGELOG_PATH = BASE_DIR / "CHANGELOG.md"


def _as_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes", "si"}


def _is_same_origin_local_request() -> bool:
    if request.remote_addr not in {"127.0.0.1", "::1", "localhost"}:
        return False
    expected = request.host_url.rstrip("/")
    for header in ("Origin", "Referer"):
        value = request.headers.get(header, "").rstrip("/")
        if value and not value.startswith(expected):
            return False
    return True


def _validate_password(password: str) -> tuple[bool, str]:
    if len(password or "") < 6 or len(password or "") > 12:
        return False, "La contraseÃ±a debe tener entre 6 y 12 caracteres."
    if not re.search(r"[A-Z]", password or ""):
        return False, "La contraseÃ±a debe incluir una mayÃºscula."
    if not re.search(r"[a-z]", password or ""):
        return False, "La contraseÃ±a debe incluir una minÃºscula."
    if not re.search(r"[0-9]", password or ""):
        return False, "La contraseÃ±a debe incluir un nÃºmero."
    if not re.search(r"[^A-Za-z0-9]", password or ""):
        return False, "La contraseÃ±a debe incluir un sÃ­mbolo."
    return True, ""


def _limit_allows(kind: str) -> bool:
    current_sql = {
        "productos": "SELECT COUNT(*) FROM productos WHERE activo=1",
        "clientes": "SELECT COUNT(*) FROM clientes WHERE activo=1",
        "proveedores": "SELECT COUNT(*) FROM proveedores WHERE activo=1",
    }[kind]
    current = int(db.q(current_sql, fetchone=True)[0] or 0)
    check = db.check_license_limits(kind, current + 1)
    if not check["ok"]:
        flash(f"âš ï¸ {check['message']}", "warning")
        return False
    return True


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("user", {}).get("rol") not in {"Administrador", "admin"}:
            flash("âŒ No tenÃ©s permisos para acceder a esa secciÃ³n.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def _cart() -> list[dict]:
    return session.setdefault("cart", [])


def _save_cart(cart: list[dict]) -> None:
    session["cart"] = cart
    session.modified = True


def _clear_cart() -> None:
    session.pop("cart", None)
    session.modified = True


def _backup_list() -> list[dict]:
    BACKUP_DIR.mkdir(exist_ok=True)
    items = []
    for path in sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        items.append({"nombre": path.name, "fecha": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"), "tamanio_kb": round(stat.st_size / 1024, 1)})
    return items


def _update_list() -> list[dict]:
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    candidates = [*UPDATE_DIR.glob("nexar-tienda_*_amd64.deb"), *UPDATE_DIR.glob("NexarTienda_*_Setup.exe")]
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        is_windows_installer = path.suffix.lower() == ".exe"
        items.append({
            "nombre": path.name,
            "ruta": str(path),
            "fecha": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "tamanio_mb": round(stat.st_size / 1024 / 1024, 1),
            "comando": str(path) if is_windows_installer else f"sudo apt install {path}",
            "tipo": "Windows" if is_windows_installer else "Linux",
        })
    return items


def _update_file(nombre: str) -> Path:
    safe_name = Path(nombre or "").name
    valid_linux = safe_name.startswith("nexar-tienda_") and safe_name.endswith("_amd64.deb")
    valid_windows = safe_name.startswith("NexarTienda_") and safe_name.endswith("_Setup.exe")
    if safe_name != nombre or not (valid_linux or valid_windows):
        abort(404)
    path = (UPDATE_DIR / safe_name).resolve()
    if path.parent != UPDATE_DIR.resolve() or not path.exists():
        abort(404)
    return path


def _apt_readable_copy(installer: Path) -> Path:
    temp_dir = Path("/tmp") / "nexar-tienda-updates"
    temp_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        temp_dir.chmod(0o755)
    target = temp_dir / installer.name
    shutil.copy2(installer, target)
    if os.name != "nt":
        target.chmod(0o644)
    return target


def _backup_file(nombre: str) -> Path:
    safe_name = Path(nombre or "").name
    if safe_name != nombre or not safe_name.endswith(".db"):
        abort(404)
    path = (BACKUP_DIR / safe_name).resolve()
    if path.parent != BACKUP_DIR.resolve() or not path.exists():
        abort(404)
    return path


def _is_sqlite_database(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except Exception:
        return False


def _make_backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"tienda_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db"
    shutil.copy2(db.DB_PATH, target)
    try:
        if os.name != "nt":
            target.chmod(0o600)
    except Exception:
        pass
    db.set_config({"backup_ultimo": datetime.now().strftime("%Y-%m-%d %H:%M")})
    keep = int(db.get_config().get("backup_keep", "10") or 10)
    for extra in sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        extra.unlink(missing_ok=True)
    return target


def _caja_abierta():
    return db.q("SELECT * FROM caja WHERE estado=1 ORDER BY id DESC LIMIT 1", fetchone=True)


def _caja_movimientos(caja_id):
    return db.q("SELECT * FROM caja_movimientos WHERE caja_id=? ORDER BY created_at DESC, id DESC", (caja_id,))


def _caja_resumen(caja_row) -> dict:
    if not caja_row:
        return {"ventas": 0, "ingresos": 0, "egresos": 0, "total": 0}
    fecha = str(caja_row["fecha_apertura"])[:10]
    ventas = db.q("SELECT COALESCE(SUM(total),0) as total FROM ventas WHERE fecha=? AND medio_pago='Efectivo'", (fecha,), fetchone=True)
    movs = _caja_movimientos(caja_row["id"])
    ingresos = sum(float(m["monto"] or 0) for m in movs if m["tipo"] == "INGRESO")
    egresos = sum(float(m["monto"] or 0) for m in movs if m["tipo"] == "EGRESO")
    total = float(caja_row["saldo_inicial"] or 0) + float(ventas["total"] or 0) + ingresos - egresos
    return {"ventas": float(ventas["total"] or 0), "ingresos": ingresos, "egresos": egresos, "total": total}


@main_bp.route("/registro-inicial", methods=["GET", "POST"])
def registro_inicial():
    if db.count_usuarios() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        nombre = request.form.get("nombre_completo", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        question = request.form.get("security_question", "").strip()
        answer = request.form.get("security_answer", "").strip()
        if not all([nombre, username, password, question, answer]):
            flash("âš ï¸ CompletÃ¡ todos los campos.", "warning")
            return render_template("registro_inicial.html", nombre=nombre, username=username)
        ok, msg = _validate_password(password)
        if not ok:
            flash(f"âŒ {msg}", "danger")
            return render_template("registro_inicial.html", nombre=nombre, username=username)
        db.add_usuario(username, password, "Administrador", nombre, question, answer)
        flash("âœ… Administrador creado. Ya podÃ©s iniciar sesiÃ³n.", "success")
        return redirect(url_for("login"))
    return render_template("registro_inicial.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if db.count_usuarios() == 0:
        return redirect(url_for("registro_inicial"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_usuario_by_username(username)
        if not user or not int(user["activo"] or 0) or not db.verify_password(password, user["password_hash"]):
            flash("âŒ Usuario o contraseÃ±a incorrectos.", "danger")
            return render_template("login.html", next=request.form.get("next", ""))
        session["user"] = {"id": user["id"], "username": user["username"], "nombre_completo": user["nombre_completo"] or user["username"], "rol": user["rol"]}
        if not user["security_question"] or not user["security_answer_hash"]:
            flash("âš ï¸ Antes de continuar, configurÃ¡ tu pregunta y respuesta secreta.", "warning")
            return redirect(url_for("configurar_recuperacion", next=request.form.get("next", "")))
        flash(f"âœ… Bienvenido, {user['nombre_completo'] or user['username']}!", "success")
        return redirect(request.form.get("next") or url_for("dashboard"))
    return render_template("login.html", next=request.args.get("next", ""))


@main_bp.route("/configurar-recuperacion", methods=["GET", "POST"])
@login_required
def configurar_recuperacion():
    usuario = db.q("SELECT * FROM usuarios WHERE id=?", (session["user"]["id"],), fetchone=True)
    if not usuario:
        session.clear()
        return redirect(url_for("login"))
    if usuario["security_question"] and usuario["security_answer_hash"]:
        return redirect(request.args.get("next") or url_for("dashboard"))

    if request.method == "POST":
        question = request.form.get("security_question", "").strip()
        answer = request.form.get("security_answer", "").strip()
        if not question or not answer:
            flash("âš ï¸ La pregunta y la respuesta secreta son obligatorias.", "warning")
            return render_template("configurar_recuperacion.html", usuario=usuario)
        db.update_perfil(usuario["id"], {
            "nombre_completo": usuario["nombre_completo"],
            "security_question": question,
            "security_answer": answer,
        })
        flash("âœ… RecuperaciÃ³n de contraseÃ±a configurada.", "success")
        return redirect(request.form.get("next") or url_for("dashboard"))

    return render_template("configurar_recuperacion.html", usuario=usuario, next=request.args.get("next", ""))


@main_bp.route("/recuperar-password", methods=["GET", "POST"])
def recuperar_password():
    step, user, username = 1, None, ""
    if request.method == "POST":
        step = int(request.form.get("step", "1") or 1)
        username = request.form.get("username", "").strip()
        if step == 1:
            user = db.get_usuario_by_username(username)
            if user and user["security_question"]:
                step = 2
            else:
                flash("âŒ Usuario inexistente o sin recuperaciÃ³n configurada.", "danger")
        elif step == 2:
            user = db.get_usuario_by_username(username)
            security_answer = request.form.get("security_answer", "")
            if user and db.verify_security_answer(security_answer, user["security_answer_hash"] or ""):
                if db.needs_security_answer_rehash(user["security_answer_hash"] or ""):
                    db.set_security_answer_hash(user["id"], security_answer)
                step = 3
            else:
                flash("âŒ La respuesta no coincide.", "danger")
                step = 1
        elif step == 3:
            ok, msg = _validate_password(request.form.get("password", ""))
            if ok:
                db.set_password_for_username(username, request.form.get("password", ""))
                flash("âœ… ContraseÃ±a restablecida.", "success")
                return redirect(url_for("login"))
            flash(f"âŒ {msg}", "danger")
    return render_template("recuperar_password.html", step=step, user=user, username=username)


@main_bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", stats=db.get_dashboard_stats())


@main_bp.route("/productos")
@login_required
def productos():
    buscar = request.args.get("q", "")
    productos_rows = [dict(r) for r in db.get_productos(search=buscar)]
    return render_template("productos.html", productos=productos_rows, categorias=db.get_categorias(), buscar=buscar, categoria_filtro=request.args.get("categoria", ""))


@main_bp.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
def producto_nuevo():
    if request.method == "POST":
        if not _limit_allows("productos"):
            return redirect(url_for("productos"))
        db.add_producto(request.form.to_dict())
        flash("âœ… Producto creado.", "success")
        return redirect(url_for("productos"))
    return render_template("producto_form.html", producto=None, stock=None, categorias=db.get_categorias(), accion="Nuevo")


@main_bp.route("/productos/<int:pid>/editar", methods=["GET", "POST"])
@login_required
def producto_editar(pid):
    producto = db.get_producto(pid)
    stock = db.q("SELECT * FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if not producto:
        flash("âŒ Producto inexistente.", "danger")
        return redirect(url_for("productos"))
    if request.method == "POST":
        data = request.form.to_dict()
        data["activo"] = 1 if _as_bool(data.get("activo", "1")) else 0
        db.update_producto(pid, data)
        db.update_stock_item(pid, float(data.get("stock_actual", stock["stock_actual"] if stock else 0)), float(data.get("stock_minimo", 5)), float(data.get("stock_maximo", 50)), data.get("proveedor_habitual", ""))
        flash("âœ… Producto actualizado.", "success")
        return redirect(url_for("productos"))
    return render_template("producto_form.html", producto=producto, stock=stock, categorias=db.get_categorias(), accion="Editar")


@main_bp.route("/productos/<int:pid>/eliminar", methods=["POST"])
@login_required
def producto_eliminar(pid):
    db.delete_producto(pid)
    flash("âœ… Producto desactivado.", "success")
    return redirect(url_for("productos"))


@main_bp.route("/stock")
@login_required
def stock():
    buscar = request.args.get("buscar", "")
    estado = request.args.get("estado", "")
    rows = []
    for r in db.get_stock_full(search=buscar):
        item = dict(r)
        item["estado"] = item["estado"].replace(" ", "_")
        rows.append(item)
    if estado:
        rows = [r for r in rows if r["estado"] == estado]
    return render_template("stock.html", productos=rows, alertas=db.get_alertas_count(), total_stock_value=sum(float(r["valor_stock"] or 0) for r in rows))


@main_bp.route("/stock/<int:pid>/ajustar", methods=["GET", "POST"])
@login_required
def stock_ajustar(pid):
    producto = db.get_producto(pid)
    stock_row = db.q("SELECT * FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if request.method == "POST":
        anterior = float(stock_row["stock_actual"] or 0)
        nuevo = float(request.form.get("stock_actual", anterior) or anterior)
        db.update_stock_item(pid, nuevo, float(request.form.get("stock_minimo", 5)), float(request.form.get("stock_maximo", 50)), request.form.get("proveedor_habitual", ""))
        db.q("INSERT INTO stock_movimientos (producto_id,tipo,cantidad,stock_anterior,stock_nuevo,motivo) VALUES (?,?,?,?,?,?)", (pid, "AJUSTE", nuevo - anterior, anterior, nuevo, request.form.get("motivo", "Ajuste manual")), commit=True)
        flash("âœ… Stock actualizado.", "success")
        return redirect(url_for("stock"))
    return render_template("stock_ajustar.html", producto=producto, stock=stock_row, movimientos=db.get_stock_movimientos(pid))


@main_bp.route("/temporadas")
@login_required
def temporadas():
    return render_template("temporadas.html", temporadas=db.get_temporadas())


@main_bp.route("/temporadas/nueva", methods=["GET", "POST"])
@login_required
def temporada_nueva():
    if request.method == "POST":
        data = request.form.to_dict()
        data["activa"] = 1 if _as_bool(data.get("activa")) else 0
        db.add_temporada(data)
        flash("âœ… Temporada creada.", "success")
        return redirect(url_for("temporadas"))
    return render_template("temporada_form.html", temporada={}, accion="Nueva")


@main_bp.route("/temporadas/<int:tid>/editar", methods=["GET", "POST"])
@login_required
def temporada_editar(tid):
    temporada = db.get_temporada(tid)
    if request.method == "POST":
        data = request.form.to_dict()
        data["activa"] = 1 if _as_bool(data.get("activa")) else 0
        db.update_temporada(tid, data)
        flash("âœ… Temporada actualizada.", "success")
        return redirect(url_for("temporadas"))
    return render_template("temporada_form.html", temporada=temporada, accion="Editar")


@main_bp.route("/temporadas/<int:tid>/eliminar", methods=["POST"])
@login_required
def temporada_eliminar(tid):
    db.delete_temporada(tid)
    flash("âœ… Temporada eliminada.", "success")
    return redirect(url_for("temporadas"))


@main_bp.route("/punto-venta")
@login_required
def punto_venta():
    return render_template("punto_venta.html", clientes=db.get_clientes(), temporada=db.get_temporada_actual())


@main_bp.route("/api/buscar_productos")
@login_required
def api_buscar_productos():
    return jsonify({"ok": True, "productos": [dict(r) for r in db.buscar_productos_pos(request.args.get("q", ""))]})


@main_bp.route("/api/carrito/agregar", methods=["POST"])
@login_required
def api_carrito_agregar():
    payload = request.get_json(silent=True) or {}
    pid = int(payload.get("producto_id", -1) or -1)
    cantidad = float(payload.get("cantidad", 0) or 0)
    cart = _cart()
    if pid < 0:
        return jsonify({"ok": True, "carrito": cart})
    producto = db.get_producto(pid)
    stock_row = db.q("SELECT stock_actual FROM stock WHERE producto_id=?", (pid,), fetchone=True)
    if not producto or not stock_row or cantidad <= 0:
        return jsonify({"ok": False, "error": "Producto o cantidad invÃ¡lida."}), 400
    if cantidad > float(stock_row["stock_actual"] or 0):
        return jsonify({"ok": False, "error": "Stock insuficiente."}), 400
    existing = next((i for i in cart if i["producto_id"] == pid), None)
    if existing:
        existing["cantidad"] += cantidad
        existing["subtotal"] = round(existing["cantidad"] * existing["precio_unitario"], 2)
    else:
        precio = float(producto["precio_venta"] or 0)
        cart.append({"producto_id": pid, "codigo_interno": producto["codigo_interno"], "descripcion": producto["descripcion"], "categoria": producto["categoria"], "unidad": producto["unidad"], "cantidad": cantidad, "precio_unitario": precio, "descuento": 0, "subtotal": round(cantidad * precio, 2)})
    _save_cart(cart)
    return jsonify({"ok": True, "carrito": cart})


@main_bp.route("/api/carrito/quitar/<int:pid>", methods=["POST"])
@login_required
def api_carrito_quitar(pid):
    cart = [i for i in _cart() if i["producto_id"] != pid]
    _save_cart(cart)
    return jsonify({"ok": True, "carrito": cart})


@main_bp.route("/api/carrito/vaciar", methods=["POST"])
@login_required
def api_carrito_vaciar():
    _clear_cart()
    return jsonify({"ok": True})


@main_bp.route("/venta/finalizar", methods=["POST"])
@login_required
def venta_finalizar():
    cart = _cart()
    if not cart:
        flash("âš ï¸ El carrito estÃ¡ vacÃ­o.", "warning")
        return redirect(url_for("punto_venta"))
    cliente_id = int(request.form.get("cliente_id", 0) or 0)
    cliente_nombre = request.form.get("cliente_nombre", "") or "Mostrador"
    if cliente_id:
        cliente = db.get_cliente(cliente_id)
        cliente_nombre = cliente["nombre"] if cliente else cliente_nombre
    venta_id = db.crear_venta(cart, cliente_nombre, request.form.get("medio_pago", "Efectivo"), float(request.form.get("descuento_adicional", 0) or 0), session["user"]["username"], cliente_id=cliente_id, temporada=(db.get_temporada_actual() or {}).get("nombre", ""))
    db.decrementar_stock_venta(venta_id)
    _clear_cart()
    flash("âœ… Venta registrada.", "success")
    return redirect(url_for("ticket", vid=venta_id))


@main_bp.route("/ticket/<int:vid>")
@login_required
def ticket(vid):
    return render_template("ticket.html", venta=db.q("SELECT * FROM ventas WHERE id=?", (vid,), fetchone=True), detalle=db.get_venta_detalle(vid), cfg=db.get_config())


@main_bp.route("/historial")
@login_required
def historial():
    ventas = db.get_ventas(request.args.get("q", ""), request.args.get("desde", ""), request.args.get("hasta", ""))
    return render_template("historial.html", ventas=ventas, search=request.args.get("q", ""), fecha_desde=request.args.get("desde", ""), fecha_hasta=request.args.get("hasta", ""), total_filtro=sum(float(v["total"] or 0) for v in ventas))


@main_bp.route("/historial/<int:vid>")
@login_required
def historial_detalle(vid):
    return redirect(url_for("ticket", vid=vid))


@main_bp.route("/compras")
@login_required
def compras():
    return render_template("compras.html", compras=db.get_compras(request.args.get("q", ""), request.args.get("fecha_desde", ""), request.args.get("fecha_hasta", "")), buscar=request.args.get("q", ""), fecha_desde=request.args.get("fecha_desde", ""), fecha_hasta=request.args.get("fecha_hasta", ""))


@main_bp.route("/compras/nueva", methods=["GET", "POST"])
@login_required
def compra_nueva():
    if request.method == "POST":
        data = request.form.to_dict()
        producto = db.get_producto(int(data.get("producto_id", 0) or 0))
        proveedor = db.get_proveedor(int(data.get("proveedor_id", 0) or 0))
        if producto:
            data["codigo_interno"], data["descripcion"] = producto["codigo_interno"], producto["descripcion"]
        if proveedor:
            data["proveedor_nombre"] = proveedor["nombre"]
        data["total"] = float(data.get("cantidad", 0) or 0) * float(data.get("costo_unitario", 0) or 0)
        db.add_compra(data)
        flash("âœ… Compra registrada.", "success")
        return redirect(url_for("compras"))
    return render_template("compra_form.html", compra=None, proveedores=db.get_proveedores(), productos=db.get_productos(), accion="Nueva")


@main_bp.route("/compras/<int:cid>")
@login_required
def compra_detalle(cid):
    return render_template("compra_detalle.html", compra=db.get_compra(cid))


@main_bp.route("/compras/<int:cid>/eliminar", methods=["POST"])
@login_required
def compra_eliminar(cid):
    db.delete_compra(cid)
    flash("âœ… Compra eliminada.", "success")
    return redirect(url_for("compras"))


@main_bp.route("/caja")
@login_required
def caja():
    caja_actual = _caja_abierta()
    return render_template("caja.html", caja=caja_actual, movimientos=_caja_movimientos(caja_actual["id"]) if caja_actual else [], resumen=_caja_resumen(caja_actual), historial=db.q("SELECT * FROM caja WHERE estado=0 ORDER BY fecha_cierre DESC LIMIT 20"))


@main_bp.route("/caja/abrir", methods=["POST"])
@login_required
def caja_abrir():
    if not _caja_abierta():
        db.q("INSERT INTO caja (usuario_id,fecha_apertura,saldo_inicial,estado) VALUES (?,?,?,1)", (session["user"]["id"], datetime.now().isoformat(sep=" "), float(request.form.get("saldo_inicial", 0) or 0)), commit=True)
    return redirect(url_for("caja"))


@main_bp.route("/caja/movimiento", methods=["POST"])
@login_required
def caja_movimiento():
    caja_actual = _caja_abierta()
    if caja_actual:
        db.q("INSERT INTO caja_movimientos (caja_id,tipo,monto,motivo) VALUES (?,?,?,?)", (caja_actual["id"], request.form.get("tipo", "INGRESO"), float(request.form.get("monto", 0) or 0), request.form.get("motivo", "")), commit=True)
    return redirect(url_for("caja"))


@main_bp.route("/caja/cerrar", methods=["POST"])
@login_required
def caja_cerrar():
    caja_actual = _caja_abierta()
    if caja_actual:
        db.q("UPDATE caja SET fecha_cierre=?,saldo_final_real=?,estado=0 WHERE id=?", (datetime.now().isoformat(sep=" "), float(request.form.get("saldo_real", 0) or 0), caja_actual["id"]), commit=True)
    return redirect(url_for("caja"))


@main_bp.route("/gastos")
@login_required
def gastos():
    rows = db.get_gastos(request.args.get("q", ""), request.args.get("fecha_desde", ""), request.args.get("fecha_hasta", ""))
    return render_template("gastos.html", gastos=rows, buscar=request.args.get("q", ""), fecha_desde=request.args.get("fecha_desde", ""), fecha_hasta=request.args.get("fecha_hasta", ""), total_gasto=sum(float(r["monto"] or 0) for r in rows), total_prescind=sum(float(r["monto"] or 0) for r in rows if "prescindible" in str(r["necesario"]).lower()), cats=db.get_gasto_categorias())


@main_bp.route("/gastos/nuevo", methods=["GET", "POST"])
@login_required
def gasto_nuevo():
    if request.method == "POST":
        db.add_gasto(request.form.to_dict())
        return redirect(url_for("gastos"))
    return render_template("gasto_form.html", categorias_gasto=db.get_gasto_categorias())


@main_bp.route("/gastos/<int:gid>/eliminar", methods=["POST"])
@login_required
def gasto_eliminar(gid):
    db.delete_gasto(gid)
    return redirect(url_for("gastos"))


@main_bp.route("/clientes")
@login_required
def clientes():
    return render_template("clientes.html", clientes=db.get_clientes(request.args.get("q", ""), _as_bool(request.args.get("solo_deuda"))), buscar=request.args.get("q", ""), solo_deuda=_as_bool(request.args.get("solo_deuda")))


@main_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
def cliente_nuevo():
    if request.method == "POST":
        if not _limit_allows("clientes"):
            return redirect(url_for("clientes"))
        db.add_cliente(request.form.to_dict())
        return redirect(url_for("clientes"))
    return render_template("cliente_form.html", cliente=None, accion="Crear")


@main_bp.route("/clientes/<int:cid>/editar", methods=["GET", "POST"])
@login_required
def cliente_editar(cid):
    cliente = db.get_cliente(cid)
    if request.method == "POST":
        data = request.form.to_dict()
        data["activo"] = 1 if _as_bool(data.get("activo")) else 0
        db.update_cliente(cid, data)
        return redirect(url_for("cliente_detalle", cid=cid))
    return render_template("cliente_form.html", cliente=cliente, accion="Editar")


@main_bp.route("/clientes/<int:cid>")
@login_required
def cliente_detalle(cid):
    return render_template("cliente_detalle.html", cliente=db.get_cliente(cid), saldo=db.get_saldo_cliente(cid), movimientos=db.get_movimientos_cliente(cid), historial_ventas=db.get_historial_ventas_cliente(cid), estadisticas=db.get_estadisticas_cliente(cid))


@main_bp.route("/clientes/<int:cid>/movimiento", methods=["POST"])
@login_required
def cliente_agregar_movimiento(cid):
    db.agregar_movimiento_cliente(cid, request.form.get("tipo", "Ajuste"), request.form.get("numero_comprobante", ""), float(request.form.get("debe", 0) or 0), float(request.form.get("haber", 0) or 0), request.form.get("vencimiento", ""), request.form.get("observaciones", ""))
    return redirect(url_for("cliente_detalle", cid=cid))


@main_bp.route("/clientes/<int:cid>/eliminar", methods=["POST"])
@login_required
def cliente_eliminar(cid):
    db.delete_cliente(cid)
    return redirect(url_for("clientes"))


@main_bp.route("/proveedores")
@login_required
def proveedores():
    buscar = request.args.get("q", "")
    return render_template("proveedores.html", proveedores=db.get_proveedores(activo_only=False, search=buscar), buscar=buscar)


@main_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@login_required
def proveedor_nuevo():
    if request.method == "POST":
        if not _limit_allows("proveedores"):
            return redirect(url_for("proveedores"))
        db.add_proveedor(request.form.to_dict())
        return redirect(url_for("proveedores"))
    return render_template("proveedor_form.html", proveedor=None, accion="Crear")


@main_bp.route("/proveedores/<int:pid>/editar", methods=["GET", "POST"])
@login_required
def proveedor_editar(pid):
    proveedor = db.get_proveedor(pid)
    if request.method == "POST":
        db.update_proveedor(pid, request.form.to_dict())
        return redirect(url_for("proveedor_detalle", pid=pid))
    return render_template("proveedor_form.html", proveedor=proveedor, accion="Editar")


@main_bp.route("/proveedores/<int:pid>")
@login_required
def proveedor_detalle(pid):
    return render_template("proveedor_detalle.html", proveedor=db.get_proveedor(pid), saldo=db.get_saldo_proveedor(pid), movimientos=db.get_movimientos_proveedor(pid), historial_compras=db.get_historial_compras_proveedor(pid), estadisticas=db.get_estadisticas_proveedor(pid))


@main_bp.route("/proveedores/<int:pid>/movimiento", methods=["POST"])
@login_required
def proveedor_agregar_movimiento(pid):
    db.agregar_movimiento_proveedor(pid, request.form.get("tipo", "Ajuste"), request.form.get("numero_comprobante", ""), float(request.form.get("debe", 0) or 0), float(request.form.get("haber", 0) or 0), request.form.get("vencimiento", ""), request.form.get("observaciones", ""))
    return redirect(url_for("proveedor_detalle", pid=pid))


@main_bp.route("/proveedores/<int:pid>/eliminar", methods=["POST"])
@login_required
def proveedor_eliminar(pid):
    db.delete_proveedor(pid)
    return redirect(url_for("proveedores"))


@main_bp.route("/reportes")
@login_required
def reportes():
    rent = db.get_stats_rentabilidad()
    pagos = [{"medio_pago": r["medio_pago"], "monto": r["total"]} for r in db.get_ventas_por_medio_pago(date.today().year, date.today().month)]
    ventas_7 = db.q("SELECT fecha as dia, ROUND(SUM(total),2) as monto FROM ventas WHERE fecha >= date('now','-6 days') GROUP BY fecha ORDER BY fecha")
    gastos_nec = sum(float(r["monto"] or 0) for r in db.get_gastos() if "prescindible" not in str(r["necesario"]).lower())
    gastos_pre = sum(float(r["monto"] or 0) for r in db.get_gastos() if "prescindible" in str(r["necesario"]).lower())
    total_g = gastos_nec + gastos_pre
    pct = round((gastos_pre / total_g) * 100, 1) if total_g else 0
    return render_template("reportes.html", rentabilidad=rent, top_productos=db.get_top_productos_vendidos(5), pagos=pagos, ventas_7_dias=ventas_7, gastos_necesarios=gastos_nec, gastos_prescindibles=gastos_pre, pct_prescindibles=pct, recomendacion_gastos="Revisar gastos prescindibles." if pct > 20 else "Gastos prescindibles controlados.")


@main_bp.route("/estadisticas")
@login_required
def estadisticas():
    year = int(request.args.get("year", date.today().year))
    ventas_mes = db.get_ventas_por_mes(year)
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    semanas = db.get_ventas_por_semana(8)
    medios = db.get_ventas_por_medio_pago(year, date.today().month)
    cats = db.get_ventas_por_categoria()
    return render_template("estadisticas.html", year=year, meses_labels=json.dumps(meses), ventas_vals=json.dumps([ventas_mes.get(m, {}).get("total", 0) for m in range(1, 13)]), tickets_vals=json.dumps([ventas_mes.get(m, {}).get("tickets", 0) for m in range(1, 13)]), semanas=semanas, semanas_labels=json.dumps([s["label"] for s in semanas]), semanas_vals=json.dumps([s["total"] for s in semanas]), medios=medios, medios_labels=json.dumps([m["medio_pago"] for m in medios]), medios_vals=json.dumps([m["total"] for m in medios]), temporadas=db.get_ventas_por_temporada(), cats=cats, cats_labels=json.dumps([c["categoria"] for c in cats[:8]]), cats_vals=json.dumps([c["total"] for c in cats[:8]]))


@main_bp.route("/analisis")
@login_required
def analisis():
    desde = request.args.get("desde", (date.today() - timedelta(days=30)).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    top = db.get_top_productos_analisis(15, desde, hasta)
    return render_template("analisis.html", top=top, bottom=db.get_bottom_productos(10), temporadas=db.get_ventas_por_temporada(), rent=db.get_stats_rentabilidad(), gastos_cat=db.q("SELECT categoria, ROUND(SUM(monto),2) as total, necesario FROM gastos GROUP BY categoria ORDER BY total DESC"), fecha_desde=desde, fecha_hasta=hasta, top_labels=json.dumps([t["descripcion"][:20] for t in top]), top_vals=json.dumps([t["total_pesos"] for t in top]))


@main_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    usuario = db.q("SELECT * FROM usuarios WHERE id=?", (session["user"]["id"],), fetchone=True)
    if request.method == "POST":
        data = request.form.to_dict()
        if data.get("password"):
            ok, msg = _validate_password(data["password"])
            if not ok:
                flash(f"âŒ {msg}", "danger")
                return render_template("perfil.html", usuario=usuario)
        if bool(data.get("security_question", "").strip()) != bool(data.get("security_answer", "").strip()):
            flash("âš ï¸ Para cambiar la recuperaciÃ³n, ingresÃ¡ pregunta y respuesta secreta.", "warning")
            return render_template("perfil.html", usuario=usuario)
        db.update_perfil(usuario["id"], data)
        flash("âœ… Perfil actualizado.", "success")
        return redirect(url_for("perfil"))
    return render_template("perfil.html", usuario=usuario)


@main_bp.route("/config", methods=["GET", "POST"])
@admin_required
def config():
    if request.method == "POST":
        data = request.form.to_dict()
        data["ticket_mostrar_iva"] = "1" if _as_bool(data.get("ticket_mostrar_iva")) else "0"
        db.set_config(data)
        return redirect(url_for("config"))
    return render_template("config.html", cfg=db.get_config(), categorias=db.get_categorias(), categorias_gastos=db.get_gasto_categorias())


@main_bp.route("/config/categoria", methods=["POST"])
@admin_required
def config_categoria():
    if request.form.get("nombre", "").strip():
        db.add_categoria(request.form.get("nombre").strip())
    return redirect(url_for("config"))


@main_bp.route("/config/categoria/eliminar", methods=["POST"])
@admin_required
def config_categoria_eliminar():
    db.delete_categoria(request.form.get("nombre", ""))
    return redirect(url_for("config"))


@main_bp.route("/config/gasto-categoria", methods=["POST"])
@admin_required
def config_gasto_categoria():
    db.add_gasto_categoria(request.form.get("nombre", ""), request.form.get("tipo", "Necesario"))
    return redirect(url_for("config"))


@main_bp.route("/config/gasto-categoria/eliminar", methods=["POST"])
@admin_required
def config_gasto_categoria_eliminar():
    db.delete_gasto_categoria(request.form.get("nombre", ""))
    return redirect(url_for("config"))


@main_bp.route("/config/gasto-categoria/editar", methods=["POST"])
@admin_required
def config_gasto_categoria_editar():
    db.update_gasto_categoria(request.form.get("nombre_actual", ""), request.form.get("nuevo_nombre", ""), request.form.get("tipo", "Necesario"))
    return redirect(url_for("config"))


@main_bp.route("/licencia")
@admin_required
def licencia():
    machine_id, machine_details = generate_activation_id(session.get("user", {}).get("username", ""))
    local_lic = cargar_licencia() or {}
    return render_template(
        "licencia.html",
        supabase_ok=supabase_configured(),
        machine_id=machine_id,
        device_hwid=get_current_hwid(),
        machine_details=machine_details,
        producto=get_license_product(),
        license_key_local=local_lic.get("license_key", ""),
    )


@main_bp.route("/licencia/activar", methods=["POST"])
@admin_required
def licencia_activar():
    license_key = request.form.get("license_key", "")
    ok, msg = validate_license_key(request.form.get("license_key", ""), debug=True)
    if ok:
        guardar_licencia(license_key, db.get_license_info())
        flash(f"âœ… {msg} La licencia quedÃ³ vinculada a este equipo.", "success")
    else:
        flash(f"âŒ {msg}", "danger")
    return redirect(url_for("licencia"))


@main_bp.route("/licencia/solicitar", methods=["POST"])
@admin_required
def licencia_solicitar():
    machine_id, machine_details = generate_activation_id(session.get("user", {}).get("username", ""))
    activation_id = request.form.get("activation_id") or get_current_hwid() or machine_id
    ok, msg, _ = create_license_request(
        nombre=request.form.get("nombre", ""),
        email=request.form.get("email", ""),
        whatsapp=request.form.get("whatsapp", ""),
        activation_id=activation_id,
        producto=get_license_product(),
        plan=request.form.get("plan", "BASICA"),
        machine_details=machine_details,
    )
    flash(f"Solicitud enviada: {msg}" if ok else f"No se pudo enviar la solicitud: {msg}", "success" if ok else "danger")
    return redirect(url_for("licencia"))


@main_bp.route("/usuarios")
@admin_required
def usuarios():
    return render_template("usuarios.html", usuarios=db.get_usuarios())


@main_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@admin_required
def usuario_nuevo():
    if request.method == "POST":
        ok, msg = _validate_password(request.form.get("password", ""))
        if not ok:
            flash(f"âŒ {msg}", "danger")
        else:
            db.add_usuario(request.form.get("username", ""), request.form.get("password", ""), request.form.get("rol", "Vendedor"), request.form.get("nombre_completo", ""))
            return redirect(url_for("usuarios"))
    return render_template("usuario_form.html", usuario=None, roles=db.get_roles(), accion="Nuevo")


@main_bp.route("/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@admin_required
def usuario_editar(uid):
    usuario = db.q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)
    if not usuario:
        flash("âŒ Usuario inexistente.", "danger")
        return redirect(url_for("usuarios"))
    if request.method == "POST":
        activo = 1 if _as_bool(request.form.get("activo")) else 0
        nuevo_rol = request.form.get("rol", usuario["rol"])
        if not activo and uid == session["user"]["id"]:
            flash("âš ï¸ No podÃ©s desactivar tu propio usuario.", "warning")
            return redirect(url_for("usuarios"))
        if not activo and usuario["rol"] in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
            flash("âš ï¸ No podÃ©s desactivar el Ãºltimo administrador activo.", "warning")
            return redirect(url_for("usuarios"))
        if usuario["rol"] in {"Administrador", "admin"} and nuevo_rol not in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
            flash("âš ï¸ No podÃ©s quitar el rol al Ãºltimo administrador activo.", "warning")
            return redirect(url_for("usuarios"))
        db.update_usuario(uid, {"rol": nuevo_rol, "nombre_completo": request.form.get("nombre_completo", usuario["nombre_completo"]), "activo": activo})
        return redirect(url_for("usuarios"))
    return render_template("usuario_form.html", usuario=usuario, roles=db.get_roles(), accion="Editar")


@main_bp.route("/usuarios/<int:uid>/toggle-activo", methods=["POST"])
@admin_required
def usuario_toggle_activo(uid):
    user = db.q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)
    if not user:
        flash("âŒ Usuario inexistente.", "danger")
        return redirect(url_for("usuarios"))
    if uid == session["user"]["id"]:
        flash("âš ï¸ No podÃ©s cambiar el estado de tu propio usuario.", "warning")
        return redirect(url_for("usuarios"))

    nuevo_estado = 0 if int(user["activo"] or 0) else 1
    if nuevo_estado == 0 and user["rol"] in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
        flash("âš ï¸ No podÃ©s desactivar el Ãºltimo administrador activo.", "warning")
        return redirect(url_for("usuarios"))

    db.set_usuario_activo(uid, nuevo_estado)
    flash("âœ… Usuario activado." if nuevo_estado else "âœ… Usuario desactivado.", "success")
    return redirect(url_for("usuarios"))


@main_bp.route("/usuarios/<int:uid>/eliminar", methods=["POST"])
@admin_required
def usuario_eliminar(uid):
    user = db.q("SELECT * FROM usuarios WHERE id=?", (uid,), fetchone=True)
    if not user:
        flash("âŒ Usuario inexistente.", "danger")
        return redirect(url_for("usuarios"))
    if uid == session["user"]["id"]:
        flash("âš ï¸ No podÃ©s eliminar tu propio usuario.", "warning")
        return redirect(url_for("usuarios"))
    if user["rol"] in {"Administrador", "admin"} and db.count_admins_activos(exclude_uid=uid) == 0:
        flash("âš ï¸ No podÃ©s eliminar el Ãºltimo administrador activo.", "warning")
        return redirect(url_for("usuarios"))
    db.delete_usuario(uid)
    flash("âœ… Usuario eliminado definitivamente.", "success")
    return redirect(url_for("usuarios"))


@main_bp.route("/respaldo")
@admin_required
def respaldo():
    cfg = db.get_config()
    update_info = get_cached_update_info(current_app, current_app.config.get("APP_VERSION", "0.0.0"))
    return render_template(
        "respaldo.html",
        archivos=_backup_list(),
        actualizaciones=_update_list(),
        update_info=update_info,
        ultimo=cfg.get("backup_ultimo", "Nunca"),
        intervalo=cfg.get("backup_intervalo_h", "24"),
        keep=cfg.get("backup_keep", "10"),
    )


@main_bp.route("/respaldo/ahora", methods=["POST"])
@admin_required
def respaldo_ahora():
    _make_backup()
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/config", methods=["POST"])
@admin_required
def respaldo_config():
    db.set_config({"backup_intervalo_h": request.form.get("backup_intervalo_h", "24"), "backup_keep": request.form.get("backup_keep", "10")})
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/descargar/<nombre>")
@admin_required
def respaldo_descargar(nombre):
    return send_file(_backup_file(nombre), as_attachment=True)


@main_bp.route("/respaldo/restaurar/<nombre>", methods=["POST"])
@admin_required
def respaldo_restaurar(nombre):
    source = _backup_file(nombre)
    if not _is_sqlite_database(source):
        abort(400)
    _make_backup()
    shutil.copy2(source, db.DB_PATH)
    try:
        if os.name != "nt":
            Path(db.DB_PATH).chmod(0o600)
    except Exception:
        pass
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/descargar", methods=["POST"])
@admin_required
def actualizacion_descargar():
    update_info = get_cached_update_info(current_app, current_app.config.get("APP_VERSION", "0.0.0"))
    if not update_info.get("available"):
        flash("No hay una actualizacion nueva disponible.", "info")
        return redirect(url_for("respaldo"))
    if not update_info.get("asset_url"):
        flash("La release existe, pero no tiene instalador compatible para este sistema. Abrila en GitHub.", "warning")
        return redirect(url_for("respaldo"))

    backup_path = _make_backup()
    try:
        target = download_release_asset(update_info["asset_url"], UPDATE_DIR)
    except Exception as exc:
        flash(f"No se pudo descargar la actualizacion: {exc}", "danger")
        return redirect(url_for("respaldo"))

    flash(
        f"Actualizacion descargada: {target.name}. Respaldo creado antes de actualizar: {backup_path.name}.",
        "success",
    )
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/abrir-carpeta", methods=["POST"])
@admin_required
def actualizacion_abrir_carpeta():
    if sys.platform.startswith("linux"):
        try:
            subprocess.Popen(["xdg-open", str(UPDATE_DIR)])
            flash("Carpeta de actualizaciones abierta.", "success")
        except Exception as exc:
            flash(f"No se pudo abrir la carpeta: {exc}", "warning")
    elif sys.platform.startswith("win"):
        try:
            os.startfile(str(UPDATE_DIR))  # type: ignore[attr-defined]
            flash("Carpeta de actualizaciones abierta.", "success")
        except Exception as exc:
            flash(f"No se pudo abrir la carpeta: {exc}", "warning")
    else:
        flash(f"Carpeta de actualizaciones: {UPDATE_DIR}", "info")
    return redirect(url_for("respaldo"))


@main_bp.route("/respaldo/actualizacion/instalar/<nombre>", methods=["POST"])
@admin_required
def actualizacion_instalar(nombre):
    installer = _update_file(nombre)
    backup_path = _make_backup()
    is_windows_installer = installer.suffix.lower() == ".exe"
    command = str(installer) if is_windows_installer else f"sudo apt install /tmp/nexar-tienda-updates/{installer.name}"

    if sys.platform.startswith("win") and is_windows_installer:
        try:
            os.startfile(str(installer))  # type: ignore[attr-defined]
            flash(
                f"Instalador de Windows iniciado. Respaldo previo: {backup_path.name}. "
                "Cuando termine, cerra y volve a abrir Nexar Tienda.",
                "success",
            )
        except Exception as exc:
            flash(f"No se pudo iniciar el instalador: {exc}. Ejecuta manualmente: {command}", "warning")
        return redirect(url_for("respaldo"))

    if not sys.platform.startswith("linux"):
        flash(f"Respaldo creado ({backup_path.name}). Instala manualmente: {command}", "info")
        return redirect(url_for("respaldo"))

    try:
        apt_installer = _apt_readable_copy(installer)
        subprocess.Popen(["pkexec", "apt", "install", "-y", str(apt_installer)])
        flash(
            f"Instalador iniciado con permisos de administrador. Respaldo previo: {backup_path.name}. "
            "Cuando termine, cerra y volve a abrir Nexar Tienda.",
            "success",
        )
    except FileNotFoundError:
        flash(f"Respaldo creado ({backup_path.name}). pkexec no esta disponible; ejecuta: {command}", "warning")
    except Exception as exc:
        flash(f"No se pudo iniciar el instalador: {exc}. Ejecuta: {command}", "warning")
    return redirect(url_for("respaldo"))


@main_bp.route("/productos/exportar/excel")
@admin_required
def exportar_excel():
    rows = db.get_catalogo_export()
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Codigo", "Descripcion", "Categoria", "Precio", "Stock", "Activo"])
        for row in rows:
            ws.append([row["codigo"], row["descripcion"], row["categoria"], row["precio_venta"], row["stock_actual"], row["activo"]])
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name="catalogo_nexar_tienda.xlsx")
    except Exception:
        csv = "codigo,descripcion,categoria,precio,stock,activo\n" + "\n".join(f'{r["codigo"]},"{r["descripcion"]}","{r["categoria"]}",{r["precio_venta"]},{r["stock_actual"]},{r["activo"]}' for r in rows)
        return Response(csv, headers={"Content-Disposition": "attachment; filename=catalogo_nexar_tienda.csv"}, mimetype="text/csv")


@main_bp.route("/productos/exportar/pdf")
@admin_required
def exportar_pdf():
    rows = db.get_catalogo_export()
    text = "\n".join(f'{r["codigo"]} - {r["descripcion"]} - $ {float(r["precio_venta"] or 0):.2f}' for r in rows)
    return Response(text, headers={"Content-Disposition": "attachment; filename=lista_precios.txt"}, mimetype="text/plain")


@main_bp.route("/ayuda")
@login_required
def ayuda():
    return render_template("ayuda.html")


@main_bp.route("/changelog")
@login_required
def changelog():
    content = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else "# Sin changelog"
    try:
        import markdown
        html = markdown.markdown(content, extensions=["extra", "sane_lists"])
    except Exception:
        html = "<pre>" + content + "</pre>"
    return render_template("changelog.html", contenido_html=html)


@main_bp.route("/acerca")
@login_required
def acerca():
    return render_template("acerca.html")


@main_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@main_bp.route("/apagar-rapido", methods=["POST"])
def apagar_rapido():
    session.clear()
    return render_template("apagado.html")


@main_bp.route("/apagar", methods=["POST"])
@admin_required
def apagar_sistema():
    session.clear()
    return render_template("apagado.html")


@main_bp.route("/shutdown", methods=["POST"])
def shutdown():
    if not _is_same_origin_local_request():
        abort(403)
    fn = request.environ.get("werkzeug.server.shutdown")
    if fn:
        fn()
        return ("", 204)
    current_app.logger.info("Shutdown solicitado, pero no disponible en este servidor.")
    return ("", 202)
