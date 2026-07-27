from __future__ import annotations

import math
import sqlite3
from collections import defaultdict

import database as db


DEFAULT_COMBINATION_KEY = "__default__"


def _normalize_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_text(value) -> str:
    return " ".join(str(value or "").strip().split())


def _validate_stock_value(value, label: str) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        value = 0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} debe ser numerico.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} debe ser un numero finito.")
    if number < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    return number


def _validate_variant_stock(stock_actual, stock_minimo, stock_maximo) -> tuple[float, float, float]:
    return (
        _validate_stock_value(stock_actual, "El stock actual"),
        _validate_stock_value(stock_minimo, "El stock minimo"),
        _validate_stock_value(stock_maximo, "El stock maximo"),
    )


def _validate_optional_money(value, label: str) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} debe ser numerico.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} debe ser un numero finito.")
    if number < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    return number


def _build_combination_key(attribute_pairs: list[dict]) -> str:
    if not attribute_pairs:
        return DEFAULT_COMBINATION_KEY
    parts = [
        f"{int(item['attribute_id'])}:{int(item['value_id'])}"
        for item in sorted(attribute_pairs, key=lambda item: (int(item["attribute_id"]), int(item["value_id"])))
    ]
    return "|".join(parts)


def _build_variant_name(attribute_pairs: list[dict]) -> str:
    if not attribute_pairs:
        return "Variante predeterminada"
    return " / ".join(f"{item['attribute_name']}: {item['value_name']}" for item in attribute_pairs)


def _ensure_attribute_value_in_cursor(cursor, attribute_name: str, value_name: str) -> dict:
    attribute_clean = _clean_text(attribute_name)
    value_clean = _clean_text(value_name)
    if not attribute_clean:
        raise ValueError("El nombre del atributo es obligatorio.")
    if not value_clean:
        raise ValueError("El valor del atributo es obligatorio.")

    attribute_norm = _normalize_text(attribute_clean)
    value_norm = _normalize_text(value_clean)

    attribute = cursor.execute(
        "SELECT id, nombre FROM producto_atributos WHERE nombre_normalizado=? LIMIT 1",
        (attribute_norm,),
    ).fetchone()
    if not attribute:
        cursor.execute(
            "INSERT INTO producto_atributos (nombre, nombre_normalizado, activo) VALUES (?,?,1)",
            (attribute_clean, attribute_norm),
        )
        attribute = {"id": int(cursor.lastrowid), "nombre": attribute_clean}

    value = cursor.execute(
        """
        SELECT id, valor
        FROM producto_atributo_valores
        WHERE atributo_id=? AND valor_normalizado=?
        LIMIT 1
        """,
        (int(attribute["id"]), value_norm),
    ).fetchone()
    if not value:
        cursor.execute(
            """
            INSERT INTO producto_atributo_valores
            (atributo_id, valor, valor_normalizado, activo)
            VALUES (?,?,?,1)
            """,
            (int(attribute["id"]), value_clean, value_norm),
        )
        value = {"id": int(cursor.lastrowid), "valor": value_clean}

    return {
        "attribute_id": int(attribute["id"]),
        "attribute_name": attribute["nombre"],
        "value_id": int(value["id"]),
        "value_name": value["valor"],
    }


def _resolve_attribute_pairs(cursor, attributes: list[dict] | None) -> list[dict]:
    attribute_pairs: list[dict] = []
    seen_attributes: set[str] = set()
    for raw_item in attributes or []:
        attribute_name = _clean_text(raw_item.get("attribute_name"))
        value_name = _clean_text(raw_item.get("value_name"))
        if not attribute_name and not value_name:
            continue
        if not attribute_name or not value_name:
            raise ValueError("Cada variante debe completar atributo y valor.")
        attribute_norm = _normalize_text(attribute_name)
        if attribute_norm in seen_attributes:
            raise ValueError("No se puede repetir el mismo atributo en una variante.")
        seen_attributes.add(attribute_norm)
        attribute_pairs.append(_ensure_attribute_value_in_cursor(cursor, attribute_name, value_name))
    return attribute_pairs


def _validate_variant_barcode(cursor, codigo_barras: str, *, exclude_variant_id=None) -> str:
    barcode_clean = db.normalize_codigo_barras(codigo_barras)
    if not barcode_clean:
        return ""
    product_exists = cursor.execute(
        "SELECT id FROM productos WHERE TRIM(COALESCE(codigo_barras, '')) = ? LIMIT 1",
        (barcode_clean,),
    ).fetchone()
    if product_exists:
        raise ValueError("Ya existe un producto legacy con ese codigo de barras.")
    sql = "SELECT id FROM producto_variantes WHERE TRIM(COALESCE(codigo_barras, '')) = ?"
    params = [barcode_clean]
    if exclude_variant_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_variant_id))
    if cursor.execute(sql, tuple(params)).fetchone() is not None:
        raise ValueError("Ya existe otra variante con ese codigo de barras.")
    return barcode_clean


def _validate_variant_sku(cursor, sku: str, *, exclude_variant_id=None) -> str | None:
    sku_clean = _clean_text(sku) or None
    if not sku_clean:
        return None
    sql = "SELECT id FROM producto_variantes WHERE sku=?"
    params = [sku_clean]
    if exclude_variant_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_variant_id))
    if cursor.execute(sql, tuple(params)).fetchone() is not None:
        raise ValueError("El SKU de la variante ya existe.")
    return sku_clean


def _get_variant_for_product_in_cursor(cursor, product_id: int, variant_id: int):
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
    return variant


def _raise_variant_integrity_error(exc: sqlite3.IntegrityError) -> None:
    message = str(exc).lower()
    if "codigo_barras" in message:
        raise ValueError("Ya existe otra variante con ese codigo de barras.") from exc
    if "producto_variantes.sku" in message:
        raise ValueError("El SKU de la variante ya existe.") from exc
    if "producto_variantes.producto_id" in message and "combination_key" in message:
        raise ValueError("La combinacion de atributos ya existe para este producto.") from exc
    raise ValueError("No se pudo guardar la variante por un conflicto de integridad.") from exc


def _insert_variant_row(cursor, payload: dict) -> int:
    cursor.execute(
        """
        INSERT INTO producto_variantes
        (producto_id, combination_key, nombre, sku, codigo_barras, costo, precio, precio_promocional, activo, external_id, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        """,
        (
            int(payload["product_id"]),
            payload["combination_key"],
            payload["variant_name"],
            payload["sku"],
            payload["codigo_barras"],
            payload["costo"],
            payload["precio"],
            payload["precio_promocional"],
            payload["activo"],
            payload["external_id"],
        ),
    )
    return int(cursor.lastrowid)


def _insert_variant_attribute_values(cursor, variant_id: int, attribute_pairs: list[dict]) -> None:
    for item in attribute_pairs:
        cursor.execute(
            """
            INSERT INTO producto_variante_valores (variante_id, atributo_id, valor_id)
            VALUES (?,?,?)
            """,
            (variant_id, int(item["attribute_id"]), int(item["value_id"])),
        )


def _insert_variant_stock(cursor, variant_id: int, *, stock_actual, stock_minimo, stock_maximo) -> None:
    cursor.execute(
        """
        INSERT INTO stock_variantes (variante_id, stock_actual, stock_minimo, stock_maximo, updated_at)
        VALUES (?,?,?,?,CURRENT_TIMESTAMP)
        """,
        (
            variant_id,
            float(stock_actual or 0),
            float(stock_minimo or 0),
            float(stock_maximo or 0),
        ),
    )


def _update_variant_stock(cursor, variant_id: int, *, stock_actual, stock_minimo, stock_maximo) -> None:
    cursor.execute(
        """
        UPDATE stock_variantes
        SET stock_actual=?, stock_minimo=?, stock_maximo=?, updated_at=CURRENT_TIMESTAMP
        WHERE variante_id=?
        """,
        (
            float(stock_actual or 0),
            float(stock_minimo or 0),
            float(stock_maximo or 0),
            int(variant_id),
        ),
    )
    if cursor.rowcount == 0:
        _insert_variant_stock(
            cursor,
            variant_id,
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
            stock_maximo=stock_maximo,
        )


def list_attributes_catalog() -> list[dict]:
    rows = db.q(
        """
        SELECT a.id AS atributo_id,
               a.nombre AS atributo_nombre,
               a.activo AS atributo_activo,
               v.id AS valor_id,
               v.valor AS valor_nombre,
               v.activo AS valor_activo
        FROM producto_atributos a
        LEFT JOIN producto_atributo_valores v ON v.atributo_id = a.id
        ORDER BY a.nombre_normalizado, v.valor_normalizado
        """
    )
    catalog: dict[int, dict] = {}
    for row in rows:
        attr_id = int(row["atributo_id"])
        entry = catalog.setdefault(
            attr_id,
            {
                "id": attr_id,
                "nombre": row["atributo_nombre"],
                "activo": int(row["atributo_activo"] or 0),
                "valores": [],
            },
        )
        if row["valor_id"] is not None:
            entry["valores"].append(
                {
                    "id": int(row["valor_id"]),
                    "valor": row["valor_nombre"],
                    "activo": int(row["valor_activo"] or 0),
                }
            )
    return list(catalog.values())


def ensure_attribute_value(attribute_name: str, value_name: str) -> dict:
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        result = _ensure_attribute_value_in_cursor(cursor, attribute_name, value_name)
        conn.commit()
        return result
    finally:
        conn.close()


def create_variant(
    product_id: int,
    *,
    attributes: list[dict] | None = None,
    sku: str = "",
    codigo_barras: str = "",
    costo=None,
    precio=None,
    precio_promocional=None,
    stock_actual=0,
    stock_minimo=5,
    stock_maximo=50,
    activo: bool = True,
    external_id: str = "",
) -> int:
    product = db.get_producto(int(product_id or 0))
    if not product:
        raise ValueError("El producto indicado no existe.")
    stock_actual, stock_minimo, stock_maximo = _validate_variant_stock(
        stock_actual,
        stock_minimo,
        stock_maximo,
    )
    costo = _validate_optional_money(costo, "El costo")
    precio = _validate_optional_money(precio, "El precio")
    precio_promocional = _validate_optional_money(precio_promocional, "El precio promocional")

    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        attribute_pairs = _resolve_attribute_pairs(cursor, attributes)
        sku_clean = _validate_variant_sku(cursor, sku)
        barcode_clean = _validate_variant_barcode(cursor, codigo_barras)
        external_id_clean = _clean_text(external_id)
        combination_key = _build_combination_key(attribute_pairs)
        variant_name = _build_variant_name(attribute_pairs)

        existing_variant = cursor.execute(
            """
            SELECT id
            FROM producto_variantes
            WHERE producto_id=? AND combination_key=?
            LIMIT 1
            """,
            (int(product_id), combination_key),
        ).fetchone()
        if existing_variant:
            raise ValueError("La combinacion de atributos ya existe para este producto.")

        variant_id = _insert_variant_row(
            cursor,
            {
                "product_id": int(product_id),
                "combination_key": combination_key,
                "variant_name": variant_name,
                "sku": sku_clean,
                "codigo_barras": barcode_clean,
                "costo": costo,
                "precio": precio,
                "precio_promocional": precio_promocional,
                "activo": 1 if activo else 0,
                "external_id": external_id_clean,
            },
        )
        _insert_variant_attribute_values(cursor, variant_id, attribute_pairs)
        _insert_variant_stock(
            cursor,
            variant_id,
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
            stock_maximo=stock_maximo,
        )
        conn.commit()
        return variant_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        _raise_variant_integrity_error(exc)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_variant(
    product_id: int,
    variant_id: int,
    *,
    attributes: list[dict] | None = None,
    sku: str = "",
    codigo_barras: str = "",
    costo=None,
    precio=None,
    precio_promocional=None,
    stock_actual=0,
    stock_minimo=5,
    stock_maximo=50,
) -> None:
    stock_actual, stock_minimo, stock_maximo = _validate_variant_stock(
        stock_actual,
        stock_minimo,
        stock_maximo,
    )
    costo = _validate_optional_money(costo, "El costo")
    precio = _validate_optional_money(precio, "El precio")
    precio_promocional = _validate_optional_money(precio_promocional, "El precio promocional")

    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        _get_variant_for_product_in_cursor(cursor, product_id, variant_id)
        attribute_pairs = _resolve_attribute_pairs(cursor, attributes)
        sku_clean = _validate_variant_sku(cursor, sku, exclude_variant_id=variant_id)
        barcode_clean = _validate_variant_barcode(cursor, codigo_barras, exclude_variant_id=variant_id)
        combination_key = _build_combination_key(attribute_pairs)
        variant_name = _build_variant_name(attribute_pairs)

        duplicate = cursor.execute(
            """
            SELECT id
            FROM producto_variantes
            WHERE producto_id=? AND combination_key=? AND id<>?
            LIMIT 1
            """,
            (int(product_id), combination_key, int(variant_id)),
        ).fetchone()
        if duplicate:
            raise ValueError("La combinacion de atributos ya existe para este producto.")

        cursor.execute(
            """
            UPDATE producto_variantes
            SET combination_key=?, nombre=?, sku=?, codigo_barras=?, costo=?,
                precio=?, precio_promocional=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND producto_id=?
            """,
            (
                combination_key,
                variant_name,
                sku_clean,
                barcode_clean,
                costo,
                precio,
                precio_promocional,
                int(variant_id),
                int(product_id),
            ),
        )
        cursor.execute("DELETE FROM producto_variante_valores WHERE variante_id=?", (int(variant_id),))
        _insert_variant_attribute_values(cursor, int(variant_id), attribute_pairs)
        _update_variant_stock(
            cursor,
            int(variant_id),
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
            stock_maximo=stock_maximo,
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        _raise_variant_integrity_error(exc)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_variant_active(product_id: int, variant_id: int, active: bool) -> None:
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        _get_variant_for_product_in_cursor(cursor, product_id, variant_id)
        cursor.execute(
            """
            UPDATE producto_variantes
            SET activo=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND producto_id=?
            """,
            (1 if active else 0, int(variant_id), int(product_id)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _find_external_variant_references(cursor, variant_id: int) -> list[str]:
    owned_tables = {"producto_variante_valores", "stock_variantes"}
    references: set[str] = set()
    tables = cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    for table_row in tables:
        table_name = str(table_row["name"])
        if table_name in owned_tables:
            continue
        quoted_table = _quote_sqlite_identifier(table_name)
        foreign_keys = cursor.execute(f"PRAGMA foreign_key_list({quoted_table})").fetchall()
        for foreign_key in foreign_keys:
            if foreign_key["table"] != "producto_variantes" or foreign_key["to"] != "id":
                continue
            column_name = str(foreign_key["from"])
            quoted_column = _quote_sqlite_identifier(column_name)
            row = cursor.execute(
                f"SELECT 1 FROM {quoted_table} WHERE {quoted_column}=? LIMIT 1",
                (int(variant_id),),
            ).fetchone()
            if row:
                references.add(table_name)
    return sorted(references)


def delete_variant(product_id: int, variant_id: int) -> dict[str, object]:
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        _get_variant_for_product_in_cursor(cursor, product_id, variant_id)
        references = _find_external_variant_references(cursor, variant_id)
        if references:
            cursor.execute(
                """
                UPDATE producto_variantes
                SET activo=0, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND producto_id=?
                """,
                (int(variant_id), int(product_id)),
            )
            conn.commit()
            return {"deleted": False, "deactivated": True, "references": references}

        cursor.execute(
            "DELETE FROM producto_variantes WHERE id=? AND producto_id=?",
            (int(variant_id), int(product_id)),
        )
        conn.commit()
        return {"deleted": True, "deactivated": False, "references": []}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_product_variants(product_id: int) -> list[dict]:
    product = db.get_producto(int(product_id or 0))
    if not product:
        return []

    rows = db.q(
        """
        SELECT v.id,
               v.producto_id,
               v.nombre,
               v.combination_key,
               v.sku,
               v.codigo_barras,
               v.costo,
               v.precio,
               v.precio_promocional,
               v.activo,
               v.external_id,
               COALESCE(sv.stock_actual, 0) AS stock_actual,
               COALESCE(sv.stock_minimo, 5) AS stock_minimo,
               COALESCE(sv.stock_maximo, 50) AS stock_maximo,
               a.id AS atributo_id,
               a.nombre AS atributo_nombre,
               av.id AS valor_id,
               av.valor AS valor_nombre
        FROM producto_variantes v
        LEFT JOIN stock_variantes sv ON sv.variante_id = v.id
        LEFT JOIN producto_variante_valores vv ON vv.variante_id = v.id
        LEFT JOIN producto_atributos a ON a.id = vv.atributo_id
        LEFT JOIN producto_atributo_valores av ON av.id = vv.valor_id
        WHERE v.producto_id=?
        ORDER BY v.id ASC, a.nombre_normalizado ASC, av.valor_normalizado ASC
        """,
        (int(product_id),),
    )
    variants: dict[int, dict] = {}
    for row in rows:
        variant_id = int(row["id"])
        entry = variants.setdefault(
            variant_id,
            {
                "id": variant_id,
                "producto_id": int(row["producto_id"]),
                "nombre": row["nombre"],
                "combination_key": row["combination_key"],
                "sku": row["sku"] or "",
                "codigo_barras": row["codigo_barras"] or "",
                "costo_propio": float(row["costo"]) if row["costo"] is not None else None,
                "precio_propio": float(row["precio"]) if row["precio"] is not None else None,
                "costo": float(row["costo"]) if row["costo"] is not None else float(product["costo"] or 0),
                "precio": float(row["precio"]) if row["precio"] is not None else float(product["precio_venta"] or 0),
                "precio_promocional": float(row["precio_promocional"]) if row["precio_promocional"] is not None else None,
                "activo": int(row["activo"] or 0),
                "external_id": row["external_id"] or "",
                "stock_actual": float(row["stock_actual"] or 0),
                "stock_minimo": float(row["stock_minimo"] or 0),
                "stock_maximo": float(row["stock_maximo"] or 0),
                "atributos": [],
            },
        )
        if row["atributo_id"] is not None and row["valor_id"] is not None:
            entry["atributos"].append(
                {
                    "attribute_id": int(row["atributo_id"]),
                    "attribute_name": row["atributo_nombre"],
                    "value_id": int(row["valor_id"]),
                    "value_name": row["valor_nombre"],
                }
            )

    for entry in variants.values():
        entry["resumen_atributos"] = ", ".join(
            f"{item['attribute_name']}: {item['value_name']}" for item in entry["atributos"]
        ) or "Variante predeterminada"
    return list(variants.values())


def count_variants_by_product(product_ids: list[int]) -> dict[int, int]:
    normalized_ids = [int(pid) for pid in product_ids if int(pid or 0) > 0]
    if not normalized_ids:
        return {}
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = db.q(
        f"""
        SELECT producto_id, COUNT(*) AS total
        FROM producto_variantes
        WHERE producto_id IN ({placeholders})
        GROUP BY producto_id
        """,
        normalized_ids,
    )
    counts = defaultdict(int)
    for row in rows:
        counts[int(row["producto_id"])] = int(row["total"] or 0)
    return dict(counts)
