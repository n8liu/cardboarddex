from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.models import Card, Set

def find_cards_by_query(session: Session, query_text: str, limit: int = 10) -> list[Card]:
    clean = query_text.strip()
    if not clean:
        return []
    # 1. Exact ID
    card = session.get(Card, clean, options=[joinedload(Card.set)])
    if card:
        return [card]
    # 2. Match all tokens across Card.name, Set.name, or Card.number
    tokens = clean.split()
    stmt = (
        select(Card)
        .options(joinedload(Card.set))
        .join(Set, Card.set_id == Set.id)
        .where(
            Card.name.not_ilike("%code card%"),
        )
    )
    for token in tokens:
        pat = f"%{token}%"
        stmt = stmt.where((Card.name.ilike(pat)) | (Set.name.ilike(pat)) | (Card.number == token))
    return list(session.scalars(stmt.order_by(Card.name, Card.id).limit(limit)))

