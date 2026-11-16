import struct
import zlib
from pathlib import Path

import pytest

from sku_to_scene.config import get_settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Isolated mock-mode settings: own data dir, no latency, no ambient Foundry/AOAI config."""
    for k in ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT",
              "AZURE_OPENAI_API_KEY", "CONTENT_SAFETY_ENDPOINT", "CONTENT_SAFETY_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("SKU2SCENE_MODE", "mock")
    monkeypatch.setenv("SKU2SCENE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SKU2SCENE_MOCK_LATENCY_SCALE", "0")
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
