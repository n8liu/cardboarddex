"""Bounded local product-image comparison, not counterfeit authentication."""
import hashlib
import logging
import subprocess
import tempfile
import time
from functools import lru_cache
from urllib.parse import urlparse
import httpx

logger = logging.getLogger(__name__)
# Exact hosts only: no arbitrary seller URLs or wildcard subdomains.
IMAGE_HOSTS = {"i.ebayimg.com", "images.pokemontcg.io", "images.tcgapi.dev", "api.tcgapi.dev", "tcgplayer-cdn.tcgplayer.com"}
MAX_BYTES = 5 * 1024 * 1024


def download_image(url):
    for _ in range(4):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS or parsed.port not in (None, 443) or parsed.username is not None or parsed.password is not None:
            raise ValueError("unapproved_image_url")
        with httpx.stream("GET", url, timeout=5, follow_redirects=False, trust_env=False) as response:
            if response.is_redirect:
                url = str(response.url.join(response.headers["location"]))
                continue
            response.raise_for_status()
            if not response.headers.get("content-type", "").split(";")[0] in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("unsupported_image_type")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError("image_byte_limit")
            return bytes(data)
    raise ValueError("image_redirect_limit")


def decode(data):
    import cv2
    import numpy as np
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 12_000_000:
            raise ValueError("image_pixel_limit")
        image.thumbnail((1200, 1200))
        return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)


@lru_cache(maxsize=32)
def reference_features(url, cache_day=None):
    import cv2
    data = download_image(url)
    gray = decode(data)
    points, descriptors = cv2.ORB_create(nfeatures=1500).detectAndCompute(gray, None)
    return gray, points, descriptors, hashlib.sha256(data).hexdigest()


def compare_images(reference_url, listing_url, expected_number, printed_total=None):
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    reference, rp, rd, reference_hash = reference_features(reference_url, int(time.time() // 86400))
    data = download_image(listing_url)
    listing = decode(data)
    lp, ld = cv2.ORB_create(nfeatures=1500).detectAndCompute(listing, None)
    evidence = {"image_sha256": hashlib.sha256(data).hexdigest(), "reference_sha256": reference_hash}
    if rd is None or ld is None:
        return "uncertain", "image_features_insufficient", evidence
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(rd, ld, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .7 * pair[1].distance]
    if len(good) < 30:
        return "uncertain", "artwork_unconfirmed", evidence
    source = np.float32([rp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dest = np.float32([lp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, mask = cv2.findHomography(dest, source, cv2.RANSAC, 3.0)
    if matrix is None or mask is None or int(mask.sum()) < 25 or float(mask.mean()) < .65:
        return "uncertain", "artwork_alignment_uncertain", evidence
    # Require one dominant card, rather than accepting a matching card in a lot.
    corners = np.float32([[0, 0], [reference.shape[1], 0], [reference.shape[1], reference.shape[0]], [0, reference.shape[0]]]).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, np.linalg.inv(matrix))
    area_ratio = abs(cv2.contourArea(projected)) / (listing.shape[0] * listing.shape[1])
    if not .55 <= area_ratio <= 1.15 or not cv2.isContourConvex(projected):
        return "uncertain", "single_card_unconfirmed", evidence
    aligned = cv2.warpPerspective(listing, matrix, (reference.shape[1], reference.shape[0]))
    # Shared borders/text can align the WRONG card. Require independent visual
    # agreement inside the illustration area, excluding header and number text.
    height, width = reference.shape
    art_slice = (slice(int(height * .16), int(height * .68)), slice(int(width * .10), int(width * .90)))
    ref_art = cv2.GaussianBlur(reference[art_slice], (5, 5), 0)
    candidate_art = cv2.GaussianBlur(aligned[art_slice], (5, 5), 0)
    correlation = float(cv2.matchTemplate(candidate_art, ref_art, cv2.TM_CCOEFF_NORMED)[0, 0])
    evidence["artwork_correlation"] = correlation
    if float(ref_art.std()) < 5 or not np.isfinite(correlation) or correlation < .65:
        return "uncertain", "artwork_unconfirmed", evidence
    # OCR the aligned image; parser owns all numeric/title normalization.
    with tempfile.TemporaryDirectory(prefix="cardboarddex-image-") as directory:
        path = f"{directory}/card.png"
        cv2.imwrite(path, aligned)
        result = subprocess.run(["tesseract", path, "stdout", "--psm", "11"], capture_output=True, text=True, timeout=10, check=True)
    from parsers.title_matcher import image_number_matches
    status, reason, numbers = image_number_matches(result.stdout, expected_number, printed_total)
    evidence["read_numbers"] = numbers
    evidence["inliers"] = int(mask.sum())
    return status, reason, evidence
