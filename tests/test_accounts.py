import hashlib
import json
import re
from pathlib import Path

from sku_to_scene import catalog
from sku_to_scene.models import get_model
from sku_to_scene.payloads import build_payload

REPO = Path(__file__).resolve().parents[1]
COMPANIES = {"Walgreens", "McDonald's", "Starbucks", "Albertsons", "Gap", "Costco", "Kroger",
             "Best Buy", "Target", "7-Eleven", "The Home Depot", "TJX", "Staples", "Lowe's"}
# "Lucerne" is a real Albertsons private-label brand, so it is excluded as a fictional analog.
FORBIDDEN = COMPANIES | {"Lucerne"}


def accounts():
    return json.loads((REPO / "catalog" / "accounts.json").read_text(encoding="utf-8"))["accounts"]


def test_representative_accounts_are_grounded_fiction_and_supported():
    rows = accounts()
    assert len(rows) == 14
    assert {a["real_company"] for a in rows} == COMPANIES
    assert len({a["fictional_brand"] for a in rows}) == 14
    assert {a["area"] for a in rows} == {"qsr", "apparel", "home", "grocery"}
    for a in rows:
        assert a["sources"], a["id"]
        assert 0 < len(a["need"].split()) <= 25, a["id"]
        for s in a["sources"]:
            assert s["url"].startswith("https://") and s["publisher"]
            assert re.fullmatch(r"\d{4}-\d{2}", s["published"])
            assert s["accessed"] == "2026-11-16"
        assert all(real.lower() not in a["fictional_brand"].lower() for real in FORBIDDEN)
        m = get_model(a["model"])
        if a["planned_clip"]:
            b = json.loads((REPO / "briefs" / a["brief_file"]).read_text())
            payload = build_payload(m, "text-to-video", m.default_deployment, b["prompt"], duration=a["duration"],
                                    resolution=a["tier"], aspect_ratio=a["aspect_ratio"], audio=False)
            assert a["aspect_ratio"] in m.t2v_aspect_ratios
            assert payload["duration"] in (6, "6")
            if m.family == "ltx":
                assert payload["generate_audio"] is False
            assert a["hero_clip"] is None
            assert catalog.get_sku(a["sku"])
            assert b["brand"] in catalog.brands()
    fictional = json.dumps(catalog.brands()) + json.dumps([
        {k: p[k] for k in ("name", "brand", "category", "attributes")} for p in catalog.products()
    ])
    for name in FORBIDDEN:
        assert not re.search(r"\b" + re.escape(name) + r"\b", fictional, re.I), name


def test_original_qa_and_evaluations_are_immutable():
    manifest = json.loads((REPO / "demo-cache" / "manifest.json").read_text())
    assert hashlib.sha256(json.dumps(manifest["clips"][:8], sort_keys=True).encode()).hexdigest() == (
        "67c6b6cc613a2df59920c1b06fa785ccf6613618f140cc31d62db34155267723")
    for name, expected in {
        "foundry-evals-v1.json": "71bd683003d936a2af14852101d36ea777043a2b6bbf2cc8cbb9eacb8d0931ee",
        "human-review.json": "d1a41ae5bd36d88f4f8a8fa7588e0740c680ff4ffe3c6f78e2895b1c87bba959",
    }.items():
        raw = (REPO / "demo-cache" / "evaluations" / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == expected


def test_new_account_drafts_are_planned_not_published_before_research():
    manifest = json.loads((REPO / "demo-cache" / "manifest.json").read_text())
    ids = {c["id"] for c in manifest["clips"]}
    assert len(manifest["clips"]) == 8
    planned = [a["planned_clip"] for a in accounts() if a["planned_clip"]]
    assert len(planned) == 9
    assert not ids & set(planned)
    assert not list((REPO / "demo-cache").glob("account-*.mp4"))
