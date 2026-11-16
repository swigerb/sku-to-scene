import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts.render_accounts import check_budget, generation_cap, override_render, plan, reservation_total
from sku_to_scene import catalog
from sku_to_scene.models import get_model
from sku_to_scene.payloads import build_payload

REPO = Path(__file__).resolve().parents[1]
COMPANIES = {"Walgreens", "McDonald's", "Starbucks", "Albertsons", "Gap", "Costco", "Kroger",
             "Best Buy", "Target", "7-Eleven", "The Home Depot", "TJX", "Staples", "Lowe's"}
# "Lucerne" is a real Albertsons private-label brand, so it is excluded as a fictional analog.
FORBIDDEN = COMPANIES | {"Lucerne"}


def test_completion_budget_is_scoped_to_proseware_and_does_not_change_default():
    assert generation_cap(False, ["coho"], None) == 8
    assert generation_cap(True, ["proseware"], None) == pytest.approx(7.62 + 2.50)
    for selected, reroll in [(None, None), (["coho"], None), (["proseware", "coho"], None),
                             (["proseware"], ["account-proseware-draft"])]:
        with pytest.raises(ValueError, match="only for"):
            generation_cap(True, selected, reroll)
    assert generation_cap(False, ["southridge"], None, True) == pytest.approx(11.22)
    with pytest.raises(ValueError, match="only for"):
        generation_cap(True, ["southridge"], None, True)
    with pytest.raises(ValueError, match="only for"):
        generation_cap(False, ["proseware"], None, True)


def accounts():
    return json.loads((REPO / "catalog" / "accounts.json").read_text(encoding="utf-8"))["accounts"]


def test_replacement_route_estimate_and_conservative_completion_budget():
    job = next(j for j in plan() if j["account"]["id"] == "proseware")
    override_render(job, "ltx-2.5-pro", "720p")
    assert job["account"]["model"] == "ltx-2.5-pro"
    assert job["account"]["tier"] == "720p"
    assert job["estimate"]["estimate_high_usd"] == pytest.approx(0.72)
    journal = {"earlier": {"estimate_usd": 7.62},
               "s4": {"estimate_usd": 0.48, "reserved_usd": 0.536}}
    assert reservation_total(journal) == pytest.approx(8.156)
    assert check_budget(journal, [job["estimate"]], 9.12) == pytest.approx(0.72)
    override_render(job, "ltx-2.5-pro", "1080p")
    with pytest.raises(SystemExit, match="nothing submitted"):
        check_budget(journal, [job["estimate"]], 9.12)
    with pytest.raises(ValueError):
        override_render(job, "ltx-2.5-pro", "768P")
    override_render(job, "minimax-h3-max", "768P")
    journal["s5"] = {"estimate_usd": 0.72, "reserved_usd": 0.72}
    for suffix in ("s6", "s7"):
        assert check_budget(journal, [job["estimate"]], 10.12) == pytest.approx(0.536)
        journal[suffix] = {"estimate_usd": 0.48, "reserved_usd": 0.536}
    with pytest.raises(SystemExit, match="nothing submitted"):
        check_budget(journal, [job["estimate"]], 10.12)


def test_southridge_high_reserve_prevents_a_third_attempt():
    job = next(j for j in plan() if j["account"]["id"] == "southridge")
    scoped = {}
    for suffix in ("s1", "s2"):
        assert check_budget(scoped, [job["estimate"]], 1.10) == pytest.approx(0.536)
        scoped[suffix] = {"estimate_usd": 0.48, "reserved_usd": 0.536}
    with pytest.raises(SystemExit, match="nothing submitted"):
        check_budget(scoped, [job["estimate"]], 1.10)


def test_realism_selection_uses_measured_gate_and_preserves_agent_rejections():
    evidence = REPO / "demo-cache" / "qa"
    control = json.loads((evidence / "proseware-s5-v3.json").read_text())
    assert control["v1_qa"]["verdict"] == "fail"
    assert control["v1_qa"]["measured"] is True
    assert control["v1_qa"]["sampled_frame_count"] == 4
    selected = json.loads((evidence / "proseware-s7-v1.json").read_text())
    assert selected["qa"]["evaluator_version"] == "brand-qa-vision-v1"
    assert selected["qa"]["verdict"] == "pass" and selected["qa"]["measured"] is True
    assert selected["qa"]["sampled_frame_count"] == 4
    assert len(selected["qa"]["content_safety"]) == 4
    assert selected["agent_review"]["decision"] == "selected_for_human_review"
    assert selected["agent_review"]["human_approval"] is False
    a = {a["id"]: a for a in accounts()}
    assert a["proseware"]["replacement_clip"] == selected["clip"]
    for account, name in (("proseware", "proseware-s6-v1.json"), ("southridge", "southridge-s2-v1.json")):
        rejected = json.loads((evidence / name).read_text())
        assert rejected["qa"]["verdict"] == "pass", "preserve AI pass separately from agent rejection"
        assert rejected["agent_review"]["decision"] == "withheld"
        assert rejected["clip"] in {c["id"] for c in a[account]["excluded_clips"]}
        assert rejected["clip"] != a[account].get("replacement_clip", a[account]["planned_clip"])


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


def test_every_account_resolves_to_playable_media_with_honest_qa():
    manifest = json.loads((REPO / "demo-cache" / "manifest.json").read_text())
    clips = {c["id"]: c for c in manifest["clips"]}
    assert len(clips) == len(manifest["clips"]), "manifest IDs are unique (append-only)"
    for a in accounts():
        chosen = a.get("replacement_clip") or a["planned_clip"] or a["recorded_clip"]
        assert chosen in clips, f"{a['id']} has no recorded example"
        assert (REPO / "demo-cache" / clips[chosen]["file"]).is_file(), chosen
        excluded = {e["id"] for e in a.get("excluded_clips", [])}
        assert chosen not in excluded
        for e in a.get("excluded_clips", []):
            assert e["id"] in clips and e["reason"], e
            assert not (REPO / "demo-cache" / clips[e["id"]]["file"]).exists(), f"withheld media {e['id']} is in the repo"
        for e in a.get("learning_clips", []):
            c = clips[e["id"]]
            assert c["qa"]["verdict"] == "fail" and e["note"], e["id"]
            assert e["id"] not in excluded and e["id"] != chosen
            assert (REPO / "demo-cache" / c["file"]).is_file()
        if a["planned_clip"]:
            c = clips[chosen]
            assert c["account"] == a["id"] and c["stage"] == "draft"
            assert c["hero_eligible"] is False and c["human_signoff_required"] is True
            assert c["source_image"] is None and a["hero_clip"] is None
            attempts = [x for x in clips.values() if x.get("account") == a["id"]]
            # Every paid attempt stays visible as evidence: chosen, learning example or withheld.
            shown = {chosen} | excluded | {e["id"] for e in a.get("learning_clips", [])}
            assert {x["id"] for x in attempts} == shown, a["id"]


def test_simplified_replacements_keep_prompt_history():
    clips = {c["id"]: c for c in json.loads((REPO / "demo-cache" / "manifest.json").read_text())["clips"]}
    for a in accounts():
        attempts = [c for c in clips.values() if c.get("account") == a["id"] and re.search(r"-s\d+$", c["id"])]
        if not attempts:
            continue
        brief = json.loads((REPO / "briefs" / a["brief_file"]).read_text(encoding="utf-8"))
        history = brief["prompt_history"]
        assert brief["brief_version"] == history[-1]["version"]
        assert history[0]["prompt_key"] == "prompt" and brief["prompt"]
        for c in attempts:
            assert c["reroll_reason"] == "simplified-brief" and c["replacement_for"] in clips
            entry = next(h for h in history if h["clip"] == c["id"])
            assert c["brief_version"] == entry["version"]
            text = entry.get("prompt") or brief[entry["prompt_key"]]
            assert c["prompt"] == text, c["id"]
