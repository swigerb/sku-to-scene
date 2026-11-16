import importlib.util
import hashlib
import json
import re
import shutil
import subprocess
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
    "step-pause": ("      pausePlayers();\n      players = {};", "      players = {};", "ok",
                   "moving on pauses the replaced hero"),
    "clip-count": ("!Number.isSafeInteger(Number(raw)) || ", "", "ok", "unsafe integers are rejected"),
    "finding-validation": ("HR = validReview(hr) ? hr : null;", "HR = hr;", "hr-empty-finding",
                           "Human-review evidence unavailable"),
    "view-pause": ("    if (changed) pausePlayers();\n", "", "ok", "hiding a view pauses its players"),
    "evidence-deep-links": ('routing: "evidence", qa: "evidence", evals: "evidence"', "", "ok",
                            "#routing opens the evidence view"),
    "draft-readiness": ("\n          readinessPill(c)),", "),", "ok", "publication readiness outside Inspect evidence"),
    "custom-duration": ("wasShown && Number.isFinite(keep) && keep >= lo && keep <= hi ? raw : String(m.default_duration)",
                        "String(m.default_duration)", "ok", "a tier change keeps a valid custom MiniMax duration"),
}


def _harness_input(out):
    return json.dumps({
        "data": json.loads((out / "data.json").read_text(encoding="utf-8")),
        "ev": json.loads((out / "evaluations" / "foundry-evals-v1.json").read_text(encoding="utf-8")),
        "hr": json.loads((out / "evaluations" / "human-review.json").read_text(encoding="utf-8")),
        "theme_script": re.search(r"<script>(.*?)</script>", (out / "index.html").read_text(encoding="utf-8"), re.S)[1],
    })


@pytest.mark.parametrize("mode,mutation", [("ok", None), *((m, None) for m in HR_MODES + THEME_MODES),
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
        assert (f"human-review {mode} handled" if mode in HR_MODES else "guided demo, tabs and calculator passed") in result.stdout


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
    assert {p.suffix for p in files} <= {".html", ".js", ".css", ".json", ".png", ".mp4", ".vtt", ""}
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


def test_disqualified_account_attempts_remain_evidence_not_previews(tmp_path):
    data = json.loads((_load_builder().build(tmp_path / "site") / "data.json").read_text(encoding="utf-8"))
    clips = {c["id"]: c for c in data["clips"]}
    measured = {c["id"]: c["qa"] for c in json.loads((REPO / "demo-cache" / "manifest.json").read_text())["clips"]}
    for c in data["clips"]:
        if c["account"]:
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
    (tmp_path / "demo-cache").mkdir()
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
