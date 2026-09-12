import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)


def to_decimal(value: Any) -> Decimal | None:
    """Safely convert value to Decimal quantized to 2 decimal places."""
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        logger.warning("Invalid decimal value=%s error=%s: %s", value, type(exc).__name__, exc)
        return None


def parse_iso_datetime(value: Any) -> datetime | None:
    """Safely parse datetime from ISO string, epoch float/int, or datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            logger.warning("Invalid ISO datetime value=%s error=%s: %s", value, type(exc).__name__, exc)
    return None


def normalize_text(value: Any) -> str:
    """Normalize text by lowercasing and stripping non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalize_card_number(value: Any) -> str:
    """Normalize a card number by taking the first part before '/' and stripping leading zeros."""
    first = str(value or "").split("/", 1)[0].strip().lower()
    return first.lstrip("0") or "0"


def escape_like(value: str) -> str:
    """Escape wildcards for SQL LIKE / ILIKE queries."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def extract_float(payload: Any, key: str) -> float | None:
    """Extract a float from a dict payload safely."""
    if isinstance(payload, dict) and payload.get(key) is not None:
        try:
            return float(payload[key])
        except (ValueError, TypeError):
            return None
    return None
