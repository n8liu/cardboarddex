"""Deterministic visual fixtures: local algorithm tests, not authenticity validation."""
import shutil
import subprocess
from types import SimpleNamespace
import httpx
import pytest
import respx
from app.services import listing_images as images


@pytest.mark.parametrize("url", ["http://i.ebayimg.com/a.jpg", "https://127.0.0.1/x", "https://i.ebayimg.com.evil.test/x", "https://u:p@i.ebayimg.com/x", "https://i.ebayimg.com:123/x"])
def test_download_rejects_untrusted_urls(url):
    with pytest.raises(ValueError, match="unapproved"):
        images.download_image(url)


@respx.mock
def test_redirects_cannot_escape_allowlist():
    respx.get("https://i.ebayimg.com/a").respond(302, headers={"location": "https://127.0.0.1/private"})
    with pytest.raises(ValueError, match="unapproved"):
        images.download_image("https://i.ebayimg.com/a")


@respx.mock
def test_download_size_and_type_limits(monkeypatch):
    respx.get("https://i.ebayimg.com/html").respond(200, headers={"content-type": "text/html"}, content=b"not an image")
    with pytest.raises(ValueError, match="unsupported"):
        images.download_image("https://i.ebayimg.com/html")
    monkeypatch.setattr(images, "MAX_BYTES", 10)
    respx.get("https://i.ebayimg.com/large").respond(200, headers={"content-type": "image/png"}, content=b"x"*11)
    with pytest.raises(ValueError, match="byte_limit"):
        images.download_image("https://i.ebayimg.com/large")


def fixture_card(seed=1, number="004/102"):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    card = np.full((700, 500, 3), 255, dtype=np.uint8)
    cv2.rectangle(card, (8, 8), (492, 692), (0, 0, 0), 4)
    cv2.putText(card, "TEST CARD", (45, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    # Distinct art with enough features for perspective registration.
    art = rng.integers(0, 255, (380, 420, 3), dtype=np.uint8)
    art = cv2.GaussianBlur(art, (5, 5), 0)
    card[100:480, 40:460] = art
    cv2.putText(card, number, (65, 625), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    return card


def png(card):
    import cv2
    return cv2.imencode(".png", card)[1].tobytes()


def setup_images(monkeypatch, candidate):
    images.reference_features.cache_clear()
    reference = png(fixture_card())
    monkeypatch.setattr(images, "download_image", lambda url: reference if url == "reference" else png(candidate))


def test_actual_feature_matching_and_identifier_gate(monkeypatch):
    setup_images(monkeypatch, fixture_card())
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="004/102"))
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "matched"
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="004/130"))
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "rejected"
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=""))
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "uncertain"


@pytest.mark.parametrize("kind", ["wrong_art", "back", "blur", "glare", "lot"])
def test_negative_visual_fixtures_do_not_match(monkeypatch, kind):
    import cv2
    import numpy as np
    card = fixture_card()
    if kind == "wrong_art":
        card = fixture_card(700, "008/102")
    elif kind == "back":
        card = np.full_like(card, 128)
    elif kind == "blur":
        card = cv2.GaussianBlur(card, (101, 101), 20)
    elif kind == "glare":
        cv2.rectangle(card, (45, 110), (455, 470), (255, 255, 255), -1)
    else:
        card = np.concatenate([card, card], axis=1)
    setup_images(monkeypatch, card)
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="004/102"))
    assert images.compare_images("reference", "candidate", "4", 102)[0] != "matched"


def test_rotated_fixture_matches(monkeypatch):
    import cv2
    card = fixture_card()
    rotated = cv2.rotate(card, cv2.ROTATE_180)
    setup_images(monkeypatch, rotated)
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="004/102"))
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "matched"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract runtime not installed")
def test_end_to_end_local_ocr(monkeypatch):
    setup_images(monkeypatch, fixture_card())
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "matched"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract runtime not installed")
def test_actual_ocr_rejects_wrong_number_despite_matching_art(monkeypatch):
    setup_images(monkeypatch, fixture_card(number="008/102"))
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "rejected"


def test_sleeve_like_light_change_preserves_artwork_match(monkeypatch):
    import cv2
    candidate = cv2.convertScaleAbs(fixture_card(), alpha=.85, beta=20)
    setup_images(monkeypatch, candidate)
    monkeypatch.setattr(images.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="004/102"))
    assert images.compare_images("reference", "candidate", "4", 102)[0] == "matched"
