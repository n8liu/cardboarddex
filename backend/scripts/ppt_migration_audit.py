"""Read-only, secret-free preservation receipt. Run in an isolated worker-budget container."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import select, text
from app.database import SessionLocal
from app.models import Card, Set, PriceObservation, ProviderCardState, MarketHistory


def audit(db):
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
    queries = {
        'card_identity': select(Card.id, Card.set_id, Card.name, Card.number, Card.printed_total).order_by(Card.id),
        'set_identity': select(Set.id, Set.name, Set.printed_total).order_by(Set.id),
        'legacy_prices': select(PriceObservation.__table__).where(PriceObservation.provider == 'tcgapi').order_by(PriceObservation.id),
        'legacy_history': select(MarketHistory.__table__).order_by(MarketHistory.card_id, MarketHistory.printing, MarketHistory.day),
        'legacy_states': select(ProviderCardState.__table__).where(ProviderCardState.provider.in_(['tcgapi', 'tcgapi_history'])).order_by(ProviderCardState.id),
    }
    receipt = {'generated_at': datetime.now(UTC).isoformat(), 'tables': {}}
    for name, query in queries.items():
        count, digest = 0, hashlib.sha256()
        identities = {}
        for row in db.execute(query.execution_options(yield_per=500)).mappings():
            encoded = json.dumps(dict(row), sort_keys=True, default=str, separators=(',', ':')).encode()
            digest.update(encoded + b'\n')
            if name.endswith('_identity'):
                identities[row['id']] = hashlib.sha256(encoded).hexdigest()
            count += 1
        receipt['tables'][name] = {'rows': count, 'sha256': digest.hexdigest()}
        if name.endswith('_identity'):
            receipt['tables'][name]['identities'] = identities
    return receipt


def preserved(previous, current):
    for name, expected in previous['tables'].items():
        actual = current['tables'][name]
        if name.endswith('_identity'):
            if any(actual['identities'].get(key) != value for key, value in expected['identities'].items()):
                return False
        elif expected != actual:
            return False
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = audit(db)
    if args.baseline:
        previous = json.loads(args.baseline.read_text())
        result['matches_baseline'] = preserved(previous, result)
    print(json.dumps(result, indent=2))
    if args.baseline and not result['matches_baseline']:
        raise SystemExit(1)
