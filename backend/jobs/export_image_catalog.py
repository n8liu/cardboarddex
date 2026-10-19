"""Read-only image inventory; preserve local IDs and select PPT replacements in batches."""
import json
from urllib.parse import urlsplit
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Card, PPTProduct


def main():
    with SessionLocal() as session:
        after = ''
        while True:
            cards = list(session.scalars(select(Card).where(Card.id > after).order_by(Card.id).limit(500)))
            if not cards:
                break
            products = {p.card_id: p for p in session.scalars(select(PPTProduct).where(
                PPTProduct.card_id.in_([c.id for c in cards]), PPTProduct.status == 'matched').order_by(PPTProduct.last_success_at))}
            for card in cards:
                url = card.image_url
                if not url or 'tcgapi.dev' in (urlsplit(url).hostname or ''):
                    metadata = products[card.id].metadata_payload if card.id in products else {}
                    url = metadata.get('imageCdnUrl800') or metadata.get('imageCdnUrl400') or metadata.get('imageUrl')
                if url:
                    print(json.dumps({'id': card.id, 'url': url}), flush=True)
            after = cards[-1].id


if __name__ == '__main__':
    main()
