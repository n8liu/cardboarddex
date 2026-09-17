# Lightsail production operations

The production design uses the $7 `micro_3_0` (1 GB RAM) bundle in `us-west-2`, Cloudflare Tunnel, PostgreSQL 16, a single Celery worker, one Beat scheduler, and separate durable/cache Redis services. The frontend stays on Cloudflare Pages. The target is under $10/month before tax, domain renewal, and API subscriptions; storage and traffic are variable.

## Files and configuration

`docker-compose.prod.yml` is the production definition. Always use Compose project `app` and explicitly set `DATA_VOLUME` to the existing PostgreSQL volume. Never run `down -v`. Production secrets live in `/etc/cardboarddex/app.env`, readable by the deployment user only, and backup credentials in root-only `/etc/cardboarddex/backup.env`. Copy the environment example in `deploy/lightsail/`; do not print resolved configuration. New database passwords are generated randomly, not copied from old source defaults.

Image references are immutable digests. Builds target `linux/amd64`; do not deploy native Apple Silicon images. `BACKEND_IMAGE` identifies the release. `POSTGRES_IMAGE`, `REDIS_IMAGE`, and `CLOUDFLARED_IMAGE` identify reviewed infrastructure images. Set a real `ADMIN_API_KEY`. Preserve existing CORS, quota, provider, and image-storage settings.

`REDIS_URL` is durable broker/quota/checkpoint storage (64 MB, no eviction, AOF every second). `CACHE_REDIS_URL` is disposable response/analytics storage (32 MB, LRU). The latter falls back to `REDIS_URL` in local development. Quota writes fail closed. Never restore old quota counters and immediately resume ingestion after a disaster: pause providers until counters are validated, or mark the current UTC day's allowance exhausted until reset.

API pools allow 3 connections plus 2 overflow; worker pools allow 2 with zero overflow. PostgreSQL allows 25 connections. No table schema changes are part of this work. Deployments check Alembic heads without applying migrations.

## Deployment and rollback

CI builds and tests the image, publishes a commit tag, resolves its digest, and uploads the matching Compose/scripts to `/opt/cardboarddex/releases/<commit>`. Local deployment uses `scripts/deploy_to_lightsail.sh` and requires `LIGHTSAIL_HOST`, `KEY_PATH`, `KNOWN_HOSTS_FILE`, `BACKEND_IMAGE`, and `RELEASE_ID`. It never builds or publishes `latest`.

GitHub settings: repository variable `LIGHTSAIL_HOST` (attached static IPv4), secret `LIGHTSAIL_SSH_KEY`, secret `LIGHTSAIL_KNOWN_HOSTS` (verified host keys), and variable `BACKUP_BUCKET`. The backup workflow assumes the dedicated `github-actions-cardboarddex-backup-read` OIDC role. Both production workflows only trust the main branch. Do not use `StrictHostKeyChecking=no` or trust a network key scan without an independent fingerprint.

A server lock and GitHub concurrency serialize deployment. Images pull before services stop. Beat stops first; the worker drains with a 3,600-second grace period. Readiness checks PostgreSQL and both Redis services. Worker ping, exactly one Beat container, running image identity, catalog search, images, and CORS must pass. The previous image/configuration is retained. Schema migrations must be reviewed separately; rollback never downgrades the database automatically.

`/health` remains a compatible liveness check. `/ready` returns 200 only when PostgreSQL and both Redis services respond, otherwise 503. A healthy HTTP response does not prove ingestion works; inspect the worker and new observations separately.

To roll back an application release on the same host, run `release.sh` with the previous release directory; database and Redis volumes stay in place. For a host migration, stop new writes and transfer the current data back before switching to the old host. Restarting an old database copy after new writes would lose data.

## Backups and recovery

The root systemd timer runs at 00:20, 06:20, 12:20, and 18:20 UTC. It uploads a PostgreSQL custom-format archive and Redis RDB snapshot, then a manifest only after S3 verifies checksums. Failures leave a `.pending-*` local directory for diagnosis, never a success marker. Check `systemctl status cardboarddex-backup.service` and `journalctl -u cardboarddex-backup.service`.

Six-hourly backups expire after seven days; weekly Sunday copies after 28 days. Successful local copies expire after 24 hours. The S3 bucket blocks public access, requires TLS, and encrypts objects. The uploader can only PutObject under the designated prefixes; restore access is separate. Rotate its access key periodically, verify an upload using the replacement, then revoke the prior key. Old local cron backup jobs must be removed only after the first successful S3 upload.

Run `python scripts/lightsail/verify_backup.py --bucket <bucket> --restore` on a CI runner or workstation with recovery credentials and Docker. This checks freshness, downloads and validates both checksums, restores PostgreSQL into an isolated container, and verifies its revision. The weekly workflow performs this drill; hourly checks report backups older than six hours through GitHub workflow failures. Six hours is the recovery target, not a guarantee during failed backups or delayed GitHub schedules.

For recovery, start an empty PostgreSQL 16 container and run `RESTORE_CONTAINER=<name> bash scripts/lightsail/restore.sh <archive>`. Nonempty databases are rejected. The restore is transactional and stops on errors. Verify application data and schema revision before attaching the Tunnel. Restore Redis separately into an empty durable volume and enable AOF. Its snapshot is taken after the PostgreSQL snapshot, so validate quota timestamps and clear ingestion cursors that could skip data missing from the PostgreSQL restore before starting ingestion. Do not blindly resume restored queued work or cursors.

## Provisioning and safe host cutover

`python scripts/lightsail/provision.py` previews resources. `--apply` creates the 1 GB replacement, private backup bucket, upload-only identity, and read-only GitHub OIDC role. It refuses unexpected AWS accounts and stores secrets under ignored `.system_generated/lightsail/`. It does not delete or stop existing resources.

Before cutover, successfully restore a backup obtained from S3. Bootstrap the clean Ubuntu 24.04 host with `bootstrap.sh`, attach a static IP, verify its host key via AWS, and install the reviewed release and secrets. Create the explicitly named empty PostgreSQL volume. Keep the replacement worker, Beat, and Tunnel stopped.

During maintenance, stop old Beat/worker, drain jobs, stop API writes, take final PostgreSQL/Redis copies, and compare source/destination table counts and Alembic revision. Rotate the database credential, validate the replacement locally, then stop the old Tunnel before starting the new Tunnel and scheduler. Exactly one host may run ingestion.

Keep the old host stopped for 48 hours after successful cutover (it remains billable). Validate a nightly sync, price jobs, backups, reboot recovery, and resource usage before deleting it. Keep the final RDS snapshot for at least seven days and until repeated off-server backups/restores succeed. Never delete it merely because a backup file exists.

On 2026-09-16, AWS rejected a second instance with an account limit of one despite inconsistent Service Quotas responses. Do not delete the only working server to bypass this condition. Retry provisioning only after AWS lifts the limit or the owner explicitly chooses a replacement outage without the host rollback window.

## Cost and capacity checks

Run `audit_costs.py` for read-only cross-region legacy-resource inventory and month-to-date billing. Migration-month spend includes retired infrastructure and temporary overlap; it is not a steady-state projection. Measure S3 backup/image storage, ECR, and snapshots separately. No load balancer or NAT gateway is required.

Run `ecr_cleanup.py --protect <running-digest> --protect <rollback-digest>` to preview cleanup. Add `--apply` only after verifying the protected digests. It also protects the three newest tagged releases and referenced manifests. Avoid broad tagged-image lifecycle rules that can delete a deployed release after several failed builds. The replacement ECR lifecycle policy in `deploy/lightsail/ecr-lifecycle.json` expires only unreferenced untagged images after seven days; apply it after verifying protected production/rollback digests, then use the explicit cleanup script for tagged releases. Keep 14-day retention on legacy logs; current observed log storage is negligible.

Watch available memory, swap-in, disk usage, API latency, and worker freshness through a full workload cycle. Investigate sustained swap-in above 1 MB/s or I/O wait above 10% for five minutes. Do not automatically buy a larger plan if those thresholds persist. Logs rotate at 10 MB × 3 files per container. Reducing job frequency does not lower a fixed VPS charge.
