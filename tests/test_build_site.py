import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_site", REPO / "scripts" / "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_site_artifact_is_curated_and_truthful(tmp_path):
    out = tmp_path / "site"
    _load_builder().build(out)

    files = [p for p in out.rglob("*") if p.is_file()]
    names = {p.name for p in files}
    assert {"index.html", "app.js", "app.css", "data.json", ".nojekyll"} <= names
    assert not any(n.startswith(".env") or ".sku2scene" in str(p) for p, n in ((p, p.name) for p in files))
    assert {p.suffix for p in files} <= {".html", ".js", ".css", ".json", ".png", ".mp4", ""}
    assert len(list((out / "brand" / "original").glob("*.png"))) == 6

    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert len(data["clips"]) == 8
    assert all((out / c["file"]).is_file() for c in data["clips"])
    hero = next(c for c in data["clips"] if c["id"] == data["lto"]["hero_clip"])
    # Only the recorded variant may claim a hero render.
    assert data["lto"]["hero_variant"] == hero["variant"] == 2
    blob = json.dumps(data).lower()
    for leaked in ("services.ai.azure.com", "cognitiveservices.azure.com", "tenant", "subscription"):
        assert leaked not in blob
