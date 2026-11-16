import importlib.util
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("mutation", [None, "choose", "reset"])
def test_playback_transitions_pause_hidden_and_replaced_players(tmp_path, mutation):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser event-handler regression")
    out = _load_builder().build(tmp_path / "site")
    source = REPO / "site" / "app.js"
    if mutation:
        text = source.read_text(encoding="utf-8")
        before = ("      pausePlayers(playingDraft);" if mutation == "choose"
                  else "      pausePlayers();\n      selected = null;")
        after = "" if mutation == "choose" else "      selected = null;"
        assert before in text
        source = tmp_path / "mutated.js"
        source.write_text(text.replace(before, after, 1), encoding="utf-8")
    result = subprocess.run(
        [node, str(REPO / "tests" / "playback.cjs"), str(source)],
        input=(out / "data.json").read_text(encoding="utf-8"),
        cwd=REPO, capture_output=True, text=True,
    )
    if mutation:
        assert result.returncode != 0
        expected = ("choosing a different concept pauses the old draft" if mutation == "choose"
                    else "reset pauses the hidden hero")
        assert expected in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "playback transitions passed" in result.stdout


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
    for name in ("foundry-evals-v1.json", "human-review.json"):
        assert json.loads((out / "evaluations" / name).read_text(encoding="utf-8"))
    assert len(data["clips"]) == 8
    assert all((out / c["file"]).is_file() for c in data["clips"])
    hero = next(c for c in data["clips"] if c["id"] == data["lto"]["hero_clip"])
    # Only the recorded variant may claim a hero render.
    assert data["lto"]["hero_variant"] == hero["variant"] == 2
    blob = json.dumps(data).lower()
    for leaked in ("services.ai.azure.com", "cognitiveservices.azure.com", "tenant", "subscription"):
        assert leaked not in blob


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
    )
    palettes = {
        ":root": (
            "#f7f4ef", "#fcfbf8", "#ffffff", "#f5f5f5", "#dedede", "#919191",
            "#242424", "#5c5c5c", "#6f6f6f", "#b11f4b", "#9a1a41", "rgba(177, 31, 75, 0.08)",
            "#ffffff", "#16a34a", "#dc2626", "#f59e0b", "#0078d4", "0 18px 48px rgba(0, 0, 0, 0.12)",
            "rgba(255, 255, 255, 0.8)", "rgba(255, 255, 255, 0.86)", "rgba(255, 255, 255, 0.96)",
            "rgba(255, 255, 255, 0.55)", "rgba(177, 31, 75, 0.12)",
        ),
        'html[data-theme="dark"]': (
            "#3d3b3a", "#343231", "#292929", "#2e2e2e", "#474747", "#5f5f5f",
            "#dedede", "#919191", "#b0b0b0", "#fd8ea1", "#fb7b91", "rgba(253, 142, 161, 0.14)",
            "#1a1a1a", "#4ade80", "#f87171", "#fbbf24", "#4da6ff", "0 18px 48px rgba(0, 0, 0, 0.32)",
            "rgba(41, 41, 41, 0.88)", "rgba(41, 41, 41, 0.72)", "rgba(41, 41, 41, 0.96)",
            "rgba(255, 255, 255, 0.04)", "rgba(253, 142, 161, 0.12)",
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
