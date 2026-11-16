"""@brand-qa evaluator: frame extraction + brand-guideline scoring + re-roll recommendation.

Evaluators, in priority order:
1. "azure-openai-vision": frames are scored by an Azure OpenAI vision deployment you configure
   (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_VISION_DEPLOYMENT). Optional Azure AI Content Safety image
   analysis when CONTENT_SAFETY_ENDPOINT is set.
2. "rehearsal-script": offline only. Uses the scripted values stored next to each SIMULATED clip in
   demo-cache/manifest.json so the presenter can rehearse the re-roll branch. These are NOT measurements
   and every response says so.
3. "not-evaluated": no evaluator available -> manual review required.
"""

from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
from typing import Any

import httpx

from . import catalog
from .config import REPO_ROOT, Settings, get_settings
from .media import extract_frames, have_ffmpeg
from .pipeline import get_job, load_manifest, save_job

CHECKS = ("logo_integrity", "label_legibility", "product_fidelity", "prompt_adherence")
AOAI_API_VERSION = "2024-10-21"
CONTENT_SAFETY_API_VERSION = "2023-10-01"


def _headers(key_env: str) -> dict[str, str]:
    key = os.environ.get(key_env)
    if key:
        return {"api-key": key} if key_env.startswith("AZURE_OPENAI") else {"Ocp-Apim-Subscription-Key": key}
    from azure.identity import DefaultAzureCredential

    tok = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
    return {"Authorization": f"Bearer {tok.token}"}


def _b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode("ascii")


def _vision_scores(frames: list[Path], brand: dict[str, Any], prompt: str, sku: dict[str, Any] | None,
                   checks: tuple[str, ...]) -> dict:
    ep = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    dep = os.environ["AZURE_OPENAI_VISION_DEPLOYMENT"]
    ref = catalog.image_path(sku) if sku else None
    rubric = (
        "You are a retail brand-compliance reviewer. Score each check from 0 to 1 using ONLY what is visible. "
        + ("The FIRST image is the approved PIM reference for the product; compare the remaining generated frames "
           "against it for product fidelity (shape, colorway, label, logo). " if ref else "")
        + f"Checks: {', '.join(checks)}. Brand rules: must={brand['must']}; must_not={brand['must_not']}; "
        f"logo={brand['logo']}. Product: {sku['name'] if sku else 'n/a'}. Prompt: {prompt}. "
        'Return JSON {"scores":{check:number},"findings":[string],"hallucinated_objects":[string]}.'
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": rubric}]
    images = ([ref] if ref else []) + frames
    content += [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(f)}"}} for f in images]
    r = httpx.post(
        f"{ep}/openai/deployments/{dep}/chat/completions?api-version={AOAI_API_VERSION}",
        headers={**_headers("AZURE_OPENAI_API_KEY"), "Content-Type": "application/json"},
        json={"messages": [{"role": "user", "content": content}], "response_format": {"type": "json_object"},
              "temperature": 0},
        timeout=120,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def _content_safety(frames: list[Path]) -> list[dict[str, Any]]:
    ep = os.environ["CONTENT_SAFETY_ENDPOINT"].rstrip("/")
    out = []
    for f in frames:
        r = httpx.post(
            f"{ep}/contentsafety/image:analyze?api-version={CONTENT_SAFETY_API_VERSION}",
            headers={**_headers("CONTENT_SAFETY_KEY"), "Content-Type": "application/json"},
            json={"image": {"content": _b64(f)}},
            timeout=60,
        )
        r.raise_for_status()
        out.append({"frame": f.name, "categories": r.json().get("categoriesAnalysis", [])})
    return out


def recommend_reroll(job: dict[str, Any], has_image: bool) -> dict[str, Any]:
    """Failed QA -> re-roll on Kling v3 Pro (approved image available) or LTX-2.5 Pro (text brief)."""
    target = "kling-v3-pro" if has_image else "ltx-2.5-pro"
    if job.get("model") == target:
        target = "ltx-2.5-pro" if target == "kling-v3-pro" else "kling-v3-pro"
    return {
        "model": target,
        "mode": "image-to-video" if has_image and target == "kling-v3-pro" else
                ("image-to-video" if has_image else "text-to-video"),
        "reason": "quality threshold failed; re-roll on the higher-fidelity tier",
    }


def evaluate(
    job_id: str | None = None,
    video_path: str | None = None,
    sku: str | None = None,
    brand: str | None = None,
    prompt: str = "",
    frames: int = 4,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or get_settings()
    job = get_job(job_id, s) if job_id else {}
    vp = Path(video_path or job.get("output", ""))
    if not vp.is_absolute():
        vp = REPO_ROOT / vp
    if not vp.is_file():
        raise FileNotFoundError(vp)
    sku_rec = catalog.get_sku(sku) if sku else None
    brand_key = brand or (sku_rec["brand"] if sku_rec else None)
    if not brand_key:
        raise ValueError("Provide sku or brand so @brand-qa knows which guidelines apply")
    guide = catalog.brands()[brand_key]
    thresholds = guide["thresholds"]
    prompt = prompt or (job.get("label") or "")

    frame_files: list[Path] = []
    if have_ffmpeg():
        frame_files = extract_frames(vp, s.data_dir / "frames" / (job_id or vp.stem), frames)

    result: dict[str, Any] = {
        "job_id": job_id, "video": str(vp), "brand": guide["display_name"], "thresholds": thresholds,
        "frames": [str(f) for f in frame_files], "content_safety": None,
    }
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_VISION_DEPLOYMENT") and frame_files:
        try:
            v = _vision_scores(frame_files, guide, prompt, sku_rec, CHECKS)
            if not isinstance(v, dict):
                raise ValueError("evaluator returned non-object JSON")
            result.update(evaluator="azure-openai-vision", measured=True, scores=v.get("scores"),
                          findings=v.get("findings", []), hallucinated_objects=v.get("hallucinated_objects", []),
                          reference_image=str(catalog.image_path(sku_rec)) if sku_rec and catalog.image_path(sku_rec)
                          else None)
        except Exception as exc:  # noqa: BLE001 - evaluator failure must never become approval
            result.update(evaluator="azure-openai-vision", measured=False, scores=None, findings=[],
                          evaluator_error=f"{type(exc).__name__}: {exc}")
    else:
        cached = next((c for c in load_manifest(s).get("clips", []) if c["id"] == job.get("cache_id")), None)
        script = (cached or {}).get("rehearsal_qa")
        # Scripted values belong to one specific cached shot; never reuse them for a different prompt.
        if script and job.get("provenance") == "simulated" and job.get("cache_match") == "explicit":
            result.update(
                evaluator="rehearsal-script", measured=False, scores=script["scores"],
                findings=script.get("findings", []),
                disclaimer="SCRIPTED REHEARSAL VALUES for a SIMULATED clip - not a measurement. Configure "
                           "AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_VISION_DEPLOYMENT for real scoring.",
            )
        else:
            result.update(evaluator="not-evaluated", measured=False, scores={}, findings=[],
                          disclaimer="No vision evaluator configured; manual review required.")
    if os.environ.get("CONTENT_SAFETY_ENDPOINT") and frame_files:
        try:
            result["content_safety"] = _content_safety(frame_files)
        except Exception as exc:  # noqa: BLE001
            result["content_safety_error"] = f"{type(exc).__name__}: {exc}"

    result.update(decide(result.get("scores"), thresholds, result["content_safety"],
                         evaluator_error=result.get("evaluator_error") or result.get("content_safety_error")))
    # Rehearsal values can exercise the branch logic, but only measured scores can approve publication.
    result["publish_approved"] = result["verdict"] == "pass" and bool(result.get("measured"))
    if result["verdict"] == "fail":
        has_image = bool(sku_rec and catalog.image_path(sku_rec))
        result["reroll"] = recommend_reroll(job, has_image)
    if job_id:
        job["qa"] = {k: result.get(k) for k in ("verdict", "evaluator", "measured", "failed_checks",
                                                "publish_approved", "reroll")}
        save_job(s, job)
    return result


def validate_scores(scores: Any) -> tuple[dict[str, float] | None, list[str]]:
    """All four checks must be present, numeric, finite and within [0, 1]; otherwise the output is unusable."""
    if not isinstance(scores, dict):
        return None, ["scores missing or not an object"]
    problems: list[str] = []
    clean: dict[str, float] = {}
    for c in CHECKS:
        v = scores.get(c)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            problems.append(f"{c}: missing or non-numeric")
        elif not math.isfinite(v) or not 0.0 <= v <= 1.0:
            problems.append(f"{c}: {v!r} outside finite [0, 1]")
        else:
            clean[c] = float(v)
    return (clean if not problems else None), problems


def decide(scores: Any, thresholds: dict[str, Any], content_safety: list[dict[str, Any]] | None,
           evaluator_error: str | None = None) -> dict[str, Any]:
    """Fail-closed verdict. Only a complete, valid score set can pass; anything malformed -> error/manual_review."""
    if evaluator_error:
        return {"verdict": "error", "failed_checks": [], "score_problems": [evaluator_error]}
    if not scores:
        return {"verdict": "manual_review", "failed_checks": [], "score_problems": ["no evaluator scores"]}
    clean, problems = validate_scores(scores)
    if clean is None:
        return {"verdict": "manual_review", "failed_checks": [], "score_problems": problems}
    failed = [c for c in CHECKS if clean[c] < float(thresholds.get(c, 0))]
    if content_safety and any(cat.get("severity", 0) >= 2 for fr in content_safety for cat in fr["categories"]):
        failed.append("content_safety")
    return {"verdict": "fail" if failed else "pass", "failed_checks": failed, "score_problems": []}
