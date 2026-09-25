"""Local, atomically published image manifest; never performs network I/O."""
import hashlib
import json
import logging
from pathlib import Path
from threading import RLock
from time import monotonic

from app.config import get_settings

logger = logging.getLogger(__name__)
from jobs.publish_image_manifest import CARD_ID, validate_manifest
PLACEHOLDER = 'placeholder.svg'
_lock = RLock()
_path = None
_checked = 0.0
_signature = None
_generation = 'empty'
_entries: dict[str, str] = {}


def _refresh() -> None:
    global _path, _checked, _signature, _generation, _entries
    path = get_settings().image_manifest_path
    now = monotonic()
    if path == _path and now - _checked < 60:
        return
    with _lock:
        if path == _path and now - _checked < 60:
            return
        if path != _path:
            _entries, _signature, _generation = {}, None, 'empty'
        _path, _checked = path, now
        try:
            file = Path(path)
            stat = file.stat()
            signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            if signature == _signature:
                return
            if stat.st_size > 32 * 1024 * 1024:
                raise ValueError('Image manifest exceeds 32 MiB')
            raw = file.read_bytes()
            entries = validate_manifest(json.loads(raw))
            _entries = entries
            _generation = hashlib.sha256(raw).hexdigest()[:16]
            _signature = signature
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.warning('Image manifest reload failed path=%s error=%s: %s; retaining last valid manifest', path, type(exc).__name__, exc)


def image_generation() -> str:
    settings = get_settings()
    if not settings.image_cdn_enabled:
        return 'legacy'
    _refresh()
    return f'{settings.image_cdn_base_url}:{_generation}'


def card_image_url(card_id: str) -> str:
    settings = get_settings()
    if not settings.image_cdn_enabled:
        return f'/cards/{card_id}/image'
    _refresh()
    return f"{settings.image_cdn_base_url.rstrip('/')}/{_entries.get(str(card_id), PLACEHOLDER)}"
