"""Build the static browser demo into a curated directory (default: _site/) for GitHub Pages.

Only an explicit allowlist is published: the site shell (site/), brand marks (assets/brand), approved product
images (assets/products), the cached authentic Foundry renders (demo-cache/*.mp4), sanitized evaluation results
(demo-cache/evaluations/), the 720p overview video and WebVTT captions (assets/sizzle/) with its poster, and a
data.json derived from
public repo data (demo-cache/manifest.json, catalog/, briefs/, model registry). The repo root, .env, .sku2scene/
run outputs and anything else are never copied. The page makes no cloud calls.

    python scripts/build_site.py [--out _site]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from sku_to_scene import models, payloads  # noqa: E402
from sku_to_scene.lto import CONCEPTS  # noqa: E402

ALLOWED_SUFFIXES = {".html", ".css", ".js", ".json", ".png", ".mp4", ".vtt", ".nojekyll"}
# Sanitized Foundry Evals results and human-review findings (written by scripts/run_foundry_evals.py / by hand).
EVAL_FILES = ("foundry-evals-v1.json", "human-review.json")
# Same-origin 720p web copy of the release media-v1 overview video plus WebVTT captions (see assets/sizzle/SOURCE.md).
SIZZLE_FILES = ("sku-to-scene-sizzle-720p.mp4", "sku-to-scene-sizzle.vtt")
# Ordered for the guided story; "label"/"story" are plain-language, "title"/"use_case"/"why" keep the technical framing.
SCENARIOS = [
    {"vertical": "qsr", "guide": "qsr", "title": "QSR, Coffee & Convenience", "label": "QSR, Coffee & Convenience",
     "story": "Compare seasonal offer concepts quickly, then review one recorded final video.",
     "accounts": "McDonald's, Starbucks, 7-Eleven",
     "use_case": "Rapid LTO social ads: iterate cheap drafts, then render the winner with native audio.",
     "why": "Fast tiers (LTX-2.5 Fast, MiniMax Turbo) for drafts; Kling v3 Pro image-to-video + audio for the hero.",
     "clips": ["lto-hero-kling"]},
    {"vertical": "apparel", "guide": "apparel", "title": "Apparel & Home Decor", "label": "Apparel & Home Decor",
     "story": "Bring an approved product image to life for product pages and lookbooks.",
     "accounts": "Gap, TJX, Target, Costco",
     "use_case": "PDP image-to-video lookbook: animate the approved studio shot with fabric movement.",
     "why": "Kling v3 Pro keeps SKU fidelity from the approved PIM image while adding fabric physics and camera motion.",
     "clips": ["hero-apparel-kling"]},
    {"vertical": "home-improvement", "guide": "home", "title": "Home Improvement & Electronics",
     "label": "Home improvement & electronics",
     "story": "Show products in use while checking product details and layout.",
     "accounts": "The Home Depot, Lowe's, Best Buy, Staples",
     "use_case": "In-context previews: products on a job site or in a styled outdoor scene.",
     "why": "Kling v3 Pro handles physical interaction; MiniMax H3 Max follows strict multi-object layout prompts.",
     "clips": ["hero-home-kling", "hero-patio-h3max"]},
    {"vertical": "grocery-pharmacy", "guide": "grocery", "title": "Grocery & Pharmacy", "label": "Grocery & Pharmacy",
     "story": "Explore lower-cost variations for frequent local promotions.",
     "accounts": "Kroger, Albertsons, Walgreens",
     "use_case": "High-volume weekly circulars and digital endcaps, localized at scale.",
     "why": "MiniMax H3 Max Turbo is half the per-second rate of H3 Max, so high-SKU personalization is affordable.",
     "clips": ["hero-grocery-turbo"]},
]


def _title(prompt: str) -> str | None:
    m = re.search(r"(?:Storyboard draft|Hero cut of) '([^']+)'", prompt or "")
    return m.group(1) if m else None


def _variant(title: str | None) -> int | None:
    for i, (t, _s) in enumerate(CONCEPTS, start=1):
        if t == title:
            return i
    return None


def _qa(q: dict) -> dict:
    cs = q.get("content_safety") or []
    sev = [c.get("severity", 0) for fr in cs for c in fr.get("categories", [])]
    return {
        "evaluator": q.get("evaluator"), "measured": q.get("measured"), "verdict": q.get("verdict"),
        "scores": q.get("scores"), "thresholds": q.get("thresholds"), "failed_checks": q.get("failed_checks", []),
        "findings": q.get("findings", []), "hallucinated_objects": q.get("hallucinated_objects", []),
        "content_safety_frames": len(cs), "content_safety_max_severity": max(sev) if sev else None,
        "reroll": q.get("reroll"), "automated_checks_passed": q.get("automated_checks_passed"),
        "human_signoff_required": q.get("human_signoff_required"), "publish_approved": q.get("publish_approved"),
    }


def _duration_constraints(m: models.ModelSpec) -> dict:
    """Per price tier, the durations the real payload validator accepts (default FPS), so the page can't drift."""
    if m.duration_range:
        lo, hi = m.duration_range
        return {"duration_range": [lo, hi], "durations_by_tier": None, "default_duration": m.default_duration}
    by_tier = {}
    for tier in m.price_per_second:
        ok = []
        for d in m.durations:
            if d == "auto":
                continue
            try:
                if m.key.startswith("ltx"):
                    payloads._ltx_duration(m, d, tier, 25)
                else:
                    payloads._kling_duration(m, d)
            except payloads.PayloadError:
                continue
            ok.append(int(d))
        by_tier[tier] = ok
    return {"duration_range": None, "durations_by_tier": by_tier, "default_duration": m.default_duration,
            "supports_auto": "auto" in m.durations}


def build_data() -> dict:
    manifest = json.loads((REPO / "demo-cache" / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((REPO / "catalog" / "products.json").read_text(encoding="utf-8"))["products"]
    brands = json.loads((REPO / "catalog" / "brands.json").read_text(encoding="utf-8"))["brands"]
    brief = json.loads((REPO / "briefs" / "qsr-lto-pumpkin-cold-brew.json").read_text(encoding="utf-8"))
    by_key = {m.key: m for m in models.REGISTRY.values()}

    products = {}
    for p in catalog:
        img = p.get("image")
        products[p["sku"]] = {
            "sku": p["sku"], "name": p["name"], "brand": brands.get(p["brand"], {}).get("display_name", p["brand"]),
            "vertical": p["vertical"], "image": f"products/{Path(img).name}" if img else None,
            "image_status": p.get("image_status"),
        }

    clips = []
    for c in manifest["clips"]:
        if c.get("provenance") != "foundry":
            raise SystemExit(f"refusing to publish non-authentic clip {c['id']} as a recorded render")
        title = _title(c.get("prompt", ""))
        est = c.get("estimate") or {}
        clips.append({
            "id": c["id"], "sku": c["sku"], "vertical": c["vertical"], "model": c["model"],
            "model_name": by_key[c["model"]].display_name, "mode": c["mode"], "aspect_ratio": c["aspect_ratio"],
            "requested_duration_s": c.get("duration"), "file": f"media/{c['file']}", "provenance": c["provenance"],
            "has_audio": (c.get("media") or {}).get("has_audio"), "audio": c.get("audio"),
            "media_duration_s": (c.get("media") or {}).get("duration_s"),
            "accepted_to_completed_s": c.get("accepted_to_completed_s"), "elapsed_s": c.get("elapsed_s"),
            "request_id": c.get("request_id"), "rendered_at": c.get("rendered_at"),
            "estimate_usd": est.get("estimate_usd"), "price_key": est.get("price_key"),
            "usd_per_second": est.get("usd_per_second"), "prompt": c.get("prompt"),
            "source_image": f"products/{Path(c['source_image']).name}" if c.get("source_image") else None,
            "concept": title, "variant": _variant(title), "qa": _qa(c["qa"]),
            "qa_evaluated_at": c.get("qa_evaluated_at"),
            "account": c.get("account"), "stage": c.get("stage"),
            "presentation_audio_removed": c.get("presentation_audio_removed", False),
            "presentation_trimmed_to_s": c.get("presentation_trimmed_to_s"),
            "qa_sampled_from": c.get("qa_sampled_from"),
            "original_file": f"media/{c['original_file']}" if c.get("original_file") else None,
        })
    ids = {c["id"]: c for c in clips}
    accounts = json.loads((REPO / "catalog" / "accounts.json").read_text(encoding="utf-8"))["accounts"]
    exclusions = {
        e["id"]: e["reason"]
        for a in accounts
        for e in a.get("excluded_clips", [])
    }
    learning = {
        e["id"]: e["note"]
        for a in accounts
        for e in a.get("learning_clips", [])
    }
    for c in clips:
        c["withheld_reason"] = exclusions.get(c["id"])
        c["learning_note"] = learning.get(c["id"])
        if c["withheld_reason"]:
            # Withheld attempts stay as screening evidence only; their media is never published.
            c["file"] = None
            c["original_file"] = None
    if set(learning) & set(exclusions):
        raise SystemExit("a withheld clip cannot also be a learning example")

    drafts = [ids[f"lto-draft-{i}"] for i in (1, 2, 3)]
    for i, d in enumerate(drafts, start=1):
        if d["variant"] != i:
            raise SystemExit(f"lto-draft-{i} prompt does not match concept #{i}")
    hero = ids["lto-hero-kling"]
    if hero["variant"] is None:
        raise SystemExit("cached LTO hero has no identifiable concept")

    for a in accounts:
        m = by_key[a["model"]]
        a["model_name"] = m.display_name
        a["estimate_usd"] = float(m.price_per_second[a["tier"]]) * a["duration"]
        selected = a.get("replacement_clip") or a["planned_clip"]
        excluded = {c["id"] for c in a.get("excluded_clips", [])}
        if selected in ids and selected not in excluded:
            a["draft_clips"] = [selected]
            a["recorded_clip"] = selected
        elif selected and a["planned_clip"]:
            raise SystemExit(f"{a['id']}: selected example {selected} is missing or withheld")
        for e in a.get("learning_clips", []):
            if e["id"] not in ids or ids[e["id"]]["account"] != a["id"] or e["id"] == selected:
                raise SystemExit(f"{a['id']}: invalid learning example {e['id']}")
            if ids[e["id"]]["qa"]["verdict"] == "pass":
                raise SystemExit(f"{e['id']}: a passing clip is not a QA learning example")
        a["brief"] = None
        if a["brief_file"]:
            doc = json.loads((REPO / "briefs" / a["brief_file"]).read_text(encoding="utf-8"))
            a["brief"] = doc.get("presenter_prompt") or doc["prompt"]
        if a["planned_clip"] and selected in ids and selected not in excluded:
            recorded = ids[selected]
            a.update(brief=recorded["prompt"], model=recorded["model"], model_name=recorded["model_name"],
                     tier=recorded["price_key"], duration=recorded["requested_duration_s"],
                     aspect_ratio=recorded["aspect_ratio"], estimate_usd=recorded["estimate_usd"])
            if recorded["model"] != m.key:
                a["why"] = f"Recorded replacement on {recorded['model_name']} ({recorded['mode']}); inspect its QA evidence."
        if a["hero_clip"] and not ids[a["hero_clip"]]["source_image"]:
            raise SystemExit(f"{a['id']} cannot claim an approved-PIM hero without a reference image")

    neg = (manifest.get("validation") or {}).get("negative_control")
    return {
        "note": "Derived from demo-cache/manifest.json. Recorded authentic Foundry renders; replay only.",
        "products": products,
        "accounts": accounts,
        "models": [{
            "key": m.key, "name": m.display_name, "modes": list(m.modes), "offering": m.offering,
            "text_aspect_ratios": list(m.t2v_aspect_ratios),
            "price_per_second_usd": dict(m.price_per_second), "native_audio": m.native_audio,
            "speed_tier": m.speed_tier, "strengths": list(m.strengths), **_duration_constraints(m),
        } for m in models.REGISTRY.values()],
        "clips": clips,
        "lto": {
            "sku": brief["sku_id"], "channel": brief["channel"], "presenter_prompt": brief["presenter_prompt"],
            "hero_prompt": brief["prompt"],
            "concepts": [{"variant": i, "title": t, "setting": s} for i, (t, s) in enumerate(CONCEPTS, start=1)],
            "drafts": [d["id"] for d in drafts], "hero_clip": hero["id"], "hero_variant": hero["variant"],
        },
        "negative_control": None if not neg else {
            "description": neg.get("description"), "reference_sku": neg.get("reference_sku"),
            "source_request_id": neg.get("source_request_id"), "qa": _qa(neg["qa"]),
        },
        "scenarios": SCENARIOS,
    }


def build(out: Path) -> Path:
    if out.resolve() == REPO.resolve() or REPO.resolve().is_relative_to(out.resolve()):
        raise SystemExit("refusing to build into the repository root")
    if out.exists():
        shutil.rmtree(out)
    (out / "brand" / "original").mkdir(parents=True)
    (out / "products").mkdir()
    (out / "media").mkdir()
    for name in ("index.html", "app.css", "app.js"):
        shutil.copy2(REPO / "site" / name, out / name)
    index = (out / "index.html").read_text(encoding="utf-8")
    for name in ("app.css", "app.js"):
        version = hashlib.sha256((out / name).read_bytes()).hexdigest()[:16]
        index = index.replace(f'"{name}"', f'"{name}?v={version}"')
    (out / "index.html").write_text(index, encoding="utf-8")
    for f in (REPO / "assets" / "brand" / "web").glob("*.png"):
        shutil.copy2(f, out / "brand" / f.name)
    for f in (REPO / "assets" / "brand").glob("sku-to-scene-*.png"):
        shutil.copy2(f, out / "brand" / "original" / f.name)
    for f in (REPO / "assets" / "products").glob("*.png"):
        shutil.copy2(f, out / "products" / f.name)
    data = build_data()
    for c in data["clips"]:
        if not c["file"]:
            continue
        shutil.copy2(REPO / "demo-cache" / Path(c["file"]).name, out / c["file"])
        if c["original_file"]:
            shutil.copy2(REPO / "demo-cache" / Path(c["original_file"]).name, out / c["original_file"])
    (out / "evaluations").mkdir()
    for name in EVAL_FILES:
        src = REPO / "demo-cache" / "evaluations" / name
        doc = json.loads(src.read_text(encoding="utf-8"))
        (out / "evaluations" / name).write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False),
                                                 encoding="utf-8")
    (out / "sizzle").mkdir()
    for name in SIZZLE_FILES:
        shutil.copy2(REPO / "assets" / "sizzle" / name, out / "sizzle" / name)
    shutil.copy2(REPO / "docs" / "images" / "sku-to-scene-sizzle-thumbnail.png",
                 out / "sizzle" / "sku-to-scene-sizzle-poster.png")
    (out / "data.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    verify(out)
    return out


def verify(out: Path) -> None:
    for f in out.rglob("*"):
        if f.is_dir():
            continue
        if f.suffix not in ALLOWED_SUFFIXES and f.name != ".nojekyll":
            raise SystemExit(f"unexpected file in site artifact: {f}")
        if f.name.startswith(".env") or ".sku2scene" in f.parts:
            raise SystemExit(f"private file in site artifact: {f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(REPO / "_site"))
    out = build(Path(ap.parse_args().out))
    files = [f for f in out.rglob("*") if f.is_file()]
    print(f"built {out} ({len(files)} files, {sum(f.stat().st_size for f in files) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
