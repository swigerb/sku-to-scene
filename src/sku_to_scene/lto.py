"""Step 2 of the executive demo: the "two-tier cost & fidelity" LTO flow.

1. @retail-merchandiser turns the LTO brief into 3 storyboard concepts (9:16 TikTok).
2. @foundry-router fans the drafts out in parallel on the lowest-cost fast tier
   (MiniMax H3 Max Turbo + LTX-2.5 Fast, text-to-video).
3. @brand-qa checks prompt adherence on each draft.
4. The presenter picks a variant (default #2).
5. @foundry-router upgrades the winner to Kling v3 Pro image-to-video using the approved hero cup
   image with native audio; @brand-qa evaluates the final and recommends a re-roll if it fails.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from . import catalog, qa
from .config import Settings, get_settings
from .pipeline import generate_drafts, generate_from_decision
from .pricing import estimate_cost
from .reroll import reroll
from .router import Brief, route

LTO_SKU = "NWC-LTO-PCB-16"
LTO_BRIEF = (
    "We're launching a fall pumpkin cold brew LTO for a national coffee chain. Generate 3 rapid storyboard "
    "concepts using our lowest-cost fast models in Microsoft Foundry, evaluate prompt adherence, and then render "
    "the best concept in high fidelity with native audio using our approved hero cup image."
)
CONCEPTS = [
    ("Harvest Market", "Pacific Northwest farmers' market at golden hour, the cup on a hay bale beside heirloom pumpkins"),
    ("First Frost Commute", "Northeast city sidewalk on the first cold morning, maple leaves swirling past the cup on a cafe ledge"),
    ("Desert Fall Evening", "Southwest patio at dusk under string lights, the cup on terracotta tile with pumpkin-spice dust drifting"),
]
DRAFT_DURATION = 6
FINAL_DURATION = 8


def draft_prompts() -> list[str]:
    base = catalog.compose_scene(LTO_SKU, channel="tiktok", needs_audio=False)
    return [
        f"Storyboard draft '{title}': {setting}. {base['prompt']} Vertical 9:16 social cut."
        for title, setting in CONCEPTS
    ]


def final_prompt(variant: int) -> str:
    title, setting = CONCEPTS[variant - 1]
    return (
        f"Hero cut of '{title}': {setting}. Start from the approved hero cup exactly as shown. "
        "Cold brew pours over clear ice, pumpkin cold foam cascades into the coffee, condensation beads run down the cup. "
        "Camera: slow dolly-in, macro on condensation, golden hour rim lighting. "
        "Audio: ice clinking, a smooth pour, a soft cafe ambience. Keep the Northwind Coffee logo upright and legible."
    )


def _sessions_dir(s: Settings) -> Path:
    d = s.data_dir / "lto"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_session(session_id: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    d = _sessions_dir(s)
    if session_id is None:
        latest = d / "latest.txt"
        if not latest.is_file():
            raise KeyError("no LTO draft session yet; run the draft step first")
        session_id = latest.read_text(encoding="utf-8").strip()
    p = d / f"{session_id}.json"
    if not p.is_file():
        raise KeyError(f"LTO session {session_id} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_session(s: Settings, sess: dict[str, Any]) -> None:
    d = _sessions_dir(s)
    (d / f"{sess['session_id']}.json").write_text(json.dumps(sess, indent=2), encoding="utf-8")
    (d / "latest.txt").write_text(sess["session_id"], encoding="utf-8")


def lto_drafts(
    settings: Settings | None = None,
    on_event: Callable[[str], None] | None = None,
    evaluate: bool = True,
) -> dict[str, Any]:
    """Step A: 3 parallel fast-tier drafts + prompt-adherence QA. Stops for the presenter to pick a variant."""
    s = settings or get_settings()
    say = on_event or (lambda _m: None)
    say("@retail-merchandiser: composing 3 storyboard concepts for TikTok 9:16")
    prompts = draft_prompts()
    draft_brief = Brief(prompt=prompts[0], channel="tiktok", source="text", stage="draft",
                        duration=DRAFT_DURATION, sku_id=LTO_SKU)
    say("@foundry-router: drafting in parallel on the fast tier (MiniMax H3 Max Turbo + LTX-2.5 Fast)")
    drafts = generate_drafts(prompts, draft_brief, [f"lto-draft-{i + 1}" for i in range(len(prompts))], s, say)
    if evaluate:
        for d in drafts:
            say(f"@brand-qa: checking draft #{d['variant']} for prompt adherence")
            d["qa"] = qa.evaluate(job_id=d["job_id"], sku=LTO_SKU, prompt=prompts[d["variant"] - 1], frames=2,
                                  settings=s)
    turbo = [d for d in drafts if d["model"] == "minimax-h3-max-turbo"]
    costs = {
        "drafts_estimate_usd": round(sum(d["estimate"]["estimate_usd"] for d in drafts), 4),
        "turbo_drafts_estimate_usd": round(sum(d["estimate"]["estimate_usd"] for d in turbo), 4),
        "same_turbo_drafts_on_h3_max_usd": round(sum(
            estimate_cost("minimax-h3-max", d["estimate"]["seconds"], "768P").estimate_usd for d in turbo), 4),
        "note": "Preview list-price estimates; not billing guarantees.",
    }
    sess = {
        "session_id": f"lto-{uuid.uuid4().hex[:8]}",
        "brief": LTO_BRIEF,
        "sku": LTO_SKU,
        "status": "awaiting_selection",
        "concepts": [{"variant": i + 1, "title": t} for i, (t, _s) in enumerate(CONCEPTS)],
        "drafts": drafts,
        "costs": costs,
        "next_step": "Presenter picks a variant in chat, then call the hero step with select=<1..3>.",
    }
    _save_session(s, sess)
    say(f"Drafts ready in session {sess['session_id']} - waiting for the presenter to pick a variant")
    return sess


def lto_hero(
    select: int,
    session_id: str | None = None,
    settings: Settings | None = None,
    on_event: Callable[[str], None] | None = None,
    evaluate: bool = True,
    max_rerolls: int = 1,
) -> dict[str, Any]:
    """Step B: after the presenter's choice, upgrade that variant to Kling v3 Pro image-to-video with audio.

    If @brand-qa returns a valid 'fail', re-roll at most `max_rerolls` times on the recommended tier.
    """
    s = settings or get_settings()
    say = on_event or (lambda _m: None)
    if not 1 <= select <= len(CONCEPTS):
        raise ValueError(f"select must be 1..{len(CONCEPTS)}")
    sess = load_session(session_id, s)
    hero = catalog.get_sku(LTO_SKU)["image"]
    say(f"Presenter selected variant #{select} ({CONCEPTS[select - 1][0]})")
    final_brief = Brief(prompt=final_prompt(select), channel="tiktok", source="pim_image", image_path=hero,
                        stage="final", needs_audio=True, duration=FINAL_DURATION, sku_id=LTO_SKU)
    decision = route(final_brief)
    say(f"@foundry-router: upgrading to {decision.model_name} ({decision.mode}, audio={decision.audio})")
    final = generate_from_decision(decision, final_brief.prompt, hero, final_brief.aspect_ratio,
                                   cache_key="lto-hero-kling", sku=LTO_SKU,
                                   label=f"Variant #{select} hero | {decision.model_name} | image-to-video | 9:16 + audio",
                                   settings=s, on_event=say)
    final["routing"] = asdict(decision)
    rerolls: list[dict[str, Any]] = []
    if evaluate:
        say("@brand-qa: evaluating the hero render against Northwind Coffee guidelines (with the approved reference)")
        final["qa"] = qa.evaluate(job_id=final["job_id"], sku=LTO_SKU, prompt=final_brief.prompt, settings=s)
        current = final
        while current["qa"]["verdict"] == "fail" and len(rerolls) < max_rerolls:
            current = reroll(current["job_id"], max_rerolls=max_rerolls, settings=s, on_event=say)
            rerolls.append(current)
    draft_cost = sess["costs"]["drafts_estimate_usd"]
    spend = final["estimate"]["estimate_usd"] + sum(r["estimate"]["estimate_usd"] for r in rerolls)
    sess.update(
        status="hero_rendered",
        selected_variant=select,
        final=final,
        rerolls=rerolls,
        costs=sess["costs"] | {
            "final_estimate_usd": final["estimate"]["estimate_usd"],
            "reroll_estimate_usd": round(sum(r["estimate"]["estimate_usd"] for r in rerolls), 4),
            "total_estimate_usd": round(draft_cost + spend, 4),
        },
        backend=final["backend"],
        provenance=sorted({d.get("provenance", "?") for d in sess["drafts"]}
                          | {final.get("provenance", "?")} | {r.get("provenance", "?") for r in rerolls}),
    )
    sess.pop("next_step", None)
    _save_session(s, sess)
    return sess


def run_lto(
    select: int = 2,
    settings: Settings | None = None,
    on_event: Callable[[str], None] | None = None,
    evaluate: bool = True,
    max_rerolls: int = 1,
) -> dict[str, Any]:
    """Presenter fallback: run both steps back to back (the chat flow calls them separately)."""
    if not 1 <= select <= len(CONCEPTS):
        raise ValueError(f"select must be 1..{len(CONCEPTS)}")
    sess = lto_drafts(settings, on_event, evaluate)
    return lto_hero(select, sess["session_id"], settings, on_event, evaluate, max_rerolls)
