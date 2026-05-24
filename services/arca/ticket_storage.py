from __future__ import annotations

from datetime import UTC, datetime, timedelta

import database as db


DATETIME_MASK = "%Y-%m-%d %H:%M:%S"


def parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(text, DATETIME_MASK).replace(tzinfo=UTC)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def row_to_ticket(row) -> dict[str, object] | None:
    if not row:
        return None
    ticket = dict(row)
    ticket["generation_dt"] = parse_datetime(ticket.get("generation_time"))
    ticket["expiration_dt"] = parse_datetime(ticket.get("expiration_time"))
    return ticket


def save_ticket(
    *,
    ambiente: str,
    service: str,
    token: str,
    sign: str,
    generation_time: str,
    expiration_time: str,
) -> dict[str, object]:
    created_at = datetime.now(UTC).strftime(DATETIME_MASK)
    ticket_id = int(
        db.q(
            """
            INSERT INTO arca_wsaa_tickets
            (ambiente, service, token, sign, generation_time, expiration_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ambiente or "").strip().lower(),
                str(service or "").strip().lower(),
                str(token or "").strip(),
                str(sign or "").strip(),
                str(generation_time or "").strip(),
                str(expiration_time or "").strip(),
                created_at,
            ),
            commit=True,
        )
    )
    return get_ticket_by_id(ticket_id) or {}


def get_ticket_by_id(ticket_id: int) -> dict[str, object] | None:
    row = db.q(
        """
        SELECT id, ambiente, service, token, sign, generation_time, expiration_time, created_at
        FROM arca_wsaa_tickets
        WHERE id = ?
        """,
        (int(ticket_id),),
        fetchone=True,
    )
    return row_to_ticket(row)


def get_latest_ticket(ambiente: str, service: str) -> dict[str, object] | None:
    row = db.q(
        """
        SELECT id, ambiente, service, token, sign, generation_time, expiration_time, created_at
        FROM arca_wsaa_tickets
        WHERE ambiente = ? AND service = ?
        ORDER BY datetime(COALESCE(created_at, '1970-01-01 00:00:00')) DESC, id DESC
        LIMIT 1
        """,
        (
            str(ambiente or "").strip().lower(),
            str(service or "").strip().lower(),
        ),
        fetchone=True,
    )
    return row_to_ticket(row)


def is_ticket_valid(
    ticket: dict[str, object] | None,
    *,
    now: datetime | None = None,
    safety_margin_seconds: int = 120,
) -> bool:
    if not ticket:
        return False
    expiration_dt = ticket.get("expiration_dt")
    if not isinstance(expiration_dt, datetime):
        expiration_dt = parse_datetime(ticket.get("expiration_time"))
    if expiration_dt is None:
        return False
    current = now.astimezone(UTC) if now else datetime.now(UTC)
    return expiration_dt > current + timedelta(seconds=max(0, int(safety_margin_seconds)))
