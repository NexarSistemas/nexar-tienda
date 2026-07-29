from __future__ import annotations

import math
import sqlite3
from datetime import datetime

import database as db


STOCK_MODE_LEGACY = "legacy"
STOCK_MODE_VARIANTS = "variantes"
SOURCE_LEGACY = "stock"
SOURCE_VARIANTS = "stock_variantes"


def _row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def _normalize_mode(value) -> str:
    mode = str(value or STOCK_MODE_LEGACY).strip().lower()
    if mode not in {STOCK_MODE_LEGACY, STOCK_MODE_VARIANTS}:
        return STOCK_MODE_LEGACY
    return mode


def _validate_finite_number(value, label: str, *, allow_zero: bool = True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} debe ser numerico.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} debe ser un numero finito.")
    if number < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    if not allow_zero and number <= 0:
        raise ValueError(f"{label} debe ser mayor a 0.")
    return number


def _validate_limits(stock_actual, stock_minimo, stock_maximo) -> tuple[float, float, float]:
    actual = _validate_finite_number(stock_actual, "El stock actual")
    minimo = _validate_finite_number(stock_minimo, "El stock minimo")
    maximo = _validate_finite_number(stock_maximo, "El stock maximo")
    if maximo < minimo:
        raise ValueError("El stock maximo debe ser mayor o igual al stock minimo.")
    return actual, minimo, maximo


def _ensure_legacy_stock(cursor, product_id: int):
    stock = cursor.execute("SELECT * FROM stock WHERE producto_id=? LIMIT 1", (int(product_id),)).fetchone()
    if stock:
        return stock
    cursor.execute(
        "INSERT INTO stock (producto_id, stock_actual, stock_minimo, stock_maximo) VALUES (?,0,5,50)",
        (int(product_id),),
    )
    return cursor.execute("SELECT * FROM stock WHERE producto_id=? LIMIT 1", (int(product_id),)).fetchone()


def _ensure_variant_stock(cursor, variant_id: int):
    stock = cursor.execute("SELECT * FROM stock_variantes WHERE variante_id=? LIMIT 1", (int(variant_id),)).fetchone()
    if stock:
        return stock
    cursor.execute(
        """
        INSERT INTO stock_variantes (variante_id, stock_actual, stock_minimo, stock_maximo, updated_at)
        VALUES (?,0,5,50,CURRENT_TIMESTAMP)
        """,
        (int(variant_id),),
    )
    return cursor.execute("SELECT * FROM stock_variantes WHERE variante_id=? LIMIT 1", (int(variant_id),)).fetchone()


def _product_for_update(cursor, product_id: int):
    product = cursor.execute("SELECT * FROM productos WHERE id=? LIMIT 1", (int(product_id or 0),)).fetchone()
    if not product:
        raise ValueError("El producto indicado no existe.")
    return product


def _variant_for_update(cursor, product_id: int, variant_id: int, *, allow_inactive: bool = False):
    variant = cursor.execute(
        """
        SELECT *
        FROM producto_variantes
        WHERE id=? AND producto_id=?
        LIMIT 1
        """,
        (int(variant_id or 0), int(product_id or 0)),
    ).fetchone()
    if not variant:
        raise ValueError("La variante indicada no pertenece al producto.")
    if not allow_inactive and int(variant["activo"] or 0) != 1:
        raise ValueError("La variante indicada no esta activa.")
    return variant


def _resolve_inventory_item_in_cursor(cursor, product_id: int, variant_id: int | None = None, *, allow_inactive_variant: bool = False) -> dict:
    product = _product_for_update(cursor, product_id)
    mode = _normalize_mode(product["stock_modo"] if "stock_modo" in product.keys() else None)

    if mode == STOCK_MODE_LEGACY:
        if variant_id is not None:
            raise ValueError("El producto opera con stock legacy; no admite movimientos por variante.")
        stock = _ensure_legacy_stock(cursor, int(product["id"]))
        return {
            "producto": product,
            "variante": None,
            "modo": STOCK_MODE_LEGACY,
            "fuente": SOURCE_LEGACY,
            "stock": stock,
            "stock_actual": float(stock["stock_actual"] or 0),
            "stock_minimo": float(stock["stock_minimo"] or 0),
            "stock_maximo": float(stock["stock_maximo"] or 0),
        }

    if variant_id is None:
        raise ValueError("El producto opera por variantes; debe indicar una variante.")
    variant = _variant_for_update(cursor, int(product["id"]), int(variant_id), allow_inactive=allow_inactive_variant)
    stock = _ensure_variant_stock(cursor, int(variant["id"]))
    return {
        "producto": product,
        "variante": variant,
        "modo": STOCK_MODE_VARIANTS,
        "fuente": SOURCE_VARIANTS,
        "stock": stock,
        "stock_actual": float(stock["stock_actual"] or 0),
        "stock_minimo": float(stock["stock_minimo"] or 0),
        "stock_maximo": float(stock["stock_maximo"] or 0),
    }


def resolve_inventory_item(product_id: int, variant_id: int | None = None) -> dict:
    conn = db.get_conn()
    try:
        return {key: _row_to_dict(value) if key in {"producto", "variante", "stock"} else value
                for key, value in _resolve_inventory_item_in_cursor(conn.cursor(), product_id, variant_id).items()}
    finally:
        conn.close()


def _movement_insert(cursor, item: dict, tipo: str, cantidad: float, anterior: float, nuevo: float, motivo: str) -> None:
    variant = item["variante"]
    cursor.execute(
        """
        INSERT INTO stock_movimientos
        (producto_id, variante_id, stock_fuente, tipo, cantidad, stock_anterior, stock_nuevo, motivo)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            int(item["producto"]["id"]),
            int(variant["id"]) if variant is not None else None,
            item["fuente"],
            str(tipo or "AJUSTE").strip().upper(),
            float(cantidad),
            float(anterior),
            float(nuevo),
            str(motivo or "").strip(),
        ),
    )


def _audit_insert(cursor, accion: str, entidad: str, entidad_id: int, detalle: str, motivo: str, usuario: str, rol: str) -> None:
    cursor.execute(
        """
        INSERT INTO auditoria (usuario, rol, accion, entidad, entidad_id, detalle, motivo)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            str(usuario or "").strip(),
            str(rol or "").strip(),
            str(accion or "").strip(),
            str(entidad or "").strip(),
            int(entidad_id or 0),
            str(detalle or "").strip(),
            str(motivo or "").strip(),
        ),
    )


def apply_inventory_delta(
    product_id: int,
    cantidad,
    *,
    variant_id: int | None = None,
    tipo: str,
    motivo: str = "",
    usuario: str = "",
    rol: str = "",
) -> dict:
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        result = apply_inventory_delta_in_cursor(
            cursor,
            product_id,
            cantidad,
            variant_id=variant_id,
            tipo=tipo,
            motivo=motivo,
            usuario=usuario,
            rol=rol,
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_inventory_delta_in_cursor(
    cursor,
    product_id: int,
    cantidad,
    *,
    variant_id: int | None = None,
    tipo: str,
    motivo: str = "",
    usuario: str = "",
    rol: str = "",
    allow_inactive_variant: bool = False,
) -> dict:
    try:
        delta = float(cantidad)
    except (TypeError, ValueError) as exc:
        raise ValueError("La cantidad debe ser numerica.") from exc
    if not math.isfinite(delta):
        raise ValueError("La cantidad debe ser un numero finito.")
    if delta == 0:
        raise ValueError("La cantidad debe ser distinta de 0.")

    tipo_normalizado = str(tipo or "").strip().upper()
    if tipo_normalizado in {"BAJA", "VENTA", "ANULACION_COMPRA"}:
        delta = -abs(delta)

    item = _resolve_inventory_item_in_cursor(cursor, product_id, variant_id, allow_inactive_variant=allow_inactive_variant)
    anterior = float(item["stock_actual"] or 0)
    nuevo = anterior + delta
    if nuevo < 0:
        raise ValueError("La operacion dejaria stock negativo.")
    if item["fuente"] == SOURCE_LEGACY:
        cursor.execute("UPDATE stock SET stock_actual=? WHERE producto_id=?", (nuevo, int(product_id)))
    else:
        cursor.execute(
            "UPDATE stock_variantes SET stock_actual=?, updated_at=CURRENT_TIMESTAMP WHERE variante_id=?",
            (nuevo, int(variant_id)),
        )
    _movement_insert(cursor, item, tipo_normalizado or "AJUSTE", delta, anterior, nuevo, motivo)
    entity_id = int(variant_id) if item["variante"] is not None else int(product_id)
    _audit_insert(
        cursor,
        f"{tipo_normalizado or 'AJUSTE'}_STOCK",
        "stock_variante" if item["variante"] is not None else "stock",
        entity_id,
        _movement_detail(item, anterior, nuevo),
        motivo,
        usuario,
        rol,
    )
    return {"stock_anterior": anterior, "stock_nuevo": nuevo, "fuente": item["fuente"]}


def adjust_inventory_item(
    product_id: int,
    *,
    stock_actual,
    stock_minimo,
    stock_maximo,
    variant_id: int | None = None,
    proveedor_habitual: str | None = None,
    motivo: str = "",
    usuario: str = "",
    rol: str = "",
) -> dict:
    nuevo, minimo, maximo = _validate_limits(stock_actual, stock_minimo, stock_maximo)
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        result = adjust_inventory_item_in_cursor(
            cursor,
            product_id,
            stock_actual=nuevo,
            stock_minimo=minimo,
            stock_maximo=maximo,
            variant_id=variant_id,
            proveedor_habitual=proveedor_habitual,
            motivo=motivo,
            usuario=usuario,
            rol=rol,
            values_already_validated=True,
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def adjust_inventory_item_in_cursor(
    cursor,
    product_id: int,
    *,
    stock_actual,
    stock_minimo,
    stock_maximo,
    variant_id: int | None = None,
    proveedor_habitual: str | None = None,
    motivo: str = "",
    usuario: str = "",
    rol: str = "",
    values_already_validated: bool = False,
) -> dict:
    if values_already_validated:
        nuevo, minimo, maximo = float(stock_actual), float(stock_minimo), float(stock_maximo)
    else:
        nuevo, minimo, maximo = _validate_limits(stock_actual, stock_minimo, stock_maximo)
    item = _resolve_inventory_item_in_cursor(cursor, product_id, variant_id)
    anterior = float(item["stock_actual"] or 0)
    if item["fuente"] == SOURCE_LEGACY:
        cursor.execute(
            """
            UPDATE stock
            SET stock_actual=?, stock_minimo=?, stock_maximo=?, proveedor_habitual=?
            WHERE producto_id=?
            """,
            (nuevo, minimo, maximo, str(proveedor_habitual or "").strip(), int(product_id)),
        )
    else:
        cursor.execute(
            """
            UPDATE stock_variantes
            SET stock_actual=?, stock_minimo=?, stock_maximo=?, updated_at=CURRENT_TIMESTAMP
            WHERE variante_id=?
            """,
            (nuevo, minimo, maximo, int(variant_id)),
        )
    _movement_insert(cursor, item, "AJUSTE", nuevo - anterior, anterior, nuevo, motivo or "Ajuste manual")
    entity_id = int(variant_id) if item["variante"] is not None else int(product_id)
    _audit_insert(
        cursor,
        "AJUSTE_STOCK",
        "stock_variante" if item["variante"] is not None else "stock",
        entity_id,
        _movement_detail(item, anterior, nuevo),
        motivo or "Ajuste manual",
        usuario,
        rol,
    )
    return {"stock_anterior": anterior, "stock_nuevo": nuevo, "fuente": item["fuente"]}


def _movement_detail(item: dict, anterior: float, nuevo: float) -> str:
    product_name = item["producto"]["descripcion"] or "Producto"
    if item["variante"] is None:
        return f"{product_name} - {anterior:.2f} -> {nuevo:.2f}"
    variant_name = item["variante"]["nombre"] or f"Variante #{item['variante']['id']}"
    return f"{product_name} / {variant_name} - {anterior:.2f} -> {nuevo:.2f}"


def activate_variant_stock_mode(
    product_id: int,
    allocations: list[dict],
    *,
    motivo: str = "",
    usuario: str = "",
    rol: str = "",
) -> dict:
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        product = _product_for_update(cursor, product_id)
        if _normalize_mode(product["stock_modo"] if "stock_modo" in product.keys() else None) != STOCK_MODE_LEGACY:
            raise ValueError("El producto ya opera por variantes.")
        legacy_stock = _ensure_legacy_stock(cursor, int(product_id))
        legacy_actual = float(legacy_stock["stock_actual"] or 0)

        normalized = []
        seen = set()
        for raw in allocations or []:
            variant_id = int(raw.get("variant_id") or 0)
            if variant_id <= 0 or variant_id in seen:
                continue
            seen.add(variant_id)
            _variant_for_update(cursor, product_id, variant_id)
            actual, minimo, maximo = _validate_limits(
                raw.get("stock_actual", 0),
                raw.get("stock_minimo", 0),
                raw.get("stock_maximo", 0),
            )
            normalized.append({"variant_id": variant_id, "stock_actual": actual, "stock_minimo": minimo, "stock_maximo": maximo})

        if not normalized:
            raise ValueError("Debe asignar stock al menos a una variante activa.")
        assigned_total = round(sum(item["stock_actual"] for item in normalized), 6)
        if round(legacy_actual, 6) != assigned_total:
            raise ValueError("La suma asignada a variantes debe coincidir con el stock legacy existente.")

        for item in normalized:
            _ensure_variant_stock(cursor, item["variant_id"])
            cursor.execute(
                """
                UPDATE stock_variantes
                SET stock_actual=?, stock_minimo=?, stock_maximo=?, updated_at=CURRENT_TIMESTAMP
                WHERE variante_id=?
                """,
                (item["stock_actual"], item["stock_minimo"], item["stock_maximo"], item["variant_id"]),
            )
            resolved = _resolve_inventory_item_in_cursor_for_variant_mode(cursor, product, item["variant_id"])
            _movement_insert(
                cursor,
                resolved,
                "TRANSICION_VARIANTES",
                item["stock_actual"],
                0,
                item["stock_actual"],
                motivo or "Activacion de stock por variantes",
            )

        cursor.execute("UPDATE productos SET stock_modo=? WHERE id=?", (STOCK_MODE_VARIANTS, int(product_id)))
        _audit_insert(
            cursor,
            "ACTIVACION_STOCK_VARIANTES",
            "producto",
            int(product_id),
            f"{product['descripcion'] or 'Producto'} - stock legacy {legacy_actual:.2f} asignado a {len(normalized)} variantes",
            motivo or "Activacion de stock por variantes",
            usuario,
            rol,
        )
        conn.commit()
        return {"producto_id": int(product_id), "stock_modo": STOCK_MODE_VARIANTS, "total_asignado": assigned_total}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _resolve_inventory_item_in_cursor_for_variant_mode(cursor, product, variant_id: int) -> dict:
    variant = _variant_for_update(cursor, int(product["id"]), int(variant_id))
    stock = _ensure_variant_stock(cursor, int(variant["id"]))
    return {
        "producto": product,
        "variante": variant,
        "modo": STOCK_MODE_VARIANTS,
        "fuente": SOURCE_VARIANTS,
        "stock": stock,
        "stock_actual": float(stock["stock_actual"] or 0),
        "stock_minimo": float(stock["stock_minimo"] or 0),
        "stock_maximo": float(stock["stock_maximo"] or 0),
    }


def list_inventory_items(search: str = "") -> list[dict]:
    rows = db.q(
        """
        SELECT p.id AS producto_id, p.codigo_interno, p.descripcion, p.categoria, p.unidad,
               p.costo, p.precio_venta, COALESCE(p.stock_modo, 'legacy') AS stock_modo,
               s.stock_actual AS legacy_stock_actual, s.stock_minimo AS legacy_stock_minimo,
               s.stock_maximo AS legacy_stock_maximo, s.ultimo_ingreso, s.proveedor_habitual,
               v.id AS variante_id, v.nombre AS variante_nombre, v.sku AS variante_sku, v.costo AS variante_costo,
               sv.stock_actual AS variante_stock_actual, sv.stock_minimo AS variante_stock_minimo,
               sv.stock_maximo AS variante_stock_maximo
        FROM productos p
        LEFT JOIN stock s ON s.producto_id = p.id
        LEFT JOIN producto_variantes v
            ON v.producto_id = p.id AND COALESCE(p.stock_modo, 'legacy') = 'variantes' AND v.activo=1
        LEFT JOIN stock_variantes sv ON sv.variante_id = v.id
        WHERE p.activo=1
        ORDER BY p.descripcion, v.id
        """
    )
    search_norm = str(search or "").strip().lower()
    items: list[dict] = []
    for row in rows:
        mode = _normalize_mode(row["stock_modo"])
        if mode == STOCK_MODE_VARIANTS and row["variante_id"] is None:
            continue
        stock_actual = float((row["variante_stock_actual"] if mode == STOCK_MODE_VARIANTS else row["legacy_stock_actual"]) or 0)
        stock_minimo = float((row["variante_stock_minimo"] if mode == STOCK_MODE_VARIANTS else row["legacy_stock_minimo"]) or 0)
        stock_maximo = float((row["variante_stock_maximo"] if mode == STOCK_MODE_VARIANTS else row["legacy_stock_maximo"]) or 0)
        estado = _stock_status(stock_actual, stock_minimo, stock_maximo)
        costo = float(row["costo"] or 0)
        if mode == STOCK_MODE_VARIANTS and row["variante_costo"] is not None:
            costo = float(row["variante_costo"] or 0)
        item = {
            "id": int(row["producto_id"]),
            "producto_id": int(row["producto_id"]),
            "variante_id": int(row["variante_id"]) if row["variante_id"] is not None else None,
            "codigo_interno": row["codigo_interno"],
            "descripcion": row["descripcion"],
            "variante_nombre": row["variante_nombre"] or "",
            "variante_sku": row["variante_sku"] or "",
            "categoria": row["categoria"],
            "unidad": row["unidad"],
            "costo": costo,
            "precio_venta": float(row["precio_venta"] or 0),
            "stock_modo": mode,
            "stock_actual": stock_actual,
            "stock_minimo": stock_minimo,
            "stock_maximo": stock_maximo,
            "ultimo_ingreso": row["ultimo_ingreso"] or "",
            "proveedor_habitual": row["proveedor_habitual"] or "",
            "estado": estado,
            "valor_stock": stock_actual * costo,
        }
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ("codigo_interno", "descripcion", "categoria", "variante_nombre", "variante_sku")
        ).lower()
        if search_norm and search_norm not in haystack:
            continue
        items.append(item)
    return items


def _stock_status(actual: float, minimo: float, maximo: float) -> str:
    if actual <= 0:
        return "SIN_STOCK"
    if actual <= minimo:
        return "CRITICO"
    if actual <= minimo * 1.5:
        return "BAJO"
    if maximo > 0 and actual >= maximo:
        return "EXCESO"
    return "NORMAL"


def get_alertas_count() -> dict:
    counts = {"sin_stock": 0, "critico": 0, "bajo": 0}
    for item in list_inventory_items():
        if item["estado"] == "SIN_STOCK":
            counts["sin_stock"] += 1
        elif item["estado"] == "CRITICO":
            counts["critico"] += 1
        elif item["estado"] == "BAJO":
            counts["bajo"] += 1
    return counts


def get_inventory_movements(product_id: int, variant_id: int | None = None) -> list[dict]:
    if variant_id is None:
        return db.q(
            """
            SELECT m.*, v.nombre AS variante_nombre, v.sku AS variante_sku
            FROM stock_movimientos m
            LEFT JOIN producto_variantes v ON v.id = m.variante_id
            WHERE m.producto_id=? AND m.variante_id IS NULL
            ORDER BY m.created_at DESC, m.id DESC LIMIT 50
            """,
            (int(product_id),),
        )
    return db.q(
        """
        SELECT m.*, v.nombre AS variante_nombre, v.sku AS variante_sku
        FROM stock_movimientos m
        LEFT JOIN producto_variantes v ON v.id = m.variante_id
        WHERE m.producto_id=? AND m.variante_id=?
        ORDER BY m.created_at DESC, m.id DESC LIMIT 50
        """,
        (int(product_id), int(variant_id)),
    )
