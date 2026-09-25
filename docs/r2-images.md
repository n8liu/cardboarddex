# R2 card images: setup, backfill, and cutover

Implementation is disabled by default. This feature does not alter Cards/Sets, restart ingestion, change the AWS backup destination, or purchase a server upgrade. Do not declare production fixed until CDN delivery and the observation window pass.

## 1. Configure Cloudflare

Use R2 Standard. Create dedicated buckets `cardboarddex-images` and `cardboarddex-images-state`. The second bucket is private synchronization state: never attach a domain or enable its r2.dev URL. The first contains only public image objects and a placeholder.

The provisioning helper previews without credentials:

```sh
backend/.venv/bin/python scripts/images/provision.py
```

To apply, supply `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ZONE_ID`, and `CLOUDFLARE_API_TOKEN` through a protected local environment. The token needs account R2 storage editing, zone read, and zone cache-rules editing permissions for the relevant account and `cardboarddex.app` zone. Never paste tokens into issues or commit environment files.

```sh
backend/.venv/bin/python scripts/images/provision.py --apply
```

The helper validates zone ownership, creates missing Standard buckets, disables r2.dev, attaches `images.cardboarddex.app`, and appends/updates only its own cache rule. Existing unrelated zone rules are preserved. It does not activate paid transformations or Workers. Confirm the domain/TLS becomes active. If a conflicting DNS record exists, investigate it before changing ownership; the helper must not delete it.

Rule: eligible for cache only on `images.cardboarddex.app` under `/cards/` or `/placeholder.svg`; respect origin cache headers; HTTP 400–599 use no-store. Successful versioned objects use one-year immutable caching. Do not apply this rule to the API hostname.

References: [R2 public domains](https://developers.cloudflare.com/r2/buckets/public-buckets/), [cache settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/), [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

## 2. Configure GitHub

Create an R2 Object Read & Write credential restricted to the two image buckets. Keep these credentials separate from AWS backup credentials. Configure repository secrets `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`, and variable `R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`. The workflow also accepts `R2_ENDPOINT_URL` as a repository secret; the variable takes precedence if both exist.

The workflow reuses existing `LIGHTSAIL_HOST`, `LIGHTSAIL_SSM_TARGET`, `LIGHTSAIL_SSH_KEY`, `LIGHTSAIL_KNOWN_HOSTS`, and AWS deployment OIDC role. It runs only trusted main-branch code. Set `R2_IMAGE_SYNC_SCHEDULE_ENABLED=false` initially (unset is also disabled). No R2 write key is installed on Lightsail.

Deploy the backend with the new export job and read-only directory mount before running sync. Leave `IMAGE_CDN_ENABLED=false`. The release script creates `/opt/cardboarddex/images`; Compose mounts the directory, not the individual manifest file, so atomic replacements are visible.

## 3. Pilot and backfill

Dispatch **R2 card image synchronization** with `limit=100`, `refresh=false`. Review the summary: uploaded, skipped, failed, deferred, bytes, inventory size, and elapsed seconds. Estimate total storage from successful pilot image sizes and total inventory. Review the GitHub run's billable runner usage as well.

The runner reads a streamed ID/source-URL export over verified SSH. Provider downloads and uploads happen on the runner with two pooled connections, not on Lightsail. A run attempts at most 500 cards. Every completed two-image transfer group checkpoints private state. Rerunning skips successful unchanged images. A failed image waits 24 hours before automatic retry, allowing later cards to progress. It keeps its older verified version, if available; otherwise visitors see the placeholder after cutover.

Repeat dispatches with `limit=500` until the inventory is covered except documented provider failures. Each run publishes a validated manifest atomically and preserves `manifest.previous.json`. Do not loop dispatches automatically without checking budget and error rate. `refresh=true` retries existing images in inventory order, so use a filtered local inventory for selective refresh beyond the first batch.

The job refuses private/unapproved redirect destinations, non-images, and downloads larger than 10 MiB. Changed bytes get a new SHA-256 URL; existing objects are not deleted. The job conservatively pauses further transfers near 8 GB of public-bucket usage. This is not an account-wide billing cap: include other R2 buckets, operation usage, and GitHub minutes in budget checks. Configure available Cloudflare usage/billing notifications in the account dashboard; monitor against the Standard allowances (10 GB-month, 1M Class A, 10M Class B). No guarantee of zero cost is implied.

## 4. Enable and verify

After frontend/backend deployment and manifest checks, set `IMAGE_CDN_ENABLED=true` in the protected production environment and recreate only the backend through the reviewed release process. Keep `/opt/cardboarddex/ingestion.paused` in place. The base URL defaults to `https://images.cardboarddex.app`; the manifest path in the container is `/var/lib/cardboarddex/images/manifest.json`.

The API refreshes its local manifest at most once per minute. Image-bearing caches include manifest generation. Normal API responses return direct CDN URLs; old `/cards/{id}/image` links issue a short-lived redirect without querying the database or storage. Missing images return the shared CDN placeholder. Frontend image errors fall back to `/image-pending.svg`, never to an API download.

```sh
backend/.venv/bin/python scripts/images/verify.py
```

This opt-in check requires the initial 24-card catalog to have real CDN images, checks concurrent image/API responses within 15-second request timeouts, repeated CDN HITs and correct headers, and no cached missing-image response. Also inspect browser Network: migrated cards must use direct `images.cardboarddex.app` requests, not `/_next/image` or API image downloads. Check catalog, Live Comps, dashboards, detail pages, sets, and existing binder entries.

After acceptance, set `R2_IMAGE_SYNC_SCHEDULE_ENABLED=true` for daily 09:40 UTC synchronization. Record CPU utilization, burst-credit trend, swapping, API latency, image origin requests, R2 operations/storage, and runner minutes over 24 hours including a scheduled backup. Image offloading alone is not authorization to restart ingestion.

## 5. Recovery

A bad replacement manifest is rejected and the running API retains its last valid manifest. With CDN mode enabled and no valid manifest, images become placeholders instead of triggering provider calls.

To roll back manifest data, acquire `/opt/cardboarddex/deploy.lock`, copy `manifest.previous.json` to a temporary file in the same directory, validate with `publish_image_manifest.py`, then publish atomically. Keep CDN mode enabled. Retain historical R2 objects until the observation window and rollback needs are satisfied; no automatic deletion is included.

Publish source changes only after the commit/push approval required by PROJECT_CONTEXT.md. Never rerun a deployment from an older revision that lacks the existing production recovery fixes.
