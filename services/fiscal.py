"""Reglas fiscales locales compartidas por catálogo y facturación."""

from __future__ import annotations

import database as db


IVA_PREDETERMINADO_IMPORTACION_CONFIG_KEY = "iva_predeterminado_importacion"

ALICUOTAS_IVA = {
    "0": {"id": 3, "rate": 0.0, "label": "0%"},
    "2.5": {"id": 9, "rate": 2.5, "label": "2.5%"},
    "5": {"id": 8, "rate": 5.0, "label": "5%"},
    "10.5": {"id": 4, "rate": 10.5, "label": "10.5%"},
    "21": {"id": 5, "rate": 21.0, "label": "21%"},
    "27": {"id": 6, "rate": 27.0, "label": "27%"},
}


def normalizar_alicuota_iva(value: object) -> dict[str, float | int | str] | None:
    raw = str(value or "").strip().replace(",", ".")
    normalized = raw[:-1] if raw.endswith("%") else raw
    return ALICUOTAS_IVA.get(normalized)


def obtener_iva_predeterminado_importacion() -> str:
    alicuota = normalizar_alicuota_iva(
        db.get_config_valor(IVA_PREDETERMINADO_IMPORTACION_CONFIG_KEY, "")
    )
    if not alicuota:
        raise ValueError(
            "Configurá una alícuota de IVA predeterminada antes de importar el catálogo."
        )
    return str(alicuota["label"])
