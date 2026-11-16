"""Model-specific request payload builders with validation against the documented schemas."""

from __future__ import annotations

from typing import Any

from .models import ModelSpec, get_model
from .pricing import normalize_resolution


class PayloadError(ValueError):
    pass


def _ltx_duration(m: ModelSpec, duration: Any, resolution: str, fps: int) -> int | str:
    if duration is None:
        duration = m.default_duration
    if isinstance(duration, str) and duration.strip().lower() == "auto":
        return "auto"
    d = float(duration)
    if not d.is_integer() or str(int(d)) not in m.durations:
        allowed = ", ".join(m.durations)
        raise PayloadError(f"{m.display_name} duration must be one of {allowed}; got {duration}")
    d = int(d)
    if m.key == "ltx-2.5-fast" and d > 10 and (resolution in ("1440p", "2160p") or fps in (48, 50)):
        raise PayloadError("LTX-2.5 Fast supports >10 s only at 720p/1080p with 24 or 25 FPS")
    return d


def _kling_duration(m: ModelSpec, duration: Any) -> str:
    if duration is None:
        duration = m.default_duration
    d = float(duration)
    if not d.is_integer() or str(int(d)) not in m.durations:
        raise PayloadError(f"Kling v3 Pro duration must be a whole number of seconds 3-15; got {duration}")
    return str(int(d))


def _minimax_duration(m: ModelSpec, duration: Any) -> float:
    if duration is None:
        duration = m.default_duration
    d = float(duration)
    lo, hi = m.duration_range
    if not lo <= d <= hi:
        raise PayloadError(f"{m.display_name} duration must be {lo}-{hi} s; got {duration}")
    return int(d) if d.is_integer() else d


def build_payload(
    model: str | ModelSpec,
    mode: str,
    deployment: str,
    prompt: str,
    *,
    image_url: str | None = None,
    end_image_url: str | None = None,
    duration: Any = None,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    audio: bool = False,
    negative_prompt: str | None = None,
    fps: int | None = None,
    reference_image_urls: list[str] | None = None,
) -> dict[str, Any]:
    m = get_model(model) if isinstance(model, str) else model
    m.route_for(mode)
    if not prompt or not prompt.strip():
        raise PayloadError("prompt is required")
    if mode == "image-to-video" and not image_url:
        raise PayloadError(f"{m.display_name} image-to-video requires a start image")

    p: dict[str, Any] = {"model": deployment, "prompt": prompt}

    if m.family == "kling":
        p["duration"] = _kling_duration(m, duration)
        p["generate_audio"] = bool(audio)
        if negative_prompt:
            p["negative_prompt"] = negative_prompt
        if mode == "image-to-video":
            p["start_image_url"] = image_url
            if end_image_url:
                p["end_image_url"] = end_image_url
        else:
            ar = aspect_ratio or "16:9"
            if ar not in m.t2v_aspect_ratios:
                raise PayloadError(f"Kling v3 Pro text-to-video aspect_ratio must be one of {m.t2v_aspect_ratios}")
            p["aspect_ratio"] = ar

    elif m.family == "ltx":
        res = normalize_resolution(m, resolution)
        f = int(fps or 25)
        allowed_fps = (24, 25, 48, 50) if m.key == "ltx-2.5-fast" else (24, 25, 50)
        if f not in allowed_fps:
            raise PayloadError(f"{m.display_name} fps must be one of {allowed_fps}")
        p["duration"] = _ltx_duration(m, duration, res, f)
        p["resolution"] = res
        p["fps"] = f
        p["generate_audio"] = bool(audio)
        allowed_ar = m.i2v_aspect_ratios if mode == "image-to-video" else m.t2v_aspect_ratios
        ar = aspect_ratio or ("auto" if mode == "image-to-video" else "16:9")
        if ar not in allowed_ar:
            raise PayloadError(
                f"{m.display_name} {mode} aspect_ratio must be one of {allowed_ar}; got {ar} "
                "(use the router's post-crop policy for square channels)"
            )
        p["aspect_ratio"] = ar
        if mode == "image-to-video":
            p["image_url"] = image_url
            if end_image_url:
                p["end_image_url"] = end_image_url

    else:  # minimax
        p["duration"] = _minimax_duration(m, duration)
        p["resolution"] = normalize_resolution(m, resolution)
        p["prompt_expansion_mode"] = "disabled"
        if mode == "text-to-video":
            ar = aspect_ratio or "16:9"
            if ar not in m.t2v_aspect_ratios:
                raise PayloadError(f"{m.display_name} text-to-video aspect_ratio must be one of {m.t2v_aspect_ratios}")
            p["aspect_ratio"] = ar
        elif mode == "image-to-video":
            p["image_url"] = image_url
            if end_image_url:
                p["end_image_url"] = end_image_url
        elif mode == "reference-to-video":
            refs = reference_image_urls or ([image_url] if image_url else [])
            if not refs:
                raise PayloadError("reference-to-video requires at least one reference image")
            if len(refs) > 12:
                raise PayloadError("MiniMax H3 Max accepts up to 12 reference files")
            p["reference_image_urls"] = refs
    return p


def redact(payload: dict[str, Any], limit: int = 64) -> dict[str, Any]:
    """Shorten data URIs so payloads are readable in logs and chat."""

    def _r(v: Any) -> Any:
        if isinstance(v, str) and v.startswith("data:") and len(v) > limit:
            return f"{v[:40]}...<{len(v)} chars>"
        if isinstance(v, list):
            return [_r(x) for x in v]
        return v

    return {k: _r(v) for k, v in payload.items()}
