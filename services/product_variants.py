from __future__ import annotations

from collections import defaultdict

import database as db


DEFAULT_COMBINATION_KEY = "__default__"


def _normalize_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_text(value) -> str:
    return " ".join(str(value or "").strip().split())


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
    attribute_clean = _clean_text(attribute_name)
    value_clean = _clean_text(value_name)
    if not attribute_clean:
        raise ValueError("El nombre del atributo es obligatorio.")
    if not value_clean:
        raise ValueError("El valor del atributo es obligatorio.")

    attribute_norm = _normalize_text(attribute_clean)
    value_norm = _normalize_text(value_clean)

    attribute = db.q(
        "SELECT id, nombre FROM producto_atributos WHERE nombre_normalizado=? LIMIT 1",
        (attribute_norm,),
        fetchone=True,
    )
    if not attribute:
        attribute_id = db.q(
            "INSERT INTO producto_atributos (nombre, nombre_normalizado, activo) VALUES (?,?,1)",
            (attribute_clean, attribute_norm),
            fetchall=False,
            commit=True,
        )
        attribute = {"id": int(attribute_id), "nombre": attribute_clean}

    value = db.q(
        """
        SELECT id, valor
        FROM producto_atributo_valores
        WHERE atributo_id=? AND valor_normalizado=?
        LIMIT 1
        """,
        (int(attribute["id"]), value_norm),
        fetchone=True,
    )
    if not value:
        value_id = db.q(
            """
            INSERT INTO producto_atributo_valores
            (atributo_id, valor, valor_normalizado, activo)
            VALUES (?,?,?,1)
            """,
            (int(attribute["id"]), value_clean, value_norm),
            fetchall=False,
            commit=True,
        )
        value = {"id": int(value_id), "valor": value_clean}

    return {
        "attribute_id": int(attribute["id"]),
        "attribute_name": attribute["nombre"],
        "value_id": int(value["id"]),
        "value_name": value["valor"],
    }


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
        attribute_pairs.append(ensure_attribute_value(attribute_name, value_name))

    sku_clean = _clean_text(sku) or None
    barcode_clean = _clean_text(codigo_barras)
    external_id_clean = _clean_text(external_id)
    combination_key = _build_combination_key(attribute_pairs)
    variant_name = _build_variant_name(attribute_pairs)

    if sku_clean:
        existing_sku = db.q(
            "SELECT id FROM producto_variantes WHERE sku=? LIMIT 1",
            (sku_clean,),
            fetchone=True,
        )
        if existing_sku:
            raise ValueError("El SKU de la variante ya existe.")

    existing_variant = db.q(
        """
        SELECT id
        FROM producto_variantes
        WHERE producto_id=? AND combination_key=?
        LIMIT 1
        """,
        (int(product_id), combination_key),
        fetchone=True,
    )
    if existing_variant:
        raise ValueError("La combinación de atributos ya existe para este producto.")

    variant_id = db.q(
        """
        INSERT INTO producto_variantes
        (producto_id, combination_key, nombre, sku, codigo_barras, costo, precio, precio_promocional, activo, external_id, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        """,
        (
            int(product_id),
            combination_key,
            variant_name,
            sku_clean,
            barcode_clean,
            costo,
            precio,
            precio_promocional,
            1 if activo else 0,
            external_id_clean,
        ),
        fetchall=False,
        commit=True,
    )
    variant_id = int(variant_id)

    for item in attribute_pairs:
        db.q(
            """
            INSERT INTO producto_variante_valores (variante_id, atributo_id, valor_id)
            VALUES (?,?,?)
            """,
            (variant_id, int(item["attribute_id"]), int(item["value_id"])),
            fetchall=False,
            commit=True,
        )

    db.q(
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
        fetchall=False,
        commit=True,
    )
    return variant_id


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
