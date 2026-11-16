import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from sku_to_scene import catalog
from sku_to_scene.models import get_model
from sku_to_scene.payloads import build_payload

REPO = Path(__file__).resolve().parents[1]
COMPANIES = {"Walgreens", "McDonald's", "Starbucks", "Albertsons", "Gap", "Costco", "Kroger",
             "Best Buy", "Target", "7-Eleven", "The Home Depot", "TJX", "Staples", "Lowe's"}
FORBIDDEN = COMPANIES | {"Lucerne"}


def accounts():
    return json.loads((REPO / "catalog" / "accounts.json").read_text(encoding="utf-8"))["accounts"]


def runner():
    spec = importlib.util.spec_from_file_location("render_accounts", REPO / "scripts" / "render_accounts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def test_account_generation_plan_is_bounded_and_nonbillable_by_default(monkeypatch):
    mod = runner()
    planned = mod.plan()
    assert len(planned) == 9
    assert sum(j["estimate"]["estimate_usd"] for j in planned) == pytest.approx(3.24)
    monkeypatch.setattr("sys.argv", ["render_accounts.py"])
    monkeypatch.setattr(mod, "get_settings", lambda: pytest.fail("plan-only must not resolve live credentials"))
    monkeypatch.setattr(mod, "generate_video", lambda *a, **k: pytest.fail("plan-only must never generate"))
    assert mod.main() == 0


def test_uncertain_reservation_never_resubmits(monkeypatch, tmp_path):
    mod = runner()
    first = mod.plan()[0]
    key = first["account"]["planned_clip"]
    (tmp_path / "account-draft-reservations.json").write_text(json.dumps({key: {"status": "reserved"}}))
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT", "CONTENT_SAFETY_ENDPOINT"):
        monkeypatch.setenv(name, "test-configured-not-a-live-value")
    monkeypatch.setattr("sys.argv", ["render_accounts.py", "--execute", "--yes"])
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(live=True, data_dir=tmp_path, cache_dir=tmp_path))
    monkeypatch.setattr(mod, "load_manifest", lambda _: {"clips": []})
    monkeypatch.setattr(mod, "generate_video", lambda *a, **k: pytest.fail("uncertain submit must not be duplicated"))
    with pytest.raises(SystemExit, match="do not resubmit"):
        mod.main()


def test_reroll_plan_is_one_deterministic_attempt_without_calls(monkeypatch, capsys):
    mod = runner()
    monkeypatch.setattr("sys.argv", [
        "render_accounts.py", "--reroll", "account-coho-draft", "account-proseware-draft",
        "--reason", "text-or-logo",
    ])
    monkeypatch.setattr(mod, "get_settings", lambda: pytest.fail("plan-only must not resolve credentials"))
    assert mod.main() == 0
    output = capsys.readouterr().out
    assert "account-coho-draft-r1 $0.2400" in output
    assert "account-proseware-draft-r1 $0.4800" in output
    assert "$0.7200" in output


@pytest.mark.parametrize("args,message", [
    (["--reroll", "account-coho-draft"], "disqualifying --reason"),
    (["--reroll", "account-coho-draft-r1", "--reason", "unsafe"], "Only known initial"),
    (["--reroll", "unknown", "--reason", "text-or-logo"], "Only known initial"),
])
def test_invalid_reroll_plan_stops_before_credentials(monkeypatch, args, message):
    mod = runner()
    monkeypatch.setattr("sys.argv", ["render_accounts.py", *args])
    monkeypatch.setattr(mod, "get_settings", lambda: pytest.fail("invalid plans must stop before credentials"))
    with pytest.raises(SystemExit, match=message):
        mod.main()


def test_generation_reservation_cap_stops_before_submit(monkeypatch, tmp_path):
    mod = runner()
    (tmp_path / "account-draft-reservations.json").write_text(json.dumps({
        "prior-attempt": {"estimate_usd": 7.90, "status": "cached"},
    }))
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT", "CONTENT_SAFETY_ENDPOINT"):
        monkeypatch.setenv(name, "test-configured-not-a-live-value")
    monkeypatch.setattr("sys.argv", ["render_accounts.py", "--execute", "--yes"])
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(live=True, data_dir=tmp_path, cache_dir=tmp_path))
    monkeypatch.setattr(mod, "load_manifest", lambda _: {"clips": []})
    monkeypatch.setattr(mod, "generate_video", lambda *a, **k: pytest.fail("over-budget submit must never run"))
    with pytest.raises(SystemExit, match="exceed \\$8"):
        mod.main()
