"""Append the nine account drafts; plan-only unless --execute --yes and live mode are explicit.

The original cache entries are never replaced. A local reservation journal prevents a second submit after
an interrupted/uncertain attempt. Recover recorded request IDs rather than submitting again. QA is paid,
explicitly enabled only inside this process, sampled at two frames per clip. No automatic re-rolls or evals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sku_to_scene import catalog, qa
from sku_to_scene.config import REPO_ROOT, get_settings
from sku_to_scene.media import probe, transcode_preview
from sku_to_scene.models import get_model
from sku_to_scene.payloads import build_payload
from sku_to_scene.pipeline import generate_video, get_job, load_manifest
from sku_to_scene.pricing import estimate_cost


def plan() -> list[dict]:
    accounts = json.loads((REPO_ROOT / "catalog" / "accounts.json").read_text())["accounts"]
    out = []
    for a in accounts:
        if not a["planned_clip"]:
            continue
        brief = json.loads((REPO_ROOT / "briefs" / a["brief_file"]).read_text())
        m = get_model(a["model"])
        payload = build_payload(m, "text-to-video", m.default_deployment, brief["prompt"],
                                duration=a["duration"], resolution=a["tier"], aspect_ratio=a["aspect_ratio"],
                                audio=False)
        estimate = estimate_cost(m, payload["duration"], payload.get("resolution"), audio=False)
        out.append({"account": a, "brief": brief, "estimate": estimate.to_dict()})
    return out


def write_json(path: Path, doc: dict) -> None:
    pending = path.with_suffix(".pending.json")
    pending.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--reroll", nargs="+", help="initial clip IDs; exactly one -r1 attempt each, only for a disqualifier")
    ap.add_argument("--reason", choices=("text-or-logo", "trade-dress", "unsafe"))
    args = ap.parse_args()
    jobs = plan()
    if args.reroll:
        if not args.reason:
            raise SystemExit("A disqualifying --reason is required for a re-roll.")
        if not set(args.reroll) <= {j["account"]["planned_clip"] for j in jobs}:
            raise SystemExit("Only known initial account drafts can receive one -r1 attempt.")
        jobs = [j for j in jobs if j["account"]["planned_clip"] in args.reroll]
        for j in jobs:
            base = j["account"]["planned_clip"]
            j["account"] = {**j["account"], "planned_clip": base + "-r1"}
            j["replacement_for"] = base
            j["brief"]["prompt"] = j["brief"].get("reroll_prompt", j["brief"]["prompt"])
    total = sum(j["estimate"]["estimate_usd"] for j in jobs)
    for j in jobs:
        print(j["account"]["planned_clip"], f"${j['estimate']['estimate_usd']:.4f}", flush=True)
    print(f"Initial generation estimate ${total:.4f}; cap $6 initial / $8 including authorized re-rolls.", flush=True)
    if total > 6:
        raise SystemExit("Plan exceeds initial generation cap; nothing submitted.")
    if not (args.execute and args.yes):
        return 0
    settings = get_settings()
    if not settings.live:
        raise SystemExit("Live mode is required; nothing submitted.")
    if not all(os.environ.get(k) for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT", "CONTENT_SAFETY_ENDPOINT")):
        raise SystemExit("Vision and Content Safety configuration required before generating.")
    journal_path = settings.data_dir / "account-draft-reservations.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    manifest_path = settings.cache_dir / "manifest.json"
    for j in jobs:
        a, brief = j["account"], j["brief"]
        clip_id = a["planned_clip"]
        manifest = load_manifest(settings)
        if j.get("replacement_for") and not any(c["id"] == j["replacement_for"] for c in manifest["clips"]):
            raise SystemExit("Cannot re-roll without retained initial request evidence.")
        if any(c["id"] == clip_id for c in manifest["clips"]):
            print(clip_id, "already cached; skipped without QA or generation", flush=True)
            continue
        if clip_id in journal:
            if not journal[clip_id].get("job_id"):
                raise SystemExit(f"{clip_id}: prior uncertain reservation; recover its existing request, do not resubmit.")
            job = get_job(journal[clip_id]["job_id"], settings)
            if job["status"] != "completed":
                raise SystemExit(f"{clip_id}: prior job incomplete; recover its existing request, do not resubmit.")
            print(clip_id, "resuming completed request", job["request_id"], flush=True)
        else:
            reserved = sum(v["estimate_usd"] for v in journal.values())
            if reserved + j["estimate"]["estimate_usd"] > 8:
                raise SystemExit("Total reserved generation would exceed $8; nothing submitted.")
            journal[clip_id] = {"estimate_usd": j["estimate"]["estimate_usd"], "status": "reserved"}
            write_json(journal_path, journal)
            job = generate_video(
                a["model"], brief["prompt"], duration=a["duration"], aspect_ratio=a["aspect_ratio"],
                resolution=a["tier"], audio=False, mode="text-to-video", sku=a["sku"],
                label=a["fictional_brand"], settings=settings, use_cache=False, on_event=print,
            )
        journal[clip_id].update(job_id=job["job_id"], request_id=job["request_id"], status="generated")
        write_json(journal_path, journal)
        source = REPO_ROOT / job["output"]
        preview = settings.data_dir / "account-previews" / f"{clip_id}.mp4"
        preview.parent.mkdir(parents=True, exist_ok=True)
        transcode_preview(source, preview)
        media = probe(preview)
        original_file = None
        if media["has_audio"]:
            original_file = f"{clip_id}-original-audio.mp4"
            shutil.copyfile(preview, settings.cache_dir / original_file)
        trimmed = media["duration_s"] > a["duration"] + 0.05
        if original_file or trimmed:
            silent = preview.with_name(f"{clip_id}-silent.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(preview), "-t", str(a["duration"]), "-map", "0:v:0",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-r", "25",
                            "-an", "-map_metadata", "-1", "-movflags", "+faststart", str(silent)],
                           check=True)
            silent.replace(preview)
            media = probe(preview)
            if media["has_audio"]:
                raise SystemExit(f"{clip_id}: audio-removal failed; refusing to publish a mislabeled silent draft.")
            if abs(media["duration_s"] - a["duration"]) > 0.05:
                raise SystemExit(f"{clip_id}: presentation duration differs from the requested duration.")
        os.environ["SKU2SCENE_QA_EVALUATORS"] = "auto"
        screening = qa.evaluate(job_id=job["job_id"], video_path=str(preview), sku=a["sku"],
                                brand=brief["brand"], prompt=brief["prompt"], frames=2, settings=settings)
        # Fail-closed evidence is recorded, never relabelled as approval or silently re-rolled.
        journal[clip_id].update(status="screened", qa_verdict=screening["verdict"])
        write_json(journal_path, journal)
        entry = {
            "id": clip_id, "sku": a["sku"], "vertical": catalog.get_sku(a["sku"])["vertical"],
            "model": a["model"], "mode": "text-to-video", "aspect_ratio": a["aspect_ratio"], "duration": a["duration"],
            "file": f"{clip_id}.mp4", "provenance": "foundry", "audio": "not requested; silent draft",
            "media": media, "elapsed_s": job["elapsed_s"], "accepted_to_completed_s": job.get("accepted_to_completed_s"),
            "processing": "H.264 display rendition; longest edge <=1280; CRF 28; metadata stripped",
            "source_media": job["media"], "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_image": None, "prompt": brief["prompt"], "request_id": job["request_id"],
            "original_file": original_file, "presentation_audio_removed": bool(original_file),
            "presentation_trimmed_to_s": a["duration"] if trimmed else None,
            "deployment": job["payload"].get("model"), "rendered_at": datetime.now(timezone.utc).isoformat(),
            "estimate": job["estimate"], "qa": qa.evidence_summary(screening),
            "qa_evaluated_at": datetime.now(timezone.utc).isoformat(),
            "account": a["id"], "stage": "draft", "hero_eligible": False, "human_signoff_required": True,
            "replacement_for": j.get("replacement_for"), "reroll_reason": args.reason if args.reroll else None,
            "evaluations": {"status": "not_yet_evaluated", "reason": "No new Foundry Evaluations run; original v1 evidence is immutable."},
        }
        if original_file:
            entry["processing"] += "; unexpected model audio removed for silent presentation; original-audio rendition retained"
        if trimmed:
            entry["processing"] += f"; presentation trimmed to requested {a['duration']} seconds; re-encoded H.264 at 25 fps / CRF 20"
        # Re-read before append so an external append is preserved; never replace any existing ID.
        manifest = load_manifest(settings)
        if any(c["id"] == clip_id for c in manifest["clips"]):
            raise SystemExit(f"{clip_id}: cache changed during rendering; refusing to overwrite.")
        preview.replace(settings.cache_dir / entry["file"])
        manifest["clips"].append(entry)
        write_json(manifest_path, manifest)
        journal[clip_id]["status"] = "cached"
        write_json(journal_path, journal)
        print(clip_id, job["request_id"], screening["verdict"], flush=True)
        if screening.get("evaluation_error") or not screening.get("measured") or screening.get("content_safety_error"):
            raise SystemExit("Screening unavailable; recorded evidence retained. Resolve before further paid work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
