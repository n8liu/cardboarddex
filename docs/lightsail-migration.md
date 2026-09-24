# Lightsail production operations

The original production design used the $5 `nano_3_0` (512 MB RAM) bundle in `us-west-2`, Cloudflare Tunnel, PostgreSQL 16, a single Celery worker, one Beat scheduler, and separate durable/cache Redis services. The frontend stays on Cloudflare Pages. The target is strictly $5/month for the server base; domain renewal and third-party APIs are separate, and backup/image storage, temporary recovery snapshots, and management usage are separate.

## Production recovery on 2026-09-23/24

The active host remains `cardboarddex-ipv6`, now on the $5/month `nano_3_0` dual-stack bundle. Its IPv4 address is dynamic; query Lightsail before direct access. GitHub deploys over SSM target `mi-04eda276674cf91be`. The old `mi-07cf7e6e80daf232f` registration is stale. Recovery used temporary Lightsail SSH access certificates with independently verified host keys; no new persistent SSH key was installed.

The outage exhausted memory and CPU burst capacity, leaving SSM offline and backups timing out. Dashboard queries now aggregate history in SQL and load only the required latest observations. PostgreSQL shared buffers are 16 MB, steady-state health probes run every minute, and the API probe uses curl. On hosts with at most 600,000 kB usable RAM, bootstrap and deployment install `cardboarddex-zram.service`: a 512 MB LZ4 compressed swap device at priority 100 before Docker starts. Existing disk swap is retained. Inspect `zramctl`, `free -m`, and `vmstat`; compressed swap does not increase CPU capacity or guarantee sufficient memory for every workload.

See `PROJECT_CONTEXT.md` for the active recovery image, checks, backup status, and source-publication status. Preserve the recovery snapshot and database volumes. Do not redeploy an older commit that lacks the query and runtime fixes.

## IPv6 migration on 2026-09-18 — historical record

The owner explicitly authorized deleting the old instance before replacement because AWS enforces a one-instance account limit. The stopped source was saved as `cardboarddex-pre-ipv6-20260918`; AWS confirmed the snapshot available before deletion. An additional S3 database backup restored successfully off-server with 54,726 cards, 489 sets, and revision `0004_price_obs_search_index`.

After deletion, AWS rejected the requested $5/month `micro_ipv6_3_0` (1 GB RAM, 40 GB disk) with: "your account can only create an instance using the smallest Lightsail plan size (nano)." The snapshot was therefore restored onto `cardboarddex-ipv6`, using the permitted `nano_ipv6_3_0` ($3.50/month, 512 MB RAM, 20 GB disk). The 1 GB upgrade still requires AWS Support to lift the restriction. IPv6 alone does not resolve the original memory/CPU exhaustion.

Management and GitHub deployment use pinned-key SSH over AWS Systems Manager; a direct IPv6 route is not required on the workstation or runner. Set `LIGHTSAIL_SSM_TARGET` to the verified managed-node ID. SSH connection multiplexing shares one SSM session per deployment. The host uses dual-stack S3/ECR service endpoints, `DOCKER_ENABLE_IPV6=true`, and `TUNNEL_EDGE_IP_VERSION=6`.

The owner approved the authenticated Worker in `deploy/ebay-relay/` to forward eBay OAuth and Browse search requests. eBay's API has no AAAA records. Configure its HTTPS origin and shared secret only in the protected server environment; the Worker restricts methods, paths, destination, and forwarded headers. Cloudflare processes those credentials and API responses.

Keep the recovery snapshot until the restored data, public API, ingestion, and a fresh off-server backup have been verified. Production checks and management bootstrap are still in progress; this document does not yet assert a completed cutover.

## Files and configuration

`docker-compose.prod.yml` is the production definition. Always use Compose project `app` and explicitly set `DATA_VOLUME` to the existing PostgreSQL volume. Never run `down -v`. Production secrets live in `/etc/cardboarddex/app.env`, readable by the deployment user only, and backup credentials in root-only `/etc/cardboarddex/backup.env`. Copy the environment example in `deploy/lightsail/`; do not print resolved configuration. New database passwords are generated randomly, not copied from old source defaults.

Image references are immutable digests. Builds target `linux/amd64`; do not deploy native Apple Silicon images. `BACKEND_IMAGE` identifies the release. `POSTGRES_IMAGE`, `REDIS_IMAGE`, and `CLOUDFLARED_IMAGE` identify reviewed infrastructure images. Set a real `ADMIN_API_KEY`. Preserve existing CORS, quota, provider, and image-storage settings.

`REDIS_URL` is durable broker/quota/checkpoint storage (64 MB, no eviction, AOF every second). `CACHE_REDIS_URL` is disposable response/analytics storage (32 MB, LRU). The latter falls back to `REDIS_URL` in local development. Quota writes fail closed. Never restore old quota counters and immediately resume ingestion after a disaster: pause providers until counters are validated, or mark the current UTC day's allowance exhausted until reset.

API pools allow 3 connections plus 2 overflow; worker pools allow 2 with zero overflow. PostgreSQL allows 25 connections. No table schema changes are part of this work. Deployments check Alembic heads without applying migrations.

## Deployment and rollback

CI builds and tests the image, publishes a commit tag, resolves its digest, and uploads the matching Compose/scripts to `/opt/cardboarddex/releases/<commit>`. Local deployment uses `scripts/deploy_to_lightsail.sh` and requires `LIGHTSAIL_HOST`, `KEY_PATH`, `KNOWN_HOSTS_FILE`, `BACKEND_IMAGE`, and `RELEASE_ID`. It never builds or publishes `latest`.

GitHub settings: repository variables `LIGHTSAIL_HOST` (verified SSH host alias/address) and `LIGHTSAIL_SSM_TARGET` (SSM managed-node ID), secret `LIGHTSAIL_SSH_KEY`, secret `LIGHTSAIL_KNOWN_HOSTS` (verified host keys), and variable `BACKUP_BUCKET`. The backup workflow assumes the dedicated `github-actions-cardboarddex-backup-read` OIDC role. Both production workflows only trust the main branch. Do not use `StrictHostKeyChecking=no` or trust a network key scan without an independent fingerprint.

A server lock and GitHub concurrency serialize deployment. Images pull before services stop. Beat stops first; the worker drains with a 3,600-second grace period. Readiness checks PostgreSQL and both Redis services. Worker ping, exactly one Beat container, running image identity, catalog search, images, and CORS must pass. The previous image/configuration is retained. Schema migrations must be reviewed separately; rollback never downgrades the database automatically.

`/health` remains a compatible liveness check. `/ready` returns 200 only when PostgreSQL and both Redis services respond, otherwise 503. A healthy HTTP response does not prove ingestion works; inspect the worker and new observations separately.

To roll back an application release on the same host, run `release.sh` with the previous release directory; database and Redis volumes stay in place. For a host migration, stop new writes and transfer the current data back before switching to the old host. Restarting an old database copy after new writes would lose data.

## Backups and recovery

The root systemd timer runs at 00:20, 06:20, 12:20, and 18:20 UTC. It uploads a PostgreSQL custom-format archive and Redis RDB snapshot, then a manifest only after S3 verifies checksums. Failures leave a `.pending-*` local directory for diagnosis, never a success marker. Check `systemctl status cardboarddex-backup.service` and `journalctl -u cardboarddex-backup.service`.

Six-hourly backups expire after seven days; weekly Sunday copies after 28 days. Successful local copies expire after 24 hours. The S3 bucket blocks public access, requires TLS, and encrypts objects. The uploader can only PutObject under the designated prefixes; restore access is separate. Rotate its access key periodically, verify an upload using the replacement, then revoke the prior key. Old local cron backup jobs must be removed only after the first successful S3 upload.

Run `python scripts/lightsail/verify_backup.py --bucket <bucket> --restore` on a CI runner or workstation with recovery credentials and Docker. This checks freshness, downloads and validates both checksums, restores PostgreSQL into an isolated container, and verifies its revision. The weekly workflow performs this drill; hourly checks report backups older than six hours through GitHub workflow failures. Six hours is the recovery target, not a guarantee during failed backups or delayed GitHub schedules.

For recovery, start an empty PostgreSQL 16 container and run `RESTORE_CONTAINER=<name> bash scripts/lightsail/restore.sh <archive>`. Nonempty databases are rejected. The restore is transactional and stops on errors. Verify application data and schema revision before attaching the Tunnel. Restore Redis separately into an empty durable volume and enable AOF. Its snapshot is taken after the PostgreSQL snapshot, so validate quota timestamps and clear ingestion cursors that could skip data missing from the PostgreSQL restore before starting ingestion. Do not blindly resume restored queued work or cursors.

## Provisioning and safe host cutover

`python scripts/lightsail/provision.py` previews resources. `--apply` creates the $5 `micro_ipv6_3_0` replacement with IPv6-only networking, private backup bucket, upload-only identity, and read-only GitHub OIDC role. It refuses unexpected AWS accounts and stores secrets under ignored `.system_generated/lightsail/`. It does not allocate a public IPv4 address, delete or stop existing resources, or cut over production.

Before cutover, successfully restore a backup obtained from S3. Bootstrap the clean Ubuntu 24.04 host with `bootstrap.sh`, establish management access, verify its host key via AWS, and install the reviewed release and secrets. Create the explicitly named empty PostgreSQL volume. Keep the replacement worker, Beat, and Tunnel stopped.

During maintenance, stop old Beat/worker, drain jobs, stop API writes, take final PostgreSQL/Redis copies, and compare source/destination table counts and Alembic revision. Rotate the database credential, validate the replacement locally, then stop the old Tunnel before starting the new Tunnel and scheduler. Exactly one host may run ingestion.

Normally keep the old host stopped for 48 hours after successful cutover (it remains billable). The owner explicitly waived that host rollback window for the 2026-09-18 replacement; its recovery snapshot is retained instead. Validate a nightly sync, price jobs, backups, reboot recovery, and resource usage before deleting it. The final RDS snapshot was retired on 2026-09-17 after off-server backups in S3 were confirmed, eliminating ongoing storage charges.

On 2026-09-16, AWS rejected a second instance with an account limit of one despite inconsistent Service Quotas responses. Do not delete the only working server to bypass this condition. Retry provisioning only after AWS lifts the limit or the owner explicitly chooses a replacement outage without the host rollback window.

## Cost and capacity checks

Run `audit_costs.py` for read-only cross-region legacy-resource inventory and month-to-date billing. Migration-month spend includes retired infrastructure and temporary overlap; it is not a steady-state projection. Measure S3 backup/image storage, ECR, and snapshots separately. No load balancer or NAT gateway is required.

Run `ecr_cleanup.py --protect <running-digest> --protect <rollback-digest>` to preview cleanup. Add `--apply` only after verifying the protected digests. It also protects the three newest tagged releases and referenced manifests. Avoid broad tagged-image lifecycle rules that can delete a deployed release after several failed builds. The replacement ECR lifecycle policy in `deploy/lightsail/ecr-lifecycle.json` expires only unreferenced untagged images after seven days; apply it after verifying protected production/rollback digests, then use the explicit cleanup script for tagged releases. Keep 14-day retention on legacy logs; current observed log storage is negligible.

Watch available memory, swap-in, disk usage, API latency, and worker freshness through a full workload cycle. Investigate sustained swap-in above 1 MB/s or I/O wait above 10% for five minutes. Do not automatically buy a larger plan if those thresholds persist. Logs rotate at 10 MB × 3 files per container. Reducing job frequency does not lower a fixed VPS charge.

SSM hybrid-node registration has no per-node fee. AWS lists Session Manager at $0.05/session starting September 30, 2026 (free during the transition through that date); Run Command is $0.002/invocation. See https://aws.amazon.com/systems-manager/pricing/. These usage charges are separate from the instance base price.
