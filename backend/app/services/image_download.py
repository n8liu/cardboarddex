"""Validated provider-independent image downloads; retired provider hosts are denied."""
import logging
import time
from urllib.parse import urljoin, urlsplit
import httpx
logger = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
CAP_BYTES = 8_000_000_000
ALLOWED = ('tcgplayer.com', 'cdn.pokemonpricetracker.com', 'pokemontcg.io', 'pokemon.com', 'githubusercontent.com', 'pokeapi.co')
TYPES = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif', 'image/avif': 'avif'}
PLACEHOLDER = b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="560" viewBox="0 0 400 560"><rect width="400" height="560" rx="20" fill="#f1f5f9"/><text x="200" y="280" text-anchor="middle" fill="#64748b" font-family="sans-serif" font-size="22">Image pending</text></svg>'


def validate_source(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or not any(host == d or host.endswith('.' + d) for d in ALLOWED):
        raise ValueError(f'Unapproved image URL: {url}')


def image_extension(content, mime):
    ext = TYPES.get(mime)
    valid = (
        (ext == 'jpg' and content.startswith(b'\xff\xd8\xff')) or
        (ext == 'png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or
        (ext == 'gif' and content[:6] in (b'GIF87a', b'GIF89a')) or
        (ext == 'webp' and content.startswith(b'RIFF') and content[8:12] == b'WEBP') or
        (ext == 'avif' and content[4:8] == b'ftyp' and b'avif' in content[8:32])
    )
    if not valid:
        raise ValueError(f'Invalid image signature or MIME type: {mime}')
    return ext


def download(client, url):
    for attempt in range(3):
        try:
            current = url
            for redirect in range(6):
                validate_source(current)
                with client.stream('GET', current, follow_redirects=False) as response:
                    if response.is_redirect:
                        if redirect == 5:
                            raise ValueError('Too many image redirects')
                        current = urljoin(current, response.headers['location'])
                        continue
                    response.raise_for_status()
                    if int(response.headers.get('content-length', 0)) > MAX_BYTES:
                        raise ValueError('Image exceeds download limit')
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise ValueError('Image exceeds download limit')
                    mime = response.headers.get('content-type', '').split(';')[0].lower()
                    return bytes(content), mime, image_extension(content, mime)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning('Image download failed url=%s attempt=%s error=%s: %s', url, attempt + 1, type(exc).__name__, exc)
            if attempt == 2 or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (429, 500, 502, 503, 504)):
                raise
            time.sleep(2 ** attempt)



class ImageClient:
    def get_image(self, url):
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            content, mime, _ = download(client, url)
            return content, mime


def source_for_card(db, card):
    """Keep canonical URLs intact; choose a verified PPT replacement for retired hosts."""
    from sqlalchemy import select
    from app.models import PPTProduct
    if card.image_url and 'tcgapi.dev' not in (urlsplit(card.image_url).hostname or ''):
        return card.image_url
    product = db.scalar(select(PPTProduct).where(PPTProduct.card_id == card.id, PPTProduct.status == 'matched')
                        .order_by(PPTProduct.last_success_at.desc().nullslast(), PPTProduct.id).limit(1))
    if product:
        metadata = product.metadata_payload
        return metadata.get('imageCdnUrl800') or metadata.get('imageCdnUrl400') or metadata.get('imageUrl')
    return None
