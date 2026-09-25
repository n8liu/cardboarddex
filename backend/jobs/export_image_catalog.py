"""Stream a read-only image inventory as JSONL; no provider/storage access."""
import json
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Card


def main():
    with SessionLocal() as session:
        rows = session.execute(select(Card.id, Card.image_url).where(Card.image_url.is_not(None)).order_by(Card.id).execution_options(yield_per=500))
        for cid, url in rows:
            print(json.dumps({'id': cid, 'url': url}), flush=True)


if __name__ == '__main__':
    main()
