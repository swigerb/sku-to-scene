import importlib.util
import hashlib
import json
import re
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

HR_MODES = ("hr-404", "hr-network", "hr-malformed-json", "hr-malformed-data",
            "hr-null-finding", "hr-empty-finding", "hr-unknown-severity")
THEME_MODES = ("theme-url-light", "theme-url-dark", "theme-stored-light", "theme-stored-dark",
               "theme-system-dark", "theme-invalid", "theme-storage-blocked")
# Each mutation removes a real safeguard from the shipped app.js; the harness must name the broken behavior.
MUTATIONS = {
    "tier-invalidation": ('tSel.addEventListener("change", () => { fillDurations(); calc(); });',
                          'tSel.addEventListener("change", calc);', "ok", "tier change re-derives durations"),
    "step-pause": ("      pausePlayers();\n      player = null;", "      player = null;", "ok",
                   "changing active concept pauses the previous player"),
    "clip-count": ("!Number.isSafeInteger(Number(raw)) || ", "", "ok", "unsafe integers are rejected"),
    "finding-validation": ("HR = validReview(hr) ? hr : null;", "HR = hr;", "hr-empty-finding",
                           "Human-review evidence unavailable"),
    "view-pause": ("    if (changed) pausePlayers();\n", "", "ok", "hiding a view pauses its players"),
    "evidence-deep-links": ('routing: "evidence", qa: "evidence", evals: "evidence"', "", "ok",
                            "#routing opens the evidence view"),
    "draft-readiness": ('$("#guide-readiness").replaceChildren(readinessBox(c));',
                        '$("#guide-readiness").replaceChildren();', "ok", "publication readiness outside Inspect evidence"),
    "step-focus": ("if (focus) focusStart();", "", "ok", "explicit step change resets scroll"),
    "selection-reset": ("      state.selected = null;", "", "ok", "restart clears the selection"),
    "custom-duration": ("wasShown && Number.isFinite(keep) && keep >= lo && keep <= hi ? raw : String(m.default_duration)",
                        "String(m.default_duration)", "ok", "a tier change keeps a valid custom MiniMax duration"),
    "blocker-spread": ('      ...currentActions.map((c) => h("p"', '      currentActions.map((c) => h("p"', "ok",
                       "#readiness-summary renders nodes, not stringified objects"),
    "denominator-note": ('h("div", { class: "qa-summary" }, base), denominatorNote(data));',
                         'h("div", { class: "qa-summary" }, base));', "ok", "#readiness-summary has one shared denominator note"),
    "service-fail-note": ('svc.includes("fail") ? "The Foundry', 'true ? "The Foundry', "ok",
                          "the recorded-as-fail explanation appears only for a non-passing service result"),
    "clip-toggle": ('        h("span", { class: "clip-toggle", "aria-hidden": "true" }),\n', "", "ok",
                    "summary draws a visible expand/collapse affordance"),
    "gallery-exact-guide": ('href: `#guide/${a.area}/${a.id}` }, "Open guided demo"',
                            'href: `#guide/${a.area}` }, "Open guided demo"', "ok", "each gallery action targets the exact account"),
    "preview-close-pause": ("      previewPlayer?.pause();\n      body.replaceChildren();",
                            "      body.replaceChildren();", "ok", "closing preview pauses its recording"),
    "silent-sound": ('$("#sound").disabled = !active?.has_audio;', '$("#sound").disabled = false;', "ok",
                     "the silent second concept disables Sound"),
    "evidence-scope": ('Object.entries(EV.media).filter(([id]) => !scope || id === scope)',
                       'Object.entries(EV.media)', "ok", "unevaluated clip never borrows another recording"),
    "fresh-guide-entry": ("if (restart || a.id !== account.id)", "if (a.id !== account.id)", "ok",
                          "explicit guide entry restarts the same example"),
    "brief-duplicate-title": ('h("p", {}, "No approved product image was used.")',
                              'h("h3", {}, p.name), h("p", {}, "No approved product image was used.")', "ok",
                              "Brief has one product title"),
    "alternative-autoplay": ('          playSafely(previewPlayer, "#preview-status");', "", "ok",
                            "alternative Preview pauses old recording and plays new recording"),
    "calculator-reset-count": ('      nIn.value = "1";', "", "ok", "reset restores a single recorded clip"),
    "playback-accessible-context": ('title: key === "concepts" ? `concept #${c.variant} preview`',
                                    'title: c.concept ? `concept #${c.variant} preview`', "ok",
                                    "recorded-result accessible name uses the current step"),
    "initial-featured": ('let account = data.accounts.find((a) => a.curation === "featured") || data.accounts[0];',
                         "let account = data.accounts[0];", "learning-first", "the initial guide example is featured"),
    "area-featured-default": ('data.accounts.find((a) => a.area === area && a.curation === "featured")',
                              "data.accounts.find((a) => a.area === area)", "learning-first",
                              "defaults to a featured presentation"),
    "learning-card-cta": ('`#guide/${a.area}/${a.id}` }, "Inspect learning case")',
                          '`#guide/${a.area}/${a.id}` }, "Open guided demo")', "ok", "CTA names its role"),
    "learning-collapsed": ('inArea.filter((a) => a.curation !== "learning").map((a) => accountCard(a, clips, preview))',
                           "inArea.map((a) => accountCard(a, clips, preview))", "ok", "shows featured presentations by default"),
    "chooser-groups": ('[["Featured presentations", false], ["Learning cases", true]]',
                       '[["Examples", false], ["More examples", true]]', "ok",
                       "the example selector distinguishes featured presentations from learning cases"),
    "brief-learning-notice": ('h("h3", {}, p.name), learningNotice(account, readiness(c).text),', 'h("h3", {}, p.name),', "ok",
                              "deep link states its learning-case role"),
    "learning-defect-once": ("const named = Boolean(shownWith && shownWith.includes(a.learning_defect));",
                             "const named = false;", "ok", "names its unresolved defect once"),
    "review-defect-once": ("c.demo_disposition?.summary === account.learning_defect",
                           "false", "ok", "Review names its unresolved defect once"),
    "campaign-approval-split": ('h("section", { class: "campaign-approval" }, h("h3", {}, "Customer-campaign approval"),',
                                'h("section", { class: "campaign-approval" }, h("h3", {}, "Approval"),', "ok",
                                "Review separates source screening, current demo disposition and campaign approval"),
    "home-concise-statement": ('h("p", { class: "hero-statement" }, h("b", {}, "Silent fictional-demo presentation."),',
                               'h("p", { class: "hero-statement" }, h("b", {}, "Silent presentation variant."),', "ok",
                               "Home states the silent presentation once"),
}


def _harness_input(out):
    return json.dumps({
        "data": json.loads((out / "data.json").read_text(encoding="utf-8")),
        "ev": json.loads((out / "evaluations" / "foundry-evals-v1.json").read_text(encoding="utf-8")),
        "hr": json.loads((out / "evaluations" / "human-review.json").read_text(encoding="utf-8")),
        "theme_script": re.search(r"<script>(.*?)</script>", (out / "index.html").read_text(encoding="utf-8"), re.S)[1],
    })


@pytest.mark.parametrize("mode,mutation", [("ok", None), ("ev-404", None), ("learning-first", None),
                                           *((m, None) for m in HR_MODES + THEME_MODES),
                                           *((None, m) for m in MUTATIONS)])
def test_browser_demo_behaviour(tmp_path, mode, mutation):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser event-handler regression")
    out = _load_builder().build(tmp_path / "site")
    source = REPO / "site" / "app.js"
    expected = None
    if mutation:
        before, after, mode, expected = MUTATIONS[mutation]
        text = source.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert before in text, f"mutation target for {mutation} no longer exists in site/app.js"
        source = tmp_path / "mutated.js"
        source.write_text(text.replace(before, after, 1), encoding="utf-8")
    result = subprocess.run(
        [node, str(REPO / "tests" / "playback.cjs"), str(source), mode],
        input=_harness_input(out), cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    )
    if mutation:
        assert result.returncode != 0, f"{mutation} mutation was not detected"
        assert expected in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        expected = (f"human-review {mode} handled" if mode in HR_MODES else
                    "evaluation evidence unavailable handled" if mode == "ev-404" else
                    "learning-first default entries handled" if mode == "learning-first" else
                    "guided demo, tabs and calculator passed")
        assert expected in result.stdout


def test_duration_constraints_come_from_the_payload_validator(tmp_path):
    data = json.loads((_load_builder().build(tmp_path / "site") / "data.json").read_text(encoding="utf-8"))
    models = {m["key"]: m for m in data["models"]}
    fast = models["ltx-2.5-fast"]["durations_by_tier"]
    assert fast["1080p"] == [6, 8, 10, 12, 14, 16, 18, 20]
    assert fast["1440p"] == fast["2160p"] == [6, 8, 10]
    assert models["ltx-2.5-pro"]["durations_by_tier"] == {"720p": [6, 8, 10], "1080p": [6, 8, 10]}
    assert all(v == list(range(3, 16)) for v in models["kling-v3-pro"]["durations_by_tier"].values())
    for key in ("minimax-h3-max", "minimax-h3-max-turbo"):
        assert models[key]["durations_by_tier"] is None
        assert models[key]["duration_range"] == [0.92, 15.0]

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
    assert {p.suffix for p in files} <= {".html", ".js", ".css", ".json", ".png", ".jpg", ".mp4", ".vtt", ""}
    assert len(list((out / "brand" / "original").glob("*.png"))) == 6

    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    for name in ("foundry-evals-v1.json", "human-review.json"):
        assert json.loads((out / "evaluations" / name).read_text(encoding="utf-8"))
    assert len(data["clips"]) >= 8
    for c in data["clips"]:
        if c["withheld_reason"]:
            assert c["file"] is None and c["original_file"] is None, c["id"]
            assert not list((out / "media").glob(f"{c['id']}.*")), f"withheld media {c['id']} was published"
        else:
            assert (out / c["file"]).is_file(), c["id"]
    for a in data["accounts"]:
        played = data["clips"][[c["id"] for c in data["clips"]].index(a["recorded_clip"])]
        assert played["file"] and not played["withheld_reason"], f"{a['id']} has no playable example"
    hero = next(c for c in data["clips"] if c["id"] == data["lto"]["hero_clip"])
    # Only the recorded variant may claim a hero render.
    assert data["lto"]["hero_variant"] == hero["variant"] == 2
    blob = json.dumps(data).lower()
    for leaked in ("services.ai.azure.com", "cognitiveservices.azure.com", "tenant", "subscription"):
        assert leaked not in blob


def test_presentation_hashes_scope_and_baseline():
    builder = _load_builder()
    data = builder.build_data()
    clips = {c["id"]: c for c in data["clips"]}
    assert sum(c["baseline_original"] for c in clips.values()) == 8
    for v in data["demo_dispositions"]["variants"]:
        c, parent = clips[v["id"]], clips[v["parent_clip"]]
        assert c["record_kind"] == "presentation" and c["has_audio"] is False
        assert c["qa"] == parent["qa"] and c["source_qa_clip"] == parent["id"]
        assert c["original_file"] == parent["file"]
        assert hashlib.sha256((REPO / "demo-cache" / v["file"]).read_bytes()).hexdigest() == v["sha256"]
    assert data["demo_dispositions"]["customer_campaign_approved"] is False
    assert clips["hero-home-kling"]["qa"]["scores"]["prompt_adherence"] == 0.72
    assert clips["hero-patio-h3max"]["qa"]["verdict"] == "fail"


def test_release_candidates_are_withheld_even_when_automated_qa_passes(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    data = json.loads((out / "data.json").read_text())
    added = json.loads((REPO / "demo-cache" / "release-20261117.json").read_text())["clips"]
    by_id = {c["id"]: c for c in data["clips"]}
    selected = {a["recorded_clip"] for a in data["accounts"]}
    assert len(added) == 6
    for candidate in added:
        c = by_id[candidate["id"]]
        assert c["id"] not in selected
        assert c["file"] is None and c["original_file"] is None and c["withheld_reason"]
        assert not (out / "media" / candidate["file"]).exists()
        assert c["independent_review"]["presentation_sha256"] == candidate["sha256"]
        assert c["qa"]["verdict"] == candidate["qa"]["verdict"]
    for account in ("tailwind", "wide-world"):
        c = by_id[f"release-{account}-20261117-v1"]
        assert c["qa"]["verdict"] == "pass" and c["withheld_reason"].startswith("Rejected despite automated pass")


def test_selected_manifest_binds_served_media_and_preserves_targeted_evaluation_scope(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    manifest = json.loads((out / "evaluations" / "selected-assets-v1.json").read_text())
    assert len(manifest["selected"]) == 14 and manifest["release_ready"] is False
    for s in manifest["selected"]:
        assert hashlib.sha256((out / s["file"]).read_bytes()).hexdigest() == s["sha256"]
        assert hashlib.sha256((out / s["source_file"]).read_bytes()).hexdigest() == s["source_sha256"]
        assert s["campaign_approval"] is False and s["review_method"] and s["scope"]
    targeted = json.loads((out / "evaluations" / "targeted-evals-v2.json").read_text())
    assert targeted["not_foundry_evals_service"] is True
    zava, rationale, control = targeted["checks"]
    assert zava["clip"] == "zava-silent-presentation-v1" and zava["result"]["label"] == "partial"
    assert rationale["route_model"] == control["route_model"] == "minimax-h3-max-turbo"
    assert rationale["grader_model"] != rationale["route_model"]
    assert (rationale["result"]["label"], control["result"]["label"]) == ("grounded", "ungrounded")


def test_disposition_refuses_changed_asset(tmp_path, monkeypatch):
    builder = _load_builder()
    data = builder.build_data()
    cache = tmp_path / "demo-cache"
    (cache / "evaluations").mkdir(parents=True)
    shutil.copyfile(REPO / "demo-cache" / "evaluations" / "demo-dispositions-v1.json",
                    cache / "evaluations" / "demo-dispositions-v1.json")
    (cache / "lto-hero-kling.mp4").write_bytes(b"not the reviewed source")
    monkeypatch.setattr(builder, "REPO", tmp_path)
    generations = [c for c in data["clips"] if c["record_kind"] == "generation"]
    with pytest.raises(SystemExit, match="asset hash mismatch"):
        builder._apply_dispositions(generations, data["accounts"])


def _move_first_learning_to_featured(doc):
    doc["featured"].append(doc["learning_cases"].pop(0))
    doc["unresolved_full_remediation"] -= 1


@pytest.mark.parametrize("breakage,message", [
    (_move_first_learning_to_featured, "only replacement-required examples are learning cases"),
    (lambda d: d["featured"].pop(), "every example exactly once"),
    (lambda d: d.update(customer_campaign_approved=True), "cannot approve campaigns"),
    (lambda d: d.update(full_remediation_complete=True), "cannot approve campaigns"),
    (lambda d: d["rejected_replacement_attempts"].update(selected=1), "must stay withheld and unselected"),
    (lambda d: d["featured"][0].update(sha256="0" * 64), "does not match its disposition"),
    (lambda d: d["learning_cases"][0].pop("unresolved_defect"), "must state its unresolved defect"),
    (lambda d: d.update(based_on="another-disposition-set"), "must name the dispositions it curates"),
])
def test_curated_scope_refuses_promotion_or_mismatch(tmp_path, monkeypatch, breakage, message):
    builder = _load_builder()
    data = builder.build_data()
    assert [a["curation"] for a in data["accounts"]].count("featured") == 8
    assert data["curated_release"]["customer_campaign_approved"] is False
    dispositions = json.loads((REPO / "demo-cache" / "evaluations" / "demo-dispositions-v1.json").read_text())
    doc = json.loads((REPO / "demo-cache" / "evaluations" / "curated-release-v1.json").read_text())
    breakage(doc)
    (tmp_path / "demo-cache" / "evaluations").mkdir(parents=True)
    (tmp_path / "demo-cache" / "evaluations" / "curated-release-v1.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(builder, "REPO", tmp_path)
    with pytest.raises(SystemExit, match=message):
        builder._apply_curation(dispositions, data["clips"], data["accounts"])


def test_embedded_overview_has_one_caption_presentation(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    index = (out / "index.html").read_text(encoding="utf-8")
    overview = re.search(r'<dialog class="overview".*?</dialog>', index, re.S)[0]
    assert "<track" not in overview, "burned captions must not receive a duplicate browser caption track"
    assert "Captions embedded" in overview
    assert 'href="sizzle/sku-to-scene-sizzle.vtt" download' in overview
    assert "Read the transcript" in overview
    assert (out / "sizzle" / "sku-to-scene-sizzle.vtt").read_bytes() == (
        REPO / "assets" / "sizzle" / "sku-to-scene-sizzle.vtt").read_bytes()


def test_disqualified_account_attempts_remain_evidence_not_previews(tmp_path):
    data = json.loads((_load_builder().build(tmp_path / "site") / "data.json").read_text(encoding="utf-8"))
    clips = {c["id"]: c for c in data["clips"]}
    measured = {c["id"]: c["qa"] for c in json.loads((REPO / "demo-cache" / "manifest.json").read_text())["clips"]}
    for c in data["clips"]:
        if c["id"] in measured and not c["baseline_original"]:
            assert c["media_duration_s"] == pytest.approx(6, abs=0.05)
            assert c["has_audio"] is False
    for a in data["accounts"]:
        for excluded in a.get("excluded_clips", []):
            c = clips[excluded["id"]]
            assert c["withheld_reason"] == excluded["reason"]
            assert c["qa"]["verdict"] == measured[c["id"]]["verdict"]
            assert c["qa"]["scores"] == measured[c["id"]]["scores"]
            assert c["id"] not in a["draft_clips"]
            assert c["id"] != a["recorded_clip"]
        if a["planned_clip"] and a["recorded_clip"]:
            c = clips[a["recorded_clip"]]
            assert not c["source_image"]
            assert c["has_audio"] is False
            assert a["hero_clip"] is None
            if c["presentation_audio_removed"]:
                assert c["original_file"]


def test_account_brief_uses_selected_recording_not_original_plan(tmp_path, monkeypatch):
    builder = _load_builder()
    shutil.copytree(REPO / "catalog", tmp_path / "catalog")
    shutil.copytree(REPO / "briefs", tmp_path / "briefs")
    shutil.copytree(REPO / "demo-cache", tmp_path / "demo-cache")
    manifest = json.loads((REPO / "demo-cache" / "manifest.json").read_text())
    account = next(a for a in json.loads((tmp_path / "catalog" / "accounts.json").read_text())["accounts"]
                   if a["id"] == "proseware")
    chosen = next(c for c in manifest["clips"] if c["id"] == account["replacement_clip"])
    chosen.update(model="ltx-2.5-pro", prompt="The effective stationary replacement, not the original cart.",
                  estimate={"estimate_usd": 0.72, "price_key": "720p", "usd_per_second": 0.12})
    (tmp_path / "demo-cache" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(builder, "REPO", tmp_path)
    data = builder.build_data()
    shown = next(a for a in data["accounts"] if a["id"] == "proseware")
    assert shown["brief"] == chosen["prompt"]
    assert shown["model"] == chosen["model"] and shown["model_name"] == "LTX-2.5 Pro"
    assert shown["tier"] == "720p" and shown["estimate_usd"] == 0.72
    assert "LTX-2.5 Pro" in shown["why"]
    assert shown["recorded_clip"] == chosen["id"]


def test_generated_asset_versions_follow_published_content(tmp_path, monkeypatch):
    builder = _load_builder()
    original = builder.build(tmp_path / "original")
    versions = {}
    for name in ("app.js", "app.css"):
        versions[name] = hashlib.sha256((original / name).read_bytes()).hexdigest()[:16]
        assert f'"{name}?v={versions[name]}"' in (original / "index.html").read_text(encoding="utf-8")

    copy = builder.shutil.copy2

    def changed_asset(src, dst):
        result = copy(src, dst)
        if Path(src).name in versions:
            with Path(dst).open("a", encoding="utf-8") as file:
                file.write("\n/* regression: changed asset content */\n")
        return result

    monkeypatch.setattr(builder.shutil, "copy2", changed_asset)
    changed = builder.build(tmp_path / "changed")
    index = (changed / "index.html").read_text(encoding="utf-8")
    for name, old_version in versions.items():
        version = hashlib.sha256((changed / name).read_bytes()).hexdigest()[:16]
        assert version != old_version
        assert f'"{name}?v={version}"' in index
        assert f'"{name}?v={old_version}"' not in index


def test_site_artifact_uses_required_theme(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    css = (out / "app.css").read_text(encoding="utf-8")
    names = (
        "bg", "bg-elevated", "surface", "surface-soft", "border", "border-strong",
        "text", "text-muted", "text-soft", "accent", "accent-hover", "accent-soft",
        "accent-fg", "success", "danger", "warning", "link", "shadow", "overlay",
        "panel", "panel-strong", "sheen", "highlight",
        "success-text", "warning-text", "danger-text", "text-secondary", "link-text",
    )
    palettes = {
        ":root": (
            "#f7f4ef", "#fcfbf8", "#ffffff", "#f5f5f5", "#dedede", "#919191",
            "#242424", "#5c5c5c", "#6f6f6f", "#b11f4b", "#9a1a41", "rgba(177, 31, 75, 0.08)",
            "#ffffff", "#16a34a", "#dc2626", "#f59e0b", "#0078d4", "0 18px 48px rgba(0, 0, 0, 0.12)",
            "rgba(255, 255, 255, 0.8)", "rgba(255, 255, 255, 0.86)", "rgba(255, 255, 255, 0.96)",
            "rgba(255, 255, 255, 0.55)", "rgba(177, 31, 75, 0.12)",
            "#15803d", "#a15c07", "#b91c1c", "#5c5c5c", "#0067b8",
        ),
        'html[data-theme="dark"]': (
            "#3d3b3a", "#343231", "#292929", "#2e2e2e", "#474747", "#5f5f5f",
            "#dedede", "#919191", "#b0b0b0", "#fd8ea1", "#fb7b91", "rgba(253, 142, 161, 0.14)",
            "#1a1a1a", "#4ade80", "#f87171", "#fbbf24", "#4da6ff", "0 18px 48px rgba(0, 0, 0, 0.32)",
            "rgba(41, 41, 41, 0.88)", "rgba(41, 41, 41, 0.72)", "rgba(41, 41, 41, 0.96)",
            "rgba(255, 255, 255, 0.04)", "rgba(253, 142, 161, 0.12)",
            "#4ade80", "#fbbf24", "#fca5a5", "#b0b0b0", "#7cbcff",
        ),
    }
    components = css
    for selector, values in palettes.items():
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert match, f"missing {selector} theme in generated app.css"
        actual = dict(re.findall(r"(--cp-[\w-]+)\s*:\s*([^;]+);", match.group(1)))
        expected = {f"--cp-{name}": value for name, value in zip(names, values, strict=True)}
        assert actual == expected, f"incorrect {selector} theme in generated app.css"
        components = components.replace(match.group(0), "")

    assert not re.search(r"#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?)\(", components, re.IGNORECASE)
    assert "gradient(" not in components.lower()
    assert "backdrop-filter" not in components.lower()
    assert set(re.findall(r"var\((--cp-[\w-]+)", components)) <= {f"--cp-{name}" for name in names}


def _theme_tokens(css, selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return dict(re.findall(r"--cp-([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", match.group(1)))


def _contrast(fg, bg):
    def luminance(hex_color):
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("selector", [":root", 'html[data-theme="dark"]'])
def test_status_and_secondary_text_meet_wcag_aa(tmp_path, selector):
    css = (_load_builder().build(tmp_path / "site") / "app.css").read_text(encoding="utf-8")
    tokens = _theme_tokens(css, selector)
    failures = [
        f"{fg} on {bg}: {_contrast(tokens[fg], tokens[bg]):.2f}"
        for fg in ("success-text", "warning-text", "danger-text", "text-secondary", "link-text", "text", "accent")
        for bg in ("bg", "bg-elevated", "surface", "surface-soft")
        if _contrast(tokens[fg], tokens[bg]) < 4.5
    ]
    assert not failures, f"{selector} text below 4.5:1 — {failures}"
    # Text-bearing status components must use the accessible -text tokens, never the raw status fills.
    for rule in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if "pill" in rule[0] or "readiness" in rule[0] or "calc-error" in rule[0] or ".issue" in rule[0]:
            assert not re.search(r"(?<![-\w])color:\s*var\(--cp-(success|warning|danger)\)", rule[1]), rule[0].strip()


def test_theme_segment_semantics_and_indicator_contrast(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    css = (out / "app.css").read_text(encoding="utf-8")
    assert 'id="theme-toggle" role="radiogroup" aria-label="Color theme"' in html
    for name in ("Light", "Dark"):
        assert f'aria-label="{name} theme" title="{name} theme"' in html
    assert html.count('role="radio"') == 2
    assert ".theme-toggle button:focus-visible" in css
    assert "min-width: 44px; min-height: 44px" in css
    for selector in (":root", 'html[data-theme="dark"]'):
        t = _theme_tokens(css, selector)
        assert _contrast(t["accent"], t["surface"]) >= 3


def _painted_box(png_path, threshold=24):
    """Bounding box of pixels with alpha > threshold in an 8-bit RGBA PNG (stdlib only; no Pillow)."""
    data = png_path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", png_path
    pos, idat, header = 8, b"", None
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    width, height = int.from_bytes(header[:4], "big"), int.from_bytes(header[4:8], "big")
    assert header[8:13] == bytes([8, 6, 0, 0, 0]), f"{png_path.name} must be non-interlaced 8-bit RGBA"
    raw, stride, prev = zlib.decompress(idat), width * 4, bytearray(width * 4)
    xs, ys = [], []
    for y in range(height):
        kind, row = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            left = row[i - 4] if i >= 4 else 0
            up, corner = prev[i], (prev[i - 4] if i >= 4 else 0)
            if kind == 1:
                row[i] = (row[i] + left) & 255
            elif kind == 2:
                row[i] = (row[i] + up) & 255
            elif kind == 3:
                row[i] = (row[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                row[i] = (row[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        painted = [x for x in range(width) if row[x * 4 + 3] > threshold]
        if painted:
            xs += (painted[0], painted[-1])
            ys.append(y)
        prev = row
    return (width, height), (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def test_light_and_dark_header_logos_paint_at_the_same_size(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    (size_l, (l0, t0, r0, b0)), (size_d, (l1, t1, r1, b1)) = (
        _painted_box(out / "brand" / f"logo-horizontal-{theme}.png") for theme in ("light", "dark"))
    assert size_l == size_d == (840, 176), "both themes share one header box"
    assert abs((r0 - l0) - (r1 - l1)) <= 1, f"painted widths differ: {r0 - l0} vs {r1 - l1}"
    assert abs((b0 - t0) - (b1 - t1)) <= 4, f"painted heights differ: {b0 - t0} vs {b1 - t1}"
    assert l0 == l1, "the same left inset keeps the wordmark aligned when the theme changes"
    assert abs((t0 + b0) - (t1 + b1)) <= 2, "both marks are vertically centred"


def test_compact_guide_has_one_example_selector_and_recorded_thumbnails(tmp_path):
    out = _load_builder().build(tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert html.count('id="guide-example"') == 1
    assert 'aria-label="Industry and fictional example"' in html
    assert 'id="guide-areas"' not in html and 'id="guide-steps"' not in html
    assert 'id="guide-heading" tabindex="-1"' in html
    assert 'id="guide-status" aria-live="polite"' in html
    assert sorted(p.name for p in (out / "posters").glob("*.png")) == [
        "lto-draft-1.png", "lto-draft-2.png", "lto-draft-3.png"]
    for p in (out / "posters").glob("*.png"):
        assert p.read_bytes() == (REPO / "site" / "posters" / p.name).read_bytes()
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    clips = {c["id"]: c for c in data["clips"]}
    guided = {a["recorded_clip"] for a in data["accounts"]}
    guided.update(c for a in data["accounts"] for c in a["draft_clips"] if clips[c]["file"])
    posters = {p.stem for p in (out / "posters").glob("*.jpg")}
    assert guided <= posters, "every selected recording and concept needs its own poster"
    assert posters <= clips.keys(), "retained historical posters must still identify a real recording"
    for clip_id in guided:
        poster = out / "posters" / f"{clip_id}.jpg"
        assert poster.read_bytes().startswith(b"\xff\xd8"), clip_id
        assert poster.read_bytes() == (REPO / "site" / "posters" / poster.name).read_bytes()
