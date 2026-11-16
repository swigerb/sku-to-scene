"""Local stdio MCP server exposing the SKU to Scene pipeline as tools for GitHub Copilot agents.

Run:  python -m sku_to_scene.mcp_server      (or the `sku2scene-mcp` script)
Mode: SKU2SCENE_MODE=mock (default, simulated clips, no Azure calls) | live (fal routes on Microsoft Foundry)
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import catalog, ledger, qa
from .config import get_settings
from .lto import lto_drafts, lto_hero, run_lto
from .media import extract_frames as _extract_frames
from .models import REGISTRY, get_model, model_summary
from .pipeline import generate_drafts as _generate_drafts
from .pipeline import generate_video as _generate_video
from .pipeline import get_job, list_jobs
from .pricing import estimate_cost as _estimate
from .readiness import readiness
from .reroll import MAX_REROLLS, reroll
from .router import Brief, route

INSTRUCTIONS = (
    "SKU to Scene creative supply chain. @retail-merchandiser uses get_sku/search_catalog/compose_scene; "
    "@foundry-router uses route_brief/estimate_cost/generate_video/generate_drafts; @brand-qa uses "
    "extract_frames/evaluate_brand_compliance. Always report each clip's provenance: 'simulated' clips are local "
    "placeholders, only 'foundry' clips are real Microsoft Foundry renders. Cost figures are preview list-price "
    "estimates, not bills."
)

server = MCPServer(name="sku-to-scene", instructions=INSTRUCTIONS, version="0.1.0")


@server.tool()
def list_models() -> list[dict[str, Any]]:
    """List the five fal video models on Microsoft Foundry with routes, prices (USD/s), audio and offering."""
    return [model_summary(m) | {"routes": {k: m.route_for(k) for k in m.modes}} for m in REGISTRY.values()]


@server.tool()
def search_catalog(query: str = "") -> list[dict[str, Any]]:
    """Search the mock PIM catalog by SKU, name, brand or vertical (empty query lists everything)."""
    return catalog.search(query)


@server.tool()
def get_sku(sku: str) -> dict[str, Any]:
    """Return one PIM record plus its brand guidelines."""
    p = catalog.get_sku(sku)
    return {"product": p, "brand_guidelines": catalog.brands()[p["brand"]]}


@server.tool()
def compose_scene(
    sku: str, channel: str = "signage", demographic: str = "adults 25-44", concept: str | None = None,
    needs_audio: bool | None = None,
) -> dict[str, Any]:
    """@retail-merchandiser: build a structured scene brief (prompt, camera, audio cues, aspect) for a SKU.
    channel: tiktok (9:16) | signage (16:9) | pdp (1:1)."""
    return catalog.compose_scene(sku, channel, demographic, concept, needs_audio)


@server.tool()
def route_brief(
    prompt: str, channel: str = "signage", source: str = "text", image_path: str | None = None,
    stage: str = "final", needs_audio: bool = False, strict_layout: bool = False,
    physical_interaction: bool = False, volume: int = 1, budget_usd_per_clip: float | None = None,
    duration: float | None = None, allow_post_crop: bool = False, sku_id: str | None = None,
) -> dict[str, Any]:
    """@foundry-router: choose the fal model for a brief using latency, budget, audio, source asset, layout and
    volume rules. Returns the decision, rationale, skipped candidates and cost estimate."""
    b = Brief(prompt=prompt, channel=channel, source=source, image_path=image_path, stage=stage,  # type: ignore[arg-type]
              needs_audio=needs_audio, strict_layout=strict_layout, physical_interaction=physical_interaction,
              volume=volume, budget_usd_per_clip=budget_usd_per_clip, duration=duration,
              allow_post_crop=allow_post_crop, sku_id=sku_id)
    return route(b).to_dict()


@server.tool()
def estimate_cost(
    model: str, duration: float | None = None, resolution: str | None = None, audio: bool = False,
    voice_control: bool = False, count: int = 1,
) -> dict[str, Any]:
    """Estimate per-second inference cost (preview list price; not a billing guarantee)."""
    e = _estimate(get_model(model), duration, resolution, audio, voice_control).to_dict()
    e["count"] = count
    e["batch_estimate_usd"] = round(e["estimate_usd"] * count, 4)
    return e


@server.tool()
def generate_video(
    model: str, prompt: str, image_path: str | None = None, duration: float | None = None,
    aspect_ratio: str = "16:9", resolution: str | None = None, audio: bool = False, mode: str | None = None,
    sku: str | None = None, cache_key: str | None = None,
) -> dict[str, Any]:
    """Generate one clip on a fal model in Microsoft Foundry (live) or serve/render a SIMULATED clip (mock).
    image_path (repo-relative) switches to image-to-video. Returns job id, output path, provenance and estimate."""
    return _generate_video(model, prompt, image_path, duration, aspect_ratio=aspect_ratio, resolution=resolution,
                           audio=audio, mode=mode, sku=sku, cache_key=cache_key)


@server.tool()
def generate_drafts(
    prompts: list[str], channel: str = "tiktok", sku: str | None = None, duration: float = 6,
    needs_audio: bool = False,
) -> list[dict[str, Any]]:
    """Fan out draft variants in parallel across the low-cost fast tier (MiniMax H3 Max Turbo + LTX-2.5 Fast)."""
    b = Brief(prompt=prompts[0], channel=channel, stage="draft", duration=duration, needs_audio=needs_audio,
              sku_id=sku)
    return _generate_drafts(prompts, b)


@server.tool()
def lto_draft_concepts() -> dict[str, Any]:
    """Step 2a: 3 storyboard drafts in parallel on the fast tier (MiniMax H3 Max Turbo + LTX-2.5 Fast) with
    prompt-adherence QA. Returns a session_id and STOPS so the presenter can choose a variant in chat."""
    return lto_drafts()


@server.tool()
def lto_render_hero(select: int, session_id: str | None = None, max_rerolls: int = 1) -> dict[str, Any]:
    """Step 2b: after the presenter picks a variant, upgrade it to Kling v3 Pro image-to-video with native audio
    from the approved hero cup image; @brand-qa evaluates and re-rolls at most `max_rerolls` times on a fail."""
    return lto_hero(select, session_id, max_rerolls=min(max(max_rerolls, 0), MAX_REROLLS))


@server.tool()
def reroll_clip(job_id: str, max_rerolls: int = MAX_REROLLS) -> dict[str, Any]:
    """Re-roll a clip whose latest @brand-qa verdict is 'fail' on the recommended tier (Kling v3 Pro or LTX-2.5
    Pro). Refuses on pass/manual_review/error and after the bounded attempt budget is used."""
    return reroll(job_id, max_rerolls=min(max_rerolls, MAX_REROLLS))


@server.tool()
def run_lto_demo(select: int = 2) -> dict[str, Any]:
    """Presenter fallback only: run Step 2a and 2b back to back without pausing for selection."""
    return run_lto(select=select)


@server.tool()
def job_status(job_id: str | None = None, limit: int = 10) -> dict[str, Any] | list[dict[str, Any]]:
    """Return one job (by id) or the most recent jobs."""
    return get_job(job_id) if job_id else list_jobs(limit=limit)


@server.tool()
def extract_frames(job_id: str, count: int = 4) -> list[str]:
    """Extract evenly spaced PNG frames from a job's output (requires ffmpeg)."""
    s = get_settings()
    job = get_job(job_id)
    from .config import REPO_ROOT

    return [str(p) for p in _extract_frames(REPO_ROOT / job["output"], s.data_dir / "frames" / job_id, count)]


@server.tool()
def evaluate_brand_compliance(
    job_id: str | None = None, video_path: str | None = None, sku: str | None = None, brand: str | None = None,
    prompt: str = "",
) -> dict[str, Any]:
    """@brand-qa: score logo integrity, label legibility, product fidelity and prompt adherence. Uses Azure OpenAI
    vision (+ Content Safety) when configured; otherwise returns clearly-labelled rehearsal values or
    manual_review. Failing clips include a re-roll recommendation (Kling v3 Pro or LTX-2.5 Pro)."""
    return qa.evaluate(job_id=job_id, video_path=video_path, sku=sku, brand=brand, prompt=prompt)


@server.tool()
def cost_report() -> dict[str, Any]:
    """Estimated spend by model across every run (one meter across Kling, LTX and MiniMax)."""
    return ledger.report()


@server.tool()
def foundry_readiness(check_auth: bool = False) -> dict[str, Any]:
    """Read-only live-mode readiness: endpoint, deployments, auth, ffmpeg, plus manual prerequisites."""
    return readiness(check_auth)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()

__all__ = ["server", "main", "asdict"]
