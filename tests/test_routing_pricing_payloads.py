import math

import pytest

from sku_to_scene.config import normalize_endpoint
from sku_to_scene.payloads import PayloadError, build_payload
from sku_to_scene.pricing import estimate_cost
from sku_to_scene.router import Brief, plan_drafts, route

HERO = "assets/products/nwc-pumpkin-cold-brew-hero.png"


@pytest.mark.parametrize(
    "brief, expected",
    [
        # Apparel PDP lookbook from approved PIM image -> Kling v3 Pro I2V
        (Brief("jacket lookbook", channel="pdp", source="pim_image", image_path="assets/products/fabrikam-quilted-jacket-rust.png"),
         "kling-v3-pro"),
        # LTO hero with approved image + native audio -> Kling v3 Pro
        (Brief("pour shot", channel="tiktok", source="pim_image", image_path=HERO, needs_audio=True), "kling-v3-pro"),
        # Strict multi-object layout from a text brief -> MiniMax H3 Max
        (Brief("5-piece patio set layout", channel="signage", strict_layout=True), "minimax-h3-max"),
        # High-volume weekly circular -> MiniMax H3 Max Turbo
        (Brief("flu season promo", channel="signage", volume=120), "minimax-h3-max-turbo"),
        # Silent draft -> Turbo; draft with audio -> LTX-2.5 Fast
        (Brief("draft", channel="tiktok", stage="draft"), "minimax-h3-max-turbo"),
        (Brief("draft", channel="tiktok", stage="draft", needs_audio=True), "ltx-2.5-fast"),
        # Text brief, final, audio -> LTX-2.5 Pro
        (Brief("sizzle", channel="signage", needs_audio=True), "ltx-2.5-pro"),
    ],
)
def test_router_scenarios(brief, expected):
    assert route(brief).model == expected


def test_draft_fanout_uses_fast_tier_only():
    models = {d.model for d in plan_drafts(Brief("x", channel="tiktok", stage="draft", duration=6), 3)}
    assert models <= {"minimax-h3-max-turbo", "ltx-2.5-fast"} and len(models) == 2


def test_budget_guardrail_skips_expensive_models():
    d = route(Brief("hero", channel="signage", source="pim_image", image_path=HERO, budget_usd_per_clip=0.5))
    assert d.estimate_high_usd <= 0.5
    assert any(s["model"] == "kling-v3-pro" for s in d.skipped)


@pytest.mark.parametrize("res", ["480P", "768P", "1080P"])
def test_turbo_is_half_of_h3_max(res):
    assert estimate_cost("minimax-h3-max-turbo", 6, res).estimate_usd == pytest.approx(
        estimate_cost("minimax-h3-max", 6, res).estimate_usd / 2)


def test_kling_audio_pricing():
    assert estimate_cost("kling-v3-pro", 8, audio=True).estimate_usd == pytest.approx(8 * 0.1848)


def test_auto_duration_reserves_model_maximum():
    e = estimate_cost("ltx-2.5-pro", "auto", "1080p")
    assert e.estimate_high_usd == pytest.approx(10 * 0.17)
    assert estimate_cost("ltx-2.5-fast", "auto", "720p").estimate_high_usd == pytest.approx(20 * 0.09)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -1, 0])
def test_invalid_durations_rejected(bad):
    with pytest.raises(ValueError):
        estimate_cost("minimax-h3-max", bad, "768P")


def test_ltx_rejects_square_aspect():
    with pytest.raises(PayloadError):
        build_payload("ltx-2.5-fast", "text-to-video", "dep", "p", duration=6, aspect_ratio="1:1")


def test_ltx_pro_duration_limited_to_6_8_10():
    assert build_payload("ltx-2.5-pro", "text-to-video", "dep", "p", duration=10)["duration"] == 10
    with pytest.raises(PayloadError):
        build_payload("ltx-2.5-pro", "text-to-video", "dep", "p", duration=12)


def test_kling_i2v_payload_shape():
    p = build_payload("kling-v3-pro", "image-to-video", "dep", "p", image_url="data:image/png;base64,AA",
                      duration=8, audio=True)
    assert p["start_image_url"].startswith("data:") and p["duration"] == "8" and p["generate_audio"] is True
    assert "aspect_ratio" not in p and p["model"] == "dep"


def test_minimax_payload_fields():
    p = build_payload("minimax-h3-max-turbo", "text-to-video", "dep", "p", duration=6, resolution="768P")
    assert p["resolution"] == "768P" and p["prompt_expansion_mode"] == "disabled"
    with pytest.raises(PayloadError):
        build_payload("minimax-h3-max", "text-to-video", "dep", "p", duration=16)


@pytest.mark.parametrize("ep", [
    "https://res.services.ai.azure.com/api/projects/demo",
    "https://res.services.ai.azure.com/",
    "https://res.services.ai.azure.com/providers/falai/v1",
])
def test_endpoint_normalization(ep):
    assert normalize_endpoint(ep) == "https://res.services.ai.azure.com"
