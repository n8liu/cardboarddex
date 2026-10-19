"""Pure legacy identity helpers; existing IDs are immutable."""
import hashlib
import logging
from datetime import date, datetime
logger = logging.getLogger(__name__)

def local_card_id(source_id: object) -> str:
    value = str(source_id)
    if len(value) <= 64:
        return value
    return hashlib.sha256(f"tcgapi:{value}".encode()).hexdigest()


def parse_release_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError as exc:
        logger.warning(
            "Provider release date invalid value=%s error=%s: %s",
            value,
            type(exc).__name__,
            exc,
        )
        return None


def split_card_number(value: object, printed_total: int | None) -> tuple[str, int | None]:
    number = str(value or "").strip()
    if "/" not in number:
        return number, printed_total
    printed, denominator = number.split("/", 1)
    try:
        return printed.strip(), int(denominator)
    except ValueError as exc:
        logger.warning(
            "Provider card number denominator invalid value=%s error=%s: %s",
            value,
            type(exc).__name__,
            exc,
        )
        return number, printed_total


