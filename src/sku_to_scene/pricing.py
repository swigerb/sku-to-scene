"""Per-second cost estimation. Estimates only - not billing guarantees."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .models import ModelSpec, get_model

MINIMAX_OVERRUN_S = 0.7


@dataclass
class CostEstimate:
    model: str
    seconds: float
    resolution: str
    price_key: str
    usd_per_second: float
    estimate_usd: float
    estimate_high_usd: float
    caveats: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_resolution(model: ModelSpec, resolution: str | None) -> str:
    if model.family == "kling":
        return "n/a"
    if not resolution:
        return model.default_resolution
    for r in model.resolutions:
        if r.lower() == resolution.strip().lower():
            return r
    if resolution.lower() in ("4k", "2160"):
        if "2160p" in model.resolutions:
            return "2160p"
    raise ValueError(f"{model.display_name} supports resolutions {', '.join(model.resolutions)}; got {resolution}")


def _auto_max(model: ModelSpec) -> float:
    vals = [float(x) for x in (model.durations or ()) if x != "auto"]
    if vals:
        return max(vals)
    return float(model.duration_range[1]) if model.duration_range else float(model.default_duration)


def numeric_duration(model: ModelSpec, duration: float | str | None) -> tuple[float, list[str]]:
    caveats: list[str] = []
    if duration is None:
        return float(model.default_duration), caveats
    if isinstance(duration, str) and duration.strip().lower() == "auto":
        caveats.append(
            "duration 'auto' is chosen by the model; estimate uses the 6 s minimum and the high estimate "
            f"reserves the model maximum ({_auto_max(model):g} s)"
        )
        return 6.0, caveats
    try:
        d = float(duration)
    except (TypeError, ValueError) as e:
        raise ValueError(f"duration must be a number or 'auto'; got {duration!r}") from e
    if not math.isfinite(d) or d <= 0:
        raise ValueError(f"duration must be a positive finite number; got {duration!r}")
    return d, caveats


def estimate_cost(
    model: str | ModelSpec,
    duration: float | str | None = None,
    resolution: str | None = None,
    audio: bool = False,
    voice_control: bool = False,
) -> CostEstimate:
    m = get_model(model) if isinstance(model, str) else model
    seconds, caveats = numeric_duration(m, duration)
    if m.family == "kling":
        price_key = "audio_voice_control" if voice_control else ("audio_on" if audio else "audio_off")
        res = "n/a"
    else:
        res = normalize_resolution(m, resolution)
        price_key = res
    rate = m.price_per_second[price_key]
    est = round(seconds * rate, 4)
    high = est
    if isinstance(duration, str) and duration.strip().lower() == "auto":
        high = round(_auto_max(m) * rate, 4)
    if m.family == "minimax":
        high = round((seconds + MINIMAX_OVERRUN_S) * rate, 4)
        caveats.append("MiniMax output can run ~0.7 s longer than requested (high estimate includes it)")
    caveats.append("preview list price per generated second; not a billing guarantee")
    return CostEstimate(
        model=m.key,
        seconds=seconds,
        resolution=res,
        price_key=price_key,
        usd_per_second=rate,
        estimate_usd=est,
        estimate_high_usd=high,
        caveats=caveats,
    )
