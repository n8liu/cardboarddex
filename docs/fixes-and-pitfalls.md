# Fixes and pitfalls

Production incidents, what actually caused them, and mistakes to avoid. Newest first.
Each entry: **Symptom → Cause → Fix → Avoid.**

---

## 2026-10-23: Catalog, sealed and grading-profit return 503

**Symptom.** `/cards/search`, `/cards/sealed-signals` and `/cards/grading-profit` returned 503
("Results temporarily unavailable"). The shared response cache returns this when a rebuild
misses its 5s SQL deadline, then holds off for 30s.

**Cause.** Background snapshot jobs ran whole-table queries every minute on the same small
Postgres (16 MB `shared_buffers`) that serves public reads. Worker time measured over one hour:

| Task | Per hour | Notes |
|---|---|---|
| `refresh_trending` | 523s (8.7s × 60) | Snapshot is servable for 30 minutes |
| `refresh_live_stats` | 267s, max 5.5s | `QueryCanceled` every minute at the 5s deadline |
| `ppt_report` | 214s, max 8.3s | Diagnostics only |
| `sync_ppt` | 186 of 240 runs | Runs queued behind the three jobs above (all at the same second) expired after 14s and were discarded |

**Fix (local until deployed).**
- `celery_app.py`: Trending runs every 5 minutes (`crontab(minute="1-59/5")`, expires 240s), and
  the PPT report every 15 minutes (`3,18,33,48`, expires 600s). Neither shares a minute with eBay
  (`:15/:45`). The health key TTL is now 1,800s (`HEALTH_SECONDS`).
- Live stats counts legacy totals once a day (see the next entry).
- On the host, checked and not the cause: the `autovacuum_vacuum_insert_*` settings were already
  applied and autovacuum was current (4,035 inserts pending on 431k rows). A manual `VACUUM` does
  not help when the visibility map is already current; only reducing the work does.
- Deploy the catalog 503 fix (migration `0013`).

Expected result: background whole-table work drops from about 1,000s an hour to about 150s.

**Avoid.**
- Don't schedule heavy snapshot jobs every minute when the snapshot stays valid much longer.
- Don't give heavy jobs the same interval and start second on a single-process worker.
- Measure before tuning, using this one-liner on the host:
  ```sh
  sudo docker logs app-celery-worker-1 --since 1h 2>&1 \
   | grep -oE "Task jobs\.[a-z_.]+\[[^]]+\] succeeded in [0-9.]+s" \
   | sed -E 's/Task (jobs\.[a-z_.]+)\[[^]]+\] succeeded in ([0-9.]+)s/\1 \2/' \
   | awk '{n[$1]++; t[$1]+=$2; if($2>m[$1])m[$1]=$2} END{for(k in n) printf "%-45s runs=%4d total=%7.1fs max=%6.1fs\n",k,n[k],t[k],m[k]}'
  ```

---

## 2026-10-21/22: Live Comps (and Trending) stopped updating

**Symptom.** Live Comps stopped receiving new PPT rows after about 8,000 API calls. Later,
`/cards/trending` and the Live Comps totals returned 503.

**What it looked like vs. what it was.**

| Suspected | Actual |
|---|---|
| PPT daily credit cap (20,000 credits ≈ 8,000 requests at 2–3 credits each) | Contributing, but not the stop. On October 22 at 05:46 UTC Redis had **no** PPT counters for the day. |
| Lightsail failure | The host was healthy: 178–287 MB available, swap-in under 0.7 MiB/s, API ready, no OOM. |
| **Ingestion monitor pause** | **The cause.** At 01:55:03 UTC on October 21, `monitor_ingestion.py` logged "Memory/swap/I/O pressure persisted for five minutes" because iowait was 10.5–15% against a **10%** limit. It created `/opt/cardboarddex/ingestion.paused` and stopped worker and Beat (`Exited … 28 hours ago`). |

Trending and the Live Comps totals are snapshots that the worker publishes. With the worker
stopped, the snapshots passed 30 minutes old and the API returned 503 by design. The host
fallback (`cardboarddex-live-stats.timer`) was disabled.

**Confirmed after the fix (October 22):** Live Comps updates normally until it reaches the
20,000 credit cap.

### Fixes

1. **Monitor iowait rule** (`scripts/lightsail/monitor_ingestion.py`). Memory below 150 MB or
   swap-in above 1 MiB/s still pauses after 5 minutes. iowait now has its own rule: **above 25%
   for 15 minutes** (`iowait_since` in `latest.json`). Normal load on this host is 9–15% iowait.
2. **Live stats I/O** (`backend/app/services/live_stats.py`). Retired-provider (tcgapi, about
   347k rows) totals are counted once a day and cached (`cardboarddex:live_stats:legacy:v1`,
   24h, 15s statement timeout). Each minute it recounts only PPT (exact provider match) and
   matched eBay rows. Totals are unchanged; about 85% fewer rows are read per minute.
3. **PPT daily pacing** (`backend/app/providers/ppt.py`). Spending before 22:00 UTC is limited
   to the daytime cap × elapsed/22h + one hour of burst, so a 15-second Beat no longer spends
   the whole day by about 04:00 UTC. A blocked request yields `paced`; retry and ≥22:00 UTC
   are unpaced. Turn it off with `PPT_DAILY_PACING_ENABLED=false`.
4. **Visible yields** (`backend/jobs/sync_ppt.py`). `PPTBlocked` used to be swallowed silently.
   Now each run logs `PPT batch yielded reason=… lane=…` and returns `blocked`.

### Recovery steps that worked

```sh
# 1. Install the monitor first. A release does NOT update it.
T=/opt/cardboarddex/operations/scripts/lightsail/monitor_ingestion.py
sudo cp -p $T $T.bak-$(date -u +%Y%m%d)
sudo install -m 0755 /tmp/monitor_ingestion.py $T

# 2. Resume ingestion.
sudo rm /opt/cardboarddex/ingestion.paused
r=/opt/cardboarddex/current
BI=$(cat $r/image.txt)
sudo BACKEND_IMAGE="$BI" docker compose -p app --env-file /etc/cardboarddex/app.env \
  -f $r/docker-compose.prod.yml up -d --no-deps --pull never celery-worker celery-beat
sudo docker update --restart unless-stopped app-celery-worker-1 app-celery-beat-1
```

---

## Errors to avoid

### Diagnosis

- **Check for a pause before blaming quotas or the host.** Run these first:
  `ls -l /opt/cardboarddex/ingestion.paused`, then
  `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep celery`, then
  `sudo journalctl -u cardboarddex-ingestion-monitor | grep -i paused`.
- **`latest.json` stops updating once paused.** The monitor exits early while the marker
  exists, so a stale `at` timestamp in `latest.json` means it has been paused since then.
- **Read the PPT counters in the durable Redis** (`app-redis-1`, db 0), not `redis-cache`:
  ```sh
  D=$(( $(date -u +%s) / 86400 ))
  sudo docker exec app-redis-1 redis-cli GET cardboarddex:ppt:v1:credits:$D
  ```
  Empty counters mean no requests at all today (paused or stopped), not a used-up quota.
- **PPT limits count credits, not requests.** A card refresh with history and eBay costs 3,
  without eBay 2; a discovery card page costs 25. 20,000 credits ≈ 7,500–8,000 requests.
- **Trending or Live Comps totals returning 503 usually means the worker is down**, not that
  the API is broken. Public reads never rebuild those snapshots.

### Operations

- **Install the new monitor before resuming.** Otherwise the old rule can re-pause within
  minutes.
- **A release does not update the monitor.** It runs from
  `/opt/cardboarddex/operations/scripts/lightsail/` and must be reinstalled by hand.
- **Always export `BACKEND_IMAGE` from `$release/image.txt`** before `docker compose up`. The
  image in `app.env` is stale and fails with ECR "pull access denied".
- **Remove the pause marker before a release**, or `release.sh` stops worker and Beat and leaves
  them stopped (October 20).
- **Never run an extra Python process in the 160 MiB API container**; it caused an OOM. Use the
  worker-budget maintenance container.
- **Never clear `cardboarddex:ppt:v1:*` quota keys to "retry".** A lost response stays charged.
- **Production `psql` needs `SET statement_timeout = 0`** before `VACUUM` or diagnostic queries
  (the server default is 12s).
- **`price_observations` is insert-only.** Without
  `autovacuum_vacuum_insert_scale_factor = 0.02` its visibility map goes stale, and index-only
  scans turn into heap reads and iowait (October 20).

### Shell pitfalls seen during recovery

- **`$C` was never defined in a fresh SSH shell.** `$C exec -T …` then ran bash's built-in
  `exec` (`exec: -T: invalid option`). Use `sudo docker exec app-redis-1 …` or define the
  compose array first.
- **Pasting several commands onto one line** joins them (`…)for k in …`). Paste one command per
  line, or separate them with `;`.
- **zsh does not word-split `$VAR`.** Put SSH options in an array (`O=(-i key -o …)`,
  `ssh "${O[@]}"`).
- **Verify the SSH host key independently**, not with `ssh-keyscan` alone. Compare it against
  `aws lightsail get-instance-access-details --instance-name cardboarddex-1gb --protocol ssh`
  (ED25519 `SHA256:+ceLr7WSLOdOPLroYQJyUffnOT5iMtg/2jcMbw3dOtY`).

### Code

- **Don't swallow scheduler yields silently.** Log the reason (AGENTS.md rule 1).
- **Don't recount all-time history every minute.** Cache totals for data that no longer grows,
  and recount only what does.
- **Don't let a protective monitor pause on a metric that isn't dangerous on its own.** Tune
  thresholds to the host's measured normal load, and keep hard-failure signals (OOM, restarts,
  API probes) strict.
