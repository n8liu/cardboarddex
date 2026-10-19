"""Explicit, resumable cutover preparation. No external requests; bounded transactions."""
import argparse
import logging
from datetime import UTC, datetime
from sqlalchemy import select
from app.database import SessionLocal
from app.models import PPTProduct, PPTCheckpoint
from app.services.catalog_prices import lock_cards
from app.services.market_history import establish_transitions


def seed_batch(db, limit=100):
    state = db.get(PPTCheckpoint, 'market-transitions:v1')
    if state is None:
        state = PPTCheckpoint(key='market-transitions:v1', payload={})
        db.add(state)
    query = select(PPTProduct).where(PPTProduct.status == 'matched', PPTProduct.last_success_at.is_not(None))
    if state.payload.get('after'):
        query = query.where(PPTProduct.id > state.payload['after'])
    products = list(db.scalars(query.order_by(PPTProduct.id).limit(limit)))
    for product in products:
        lock_cards(db, [product.card_id])
        establish_transitions(db, product, datetime.now(UTC))
    state.payload = {'after': products[-1].id if products else state.payload.get('after'), 'complete': len(products) < limit}
    db.commit()
    return {'products': len(products), **state.payload}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        while True:
            result = seed_batch(db)
            print(result)
            if result['complete']:
                break
