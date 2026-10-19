from app.services.price_sources import market_observation
"""Durable weekly coverage and bounded passive pricing; no catalog schema changes."""
import json
import logging
import time
from bisect import bisect_left, bisect_right
from uuid import uuid4

from redis.exceptions import RedisError
from sqlalchemy import and_, func, or_, select

from app.common.redis import get_durable_redis, get_redis
from app.config import get_settings
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.providers.limiter import scheduled_budget

logger = logging.getLogger(__name__)
PREFIX = "cardboarddex:passive:v1"  # Preserve the shared lease during upgrades.
STATE = "cardboarddex:passive:v2"
WEEK = 7 * 86400
RETRY_DELAY = 3600
MAX_RETRIES = 1000
PROVIDERS = ("ebay",)
LOCK = f"{PREFIX}:batch"
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
SAVE = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
for i=2,#KEYS do redis.call('set', KEYS[i], ARGV[i]) end
return 1
"""


class LeaseExpired(RuntimeError):
    pass


def record_card_interest(redis, card_id: str, now: float | None = None) -> None:
    """Bound views/clicks to 2,000 cards per UTC day, retaining seven-day input."""
    day = int((time.time() if now is None else now) // 86400)
    key = f"{PREFIX}:interest:{day}"
    pipe = redis.pipeline(transaction=True)
    pipe.zincrby(key, 1, card_id)
    pipe.zremrangebyrank(key, 0, -2001)
    pipe.expire(key, 8 * 86400)
    pipe.execute()


def interest_scores(now: float) -> dict[str, float]:
    redis = get_redis()
    scores: dict[str, float] = {}
    if redis is None:
        return scores
    try:
        day = int(now // 86400)
        for bucket in range(day - 6, day + 1):
            for member, score in redis.zrevrange(f"{PREFIX}:interest:{bucket}", 0, 1999, withscores=True):
                card_id = member.decode() if isinstance(member, bytes) else member
                scores[card_id] = scores.get(card_id, 0) + score
    except RedisError as exc:
        logger.warning("Passive popularity unavailable error=%s: %s", type(exc).__name__, exc)
    return scores


def percentiles(values: dict) -> dict[str, float]:
    """Midrank percentile among present values; ties equal, missing values zero."""
    ordered = sorted(v for v in values.values() if v is not None)
    n = len(ordered)
    return {key: (0.0 if value is None else 1.0 if n == 1 else
                  (bisect_left(ordered, value) + bisect_right(ordered, value) - 1) / (2 * (n - 1)))
            for key, value in values.items()}


def eligible_cards():
    from app.services.product_metadata import product_type_expression
    explicit_type = product_type_expression()
    return (select(Card.id).outerjoin(ProviderCardState, and_(
        ProviderCardState.card_id == Card.id, ProviderCardState.provider == "tcgapi"))
        .where(Card.name.not_ilike("%code card%"), Card.number.is_not(None),
               Card.number.not_in(("", "None")),
               or_(explicit_type == "Cards", and_(explicit_type.is_(None),
                   Card.rarity.is_not(None), Card.rarity != "", Card.rarity.not_ilike("none")))))


def rank_priority(session, popularity, limit):
    latest = (select(PriceObservation.card_id, PriceObservation.price,
                     func.row_number().over(partition_by=PriceObservation.card_id,
                         order_by=(PriceObservation.observed_at.desc(), PriceObservation.id.desc())).label("rn"))
              .where(market_observation(), PriceObservation.currency == "USD",
                     PriceObservation.price > 0, PriceObservation.grading_company.is_(None),
                     PriceObservation.grade.is_(None)).subquery())
    eligible = eligible_cards().subquery()
    rows = session.execute(select(Card.id, Set.release_date, latest.c.price)
        .join(eligible, eligible.c.id == Card.id).join(Set, Set.id == Card.set_id)
        .outerjoin(latest, and_(latest.c.card_id == Card.id, latest.c.rn == 1))).all()
    pop = percentiles({cid: popularity.get(cid) or None for cid, _, _ in rows})
    age = percentiles({cid: date.toordinal() if date else None for cid, date, _ in rows})
    price = percentiles({cid: amount for cid, _, amount in rows})
    return sorted(pop, key=lambda cid: (-(.5 * pop[cid] + .25 * age[cid] + .25 * price[cid]), cid))[:limit]


def initial_progress():
    return {"checked": {}, "attempts": {}, "retries": {}, "cursor": "", "wraps": 0,
            "catalog_advances": 0, "catalog_turn": 0, "total_attempts": 0, "total_checked": 0,
            "retry_overflow": 0, "last_success": None, "last_run": None}


def load_state(redis):
    values = redis.mget([f"{STATE}:cycle", *(f"{STATE}:{p}" for p in PROVIDERS)])
    return (json.loads(values[0]) if values[0] else None,
            {p: json.loads(value) if value else initial_progress() for p, value in zip(PROVIDERS, values[1:])})


def save_state(redis, token, values):
    keys = list(values)
    if not redis.eval(SAVE, len(keys) + 1, LOCK, *keys, token,
                      *(json.dumps(values[k], separators=(",", ":")) for k in keys)):
        raise LeaseExpired("Passive pricing lease expired; refusing stale state writes")


def ensure_cycle(session, redis, token, now, popularity):
    cycle, states = load_state(redis)
    if cycle is not None and now < cycle["ends"]:
        return cycle, states
    history = cycle.get("history", []) if cycle else []
    if cycle:
        completed = {p: sum(states[p]["checked"].get(cid, 0) >= cycle["starts"] for cid in cycle["members"])
                     for p in PROVIDERS}
        summary = {"starts": cycle["starts"], "ends": cycle["ends"], "size": len(cycle["members"]),
                   "checked": completed, "missed": {p: len(cycle["members"]) - completed[p] for p in PROVIDERS}}
        history = [*history, summary][-12:]
        logger.info("passive_cycle_finished %s", json.dumps(summary, sort_keys=True))
    members = rank_priority(session, popularity, get_settings().passive_priority_card_count)
    cycle = {"starts": now, "ends": now + WEEK, "members": members, "history": history}
    for state in states.values():
        state["checked"] = {cid: value for cid, value in state["checked"].items() if cid in members}
        state["attempts"] = {cid: value for cid, value in state["attempts"].items() if cid in members}
    save_state(redis, token, {f"{STATE}:cycle": cycle, **{f"{STATE}:{p}": states[p] for p in PROVIDERS}})
    logger.info("passive_cycle_started starts=%s ends=%s size=%s", now, cycle["ends"], len(members))
    return cycle, states


def select_batch(session, cycle, state, popularity, now, limit):
    """Return (card ID, lane, cursor wrapped) with at least one new catalog slot."""
    limit = min(limit, 8)
    selected = []
    ids = set()
    members = cycle["members"]
    ranks = {cid: index for index, cid in enumerate(members)}
    def available(cid):
        return cid not in ids and state["retries"].get(cid, 0) <= now
    def add(cid, lane, wrap=False):
        selected.append((cid, lane, wrap)); ids.add(cid)
    hottest = sorted(members, key=lambda cid: (-popularity.get(cid, 0), ranks[cid]))[:12]
    hot = sorted((cid for cid in hottest if available(cid) and state["checked"].get(cid, 0) <= now - 10800),
                 key=lambda cid: (state["checked"].get(cid, 0), cid))
    # Decide hot reservations first; weekly selection cannot duplicate them.
    for cid in hot[:min(2, max(0, limit - 1))]:
        add(cid, "hot")
    due = sorted((cid for cid in members if state["checked"].get(cid, 0) < cycle["starts"]),
                 key=lambda cid: (state["attempts"].get(cid, 0), ranks[cid]))
    # One due priority retry gets an early slot; other failures cannot crowd out
    # previously unattempted members. The retry is still a weekly-priority slot.
    priority_retry = next((cid for cid, at in sorted(state["retries"].items(), key=lambda item: (item[1], item[0]))
                           if cid in due and at <= now and available(cid)), None)
    if priority_retry and len(selected) < min(len(hot[:2]) + 5, limit - 1):
        add(priority_retry, "priority")
    for cid in (cid for cid in due if available(cid)):
        if len(selected) >= min(len(hot[:2]) + 5, limit - 1): break
        add(cid, "priority")
    cursor = state["cursor"]
    def catalog():
        nonlocal cursor
        query = eligible_cards().where(Card.id.not_in(members), Card.id.not_in(ids)).order_by(Card.id)
        # Cooldown failures live in the retry lane; they never hold the cursor.
        cooling = [cid for cid, retry in state["retries"].items() if retry > now]
        if cooling: query = query.where(Card.id.not_in(cooling))
        cid = session.scalar(query.where(Card.id > cursor).limit(1))
        wrapped = False
        if cid is None and cursor:
            cid = session.scalar(query.limit(1)); wrapped = cid is not None
        if cid is not None:
            cursor = cid; add(cid, "catalog", wrapped)
        return cid is not None
    catalog_retry = next((cid for cid, at in sorted(state["retries"].items(), key=lambda item: (item[1], item[0]))
                          if cid not in members and at <= now and available(cid)), None)
    if len(selected) < limit:
        # Alternate failed catalog work with cursor advancement. Even a permanent
        # provider failure cannot monopolize the daily catalog lane.
        if catalog_retry and state.get("catalog_turn", 0) % 2:
            add(catalog_retry, "catalog_retry")
        else:
            catalog()
    # Unused slots go to weekly coverage, then bounded retry/catalog progress.
    for cid in due:
        if len(selected) >= limit: break
        if available(cid): add(cid, "priority")
    for cid, retry_at in sorted(state["retries"].items(), key=lambda item: (item[1], item[0])):
        if len(selected) >= limit: break
        if retry_at <= now and available(cid):
            add(cid, "retry"); break
    while len(selected) < limit and catalog():
        pass
    return selected


def reserve_attempt(state, cid, lane, wrapped, now):
    state["total_attempts"] += 1
    state["attempts"][cid] = now
    state["retries"][cid] = now + RETRY_DELAY
    if len(state["retries"]) > MAX_RETRIES:
        # Keep oldest due failures; report that the newest retry could not fit.
        victim = max(state["retries"], key=lambda key: (state["retries"][key], key))
        del state["retries"][victim]
        state["retry_overflow"] += 1
    if lane in ("catalog", "catalog_retry"):
        state["catalog_turn"] = state.get("catalog_turn", 0) + 1
    if lane == "catalog":
        state["cursor"] = cid
        state["catalog_advances"] += 1
        state["wraps"] += int(wrapped)


def quota_usage(redis, provider, now):
    settings = get_settings()
    day = int(now // 86400)
    global_used, scheduled_used = redis.mget([f"cardboarddex:{provider}:requests:{day}",
                                             f"cardboarddex:{provider}:scheduled_requests:{day}"])
    return {"global_used": int(global_used or 0), "global_limit": getattr(settings, f"{provider}_daily_request_limit"),
            "scheduled_used": int(scheduled_used or 0), "scheduled_limit": getattr(settings, f"{provider}_scheduled_request_limit")}


def exhausted(usage):
    return usage["global_used"] >= usage["global_limit"] or usage["scheduled_used"] >= usage["scheduled_limit"]


def coverage_report(redis=None, now=None):
    redis = redis if redis is not None else get_durable_redis()
    now = time.time() if now is None else now
    cycle, states = load_state(redis)
    report = {"generated_at": now, "cycle": cycle, "providers": {}}
    if cycle:
        report["cycle"] = {key: value for key, value in cycle.items() if key != "members"}
        report["cycle"]["size"] = len(cycle["members"])
    for provider, state in states.items():
        checked = sum(state["checked"].get(cid, 0) >= cycle["starts"] for cid in cycle["members"]) if cycle else 0
        remaining = len(cycle["members"]) - checked if cycle else 0
        overdue = sum((state["checked"].get(cid, 0) < now - WEEK if cid in state["checked"] else now >= cycle["ends"])
                      for cid in cycle["members"]) if cycle else 0
        report["providers"][provider] = {**{k: v for k, v in state.items() if k not in ("checked", "attempts", "retries")},
            "checked_this_cycle": checked, "remaining": remaining, "overdue": overdue,
            "retry_count": len(state["retries"]), "retries_due": sum(t <= now for t in state["retries"].values()),
            "quota": quota_usage(redis, provider, now)}
    return report


def run_scheduled_collection(session, provider, collect, *, now=None):
    settings = get_settings()
    if provider not in PROVIDERS: raise ValueError("Unsupported pricing provider")
    if not settings.passive_refresh_enabled: return {"skipped": "disabled"}
    redis = get_durable_redis()
    token = uuid4().hex
    acquired = False
    try:
        acquired = bool(redis.set(LOCK, token, nx=True, ex=900))
        if not acquired: return {"skipped": "busy"}
        clock = time.time if now is None else lambda: now
        started = clock()
        usage = quota_usage(redis, provider, started)
        if exhausted(usage): return {"skipped": "daily_limit"}
        popularity = interest_scores(started)
        cycle, states = ensure_cycle(session, redis, token, started, popularity)
        state = states[provider]
        state["last_run"] = started
        state["attempts"] = {cid: at for cid, at in state["attempts"].items() if cid in cycle["members"]}
        selected = select_batch(session, cycle, state, popularity, started, settings.price_collection_card_limit)
        totals = {"cards": 0, "successful_checks": 0, "provider_errors": 0}
        with scheduled_budget(provider, usage["scheduled_limit"], LOCK, token):
            for cid, lane, wrapped in selected:
                if exhausted(quota_usage(redis, provider, clock())): break
                reserve_attempt(state, cid, lane, wrapped, clock())
                save_state(redis, token, {f"{STATE}:{provider}": state})
                # One card per collector call makes committed empty responses distinguishable
                # from partial batch failures without changing observation semantics.
                result = collect(session, card_ids=[cid])
                for key, value in result.items():
                    if isinstance(value, int): totals[key] = totals.get(key, 0) + value
                if result.get("cards") == 1 and result.get("provider_errors") == 0:
                    if cid in cycle["members"]: state["checked"][cid] = clock()
                    state["retries"].pop(cid, None)
                    state["total_checked"] += 1
                    state["last_success"] = clock()
                    totals["successful_checks"] += 1
                # Attempts only need per-card retention for the frozen priority pool.
                if cid not in cycle["members"]: state["attempts"].pop(cid, None)
                save_state(redis, token, {f"{STATE}:{provider}": state})
        save_state(redis, token, {f"{STATE}:{provider}": state})
        logger.info("passive_refresh %s", json.dumps({"provider": provider, "result": totals,
                    "coverage": coverage_report(redis, clock())}, sort_keys=True))
        return totals
    except (RedisError, LeaseExpired) as exc:
        logger.error("Passive refresh stopped provider=%s error=%s: %s", provider, type(exc).__name__, exc)
        return {"skipped": "redis_unavailable" if isinstance(exc, RedisError) else "lease_expired"}
    except Exception as exc:
        logger.exception("Passive collector interrupted provider=%s error=%s: %s", provider, type(exc).__name__, exc)
        raise
    finally:
        if acquired:
            try: redis.eval(RELEASE, 1, LOCK, token)
            except RedisError as exc:
                logger.error("Passive lease release failed error=%s: %s", type(exc).__name__, exc)
