"""Three single-attempt, token-bounded Azure OpenAI evaluations under the approved release envelope.

These are direct Azure OpenAI reviews, not Foundry Evals service runs. The label_model API does not expose
a completion-token cap in this installed SDK, so it is not used for this tightly bounded paid batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from render_release import ROOT, reserve, save
from sku_to_scene import qa
from sku_to_scene.config import get_settings
from sku_to_scene.media import extract_frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Use --execute only under the separately approved $4 release envelope")
    settings = get_settings()
    journal_path = settings.data_dir / "release-20261117-reservations.json"
    lock = journal_path.with_suffix(".lock")
    with lock.open("x"):
        pass
    try:
        journal = json.loads(journal_path.read_text())
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / "targeted-evals-v2.json"
        if path.exists():
            raise SystemExit("Evaluation artifact already exists; no paid retry")
        artifact = {
            "version": "targeted-evals-20261117-v2", "method": "direct Azure OpenAI vision/text with explicit output-token cap",
            "not_foundry_evals_service": True, "historical_results_unchanged": True, "campaign_approval": False,
            "scope": "One attempt per check, no majority vote. Sampled-frame grading plus separate full visual inspection.",
            "checks": []}
        rationale = json.loads((ROOT / "briefs" / "grocery-routing-rationale-v2.json").read_text())
        original = json.loads((ROOT / "demo-cache" / "manifest.json").read_text())
        zava = next(c for c in original["clips"] if c["id"] == "hero-patio-h3max")
        video = ROOT / "demo-cache" / "zava-silent-presentation-v1.mp4"
        frames = extract_frames(video, args.out / "zava-eval-frames", 12)
        zava_prompt = (
            "Review this generic unbranded text-to-video patio-layout concept using only the supplied chronological "
            "frames. Exact branded-product identity and FABRIKAM labels are NOT requirements; no PIM reference "
            "was supplied. Apply the actual creative brief without rewriting its object or layout constraints: "
            + zava["prompt"] +
            ' Return JSON {"label":"pass|partial|fail","observations":[string],"reasons":[string],'
            '"limitations":[string]}. Pass only when requested objects, count, layout and scene are visible; '
            "partial if the core scene exists but a requirement is absent or uncertain; fail for wrong core layout. "
            "Do not infer sounds or full-clip motion from sampled still frames. No campaign approval.")
        cases = [
            ("zava-concept-v2", zava_prompt, frames, {"clip": "zava-silent-presentation-v1",
                "sha256": hashlib.sha256(video.read_bytes()).hexdigest(), "expected_identity": "generic concept",
                "product_identity": "not_applicable: no approved PIM likeness required",
                "brand_marks": "not_applicable: unbranded concept", "audio": "silent derivative; not new native silence"}),
        ]
        grader = (
            "Audit the provided routing rationale against ONLY these supported facts: "
            + json.dumps(rationale["supported_facts"]) +
            '. Return JSON {"label":"grounded|ungrounded","reasons":[string]}. A rationale may paraphrase facts '
            "but must not invent guarantees of quality, exact logos, product identity, medical effects or other capabilities. "
            "Pricing is a preview estimate, not a bill. Grade the rationale, not whether the generated media looks good. Rationale: ")
        for key, text, expected in [
            ("grocery-rationale-v2", rationale["rationale"], "grounded"),
            ("grocery-rationale-unsupported-control", rationale["rationale"] + " " + rationale["negative_control_addition"], "ungrounded"),
        ]:
            cases.append((key, grader + text, [], {"expected": expected, "rationale": text,
                "rationale_version": rationale["version"], "model": rationale["model"], "mode": rationale["mode"]}))
        for key, prompt, images, metadata in cases:
            bound = len(images) * 4096 + len(prompt.encode("utf-8"))
            if bound > 70000:
                raise ValueError("Unpriced input envelope; nothing dispatched")
            reserve(journal, key, 0.1)
            save(journal_path, journal)
            content = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + qa._b64(f)}} for f in images]
            response = qa.httpx.post(
                os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/deployments/" +
                os.environ["AZURE_OPENAI_VISION_DEPLOYMENT"] + "/chat/completions?api-version=" + qa.AOAI_API_VERSION,
                headers={**qa._headers("AZURE_OPENAI_API_KEY"), "Content-Type": "application/json"},
                json={"messages": [{"role": "user", "content": content}], "temperature": 0,
                      "response_format": {"type": "json_object"}, "max_completion_tokens": 3000}, timeout=180)
            rec = {"id": key, **metadata, "request_id": response.headers.get("apim-request-id") or response.headers.get("x-request-id"),
                   "http_status": response.status_code, "input_bound_tokens": bound, "max_output_tokens": 3000,
                   "reserved_usd": 0.1, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
            artifact["checks"].append(rec)
            save(path, artifact)
            response.raise_for_status()
            body = response.json()
            rec.update(grader_model=body["model"], usage=body.get("usage"),
                       result=json.loads(body["choices"][0]["message"]["content"]))
            if rec["result"].get("label") not in {"pass", "partial", "fail", "grounded", "ungrounded"}:
                raise ValueError("Malformed grader label; not accepted, no retry")
            save(path, artifact)
            journal["calls"][key].update(status="completed", request_id=rec["request_id"], usage=rec["usage"])
            save(journal_path, journal)
            print(key, rec["result"]["label"], rec["request_id"], flush=True)
        artifact["rationale_calibration_matched_expected"] = all(
            c["result"]["label"] == c["expected"] for c in artifact["checks"] if "expected" in c)
        save(path, artifact)
    finally:
        lock.unlink()


if __name__ == "__main__":
    main()
