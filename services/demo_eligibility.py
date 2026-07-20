from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any


DEMO_ELIGIBLE = "eligible"
DEMO_ALREADY_USED = "already_used"
DEMO_ACTIVE = "active"
DEMO_EXPIRED = "expired"
DEMO_BLOCKED = "blocked"
DEMO_OFFLINE_UNVERIFIED = "offline_unverified"
DEMO_ERROR = "error"

ADMIN_BLOCKED_STATES = {
    "bloqueada",
    "bloqueado",
    "suspendida",
    "suspendido",
    "revocada",
    "revocado",
    "anulada",
    "anulado",
    "cancelada",
    "cancelado",
}


@dataclass(frozen=True)
class DemoIdentity:
    product: str
    activation_id: str
    hardware_id: str = ""
    machine_id: str = ""
    email: str = ""

    @property
    def strong_identifiers(self) -> tuple[str, ...]:
        values = []
        for value in (self.activation_id, self.hardware_id, self.machine_id):
            normalized = normalize_identifier(value)
            if normalized and normalized not in values:
                values.append(normalized)
        return tuple(values)

    @property
    def identity_hashes(self) -> dict[str, str]:
        return {
            key: hash_identifier(self.product, value)
            for key, value in {
                "activation_id": self.activation_id,
                "hardware_id": self.hardware_id,
                "machine_id": self.machine_id,
            }.items()
            if normalize_identifier(value)
        }


@dataclass(frozen=True)
class DemoEligibilityResult:
    state: str
    message: str
    matched_record: dict[str, Any] | None = None
    started_at: str = ""
    expires_at: str = ""
    can_start_demo: bool = False
    can_recover_demo: bool = False

    @property
    def blocked_for_new_demo(self) -> bool:
        return self.state in {
            DEMO_ALREADY_USED,
            DEMO_ACTIVE,
            DEMO_EXPIRED,
            DEMO_BLOCKED,
            DEMO_OFFLINE_UNVERIFIED,
            DEMO_ERROR,
        }


def normalize_identifier(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_product(value: object) -> str:
    return str(value or "").strip().lower()


def hash_identifier(product: str, value: object) -> str:
    normalized = normalize_identifier(value)
    if not normalized:
        return ""
    namespace = f"nexar-demo:{normalize_product(product)}"
    return hashlib.sha256(f"{namespace}:{normalized}".encode("utf-8")).hexdigest()


def mask_identifier(value: object) -> str:
    normalized = str(value or "").strip()
    if len(normalized) <= 8:
        return "***" if normalized else ""
    return f"{normalized[:4]}...{normalized[-4:]}"


def build_demo_identity(
    *,
    product: str,
    activation_id: str,
    hardware_id: str = "",
    email: str = "",
    machine_details: dict[str, Any] | None = None,
) -> DemoIdentity:
    details = machine_details or {}
    machine_id = ""
    raw_machine_id = str(details.get("machine_id", "") or "").strip()
    if raw_machine_id and raw_machine_id != "(sin machine-id)":
        machine_id = raw_machine_id
    return DemoIdentity(
        product=normalize_product(product),
        activation_id=str(activation_id or "").strip(),
        hardware_id=str(hardware_id or "").strip(),
        machine_id=machine_id,
        email=str(email or "").strip().lower(),
    )


def build_demo_metadata(
    *,
    identity: DemoIdentity,
    base_metadata: dict[str, Any],
    machine_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(base_metadata)
    metadata["activation_id"] = identity.activation_id
    metadata["producto"] = identity.product
    metadata["identity_hashes"] = identity.identity_hashes
    metadata["identity_version"] = "demo-v1"
    # Se conserva el resumen legacy para compatibilidad administrativa; las
    # comparaciones nuevas usan identificadores normalizados y hashes.
    metadata["machine_details"] = machine_details or {}
    return metadata


def parse_demo_message(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_admin_state(value: object) -> str:
    return normalize_identifier(value)


def _get_row_admin_state_candidates(row: dict[str, Any]) -> tuple[str, ...]:
    metadata = parse_demo_message(row.get("mensaje"))
    normalized_states: list[str] = []
    for candidate in (
        row.get("estado"),
        metadata.get("estado"),
        metadata.get("license_status"),
        metadata.get("demo_admin_status"),
    ):
        normalized = _normalize_admin_state(candidate)
        if normalized and normalized not in normalized_states:
            normalized_states.append(normalized)
    return tuple(normalized_states)


def _get_row_admin_state(row: dict[str, Any]) -> str:
    fallback_state = ""
    for normalized in _get_row_admin_state_candidates(row):
        if normalized in ADMIN_BLOCKED_STATES:
            return normalized
        if not fallback_state:
            fallback_state = normalized
    if fallback_state:
        return fallback_state
    return ""


def _extract_demo_dates(row: dict[str, Any]) -> tuple[str, str, date | None]:
    metadata = parse_demo_message(row.get("mensaje"))
    started_at = str(metadata.get("demo_started_at") or metadata.get("started_at") or "").strip()[:10]
    expires_at = str(metadata.get("demo_expires_at") or metadata.get("expires_at") or "").strip()[:10]
    expires_on = None
    if expires_at:
        try:
            expires_on = date.fromisoformat(expires_at)
        except Exception:
            expires_on = None
    return started_at, expires_at, expires_on


def _candidate_sort_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    started_at, expires_at, _ = _extract_demo_dates(row)
    created_at = str(row.get("created_at") or "").strip()[:32]
    identifier = int(row.get("id") or 0) if str(row.get("id") or "").isdigit() else 0
    return (
        expires_at or "9999-12-31",
        started_at or "9999-12-31",
        created_at or "9999-12-31T23:59:59",
        identifier,
    )


def row_matches_identity(row: dict[str, Any], identity: DemoIdentity) -> bool:
    if not row or normalize_product(row.get("producto") or identity.product) != identity.product:
        return False

    metadata = parse_demo_message(row.get("mensaje"))
    row_values = {
        normalize_identifier(row.get("activation_id")),
        normalize_identifier(row.get("hardware_id")),
        normalize_identifier(row.get("hwid")),
        normalize_identifier(metadata.get("activation_id")),
        normalize_identifier(metadata.get("hardware_id")),
        normalize_identifier(metadata.get("hwid")),
    }
    machine_details = metadata.get("machine_details") if isinstance(metadata.get("machine_details"), dict) else {}
    row_values.add(normalize_identifier(machine_details.get("machine_id")))

    hashes = metadata.get("identity_hashes") if isinstance(metadata.get("identity_hashes"), dict) else {}
    row_hashes = {
        normalize_identifier(row.get("identity_hash")),
        normalize_identifier(row.get("activation_id_hash")),
        normalize_identifier(row.get("hardware_id_hash")),
        normalize_identifier(row.get("machine_id_hash")),
    }
    row_hashes.update(normalize_identifier(value) for value in hashes.values())

    for current in identity.strong_identifiers:
        if current and current in row_values:
            return True
        if hash_identifier(identity.product, current) in row_hashes:
            return True
        message_text = normalize_identifier(row.get("mensaje"))
        if current and current in message_text:
            return True

    return False


def resolve_demo_eligibility_from_records(
    *,
    identity: DemoIdentity,
    records: list[dict[str, Any]] | None,
    today: date | None = None,
) -> DemoEligibilityResult:
    current_date = today or date.today()
    matches = [row for row in (records or []) if row_matches_identity(row, identity)]
    if not matches:
        return DemoEligibilityResult(
            state=DEMO_ELIGIBLE,
            message="La prueba gratuita esta disponible para este equipo.",
            can_start_demo=True,
        )

    blocked_matches = [
        row for row in matches
        if _get_row_admin_state(row) in ADMIN_BLOCKED_STATES
    ]
    if blocked_matches:
        blocked_row = sorted(blocked_matches, key=_candidate_sort_key)[0]
        return DemoEligibilityResult(
            state=DEMO_BLOCKED,
            message="No es posible iniciar la prueba gratuita para este equipo. Contacta a soporte.",
            matched_record=blocked_row,
        )

    active_candidates: list[tuple[tuple[str, str, str, int], dict[str, Any], str, str]] = []
    expired_candidates: list[tuple[tuple[str, str, str, int], dict[str, Any], str, str]] = []
    ambiguous_matches: list[dict[str, Any]] = []
    for row in matches:
        started_at, expires_at, expires_on = _extract_demo_dates(row)
        if expires_on is None:
            ambiguous_matches.append(row)
            continue
        candidate = (_candidate_sort_key(row), row, started_at, expires_at)
        if current_date < expires_on:
            active_candidates.append(candidate)
        else:
            expired_candidates.append(candidate)

    if active_candidates:
        _, row, started_at, expires_at = sorted(active_candidates, key=lambda item: item[0])[0]
        return DemoEligibilityResult(
            state=DEMO_ACTIVE,
            message="Encontramos una prueba gratuita vigente para este equipo.",
            matched_record=row,
            started_at=started_at,
            expires_at=expires_at,
            can_recover_demo=True,
        )

    if expired_candidates:
        _, row, started_at, expires_at = sorted(expired_candidates, key=lambda item: item[0])[0]
        return DemoEligibilityResult(
            state=DEMO_EXPIRED,
            message="Este equipo ya utilizo la prueba gratuita. Podes elegir un plan para continuar.",
            matched_record=row,
            started_at=started_at,
            expires_at=expires_at,
        )

    if ambiguous_matches:
        row = sorted(ambiguous_matches, key=_candidate_sort_key)[0]
        return DemoEligibilityResult(
            state=DEMO_ALREADY_USED,
            message="Este equipo ya utilizo la prueba gratuita. Podes elegir un plan para continuar.",
            matched_record=row,
        )

    return DemoEligibilityResult(
        state=DEMO_ALREADY_USED,
        message="Este equipo ya utilizo la prueba gratuita. Podes elegir un plan para continuar.",
        matched_record=sorted(matches, key=_candidate_sort_key)[0],
    )


def resolve_local_demo_evidence(demo_status: dict[str, Any], config: dict[str, Any]) -> DemoEligibilityResult | None:
    if demo_status.get("demo") and demo_status.get("install_date"):
        if demo_status.get("vencido"):
            return DemoEligibilityResult(
                state=DEMO_EXPIRED,
                message="Tu periodo de prueba finalizo. Elegi BASICA, PRO o FULL para continuar usando Nexar Comercio.",
                started_at=str(demo_status.get("install_date") or ""),
                expires_at=str(demo_status.get("expires_at") or ""),
            )
        return DemoEligibilityResult(
            state=DEMO_ACTIVE,
            message="La prueba gratuita local sigue vigente.",
            started_at=str(demo_status.get("install_date") or ""),
            expires_at=str(demo_status.get("expires_at") or ""),
            can_recover_demo=True,
        )
    if str(config.get("activation_demo_request_key", "") or "").strip():
        return DemoEligibilityResult(
            state=DEMO_ALREADY_USED,
            message="Este equipo ya utilizo la prueba gratuita. Podes elegir un plan para continuar.",
        )
    return None
