"""One bounded release batch; no selection, manifest overwrite, retries, or automatic re-roll.

The separate $4 envelope was approved for briefs/release-20261117.json. Failed/uncertain reservations
remain spent. A restart may inspect existing requests but must never resubmit a reserved account.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sku_to_scene import catalog, pipeline, qa
from sku_to_scene.config import get_settings
from sku_to_scene.foundry import FoundryVideoClient
from sku_to_scene.media import extract_frames, probe, transcode_preview
from sku_to_scene.models import get_model
from sku_to_scene.pricing import estimate_cost

PLAN = ROOT / "briefs" / "release-20261117.json"
CAP = 4.0


def save(path, data):
    pending = path.with_suffix(".pending.json")
    pending.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def reserve(journal, key, amount):
    if key in journal["calls"]:
        raise ValueError(f"{key} already reserved; recover its request, never resubmit")
    if isinstance(amount, bool) or not math.isfinite(amount) or amount <= 0 or sum(
        x["reserved_usd"] for x in journal["calls"].values()
    ) + amount > CAP + 1e-9:
        raise ValueError("Separate $4 envelope exhausted; nothing submitted")
    journal["calls"][key] = {"reserved_usd": amount, "status": "reserved"}


class SingleSubmit(FoundryVideoClient):
    def _request(self, method, url, **kwargs):
        if method == "POST":
            return self.http.request(method, url, **kwargs)
        return super()._request(method, url, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--continue-unstarted", action="store_true",
                        help="Continue only unstarted calls; completed generations are recovered, never resubmitted")
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text())
    estimates = {c["account"]: estimate_cost(get_model(c["model"]), c["duration"], c["resolution"],
                                           audio=False).to_dict() for c in plan["candidates"]}
    total = sum(v["estimate_high_usd"] for v in estimates.values()) + 6 * 0.1 + 0.3
    if total > CAP:
        raise SystemExit("Plan exceeds approved envelope")
    print(json.dumps({"estimates": estimates, "total_reserve_usd": round(total, 4)}), flush=True)
    if not args.execute:
        return
    settings = get_settings()
    if not settings.live or not all(os.environ.get(k) for k in (
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT", "CONTENT_SAFETY_ENDPOINT"
    )):
        raise SystemExit("Existing live generation, vision and Content Safety configuration required")
    args.out.mkdir(parents=True, exist_ok=True)
    journal_path = settings.data_dir / "release-20261117-reservations.json"
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {
        "cap_usd": CAP, "authorization": "ask_user: Approve the separate $4.00 envelope, 2026-11-17",
        "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(), "calls": {},
        "cost_basis": {
            "generation": "Repository preview list-price high estimate",
            "vision": "$1/M input + $5/M output planning rates; per call <=70000 estimated input and 3000 output tokens",
            "content_safety": "$0.001/image conservative reserve; Azure retail Standard Images max $0.938/1000 checked 2026-11-17",
            "actual_bill_available": False
        }}
    if journal["plan_sha256"] != hashlib.sha256(PLAN.read_bytes()).hexdigest():
        raise SystemExit("Plan changed since reservation; do not silently reuse the budget journal")
    accounts = {a["id"]: a for a in json.loads((ROOT / "catalog" / "accounts.json").read_text())["accounts"]}
    pipeline.FoundryVideoClient = SingleSubmit
    lock = journal_path.with_suffix(".lock")
    with lock.open("x"):
        pass
    try:
        for c in plan["candidates"]:
            name, estimate = c["account"], estimates[c["account"]]
            key = name + ":generation"
            existing = journal["calls"].get(key)
            if existing and not args.continue_unstarted:
                raise ValueError(f"{key} already exists; no repeat dispatch")
            if existing and existing["status"] != "completed":
                raise ValueError(f"{key} is uncertain; recover the existing request, never resubmit")
            if journal["calls"].get(name + ":qa", {}).get("status") == "completed":
                continue
            out = args.out / name
            out.mkdir(exist_ok=True)
            image = args.references / f"{name}-padded-16x9.png" if c["reference"] else None
            if image and not image.is_file():
                raise ValueError("Inspected padded reference is missing")

            def event(message):
                if "] submit " in message:
                    journal["calls"][key]["job_id"] = message.split("]")[0].lstrip("[")
                    save(journal_path, journal)
                if "completed in" in message or "] submit " in message:
                    print(message, flush=True)

            if existing:
                job = pipeline.get_job(existing["job_id"], settings)
                if job["request_id"] != existing["request_id"] or job["status"] != "completed":
                    raise ValueError("Completed request recovery does not match the journal")
            else:
                reserve(journal, key, estimate["estimate_high_usd"])
                save(journal_path, journal)
                job = pipeline.generate_video(
                    c["model"], c["prompt"], str(image) if image else None, duration=c["duration"],
                    aspect_ratio=c["aspect_ratio"], resolution=c["resolution"], audio=False, mode=c["mode"],
                    sku=accounts[name]["sku"], settings=settings, on_event=event, use_cache=False)
            journal["calls"][key].update(status="completed", job_id=job["job_id"], request_id=job["request_id"])
            save(journal_path, journal)
            source = ROOT / job["output"]
            original = out / "source.mp4"
            import shutil
            shutil.copyfile(source, original)
            display = out / "presentation.mp4"
            transcode_preview(original, display)
            if probe(display)["has_audio"]:
                silent = out / "silent.mp4"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(display), "-map", "0:v:0",
                                "-c:v", "copy", "-an", "-map_metadata", "-1", str(silent)], check=True)
                silent.replace(display)
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(display), "-f", "null", "-"], check=True)
            save(out / "generation.json", {
                "brief": c, "brief_version": plan["version"], "request_id": job["request_id"],
                "job_id": job["job_id"], "estimate": job["estimate"], "media": probe(display),
                "source_media": job["media"], "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                "presentation_sha256": hashlib.sha256(display.read_bytes()).hexdigest(),
                "reference_sha256": hashlib.sha256(image.read_bytes()).hexdigest() if image else None,
                "accepted_to_completed_s": job.get("accepted_to_completed_s"),
                "presentation_transform": "H.264 display rendition <=1280; original audio removed if present; no trim or crop",
                "selected": False})
            qkey = name + ":qa"
            frames = extract_frames(display, out / "qa-frames", 12)
            product = catalog.get_sku(accounts[name]["sku"])
            original_brief = json.loads((ROOT / "briefs" / accounts[name]["brief_file"]).read_text())
            brand = (json.loads((ROOT / "catalog" / "contoso-pro-v2.json").read_text()) if name == "alpine"
                     else catalog.brands()[original_brief.get("brand", product["brand"])])
            if qkey in journal["calls"]:
                if not args.continue_unstarted or journal["calls"][qkey]["status"] != "not_dispatched":
                    raise ValueError("QA was dispatched or uncertain; no retry is permitted")
                journal["calls"][qkey]["status"] = "reserved"
            else:
                reserve(journal, qkey, 0.1)
            save(journal_path, journal)
            calls = []
            original_post = qa.httpx.post

            def metered_post(url, **kwargs):
                if len(calls) >= 13:
                    raise ValueError("QA call limit exceeded")
                if "chat/completions" in url:
                    content = kwargs["json"]["messages"][0]["content"]
                    image_count = sum(v["type"] == "image_url" for v in content)
                    text_bound = sum(len(v["text"].encode("utf-8")) for v in content if v["type"] == "text")
                    if image_count > 13 or image_count * 4096 + text_bound > 70000:
                        raise ValueError("Vision input exceeds the conservative reserved token envelope")
                response = original_post(url, **kwargs)
                body = response.json()
                calls.append({"kind": "vision" if "chat/completions" in url else "content_safety",
                              "request_id": response.headers.get("apim-request-id") or response.headers.get("x-request-id"),
                              "status": response.status_code, "usage": body.get("usage")})
                save(out / "qa-requests.json", calls)
                return response

            qa.httpx.post = metered_post
            try:
                # The unchanged v1 scoring contract, with an explicitly versioned brand correction for new Alpine work.
                scores = qa._vision_scores(frames, brand, c["prompt"], product, qa.CHECKS)
                safety = qa._content_safety(frames)
            finally:
                qa.httpx.post = original_post
            result = {**scores, **qa.decide(scores.get("scores"), brand["thresholds"], safety),
                      "thresholds": brand["thresholds"], "content_safety": safety,
                      "evaluator": "azure-openai-vision", "evaluator_version": "brand-qa-vision-v1",
                      "brand_rule_version": c.get("brand_rule_version", "catalog-v1"),
                      "sampled_frame_count": 12, "measured": True, "publish_approved": False,
                      "human_signoff_required": True, "calls": calls}
            result["automated_checks_passed"] = result["verdict"] == "pass"
            save(out / "qa.json", result)
            journal["calls"][qkey].update(status="completed", verdict=result["verdict"], calls=calls)
            save(journal_path, journal)
            # Full decoded-frame sheets support independent inspection; automatic screening never selects a clip.
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(display),
                            "-vf", "scale=384:-2,tile=4x4", "-fps_mode", "passthrough",
                            str(out / "full-frames-%02d.jpg")], check=True)
            print(f"{name}: {job['request_id']} | QA {result['verdict']} | candidate only: {display}", flush=True)
    finally:
        lock.unlink()


if __name__ == "__main__":
    main()
