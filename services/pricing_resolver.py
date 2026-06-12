from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from licensing.planes import normalize_plan


DEFAULT_PRICE_BY_PLAN = {
    "DEMO": 0,
    "BASICA": 49900,
    "PRO": 9900,
    "FULL": 19900,
}

RUNTIME_PRICE_CACHE: dict[str, dict[str, int]] = {}
REQUEST_TIMEOUT_SECONDS = 5


def normalize_price_plan(plan: str | None, default: str = "") -> str:
    normalized = normalize_plan(plan, default=default or "DEMO")
    return "" if not plan and not default else normalized


def get_default_price_map() -> dict[str, int]:
    return dict(DEFAULT_PRICE_BY_PLAN)


def _cache_key(producto: str | None = None) -> str:
    return (producto or "").strip().lower() or "__default__"


def set_runtime_price_cache(producto: str | None, prices_by_plan: dict[str, Any]) -> None:
    normalized: dict[str, int] = {}
    for plan, amount in dict(prices_by_plan or {}).items():
        normalized_plan = normalize_price_plan(plan)
        try:
            normalized_amount = int(amount)
        except (TypeError, ValueError):
            continue
        if not normalized_plan or normalized_amount < 0:
            continue
        normalized[normalized_plan] = normalized_amount
    if normalized:
        RUNTIME_PRICE_CACHE[_cache_key(producto)] = normalized


def get_runtime_price_cache(producto: str | None = None) -> dict[str, int] | None:
    cached = RUNTIME_PRICE_CACHE.get(_cache_key(producto))
    return dict(cached) if cached else None


def clear_runtime_price_cache() -> None:
    RUNTIME_PRICE_CACHE.clear()


def _row_matches_product(row: dict[str, Any], producto: str | None = None) -> bool:
    requested = (producto or "").strip().lower()
    if not requested:
        return True
    row_product = str(row.get("producto") or "").strip().lower()
    return row_product in {requested, "global", "*"}


def _row_is_active(row: dict[str, Any], now: datetime | None = None) -> bool:
    if str(row.get("estado") or "").strip().lower() != "activo":
        return False

    current = now or datetime.now(timezone.utc)
    since_raw = str(row.get("vigencia_desde") or "").strip()
    until_raw = str(row.get("vigencia_hasta") or "").strip()

    try:
        since = datetime.fromisoformat(since_raw.replace("Z", "+00:00")) if since_raw else None
    except ValueError:
        since = None
    try:
        until = datetime.fromisoformat(until_raw.replace("Z", "+00:00")) if until_raw else None
    except ValueError:
        until = None

    if since and since > current:
        return False
    if until and until < current:
        return False
    return True


def build_price_map_from_rows(rows: list[dict[str, Any]] | None, producto: str | None = None) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for row in rows or []:
        if not _row_matches_product(row, producto) or not _row_is_active(row):
            continue
        normalized_plan = normalize_price_plan(
            row.get("plan_tecnico") or row.get("plan_comercial") or ""
        )
        try:
            amount = int(row.get("monto"))
        except (TypeError, ValueError):
            continue
        if not normalized_plan or amount < 0:
            continue
        resolved[normalized_plan] = amount
    return resolved


def fetch_supabase_prices(producto: str | None = None) -> dict[str, int] | None:
    base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not base_url or not anon_key:
        return None

    response = requests.get(
        f"{base_url}/rest/v1/precios_planes",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
        },
        params={
            "select": "producto,plan_comercial,plan_tecnico,monto,estado,vigencia_desde,vigencia_hasta",
            "estado": "eq.activo",
            "order": "vigencia_desde.desc",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    rows = response.json() if response.text else []
    resolved = build_price_map_from_rows(rows, producto)
    return resolved or None


def resolve_plan_price(plan: str, *, producto: str | None = None) -> dict[str, Any]:
    normalized_plan = normalize_price_plan(plan)
    fallback_prices = get_default_price_map()
    if normalized_plan not in fallback_prices:
        raise ValueError("plan no soportado")

    try:
        supabase_prices = fetch_supabase_prices(producto)
        if supabase_prices and normalized_plan in supabase_prices:
            set_runtime_price_cache(producto, supabase_prices)
            return {
                "plan": normalized_plan,
                "monto": supabase_prices[normalized_plan],
                "source": "supabase",
            }
    except requests.RequestException:
        pass

    runtime_prices = get_runtime_price_cache(producto)
    if runtime_prices and normalized_plan in runtime_prices:
        return {
            "plan": normalized_plan,
            "monto": runtime_prices[normalized_plan],
            "source": "runtime",
        }

    return {
        "plan": normalized_plan,
        "monto": fallback_prices[normalized_plan],
        "source": "fallback_local",
    }
