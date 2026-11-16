"""Registry of the five fal video models available in Microsoft Foundry (public preview).

Sources (verified 2026-11-16):
- https://learn.microsoft.com/azure/foundry/how-to/fal-ai-models/enable-fal-models
- https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/building-the-next-generation-of-multimodal-ai-experiences-with-fal-in-microsoft-/4570032
- fal public model API schemas linked from Learn (payload fields only; transport/auth stay on Foundry).

Prices are preview list prices in USD per generated second. They are estimates for planning,
not billing guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["text-to-video", "image-to-video", "reference-to-video"]
Speed = Literal["fast", "standard", "quality"]


@dataclass(frozen=True)
class ModelSpec:
    key: str
    display_name: str
    family: Literal["kling", "ltx", "minimax"]
    base_path: str
    routes: dict[str, str]
    offering: str
    deployment_env: str
    default_deployment: str
    resolutions: tuple[str, ...]
    default_resolution: str
    durations: tuple[str, ...] | None
    duration_range: tuple[float, float] | None
    default_duration: float
    price_per_second: dict[str, float]
    native_audio: bool
    t2v_aspect_ratios: tuple[str, ...]
    i2v_aspect_ratios: tuple[str, ...]
    speed_tier: Speed
    strengths: tuple[str, ...]
    simulated_latency_s: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def modes(self) -> tuple[str, ...]:
        return tuple(self.routes)

    def route_for(self, mode: str) -> str:
        if mode not in self.routes:
            raise ValueError(f"{self.display_name} does not support {mode}; supported: {', '.join(self.routes)}")
        return f"{self.base_path}{self.routes[mode]}"


KLING_V3_PRO = ModelSpec(
    key="kling-v3-pro",
    display_name="Kling v3 Pro",
    family="kling",
    base_path="kling/v3/pro",
    routes={"text-to-video": "/text-to-video", "image-to-video": "/image-to-video"},
    offering="US Data Zone",
    deployment_env="FOUNDRY_DEPLOYMENT_KLING_V3_PRO",
    default_deployment="kling-v3-pro",
    resolutions=(),
    default_resolution="n/a",
    durations=tuple(str(n) for n in range(3, 16)),
    duration_range=None,
    default_duration=5,
    price_per_second={"audio_off": 0.1232, "audio_on": 0.1848, "audio_voice_control": 0.2156},
    native_audio=True,
    t2v_aspect_ratios=("16:9", "9:16", "1:1"),
    i2v_aspect_ratios=(),
    speed_tier="quality",
    strengths=(
        "Image-to-video from an approved start frame (SKU fidelity)",
        "Native audio generation",
        "Complex physical interaction and fluid camera motion",
        "Multi-shot prompts and optional end frame",
    ),
    simulated_latency_s=45.0,
    notes=(
        "duration is sent as a string ('3'..'15')",
        "image-to-video requires start_image_url and has no aspect_ratio field; output follows the start image",
    ),
)

LTX_25_FAST = ModelSpec(
    key="ltx-2.5-fast",
    display_name="LTX-2.5 Fast",
    family="ltx",
    base_path="lightricks/ltx-2.5",
    routes={"text-to-video": "/text-to-video/fast", "image-to-video": "/image-to-video/fast"},
    offering="Global Standard PayGo",
    deployment_env="FOUNDRY_DEPLOYMENT_LTX_25_FAST",
    default_deployment="ltx-2.5-fast",
    resolutions=("720p", "1080p", "1440p", "2160p"),
    default_resolution="720p",
    durations=("6", "8", "10", "12", "14", "16", "18", "20", "auto"),
    duration_range=None,
    default_duration=6,
    price_per_second={"720p": 0.09, "1080p": 0.13, "1440p": 0.19, "2160p": 0.30},
    native_audio=True,
    t2v_aspect_ratios=("16:9", "9:16"),
    i2v_aspect_ratios=("auto", "16:9", "9:16"),
    speed_tier="fast",
    strengths=("Rapid iteration and previews", "Synchronized audio", "Optional end image for image-to-video"),
    simulated_latency_s=12.0,
    notes=(
        "720p/1080p: 24/25 FPS up to 20 s, 48/50 FPS up to 10 s; 1440p/2160p: up to 10 s",
        "no 1:1 aspect ratio; square channels need a post-crop policy",
    ),
)

LTX_25_PRO = ModelSpec(
    key="ltx-2.5-pro",
    display_name="LTX-2.5 Pro",
    family="ltx",
    base_path="lightricks/ltx-2.5",
    routes={"text-to-video": "/text-to-video/pro", "image-to-video": "/image-to-video/pro"},
    offering="Global Standard PayGo",
    deployment_env="FOUNDRY_DEPLOYMENT_LTX_25_PRO",
    default_deployment="ltx-2.5-pro",
    resolutions=("720p", "1080p"),
    default_resolution="1080p",
    durations=("6", "8", "10", "auto"),
    duration_range=None,
    default_duration=6,
    price_per_second={"720p": 0.12, "1080p": 0.17},
    native_audio=True,
    t2v_aspect_ratios=("16:9", "9:16"),
    i2v_aspect_ratios=("auto", "16:9", "9:16"),
    speed_tier="quality",
    strengths=("High-fidelity final output", "Synchronized audio", "Optional end image for image-to-video"),
    simulated_latency_s=30.0,
    notes=("FPS 24/25/50", "no 1:1 aspect ratio; square channels need a post-crop policy"),
)

MINIMAX_H3_MAX = ModelSpec(
    key="minimax-h3-max",
    display_name="MiniMax H3 Max",
    family="minimax",
    base_path="minimax/h3-max",
    routes={
        "text-to-video": "/text-to-video",
        "image-to-video": "/image-to-video",
        "reference-to-video": "/reference-to-video",
    },
    offering="Global Standard PayGo",
    deployment_env="FOUNDRY_DEPLOYMENT_MINIMAX_H3_MAX",
    default_deployment="minimax-h3-max",
    resolutions=("480P", "768P", "1080P"),
    default_resolution="768P",
    durations=None,
    duration_range=(0.92, 15.0),
    default_duration=5,
    price_per_second={"480P": 0.05, "768P": 0.08, "1080P": 0.16},
    native_audio=False,
    t2v_aspect_ratios=("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
    i2v_aspect_ratios=(),
    speed_tier="standard",
    strengths=(
        "Prompt adherence for strict multi-object / technical layouts",
        "Reference-to-video (up to 12 reference images, videos, audio)",
    ),
    simulated_latency_s=25.0,
    notes=(
        "output can run ~0.7 s longer than requested",
        "1080P uses latent refinement from a native 768P source",
        "image-to-video output canvas follows the input image",
    ),
)

MINIMAX_H3_MAX_TURBO = ModelSpec(
    key="minimax-h3-max-turbo",
    display_name="MiniMax H3 Max Turbo",
    family="minimax",
    base_path="minimax/h3-max-turbo",
    routes={"text-to-video": "/text-to-video", "image-to-video": "/image-to-video"},
    offering="Global Standard PayGo",
    deployment_env="FOUNDRY_DEPLOYMENT_MINIMAX_H3_MAX_TURBO",
    default_deployment="minimax-h3-max-turbo",
    resolutions=("480P", "768P", "1080P"),
    default_resolution="768P",
    durations=None,
    duration_range=(0.92, 15.0),
    default_duration=5,
    price_per_second={"480P": 0.025, "768P": 0.04, "1080P": 0.08},
    native_audio=False,
    t2v_aspect_ratios=("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
    i2v_aspect_ratios=(),
    speed_tier="fast",
    strengths=("Half the per-second price of H3 Max", "High-volume drafts and localized promos"),
    simulated_latency_s=10.0,
    notes=("output can run ~0.7 s longer than requested", "image-to-video output canvas follows the input image"),
)

REGISTRY: dict[str, ModelSpec] = {
    m.key: m for m in (KLING_V3_PRO, LTX_25_FAST, LTX_25_PRO, MINIMAX_H3_MAX, MINIMAX_H3_MAX_TURBO)
}

ALIASES = {
    "kling": "kling-v3-pro",
    "kling-v3": "kling-v3-pro",
    "ltx-fast": "ltx-2.5-fast",
    "ltx-pro": "ltx-2.5-pro",
    "h3-max": "minimax-h3-max",
    "minimax": "minimax-h3-max",
    "h3-max-turbo": "minimax-h3-max-turbo",
    "minimax-turbo": "minimax-h3-max-turbo",
    "turbo": "minimax-h3-max-turbo",
}


def get_model(name: str) -> ModelSpec:
    key = name.strip().lower().replace(" ", "-").replace("_", "-")
    key = ALIASES.get(key, key)
    if key not in REGISTRY:
        raise KeyError(f"Unknown model '{name}'. Known: {', '.join(REGISTRY)}")
    return REGISTRY[key]


def model_summary(m: ModelSpec) -> dict:
    return {
        "key": m.key,
        "name": m.display_name,
        "modes": list(m.modes),
        "offering": m.offering,
        "resolutions": list(m.resolutions),
        "durations": list(m.durations) if m.durations else f"{m.duration_range[0]}-{m.duration_range[1]} s",
        "price_per_second_usd": m.price_per_second,
        "native_audio": m.native_audio,
        "speed_tier": m.speed_tier,
        "strengths": list(m.strengths),
        "notes": list(m.notes),
        "deployment_env": m.deployment_env,
    }
