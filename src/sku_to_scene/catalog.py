"""Mock PIM catalog access and the merchandiser's structured scene-prompt composer."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

CATALOG_DIR = REPO_ROOT / "catalog"

CAMERA_BY_VERTICAL = {
    "qsr": "slow dolly-in, macro on condensation, golden hour rim lighting",
    "apparel": "slow 360-degree orbit, soft key light, gentle breeze moving the fabric",
    "home-improvement": "handheld push-in to medium close-up, warm late-afternoon sun, shallow depth of field",
    "electronics": "smooth slider move left to right, soft window light, clean desk",
    "grocery-pharmacy": "locked-off tabletop shot with a gentle push-in, soft diffused morning light",
}


@lru_cache(maxsize=1)
def _load(name: str) -> dict[str, Any]:
    return json.loads((CATALOG_DIR / name).read_text(encoding="utf-8"))


def products() -> list[dict[str, Any]]:
    return _load("products.json")["products"]


def brands() -> dict[str, Any]:
    return _load("brands.json")["brands"]


def channels() -> dict[str, Any]:
    return _load("channels.json")["channels"]


def get_sku(sku: str) -> dict[str, Any]:
    for p in products():
        if p["sku"].lower() == sku.lower():
            return p
    raise KeyError(f"SKU {sku} not found")


def search(query: str = "") -> list[dict[str, Any]]:
    q = query.lower().strip()
    out = []
    for p in products():
        hay = " ".join([p["sku"], p["name"], p["brand"], p["vertical"], p["category"]]).lower()
        if not q or all(tok in hay for tok in q.split()):
            out.append(p)
    return out


def image_path(p: dict[str, Any]) -> Path | None:
    if p.get("image") and p.get("image_status") == "approved":
        return REPO_ROOT / p["image"]
    return None


def compose_scene(
    sku: str,
    channel: str = "signage",
    demographic: str = "adults 25-44",
    concept: str | None = None,
    needs_audio: bool | None = None,
) -> dict[str, Any]:
    """Turn PIM metadata + channel spec into a structured scene brief (the @retail-merchandiser output)."""
    p = get_sku(sku)
    ch = channels()[channel]
    brand = brands()[p["brand"]]
    camera = CAMERA_BY_VERTICAL.get(p["vertical"], "slow dolly-in, soft key light")
    audio_cues = p.get("sensory_cues", [])
    if needs_audio is None:
        needs_audio = ch["audio"].startswith("recommended")
    concept_txt = f" Concept: {concept}." if concept else ""
    layout = p.get("layout_constraints", [])
    prompt = (
        f"{p['name']} by {brand['display_name']}.{concept_txt} "
        f"Scene for {demographic}: {', '.join(audio_cues[:3])}. "
        f"Camera: {camera}. Brand palette {', '.join(brand['palette'])}. "
        f"Keep the product exactly as in the reference: {', '.join(brand['must'])}."
    )
    if layout:
        prompt += f" Layout constraints: {'; '.join(layout)}."
    img = image_path(p)
    return {
        "sku": p["sku"],
        "brand": brand["display_name"],
        "vertical": p["vertical"],
        "channel": channel,
        "aspect_ratio": ch["aspect_ratio"],
        "demographic": demographic,
        "prompt": prompt,
        "negative_prompt": "distorted logo, warped text, extra objects, " + ", ".join(brand["must_not"]),
        "camera": camera,
        "audio_cues": audio_cues if needs_audio else [],
        "needs_audio": bool(needs_audio),
        "source": "pim_image" if img else "text",
        "image_path": str(img.relative_to(REPO_ROOT)).replace("\\", "/") if img else None,
        "strict_layout": bool(layout),
        "physical_interaction": p["vertical"] == "home-improvement" and img is not None,
        "regulated_claims": bool(p.get("regulated_claims")),
    }
