import struct
import zlib
import json
from pathlib import Path

import pytest

from sku_to_scene.config import get_settings
from sku_to_scene.media import render_placeholder


@pytest.fixture(scope="session")
def rehearsal_cache(tmp_path_factory):
    """Synthetic test-only media: public demo-cache can be replaced by authentic renders."""
    cache = tmp_path_factory.mktemp("rehearsal-cache")
    render_placeholder(cache / "simulated.mp4", "TEST FIXTURE - scripted QA", duration=1, aspect="9:16")
    clips = []
    for i, model in enumerate(("minimax-h3-max-turbo", "ltx-2.5-fast",
                               "minimax-h3-max-turbo", "kling-v3-pro"), 1):
        hero = i == 4
        scores = {k: 0.9 for k in ("logo_integrity", "label_legibility", "product_fidelity", "prompt_adherence")}
        if i == 3:
            scores["prompt_adherence"] = 0.5
        clips.append({"id": "lto-hero-kling" if hero else f"lto-draft-{i}", "sku": "NWC-LTO-PCB-16",
                      "model": model, "mode": "image-to-video" if hero else "text-to-video",
                      "aspect_ratio": "9:16", "provenance": "simulated", "file": "simulated.mp4",
                      "rehearsal_qa": {"scores": scores}})
    (cache / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    return cache


@pytest.fixture
def settings(tmp_path, monkeypatch, rehearsal_cache):
    """Isolated mock-mode settings: own data dir, no latency, no ambient Foundry/AOAI config."""
    for k in ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT",
              "AZURE_OPENAI_API_KEY", "CONTENT_SAFETY_ENDPOINT", "CONTENT_SAFETY_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("SKU2SCENE_MODE", "mock")
    monkeypatch.setenv("SKU2SCENE_QA_EVALUATORS", "on")  # tests mock evaluators; ambient rehearsal "off" must not leak
    monkeypatch.setenv("SKU2SCENE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SKU2SCENE_MOCK_LATENCY_SCALE", "0")
    monkeypatch.setenv("SKU2SCENE_CACHE_DIR", str(rehearsal_cache))
    return get_settings()


def write_png(path: Path, w: int, h: int) -> Path:
    """Minimal valid grayscale PNG (no Pillow dependency)."""
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    path.write_bytes(data)
    return path
