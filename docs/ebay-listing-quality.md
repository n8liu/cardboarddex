# eBay listing quality

This feature matches product identity. It does not authenticate a physical card or turn an asking price into a completed sale. A copied authentic image can pass image matching.

## Behavior

- Strict title matching requires the card name, number and set. Printed denominators, structured item specifics, language, raw/graded status, variations and auction offers can disqualify a candidate. Unknown condition/finish never silently becomes Near Mint or a known finish.
- Raw singles require text and image matches. Graded and sealed products require strict text matching only in v1. A missing rarity does not make a product sealed.
- Original observations and raw listing payloads remain stored. Assessments are keyed by target catalog metadata, listing identity content and matcher version. Price-only changes reuse checks; changed titles/images invalidate previous matches. Ingestion queues a new image check after seven days, and reference-feature caches rotate daily. New observations include the assessment fingerprint, including when identity changes without a price change.
- The shared SQL rule runs before aggregates, ranking and pagination. It covers card pricing, Live Comps and shared homepage counts, grading comparisons, Trending and Pokémon observation-volume aggregates. TCGAPI remains independent.
- Card summaries use a seven-day window, USD, one latest observation per listing and the selected printing/condition. Average and median require three listings and two named sellers. Lowest requires one. Unknown sellers do not satisfy the seller threshold. Shipping is not added; these remain item asking prices.
- Unconfirmed observations remain inspectable in the card profile, capped at 100 displayed listings with the full excluded count. Graphs and statistics omit them. Conditions/printings can be switched without a network request.

## Image processing and limits

OpenCV ORB features and a RANSAC homography align the card. Acceptance requires at least 30 feature matches, 25 inliers, a 65% inlier ratio, a dominant card occupying 55–115% of image area, and illustration-region correlation of at least 0.65. Tesseract then reads the card number; conflicting readable numbers or denominators reject the listing. An extra contradictory photo overrides a matching photo. Low evidence is uncertain, not counterfeit.

Only approved HTTPS image hosts are fetched, including on redirects. Downloads allow JPEG/PNG/WebP, at most 5 MiB and 12 million decoded pixels, resized to 1200 pixels. Processing inspects at most three photos and caches at most 32 reference images/features per process. Tesseract has a 10-second timeout. Celery imposes a 120-second hard limit and uses a Redis lock (150-second expiry) to allow one active check. Failed checks retry at most three times, separated by at least 15 minutes; exhausted or interrupted attempts remain excluded.

The default schedule checks one listing every three minutes. Monitor backlog before increasing throughput on the 1 GB host; do not add worker concurrency to speed up this job. Reference images from unsupported hosts remain uncertain. OCR currently uses English data and does not claim Japanese text verification. Deterministic visual tests are algorithm validation, not a measured accuracy estimate on real eBay photographs.

## Local validation and rollout

Dependencies are declared in both backend dependency manifests; the backend Docker image installs Tesseract. For local development, install backend dependencies and the system `tesseract` command.

1. Back up the database and deploy migration `0008_listing_assessments` **before** the application backend. It adds only the assessment table and indexes; Cards/Sets are unchanged. Validate in a disposable database first. Backend eligibility queries require this table.
2. Deploy the backend, then frontend. The migration does not grandfather existing eBay observations: unchecked records immediately disappear from statistics. TCGAPI continues to populate its own price data. Versioned caches prevent old aggregates from being reused.
3. Prepare historical observations using the stored payloads, newest first (therefore the past seven days first), in bounded batches. From `backend/`:

   ```sh
   python -m jobs.check_listing_images --limit 50
   python -m jobs.check_listing_images --report
   ```

   Repeat bounded preparation until `prepared` is zero. It is resumable and does not call eBay or delete observations. Old payloads without enough identity evidence stay uncertain.
4. Set `LISTING_IMAGE_CHECKS_ENABLED=true` to enable the scheduled checks. Keep `LISTING_IMAGE_ACCEPTANCE_ENABLED=false` while reviewing local-check outcomes and host resource use. Both default to false; do not enable production jobs as part of a frontend release.
5. After reviewing representative photos and confirming resource headroom, set `LISTING_IMAGE_ACCEPTANCE_ENABLED=true`. Return previously inconclusive checks to the queue in bounded batches:

   ```sh
   python -m jobs.check_listing_images --retry-images --limit 50
   ```

   This resets only uncertain image checks with passing text evidence; explicit text/image rejections and superseded assessments are not reopened. Restart the worker/Beat when changing environment settings.
6. Monitor `--report` for pending age, accepted/excluded counts and reasons, and the worker logs for per-check duration and errors. Watch process memory/restarts using the existing host monitor. Rising backlog or repeated timeouts should pause scheduling while filtering remains fail-closed.

Disable image scheduling to stop new processing; existing eligibility remains effective. Application rollback can retain the additive table. A schema downgrade removes assessment evidence and is not required for an application rollback.

The migration was applied to the verified localhost development PostgreSQL database and read-only profile/count queries passed. No production migration, backfill, provider refresh, or image-check scheduling was performed during implementation.
