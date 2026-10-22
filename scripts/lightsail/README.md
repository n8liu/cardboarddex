These scripts operate on production only when explicitly invoked with production configuration.

- For the capacity upgrade, use `provision.py --instance-only --apply` to reuse existing backup infrastructure. The initial October 13 restriction was lifted; `cardboarddex-1gb` is now production and `cardboarddex-recovered` is retained with application services stopped. Do not rerun provisioning for the completed migration.
- `provision.py`: preview AWS resources; `--apply` provisions the $7/month dual-stack 1 GB replacement `cardboarddex-1gb` and private backup bucket. It does not cut over production or delete the source. Secrets are written under ignored `.system_generated/lightsail/`, mode 0600, never printed. See `docs/lightsail-migration.md` for the active release, retained source, and rollback requirements.
- `bootstrap.sh`: root-only setup on a clean Ubuntu 24.04 AMD64 instance.
- `wait_for_ssm.sh`: fail deployment before SSH if the managed node stays offline; AWS API errors remain visible.
- `provision.py` waits up to 60 readiness polls (10 seconds apart) after accepted creation, verifies operation success and actual dual-stack 1 GB/40 GB hardware before reporting readiness or configuring backup resources. A timeout leaves the destination intact for inspection; never delete the source to retry.
- `ipv6_preflight.py --relay-url https://<relay-origin> [--url https://<image-origin/path>]`: run on the replacement host and inside its backend container. Forces IPv6, bypasses proxies, verifies TLS across HTTPS redirects, and reports transport separately from application success. Pass public URLs only. It sends no credentials and does not replace authenticated provider, registry-pull, S3 upload/restore, or Tunnel checks.
- `install_zram.sh` / `zram.sh`: install persistent compressed swap on the 512 MB host without replacing its disk swap.
- `release.sh`: server-side deployment, used by `../deploy_to_lightsail.sh`; never migrates schemas. Waits up to 120 seconds for the exclusive deployment lock because the Live Comps maintenance timer also uses it in shared mode. On timeout, no services are changed. Inspect `sudo lslocks -o PID,COMMAND,MODE,PATH` and `systemctl status cardboarddex-live-stats.service` to identify contention; do not unlink an active lock file. The script explicitly unlocks on success, setup failure, and rollback.
- `monitor_ingestion.py`: minute-by-minute production health/coverage sampling and automatic ingestion pause on regressions; installed with `deploy/lightsail/cardboarddex-ingestion-monitor.{service,timer}`. Review `/var/lib/cardboarddex/ingestion-monitor/latest.json` and its system journal. It never resumes ingestion automatically. It pauses on memory below 150 MB or swap-in above 1 MiB/s for five minutes, or on iowait above 25% for fifteen minutes. It runs from `/opt/cardboarddex/operations/`, so a release does not update it: reinstall with `sudo install -m 0755 <release>/scripts/lightsail/monitor_ingestion.py /opt/cardboarddex/operations/scripts/lightsail/monitor_ingestion.py`.
- `backup.py`: root systemd backup, `/etc/cardboarddex/backup.env` and `/etc/cardboarddex/app.env`.
- `restore.sh`: refuses existing tables; `RESTORE_CONTAINER` must explicitly name an empty destination.
- `verify_backup.py`: freshness validation; `--restore` verifies downloaded archives on a disposable Docker container.
- `ecr_cleanup.py`: preview unless `--apply`; supply both running and rollback digests using repeated `--protect`.

Never use `docker compose down -v`. The database volume is external and explicitly named. SSH host keys must be verified independently; do not replace verification with `ssh-keyscan` alone.

## Live Comps totals during ingestion pauses

`refresh_live_stats.sh` runs only the stored-data totals job in a separate container
using the current release's worker memory limits. Do not seed using `docker exec`
inside the API: the extra Python process caused an API OOM on October 18.
The script takes a shared deployment lock and skips a refresh during deployment.
Install the script and units on the host from a reviewed copy of these files:

```bash
sudo install -m 755 scripts/lightsail/refresh_live_stats.sh /usr/local/sbin/cardboarddex-refresh-live-stats
sudo install -m 644 scripts/lightsail/cardboarddex-live-stats.service /etc/systemd/system/
sudo install -m 644 scripts/lightsail/cardboarddex-live-stats.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cardboarddex-live-stats.timer
sudo systemctl start cardboarddex-live-stats.service
```

The service runs only while `/opt/cardboarddex/ingestion.paused` exists; normal
Celery scheduling owns refreshes after ingestion resumes. It also publishes the
default Trending snapshot that `/cards/trending` serves; reinstall the script and
units after upgrading from a copy that refreshed only Live Comps totals. Its start
timeout stays below the release script's 120-second lock wait. Neither the service nor
the script starts provider ingestion. Inspect `journalctl -u cardboarddex-live-stats.service`
and the public stats endpoint to verify advancing `generated_at` timestamps.
The timer follows `/opt/cardboarddex/current`; disable it before rolling back to
a release without `jobs.refresh_live_stats`. Disable with
`sudo systemctl disable --now cardboarddex-live-stats.timer` and stop any active
refresh with `sudo systemctl stop cardboarddex-live-stats.service`.
These units are installed separately; existing release/bootstrap scripts do not
install them automatically on replacement hosts.

## Delete-first recovery (explicitly authorized maintenance only)

`delete_first_migration.py` handles the AWS deletion/restore phase, not host quiescing
or application readiness. Its default is preview. Before calling it, stop writers,
create a final backup, verify both archives using `verify_backup.py --restore
--manifest-key <exact-key> --report <private-receipt.json>`, stop the data services,
mask Docker startup, stop the instance, and create an available manual snapshot.
Prepare reviewed launch data that keeps Docker masked and registers a fresh SSM
identity; activation credentials belong only in a private ignored file.

Supply `--state <private-checkpoint.json> --snapshot <manual-snapshot-name>
--receipt <private-receipt.json> --bootstrap <private-bootstrap.sh>` to preview.
Add `--apply` only for the authorized deletion. The guard requires the exact
stopped source ARN, 20 GB snapshot created after restore verification, expected
backup bucket, and PostgreSQL/Redis restore receipt less than two hours old.
It retains the snapshot and records intent before each AWS mutation.

If creation explicitly rejects the target, repeat with `--apply --fallback` to
restore `cardboarddex-recovered` on the original dual-stack `nano_3_0` bundle.
Ambiguous API errors, interrupted deletion, or a partially created target stop
automation: inspect operation IDs and inventory before advancing the checkpoint.
Never repeat a create request blindly. This command does not automatically delete
a failed replacement, switch traffic, or restore stale data after production writes.
After restoration, verify hardware, fresh SSM and SSH identity, data counts, local
readiness, dependencies, and public endpoints before declaring recovery complete.

Use `bash scripts/lightsail/recover_services.sh /opt/cardboarddex/current` after
unmasking/enabling Docker to recover infrastructure/API. Add `--traffic` only when
ready to reopen public access. This exports the exact release `image.txt` digest,
overriding potentially stale `BACKEND_IMAGE` in the protected env file, verifies
the running image and readiness, and starts no ingestion services. Do not run a
plain Compose recovery using the env file alone: it selected an obsolete image
without `/ready` during the October 8 recovery. Lightsail launch data must explicitly
invoke Bash because Lightsail prepends an `sh` initialization script; the migration
command now wraps launch data accordingly.

`verify_backup.py --restore` now restores Redis in an isolated networkless
container as well as PostgreSQL. Expired Redis keys may disappear on load; the
report contains counts only, never keys or values. All restore receipts are
non-secret operator evidence, not cryptographically signed attestations.
