"""Shared quota-controlled refresh for scheduled and manual PPT work."""
from datetime import UTC, datetime
from sqlalchemy import select
from app.config import get_settings
from app.models import PPTProduct
from app.providers.ppt import PPTClient, PPTBlocked
from app.services.ppt_ingestion import ingest


def refresh_product(db, client, product, *, lane='rotation', include_graded=True, bonus_graded=False, now=None):
    language, kind = product.segment.split(':')
    provider_id = product.provider_id
    db.commit()  # Release database connection before provider I/O.
    rows = client.request('cards' if kind == 'cards' else 'sealed-products', lane=lane,
        language=language, tcgPlayerId=provider_id, limit=1, includeHistory=True,
        includeEbay=kind == 'cards' and include_graded, bonus_graded=bonus_graded)
    if len(rows) != 1:
        raise ValueError('PPT product lookup returned no product')
    ingest(db, product, rows[0], now or datetime.now(UTC))


def refresh_cards(db, card_ids=None, *, limit=8, client=None):
    if not get_settings().ppt_ingestion_enabled:
        return {'status': 'disabled', 'cards': 0}
    if not 1 <= limit <= 50:
        raise ValueError('Manual PPT batches must contain 1–50 products')
    query = select(PPTProduct).where(PPTProduct.status == 'matched')
    if card_ids is not None:
        query = query.where(PPTProduct.card_id.in_(card_ids))
    products = list(db.scalars(query.order_by(PPTProduct.last_success_at.asc().nullsfirst(), PPTProduct.id).limit(limit)))
    own_client = client is None
    client = client or PPTClient()
    result = {'status': 'completed', 'cards': 0, 'unmapped_card_ids': sorted(set(card_ids or []) - {p.card_id for p in products})}
    try:
        for product in products:
            try:
                refresh_product(db, client, product, lane='priority')
                db.commit()
                result['cards'] += 1
            except PPTBlocked as exc:
                db.rollback()
                result.update(status='blocked', reason=str(exc))
                break
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('PPT manual refresh failed product=%s error=%s: %s', product.id, type(exc).__name__, exc)
                db.rollback()
                raise
    finally:
        if own_client:
            client.close()
    return result
