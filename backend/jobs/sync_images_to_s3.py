import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from pathlib import Path
import sys
from typing import Any

# Ensure backend root is in sys.path when executed directly
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Card
from app.tcgapi.client import TCGAPIClient

logger = logging.getLogger(__name__)


def _object_exists(s3_client: Any, bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        logger.warning("Error checking S3 key=%s in bucket=%s: %s", key, bucket, exc)
        return False


def _sync_single_card_image(
    card_id: str,
    image_url: str,
    s3_client: Any,
    bucket: str,
    tcg_client: TCGAPIClient,
    overwrite: bool = False,
) -> tuple[str, bool, str]:
    """
    Downloads card image from upstream CDN and uploads to S3.
    Returns: (card_id, success, message)
    """
    key = f"cards/{card_id}.png"
    if not overwrite and _object_exists(s3_client, bucket, key):
        return card_id, True, "cached"

    try:
        content, content_type = tcg_client.get_image(image_url)
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "image/png",
            CacheControl="public, max-age=31536000, immutable",
        )
        return card_id, True, "uploaded"
    except Exception as exc:
        logger.error(
            "Failed syncing image for card_id=%s from url=%s: %s: %s",
            card_id,
            image_url,
            type(exc).__name__,
            exc,
        )
        return card_id, False, str(exc)


def run_image_sync(
    session: Session,
    bucket: str | None = None,
    region: str | None = None,
    limit: int | None = None,
    set_id: str | None = None,
    workers: int = 8,
    overwrite: bool = False,
) -> dict[str, int]:
    settings = get_settings()
    target_bucket = bucket or settings.s3_bucket_name
    target_region = region or settings.aws_region

    s3_client = boto3.client("s3", region_name=target_region)
    tcg_client = TCGAPIClient()

    query = select(Card.id, Card.image_url).where(Card.image_url.is_not(None))
    if set_id:
        query = query.where(Card.set_id == set_id)
    if limit:
        query = query.limit(limit)

    cards = session.execute(query).all()
    total = len(cards)
    logger.info("Found %s cards to sync to S3 bucket=%s", total, target_bucket)

    uploaded = 0
    cached = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                _sync_single_card_image,
                card_id=cid,
                image_url=url,
                s3_client=s3_client,
                bucket=target_bucket,
                tcg_client=tcg_client,
                overwrite=overwrite,
            ): cid
            for cid, url in cards
            if url
        }

        for i, future in enumerate(as_completed(futures), start=1):
            cid, success, status = future.result()
            if success:
                if status == "uploaded":
                    uploaded += 1
                else:
                    cached += 1
            else:
                failed += 1

            if i % 50 == 0 or i == total:
                logger.info(
                    "Image sync progress: %s/%s cards processed (uploaded=%s, cached=%s, failed=%s)",
                    i,
                    total,
                    uploaded,
                    cached,
                    failed,
                )

    logger.info(
        "Image sync complete: total=%s, uploaded=%s, cached=%s, failed=%s",
        total,
        uploaded,
        cached,
        failed,
    )
    return {"total": total, "uploaded": uploaded, "cached": cached, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize card images from CDN to Amazon S3")
    parser.add_argument("--all", action="store_true", help="Sync all cards")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cards to sync")
    parser.add_argument("--set-id", type=str, default=None, help="Sync cards for a specific set ID")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent worker threads")
    parser.add_argument("--overwrite", action="store_true", help="Re-download and overwrite existing S3 objects")
    parser.add_argument("--bucket", type=str, default=None, help="Override destination S3 bucket")
    parser.add_argument("--region", type=str, default=None, help="Override AWS region")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    with SessionLocal() as session:
        result = run_image_sync(
            session=session,
            bucket=args.bucket,
            region=args.region,
            limit=None if args.all else args.limit,
            set_id=args.set_id,
            workers=args.workers,
            overwrite=args.overwrite,
        )
        print(result)


if __name__ == "__main__":
    main()
