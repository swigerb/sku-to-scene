"""Build the SIMULATED fallback clips in demo-cache/ and write demo-cache/manifest.json.

Every clip produced here is an ffmpeg Ken Burns pan over an approved product still (or a flat
background for text-only SKUs) with a burned-in "SIMULATED PREVIEW - not a Foundry render" banner.
Audio, where present, is a synthetic brown-noise bed - NOT model-generated audio.
`rehearsal_qa` values are scripted so presenters can rehearse the QA/re-roll branch; they are not
measurements. Replace these clips with real renders via scripts/precache.py once endpoints exist.

Usage:  python scripts/build_placeholders.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sku_to_scene.media import have_ffmpeg, probe, render_placeholder  # noqa: E402

CACHE = ROOT / "demo-cache"
REHEARSAL = "SCRIPTED REHEARSAL VALUES - not a measurement"

CLIPS = [
    # --- Step 2: LTO two-tier flow (Northwind Pumpkin Cold Brew) ---------------------------------
    dict(id="lto-draft-1", sku="NWC-LTO-PCB-16", vertical="qsr", model="minimax-h3-max-turbo",
         mode="text-to-video", aspect_ratio="9:16", duration=6, audio=False, hue=0, zoom=1,
         image="assets/products/nwc-pumpkin-cold-brew-hero.png",
         label="Draft #1 Harvest Market | MiniMax H3 Max Turbo | T2V 768P",
         rehearsal_qa={"scores": {"logo_integrity": 0.85, "label_legibility": 0.75, "product_fidelity": 0.82, "prompt_adherence": 0.74}, "findings": [
             "Rehearsal script: market setting reads clearly; pumpkins present."]}),
    dict(id="lto-draft-2", sku="NWC-LTO-PCB-16", vertical="qsr", model="ltx-2.5-fast",
         mode="text-to-video", aspect_ratio="9:16", duration=6, audio=False, hue=-12, zoom=-1,
         image="assets/products/nwc-pumpkin-cold-brew-hero.png",
         label="Draft #2 First Frost Commute | LTX-2.5 Fast | T2V 720p",
         rehearsal_qa={"scores": {"logo_integrity": 0.88, "label_legibility": 0.8, "product_fidelity": 0.85, "prompt_adherence": 0.86}, "findings": [
             "Rehearsal script: strongest match to brief; leaves and cafe ledge present."]}),
    dict(id="lto-draft-3", sku="NWC-LTO-PCB-16", vertical="qsr", model="minimax-h3-max-turbo",
         mode="text-to-video", aspect_ratio="9:16", duration=6, audio=False, hue=18, zoom=1,
         image="assets/products/nwc-pumpkin-cold-brew-hero.png",
         label="Draft #3 Desert Fall Evening | MiniMax H3 Max Turbo | T2V 768P",
         rehearsal_qa={"scores": {"logo_integrity": 0.84, "label_legibility": 0.76, "product_fidelity": 0.81, "prompt_adherence": 0.66}, "findings": [
             "Rehearsal script: string lights missing; below 0.70 adherence threshold."]}),
    dict(id="lto-hero-kling", sku="NWC-LTO-PCB-16", vertical="qsr", model="kling-v3-pro",
         mode="image-to-video", aspect_ratio="9:16", duration=8, audio=True, hue=0, zoom=1,
         image="assets/products/nwc-pumpkin-cold-brew-hero.png",
         label="Variant #2 HERO | Kling v3 Pro | I2V + audio\nNorthwind Pumpkin Cold Brew",
         rehearsal_qa={"scores": {"logo_integrity": 0.9, "label_legibility": 0.85, "product_fidelity": 0.9,
                                  "prompt_adherence": 0.88},
                       "findings": ["Rehearsal script: logo upright; foam and condensation preserved."]}),
    # --- One hero per vertical ------------------------------------------------------------------
    dict(id="hero-apparel-kling", sku="FAB-JKT-QLT-RST-M", vertical="apparel", model="kling-v3-pro",
         mode="image-to-video", aspect_ratio="1:1", duration=5, audio=False, hue=0, zoom=1,
         image="assets/products/fabrikam-quilted-jacket-rust.png",
         label="PDP lookbook | Kling v3 Pro | I2V 1:1\nFabrikam Quilted Field Jacket"),
    dict(id="hero-home-kling", sku="CTP-DRL-20V-BL", vertical="home-improvement", model="kling-v3-pro",
         mode="image-to-video", aspect_ratio="16:9", duration=5, audio=False, hue=0, zoom=-1,
         image="assets/products/contoso-pro-20v-drill.png",
         label="In-context job site | Kling v3 Pro | I2V 16:9\nContoso Pro 20V Drill"),
    dict(id="hero-patio-h3max", sku="FAB-HOME-PATIO-5PC", vertical="home-improvement", model="minimax-h3-max",
         mode="text-to-video", aspect_ratio="16:9", duration=6, audio=False, hue=0, zoom=1, image=None,
         label="Strict layout (text brief) | MiniMax H3 Max | T2V 1080P\nFabrikam Home Patio Set - no image in PIM"),
    dict(id="hero-grocery-turbo", sku="WGW-BND-FLU-01", vertical="grocery-pharmacy", model="minimax-h3-max-turbo",
         mode="image-to-video", aspect_ratio="16:9", duration=6, audio=False, hue=0, zoom=1,
         image="assets/products/woodgrove-wellness-bundle.png",
         label="Weekly endcap at scale | MiniMax H3 Max Turbo | I2V 768P\nWoodgrove Wellness Flu Season Bundle"),
]


def main() -> int:
    if not have_ffmpeg():
        print("ffmpeg is required to build placeholders", file=sys.stderr)
        return 1
    CACHE.mkdir(exist_ok=True)
    manifest = {
        "_note": ("All clips with provenance 'simulated' are local ffmpeg placeholders, NOT Foundry renders. "
                  "scripts/precache.py replaces entries with provenance 'foundry' after a real render."),
        "clips": [],
    }
    for c in CLIPS:
        out = CACHE / f"{c['id']}.mp4"
        img = ROOT / c["image"] if c["image"] else None
        render_placeholder(out, c["label"], img, c["aspect_ratio"], c["duration"], c["hue"], c["audio"], c["zoom"])
        entry = {k: c[k] for k in ("id", "sku", "vertical", "model", "mode", "aspect_ratio", "duration")}
        entry.update(
            file=out.name,
            provenance="simulated",
            audio="synthetic noise bed (placeholder, not generated audio)" if c["audio"] else "none",
            source_image=c["image"],
            media=probe(out),
        )
        if "rehearsal_qa" in c:
            entry["rehearsal_qa"] = {**c["rehearsal_qa"], "label": REHEARSAL}
        manifest["clips"].append(entry)
        print(f"built {out.relative_to(ROOT)} ({entry['media']['size_bytes'] // 1024} KB)")
    (CACHE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
