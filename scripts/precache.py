"""Replace SIMULATED demo-cache clips with real Microsoft Foundry renders.

Run only after the fal models are deployed in a designated demo Foundry resource and an administrator
has reviewed the separate fal terms (see docs/foundry-setup.md). This script makes billable calls.

    SKU2SCENE_MODE=live FOUNDRY_ENDPOINT=https://<res>.services.ai.azure.com python scripts/precache.py --yes

Each rendered clip replaces the manifest entry with the same id and is marked provenance "foundry" with the
Foundry request id. Failed entries retain their previous media and provenance.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from sku_to_scene import lto, qa
from sku_to_scene.config import REPO_ROOT, get_settings
from sku_to_scene.pipeline import generate_from_decision, load_manifest
from sku_to_scene.media import probe, transcode_preview
from sku_to_scene.router import Brief, plan_drafts, route

BRIEFS = REPO_ROOT / "briefs"


def plan() -> list[dict]:
    jobs = []
    for f in sorted(BRIEFS.glob("*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        if raw.get("cache_id"):
            if raw["cache_id"] == "lto-hero-kling":  # the hero the demo renders after "select variant 2"
                raw = {**raw, "prompt": lto.final_prompt(2)}
            b = Brief.from_dict(raw)
            jobs.append({"id": raw["cache_id"], "brief": b, "decision": route(b)})
    lto_brief = Brief(prompt=lto.draft_prompts()[0], channel="tiktok", source="text", stage="draft",
                      sku_id=lto.LTO_SKU, duration=6)
    for i, (p, d) in enumerate(zip(lto.draft_prompts(), plan_drafts(lto_brief, 3))):
        jobs.append({"id": f"lto-draft-{i + 1}", "brief": Brief.from_dict({**lto_brief.__dict__, "prompt": p}),
                     "decision": d})
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="manifest ids to render (default: all)")
    ap.add_argument("--yes", action="store_true", help="confirm billable live renders")
    a = ap.parse_args()

    s = get_settings()
    jobs = [j for j in plan() if not a.only or j["id"] in a.only]
    total = sum(j["decision"].estimate_high_usd for j in jobs)
    for j in jobs:
        d = j["decision"]
        print(f"{j['id']:<20} {d.model_name:<22} {d.mode:<15} {d.aspect_ratio:<5} est<=${d.estimate_high_usd:.2f}")
    print(f"Estimated total (list price, not a bill): <= ${total:.2f}")
    if not s.live:
        print("SKU2SCENE_MODE is not 'live': plan only, nothing rendered.")
        return 0
    if not a.yes:
        print("Add --yes to make these billable Foundry calls.")
        return 2

    manifest = load_manifest(s)
    by_id = {c["id"]: c for c in manifest["clips"]}
    failures = 0
    for j in jobs:
        b, d = j["brief"], j["decision"]
        dest = s.cache_dir / f"{j['id']}.mp4"
        pending = dest.with_name(f".{j['id']}.pending.mp4")
        try:
            job = generate_from_decision(d, b.prompt, b.image_path, b.aspect_ratio, sku=b.sku_id, settings=s,
                                         use_cache=False, on_event=print)
            if job.get("provenance") != "foundry":
                raise RuntimeError(f"unexpected provenance {job.get('provenance')}")
            out = Path(job["output"])
            source = out if out.is_absolute() else REPO_ROOT / out
            transcode_preview(source, pending)
            screening = qa.evaluate(job_id=job["job_id"], video_path=str(pending), sku=b.sku_id,
                                    prompt=b.prompt, settings=s)
            prev = by_id.get(j["id"], {})
            entry = {
                "id": j["id"], "sku": b.sku_id, "vertical": prev.get("vertical"), "model": d.model, "mode": d.mode,
                "aspect_ratio": b.aspect_ratio, "duration": d.duration, "file": dest.name, "provenance": "foundry",
                "audio": "native requested" if d.audio else "not requested; inspect media.has_audio",
                "media": probe(pending), "elapsed_s": job["elapsed_s"],
                "accepted_to_completed_s": job.get("accepted_to_completed_s"),
                "processing": "H.264 display rendition; longest edge <=1280; CRF 28; audio preserved; metadata stripped",
                "source_media": job.get("media"),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_image": b.image_path if d.mode != "text-to-video" else None,
                "prompt": b.prompt, "request_id": job.get("request_id"), "deployment": job["payload"].get("model"),
                "rendered_at": datetime.now(timezone.utc).isoformat(),
                "estimate": job["estimate"], "qa": qa.evidence_summary(screening),
            }
            pending.replace(dest)
            by_id[j["id"]] = entry
            manifest["clips"] = list(by_id.values())
            manifest_path = s.cache_dir / "manifest.json"
            pending_manifest = manifest_path.with_suffix(".pending.json")
            pending_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            pending_manifest.replace(manifest_path)
        except Exception as e:  # retain previous cache entries when generation or local processing fails
            failures += 1
            print(f"!! {j['id']}: {e}")
        finally:
            pending.unlink(missing_ok=True)
    print(f"Done: {len(jobs) - failures} rendered, {failures} failed (previous failed entries retained).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
