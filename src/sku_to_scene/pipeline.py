"""Generation pipeline: validate -> (pre-crop) -> payload -> mock or live Foundry backend -> ledger.

SKU2SCENE_MODE=mock (default) serves clips from demo-cache/ (provenance recorded in manifest.json) or
renders a labelled SIMULATED placeholder. SKU2SCENE_MODE=live calls the fal routes on Microsoft Foundry.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from . import ledger
from .config import REPO_ROOT, Settings, get_settings
from .foundry import FoundryVideoClient, image_to_data_uri
from .media import (
    crop_image_to_aspect,
    crop_video_to_aspect,
    have_ffmpeg,
    image_size,
    matches_aspect,
    probe,
    render_placeholder,
)
from .models import get_model
from .payloads import build_payload, redact
from .pricing import estimate_cost
from .router import Brief, RoutingDecision, _aspect_policy, plan_drafts

Event = Callable[[str], None]


class ProcessingUnavailable(RuntimeError):
    """Raised before submit when required local pre/post-processing cannot run."""


class CacheMismatch(ValueError):
    """Raised when a requested cache entry does not match the requested content."""


# ---------------------------------------------------------------- job store
def _jobs_dir(s: Settings) -> Path:
    d = s.data_dir / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_job(s: Settings, job: dict[str, Any]) -> None:
    (_jobs_dir(s) / f"{job['job_id']}.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def get_job(job_id: str, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    p = _jobs_dir(s) / f"{job_id}.json"
    if not p.is_file():
        raise KeyError(f"job {job_id} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def list_jobs(settings: Settings | None = None, limit: int = 20) -> list[dict[str, Any]]:
    s = settings or get_settings()
    files = sorted(_jobs_dir(s).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


# ---------------------------------------------------------------- cache manifest
def load_manifest(s: Settings) -> dict[str, Any]:
    p = s.cache_dir / "manifest.json"
    if not p.is_file():
        return {"clips": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _find_cached(
    s: Settings, cache_key: str | None, model: str, mode: str, aspect: str, sku: str | None
) -> dict[str, Any] | None:
    """Return a cached clip only when it is explicitly associated with the same SKU, model, mode and aspect.

    Unrelated footage is never relabelled: without a SKU (or an explicit cache_key whose metadata matches),
    the mock backend renders a fresh labelled placeholder instead.
    """
    clips = load_manifest(s).get("clips", [])

    def ok(c: dict[str, Any]) -> bool:
        return (
            c.get("model") == model and c.get("mode") == mode and c.get("aspect_ratio") == aspect
            and c.get("sku") == sku
        )

    if cache_key:
        c = next((c for c in clips if c.get("id") == cache_key), None)
        if c is None:
            raise CacheMismatch(f"cache entry {cache_key!r} not found in manifest")
        if not ok(c):
            raise CacheMismatch(
                f"cache entry {cache_key!r} is {c.get('sku')}/{c.get('model')}/{c.get('mode')}/{c.get('aspect_ratio')}; "
                f"requested {sku}/{model}/{mode}/{aspect}"
            )
        if not (s.cache_dir / c["file"]).is_file():
            raise CacheMismatch(f"cache file for {cache_key!r} is missing: {c['file']}")
        return c
    if not sku:
        return None
    for c in clips:
        if ok(c) and (s.cache_dir / c["file"]).is_file():
            return c
    return None


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- core
def generate_video(
    model: str,
    prompt: str,
    image_path: str | None = None,
    duration: float | str | None = None,
    *,
    aspect_ratio: str = "16:9",
    resolution: str | None = None,
    audio: bool = False,
    negative_prompt: str | None = None,
    mode: str | None = None,
    cache_key: str | None = None,
    sku: str | None = None,
    label: str | None = None,
    settings: Settings | None = None,
    on_event: Event | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    s = settings or get_settings()
    m = get_model(model)
    say = on_event or (lambda _msg: None)
    mode = mode or ("image-to-video" if image_path else "text-to-video")
    if mode != "text-to-video" and not image_path:
        raise ValueError(f"{mode} needs image_path")
    if audio and not m.native_audio:
        raise ValueError(f"{m.display_name} has no native audio generation")
    job_id = f"{m.key}-{uuid.uuid4().hex[:8]}"
    out_dir = s.data_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    # Aspect handling: LTX I2V supports auto/16:9/9:16; Kling/MiniMax I2V follow the source image.
    # Required processing is validated BEFORE any billable submit.
    payload_ar, policy = _aspect_policy(m, mode, aspect_ratio, allow_post_crop=True)
    src = Path(image_path) if image_path else None
    if src and not src.is_absolute():
        src = REPO_ROOT / src
    if src and not src.is_file():
        raise FileNotFoundError(src)
    if src and policy.startswith("output follows"):
        if matches_aspect(image_size(src), aspect_ratio):
            notes.append(f"source image already {aspect_ratio}; no pre-crop needed")
        elif have_ffmpeg():
            src = crop_image_to_aspect(
                src, aspect_ratio, out_dir / f"{job_id}-source-{aspect_ratio.replace(':', 'x')}.png"
            )
            notes.append(f"source image center-cropped to {aspect_ratio} before submit")
        elif not s.live:
            notes.append(f"mock backend: pre-crop to {aspect_ratio} skipped (ffmpeg unavailable; nothing billable)")
        else:
            raise ProcessingUnavailable(
                f"{m.display_name} {mode} output follows the source image, which is not {aspect_ratio}; "
                "ffmpeg is required to pre-crop it. Install ffmpeg or supply a correctly-cropped image."
            )
    needs_post_crop = "center-crop to" in policy
    if needs_post_crop:
        if s.live and not have_ffmpeg():
            raise ProcessingUnavailable(
                f"{aspect_ratio} on {m.display_name} {mode} requires post-crop with ffmpeg; refusing to submit"
            )
        notes.append(policy)

    image_url = image_to_data_uri(src) if src else None
    if mode == "reference-to-video":
        payload = build_payload(m, mode, s.deployment_for(m), prompt, reference_image_urls=[image_url],
                                duration=duration, resolution=resolution)
    else:
        payload = build_payload(
            m, mode, s.deployment_for(m), prompt, image_url=image_url, duration=duration,
            resolution=resolution, aspect_ratio=payload_ar if m.family != "minimax" or mode == "text-to-video" else None,
            audio=audio, negative_prompt=negative_prompt,
        )
    est = estimate_cost(m, payload.get("duration"), payload.get("resolution"), audio=audio)
    job: dict[str, Any] = {
        "job_id": job_id,
        "model": m.key,
        "model_name": m.display_name,
        "mode": mode,
        "route": m.route_for(mode),
        "aspect_ratio": aspect_ratio,
        "backend": "foundry" if s.live else "mock",
        "status": "submitted",
        "payload": redact(payload),
        "estimate": est.to_dict(),
        "notes": notes,
        "label": label,
        "sku": sku,
        "prompt": prompt,
        "audio": audio,
        "source_image": _rel(Path(image_path) if Path(image_path).is_absolute() else REPO_ROOT / image_path)
        if image_path else None,
    }
    save_job(s, job)
    say(f"[{job_id}] submit {m.display_name} {mode} ({job['backend']}) est ${est.estimate_usd:.3f}")
    t0 = time.time()
    try:
        dest = out_dir / f"{job_id}.mp4"
        if s.live:
            client = FoundryVideoClient(s)
            rid = client.submit(m, mode, payload)
            accepted = time.time()
            job.update(request_id=rid, status="in_progress", accepted_at_unix_s=accepted)
            save_job(s, job)

            def status_event(st: str) -> None:
                say(f"[{job_id}] {st}")
                if st == "COMPLETED":
                    job["accepted_to_completed_s"] = round(time.time() - accepted, 2)

            result = client.wait(m, rid, on_status=status_event)
            url = (result.get("video") or {}).get("url")
            if not url:
                raise RuntimeError(f"No video.url in result: {str(result)[:300]}")
            client.download(url, dest)
            job.update(provenance="foundry", source_note=f"Foundry request {rid}")
            if needs_post_crop:
                raw = dest.with_name(f"{job_id}-raw.mp4")
                dest.replace(raw)
                crop_video_to_aspect(raw, aspect_ratio, dest)
                job["raw_output"] = _rel(raw)
                notes.append(f"post-processed: center-cropped Foundry output to {aspect_ratio}")
        else:
            time.sleep(m.simulated_latency_s * s.mock_latency_scale)
            cached = _find_cached(s, cache_key, m.key, mode, aspect_ratio, sku) if use_cache else None
            if cached:
                shutil.copyfile(s.cache_dir / cached["file"], dest)
                job.update(provenance=cached.get("provenance", "simulated"), cache_id=cached["id"],
                           cache_match="explicit" if cache_key else "sku",
                           source_note=f"served from demo-cache/{cached['file']}")
            elif have_ffmpeg():
                render_placeholder(dest, label or f"{m.display_name} | {mode} | {aspect_ratio}", src, aspect_ratio,
                                   float(est.seconds if est.seconds <= 8 else 8), audio=audio)
                job.update(provenance="simulated", source_note="placeholder rendered locally with ffmpeg")
            else:
                raise RuntimeError("Mock mode: no cached clip matches and ffmpeg is unavailable")
        job["elapsed_s"] = round(time.time() - t0, 2)
        job["output"] = _rel(dest)
        if have_ffmpeg():
            job["media"] = probe(dest)
            if s.live and audio and not job["media"]["has_audio"]:
                raise RuntimeError("Foundry output has no audio stream despite native audio being requested")
            if s.live and not matches_aspect((job["media"]["width"], job["media"]["height"]), aspect_ratio):
                notes.append(f"model output dimensions {job['media']['width']}x{job['media']['height']} differ "
                             f"from requested {aspect_ratio}; inspect/crop before publishing")
        job["status"] = "completed"
        say(f"[{job_id}] completed in {job['elapsed_s']}s -> {job['output']} ({job['provenance']})")
    except Exception as e:  # noqa: BLE001 - recorded on the job and re-raised
        job.update(status="failed", error=str(e), elapsed_s=round(time.time() - t0, 2))
        save_job(s, job)
        ledger.record({"job_id": job_id, "model": m.key, "status": "failed", "backend": job["backend"]}, s)
        raise
    save_job(s, job)
    ledger.record(
        {
            "job_id": job_id, "model": m.key, "mode": mode, "status": "completed", "backend": job["backend"],
            "provenance": job["provenance"], "seconds": est.seconds, "resolution": est.resolution,
            "audio": audio, "estimate_usd": est.estimate_usd,
        },
        s,
    )
    return job


def generate_from_decision(
    d: RoutingDecision, prompt: str, image_path: str | None, channel_aspect: str, **kw: Any
) -> dict[str, Any]:
    return generate_video(
        d.model, prompt, image_path if d.mode != "text-to-video" else None, d.duration,
        aspect_ratio=channel_aspect, resolution=None if d.resolution == "n/a" else d.resolution,
        audio=d.audio, mode=d.mode, **kw,
    )


def generate_drafts(
    prompts: list[str],
    brief: Brief,
    cache_keys: list[str] | None = None,
    settings: Settings | None = None,
    on_event: Event | None = None,
) -> list[dict[str, Any]]:
    """Fan out draft variants across the fast tier in parallel."""
    plans = plan_drafts(brief, len(prompts))
    keys = cache_keys or [None] * len(prompts)

    def _one(i: int) -> dict[str, Any]:
        d = plans[i]
        job = generate_from_decision(
            d, prompts[i], brief.image_path, brief.aspect_ratio, cache_key=keys[i], sku=brief.sku_id,
            label=f"Draft #{i + 1} | {d.model_name} | {d.mode} | {brief.aspect_ratio}",
            settings=settings, on_event=on_event,
        )
        job["variant"] = i + 1
        job["routing"] = asdict(d)
        return job

    with ThreadPoolExecutor(max_workers=len(prompts)) as ex:
        return list(ex.map(_one, range(len(prompts))))
