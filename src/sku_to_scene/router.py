"""Explainable routing policy: brief -> Foundry fal model.

Implements the demo's routing rules:
- Drafting / A-B testing          -> LTX-2.5 Fast or MiniMax H3 Max Turbo
- Approved hero image + audio     -> Kling v3 Pro (image-to-video)
- Strict multi-object layout      -> MiniMax H3 Max
- High-volume localized promos    -> MiniMax H3 Max Turbo (half the H3 Max rate)
- Text-only final with audio      -> LTX-2.5 Pro
Hard guardrails (audio support, channel aspect ratio, per-clip budget) are checked for every candidate
and each skipped candidate is reported with its reason.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .models import REGISTRY, ModelSpec, get_model
from .pricing import estimate_cost

CHANNEL_ASPECT = {"tiktok": "9:16", "reels": "9:16", "signage": "16:9", "pdp": "1:1"}
HIGH_VOLUME_THRESHOLD = 20


@dataclass
class Brief:
    prompt: str
    channel: str = "signage"
    source: Literal["pim_image", "text"] = "text"
    image_path: str | None = None
    stage: Literal["draft", "final"] = "final"
    needs_audio: bool = False
    strict_layout: bool = False
    physical_interaction: bool = False
    volume: int = 1
    budget_usd_per_clip: float | None = None
    duration: float | None = None
    allow_post_crop: bool = False
    sku_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Brief":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    @property
    def aspect_ratio(self) -> str:
        return CHANNEL_ASPECT.get(self.channel.lower(), self.channel if ":" in self.channel else "16:9")


@dataclass
class RoutingDecision:
    model: str
    model_name: str
    mode: str
    aspect_ratio: str
    aspect_policy: str
    resolution: str
    duration: float | str
    audio: bool
    estimate_usd: float
    estimate_high_usd: float
    rationale: list[str]
    skipped: list[dict[str, str]] = field(default_factory=list)
    companions: list[str] = field(default_factory=list)
    batch_estimate_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULTS = {
    "kling-v3-pro": {"duration": 5, "resolution": None},
    "ltx-2.5-fast": {"duration": 6, "resolution": "720p"},
    "ltx-2.5-pro": {"duration": 6, "resolution": "1080p"},
    "minimax-h3-max": {"duration": 6, "resolution": "1080P"},
    "minimax-h3-max-turbo": {"duration": 5, "resolution": "768P"},
}
DRAFT_RESOLUTION = {"minimax-h3-max-turbo": "768P", "ltx-2.5-fast": "720p"}


def snap_duration(m: ModelSpec, requested: float | None) -> tuple[float | int, str | None]:
    """Return a duration valid for the model and a note if it had to change."""
    if requested is None:
        return DEFAULTS[m.key]["duration"], None
    r = float(requested)
    if m.family == "minimax":
        lo, hi = m.duration_range
        v = min(max(r, lo), hi)
        v = int(v) if float(v).is_integer() else v
    elif m.family == "kling":
        v = int(min(max(round(r), 3), 15))
    else:
        valid = [int(x) for x in m.durations if x != "auto"]
        v = min(valid, key=lambda x: (abs(x - r), x))
        if v < r:
            bigger = [x for x in valid if x >= r]
            v = bigger[0] if bigger else v
    note = None if float(v) == r else f"duration snapped {r:g}s -> {v}s for {m.display_name}"
    return v, note


def _aspect_policy(m: ModelSpec, mode: str, aspect: str, allow_post_crop: bool) -> tuple[str | None, str]:
    """Return (payload_aspect or None, policy text). policy 'UNSUPPORTED' means skip."""
    if mode == "image-to-video":
        if m.family == "ltx":
            if aspect in m.i2v_aspect_ratios:
                return aspect, "native"
            if allow_post_crop:
                return "auto", f"render from source canvas, then center-crop to {aspect} (post-process)"
            return None, "UNSUPPORTED"
        return None, f"output follows the start image; pre-crop source image to {aspect}"
    if aspect in m.t2v_aspect_ratios:
        return aspect, "native"
    if allow_post_crop:
        fallback = "9:16" if aspect in ("1:1", "3:4", "4:5") else "16:9"
        return fallback, f"render {fallback}, then center-crop to {aspect} (post-process)"
    return None, "UNSUPPORTED"


def _candidates(brief: Brief) -> tuple[list[str], list[str], list[str]]:
    """Ordered candidate keys, rationale for the ordering, and companion models."""
    why: list[str] = []
    companions: list[str] = []
    if brief.stage == "draft":
        why.append("Drafting / A-B testing -> lowest-cost fast tier (LTX-2.5 Fast, MiniMax H3 Max Turbo)")
        if brief.needs_audio:
            why.append("Audio requested in draft -> LTX-2.5 Fast first (synchronized audio)")
            return ["ltx-2.5-fast", "minimax-h3-max-turbo"], why, companions
        if brief.volume >= HIGH_VOLUME_THRESHOLD:
            why.append(f"Volume {brief.volume} >= {HIGH_VOLUME_THRESHOLD} -> Turbo first (50% of H3 Max per second)")
        return ["minimax-h3-max-turbo", "ltx-2.5-fast"], why, companions

    if brief.volume >= HIGH_VOLUME_THRESHOLD:
        why.append(
            f"High-volume run ({brief.volume} clips) -> MiniMax H3 Max Turbo makes per-SKU personalization viable"
        )
        return ["minimax-h3-max-turbo", "ltx-2.5-fast", "minimax-h3-max"], why, companions

    if brief.source == "pim_image" and (brief.needs_audio or brief.physical_interaction or not brief.strict_layout):
        why.append("Approved PIM hero image -> image-to-video on Kling v3 Pro preserves SKU fidelity")
        if brief.needs_audio:
            why.append("Native audio required -> Kling v3 Pro audio-on")
        if brief.physical_interaction:
            why.append("Complex physical interaction -> Kling v3 Pro")
        if brief.strict_layout:
            why.append("Strict layout also requested -> MiniMax H3 Max as companion shot")
            companions.append("minimax-h3-max")
        return ["kling-v3-pro", "ltx-2.5-pro", "minimax-h3-max"], why, companions

    if brief.strict_layout:
        why.append("Strict adherence to multi-object / technical layout -> MiniMax H3 Max")
        if brief.physical_interaction:
            why.append("Physical interaction also requested -> Kling v3 Pro as companion shot")
            companions.append("kling-v3-pro")
        return ["minimax-h3-max", "kling-v3-pro", "ltx-2.5-pro"], why, companions

    if brief.needs_audio:
        why.append("Text brief, final render with synchronized audio -> LTX-2.5 Pro")
        return ["ltx-2.5-pro", "kling-v3-pro"], why, companions

    why.append("Text brief, final render -> LTX-2.5 Pro for fidelity, MiniMax H3 Max as alternative")
    return ["ltx-2.5-pro", "minimax-h3-max", "kling-v3-pro"], why, companions


def route(brief: Brief, exclude: list[str] | None = None) -> RoutingDecision:
    order, why, companions = _candidates(brief)
    for extra in REGISTRY:
        if extra not in order:
            order.append(extra)
    exclude = exclude or []
    mode = "image-to-video" if brief.source == "pim_image" and brief.image_path else "text-to-video"
    if brief.source == "pim_image" and not brief.image_path:
        why.append("No image file supplied for PIM brief -> falling back to text-to-video")
    skipped: list[dict[str, str]] = []
    for key in order:
        m = get_model(key)
        if key in exclude:
            skipped.append({"model": key, "reason": "excluded by caller"})
            continue
        if brief.needs_audio and not m.native_audio:
            skipped.append({"model": key, "reason": "no native audio generation"})
            continue
        payload_ar, policy = _aspect_policy(m, mode, brief.aspect_ratio, brief.allow_post_crop)
        if policy == "UNSUPPORTED":
            skipped.append({"model": key, "reason": f"{brief.aspect_ratio} not supported for {mode} (no post-crop)"})
            continue
        duration, note = snap_duration(m, brief.duration)
        res = DRAFT_RESOLUTION.get(key) if brief.stage == "draft" else DEFAULTS[key]["resolution"]
        est = estimate_cost(m, duration, res, audio=brief.needs_audio)
        if brief.budget_usd_per_clip is not None and est.estimate_high_usd > brief.budget_usd_per_clip:
            skipped.append(
                {"model": key, "reason": f"${est.estimate_high_usd:.3f} exceeds budget ${brief.budget_usd_per_clip:.3f}"}
            )
            continue
        rationale = list(why)
        if skipped:
            rationale.append(f"Guardrails skipped {len(skipped)} candidate(s) before selecting {m.display_name}")
        if note:
            rationale.append(note)
        rationale.append(f"Offering: {m.offering}")
        return RoutingDecision(
            model=m.key,
            model_name=m.display_name,
            mode=mode,
            aspect_ratio=payload_ar or brief.aspect_ratio,
            aspect_policy=policy,
            resolution=est.resolution,
            duration=duration,
            audio=brief.needs_audio and m.native_audio,
            estimate_usd=est.estimate_usd,
            estimate_high_usd=est.estimate_high_usd,
            rationale=rationale,
            skipped=skipped,
            companions=companions,
            batch_estimate_usd=round(est.estimate_usd * brief.volume, 4) if brief.volume > 1 else None,
        )
    raise ValueError(f"No model satisfies the brief guardrails: {skipped}")


def plan_drafts(brief: Brief, count: int = 3) -> list[RoutingDecision]:
    """Spread draft variants across the two fast-tier models (Turbo and LTX Fast)."""
    draft = Brief.from_dict({**asdict(brief), "stage": "draft"})
    primary = route(draft)
    other = "ltx-2.5-fast" if primary.model == "minimax-h3-max-turbo" else "minimax-h3-max-turbo"
    try:
        alt = route(draft, exclude=[k for k in REGISTRY if k != other])
    except ValueError:
        alt = primary
    return [primary if i % 2 == 0 else alt for i in range(count)]
