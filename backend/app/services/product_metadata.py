"""PPT identity metadata with read-only legacy fallback."""
from sqlalchemy import and_, case, func, or_, select
from app.models import Card, PPTProduct, ProviderCardState


def product_type_expression():
    ppt = select(case((PPTProduct.segment.in_(['english:sealed', 'japanese:sealed']), 'Sealed Products'), else_='Cards')).where(
        PPTProduct.card_id == Card.id, PPTProduct.status == 'matched').order_by(PPTProduct.id).limit(1).correlate(Card).scalar_subquery()
    legacy = select(func.coalesce(ProviderCardState.payload['card']['product_type'].as_string(),
        ProviderCardState.payload['card']['data']['product_type'].as_string())).where(
        ProviderCardState.card_id == Card.id, ProviderCardState.provider == 'tcgapi').correlate(Card).scalar_subquery()
    return func.coalesce(ppt, legacy)


def sealed_product():
    """Exactly what the sealed page lists. Explicit metadata wins over the rarity fallback.
    Never NULL, so not_() keeps cards that have no product metadata."""
    explicit_type = product_type_expression()
    return or_(func.coalesce(explicit_type, '') == 'Sealed Products',
               and_(explicit_type.is_(None), or_(Card.rarity.is_(None), Card.rarity == '')))


def ppt_catalog_coverage(db):
    """PPT discovery checkpoints drive current catalog health; old snapshots stay archived."""
    from datetime import UTC, datetime
    from app.models import PPTCheckpoint, Set
    checkpoints = list(db.scalars(select(PPTCheckpoint).where(PPTCheckpoint.key.like('sets:%'))))
    if not checkpoints:
        return {'games': [], 'status': 'not_synced', 'source': 'pokemonpricetracker'}
    counts = dict(db.execute(select(Card.set_id, func.count()).group_by(Card.set_id)).all())
    local = list(db.scalars(select(Set)))
    games = []
    for language, game in [('english', 'pokemon'), ('japanese', 'pokemon-japan')]:
        sets = {}
        updated = None
        for checkpoint in checkpoints:
            if not checkpoint.key.startswith('sets:' + language + ':'):
                continue
            updated = checkpoint.payload.get('fetched_at') or updated
            for metadata in checkpoint.payload.get('sets', []):
                provider_id = str(metadata.get('tcgPlayerNumericId') or metadata.get('id') or '')
                sets[provider_id] = metadata
        entries = []
        for provider_id, metadata in sets.items():
            candidates = [s for s in local if s.name.casefold() == str(metadata.get('name', '')).casefold()
                          and (s.series == 'Pokemon Japan') == (language == 'japanese')]
            matched = candidates[0] if len(candidates) == 1 else None
            entries.append(dict(id=matched.id if matched else 'ppt:' + language + ':' + provider_id,
                name=metadata.get('name', provider_id), release_date=metadata.get('releaseDate'),
                provider_card_count=metadata.get('cardCount'), local_card_count=counts.get(matched.id, 0) if matched else 0,
                present_locally=matched is not None, provider_synced_at=updated))
        entries.sort(key=lambda e: (e['release_date'] or '', e['id']), reverse=True)
        games.append(dict(game=game, fetched_at=updated, provider_synced_at=updated,
            provider_set_count=len(entries), discovered_set_count=len(entries),
            local_set_count=sum(e['present_locally'] for e in entries), provider_card_count=None,
            local_card_count=sum(e['local_card_count'] for e in entries),
            missing_sets=[e for e in entries if not e['present_locally']][:30], latest_sets=entries[:20]))
    return {'games': games, 'status': 'ready', 'source': 'pokemonpricetracker'}
