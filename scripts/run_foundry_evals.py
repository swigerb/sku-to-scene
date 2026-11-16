"""Run the SKU to Scene Foundry Evaluations (billable; explicit opt-in).

Two stages, disclosed in docs/foundry-evaluations-plan.md:
  A. ``brand-qa-vision`` chat completions write neutral visual observations of each cached clip (plus the approved
     PIM reference when the render used one). Foundry Evals rejected image inputs for grader models in this account,
     so the cloud graders never see pixels.
  B. Foundry Evaluations (Evals API on the Foundry project) grade those observations, the routing cases and the
     audio signal measurements, ``--repeats`` times for variance.

No video generation. Historical manifest QA is untouched. Without ``--yes`` the script prints the plan and estimate
and exits. Spend is estimated with conservative assumed token prices and capped by ``--max-usd`` before and during
the run.

    python scripts/run_foundry_evals.py                 # plan + estimate only, no network
    python scripts/run_foundry_evals.py --yes --repeats 3
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from sku_to_scene import evals  # noqa: E402
from sku_to_scene.config import load_dotenv  # noqa: E402

PUBLIC_OUT = REPO / "demo-cache" / "evaluations" / "foundry-evals-v1.json"
PRIVATE_DIR = REPO / ".sku2scene" / "evals"
OBS_CACHE = PRIVATE_DIR / "observations.json"
IMG_TOKENS = 1100  # conservative per 512px image
SPIKE_RESERVE_USD = 0.05  # reservation for the three rejected image-input spikes (service reported no usage)

# Recorded spike evidence (service responses, not a documented allowlist).
SPIKES = [
    {"grader_deployment": "brand-qa-vision (gpt-5.4-mini 2026-03-17)", "eval_id": "eval_5b46a97db5884737a8f10fee6ebaf0f2",
     "run_id": "evalrun_1b8f4d68c60b47b4bb63ba7cbde6dd26", "status": "failed",
     "error": "Image inputs are not supported for grader model: brand-qa-vision. Try again with a vision model."},
    {"grader_deployment": "temporary gpt-5-mini 2025-08-07 (custom deployment name, deleted)",
     "eval_id": "eval_ea6a751601da4effb24298a8d74051d9", "run_id": "evalrun_ef2b2061ab974146a846e17fe533bb02",
     "status": "failed", "error": "Image inputs are not supported for grader model: <deployment>. Try again with a vision model."},
    {"grader_deployment": "temporary gpt-5-mini 2025-08-07 (canonical deployment name, deleted)",
     "eval_id": "eval_f21a5e601de5477b82544c185674de4c", "run_id": "evalrun_0ef8fe50c7e049cb9adc2c26b51d4a3f",
     "status": "failed", "error": "Image inputs are not supported for grader model: gpt-5-mini. Try again with a vision model."},
]


def jpg_uri(src: Path, at: float | None = None, width: int = 512) -> str:
    args = ["ffmpeg", "-v", "error"] + (["-ss", f"{at:.2f}"] if at is not None else []) + [
        "-i", str(src), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", "-f", "image2", "-c:v", "mjpeg",
        "pipe:1"]
    return "data:image/jpeg;base64," + base64.b64encode(subprocess.run(args, capture_output=True, check=True).stdout).decode()


def measure_audio(video: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null",
                        "-"], capture_output=True, text=True)
    return evals.finite(evals.parse_ebur128(r.stderr))


def load_inputs() -> tuple[list[dict], dict, dict]:
    manifest = json.loads((REPO / "demo-cache" / "manifest.json").read_text(encoding="utf-8"))
    products = {p["sku"]: p for p in json.loads((REPO / "catalog" / "products.json").read_text(encoding="utf-8"))["products"]}
    brands = json.loads((REPO / "catalog" / "brands.json").read_text(encoding="utf-8"))["brands"]
    return manifest["clips"], products, brands


def media_rows(clips, products, brands) -> list[dict]:
    rows = []
    for c in clips:
        p = products[c["sku"]]
        rows.append({"row_id": c["id"], "clip": c, "video": REPO / "demo-cache" / c["file"],
                     "reference": REPO / c["source_image"] if c.get("source_image") else None,
                     "product_name": p["name"], "logo_rule": brands[p["brand"]]["logo"], "expected_identity": "match",
                     "applicability": evals.applicability(c), "stage": evals.stage_of(c)})
    src = next(c for c in clips if c["id"] == evals.NEGATIVE_CONTROL_SOURCE_CLIP)
    ref = products[evals.NEGATIVE_CONTROL_REFERENCE_SKU]
    nc_na = "negative control tests product identity only"
    rows.append({"row_id": evals.NEGATIVE_CONTROL_ID, "clip": src, "video": REPO / "demo-cache" / src["file"],
                 "reference": REPO / ref["image"], "product_name": ref["name"],
                 "logo_rule": brands[ref["brand"]]["logo"], "expected_identity": "mismatch", "stage": "negative control",
                 "applicability": {"concept_adherence": nc_na, "product_identity": None, "brand_marks": nc_na,
                                   "audio_signal": nc_na}})
    return rows


# Conservative per-call bounds used for pre-dispatch reservation.
OBS_MAX_OUTPUT = 3000
GRADER_IN_PER_ROW, GRADER_OUT_PER_ROW = 4000, 1200


def plan_estimate(rows, routing, repeats, n_frames) -> dict:
    a_in = sum((n_frames + (1 if r["reference"] else 0)) * IMG_TOKENS + 900 for r in rows)
    a_out = OBS_MAX_OUTPUT * len(rows)
    grader_calls = sum(1 for r in rows for k in ("concept_adherence", "product_identity", "brand_marks")
                       if r["applicability"][k] is None) + len(routing)
    b_in, b_out = grader_calls * repeats * GRADER_IN_PER_ROW, grader_calls * repeats * GRADER_OUT_PER_ROW
    return {"stage_a_tokens": [a_in, a_out], "stage_b_tokens": [b_in, b_out], "grader_calls": grader_calls * repeats,
            "estimate_usd": round(evals.estimate_usd(a_in + b_in, a_out + b_out) + SPIKE_RESERVE_USD, 4)}


class Ledger:
    """Reserve a conservative estimate BEFORE each dispatch; settle to actual usage only when the service reports it.

    Failed or usage-less attempts keep their reservation, so the cap can never be exceeded by unreported spend.
    """

    def __init__(self, cap: float, carried_usd: float = 0.0):
        self.cap, self.inp, self.out, self.carried = cap, 0, 0, carried_usd
        self.unreported: list[str] = []

    def usd(self) -> float:
        return round(evals.estimate_usd(self.inp, self.out) + SPIKE_RESERVE_USD + self.carried, 4)

    def reserve(self, label: str, i: int, o: int) -> tuple[int, int]:
        if self.usd() + evals.estimate_usd(i, o) > self.cap:
            raise SystemExit(f"spend cap: reserving {label} would exceed ${self.cap:.2f} "
                             f"(current ${self.usd():.4f}); stopping before dispatch")
        self.inp += i
        self.out += o
        return i, o

    def settle(self, label: str, reserved: tuple[int, int], actual: tuple[int, int] | None) -> None:
        if actual is None or not any(actual):
            self.unreported.append(label)  # keep reservation: service returned no usage attribution
            return
        self.inp += actual[0] - reserved[0]
        self.out += actual[1] - reserved[1]


def observe(row, n_frames: int, ledger: Ledger) -> dict:
    import httpx
    from sku_to_scene import qa
    dur = float((row["clip"].get("media") or {}).get("duration_s") or 6)
    images = ([jpg_uri(row["reference"])] if row["reference"] else []) + [
        jpg_uri(row["video"], at=dur * (k + 0.5) / n_frames) for k in range(n_frames)]
    content = [{"type": "text", "text": evals.observation_prompt(None, row["reference"] is not None)}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
    ep = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    dep = os.environ["AZURE_OPENAI_VISION_DEPLOYMENT"]
    label = f"observe:{row['row_id']}"
    res = ledger.reserve(label, len(images) * IMG_TOKENS + 900, OBS_MAX_OUTPUT)
    t0 = time.time()
    r = httpx.post(f"{ep}/openai/deployments/{dep}/chat/completions?api-version={qa.AOAI_API_VERSION}",
                   headers={**qa._headers("AZURE_OPENAI_API_KEY"), "Content-Type": "application/json"},
                   json={"messages": [{"role": "user", "content": content}], "max_completion_tokens": OBS_MAX_OUTPUT,
                         "response_format": {"type": "json_object"}, "temperature": 0}, timeout=180)
    if r.status_code >= 400:
        ledger.settle(label, res, None)
    r.raise_for_status()
    body = r.json()
    u = body.get("usage") or {}
    ledger.settle(label, res, (u.get("prompt_tokens", 0), u.get("completion_tokens", 0)) if u else None)
    return {"row_id": row["row_id"], "observations": json.loads(body["choices"][0]["message"]["content"]),
            "deployment": dep, "model": body.get("model"), "request_id": r.headers.get("apim-request-id")
            or r.headers.get("x-request-id"), "usage": {"input_tokens": u.get("prompt_tokens"),
                                                        "output_tokens": u.get("completion_tokens")},
            "frames": n_frames, "reference_image": row["reference"].name if row["reference"] else None,
            "latency_s": round(time.time() - t0, 2), "prompt_version": evals.OBSERVATION_PROMPT_VERSION,
            "prompt_sha256": evals.sha256_json(content[0]["text"])}


def _items(oai, eval_id, run_id) -> list[dict]:
    items = []
    for it in oai.evals.runs.output_items.list(run_id=run_id, eval_id=eval_id):
        d = it.model_dump()
        items.append({"item": {k: v for k, v in (d.get("datasource_item") or {}).items() if k != "observations"},
                      "status": d.get("status"), "results": d.get("results")})
    return items


def run_eval(oai, name, rows, criteria, repeats, ledger, progress, model_rows: int) -> dict:
    """One eval definition, ``repeats`` runs. Persists IDs immediately; stops (and cancels) on timeout or error."""
    dataset = {"kind": "inline file_content (not a registered Foundry dataset)", "rows": len(rows),
               "rows_sha256": evals.sha256_json(rows), "criteria_sha256": evals.sha256_json(criteria)}
    ev = oai.evals.create(name=name, data_source_config={"type": "custom", "item_schema": evals.schema_for(rows),
                                                         "include_sample_schema": False},
                          testing_criteria=criteria, metadata={"dataset_version": evals.DATASET_VERSION})
    out = {"name": name, "eval_id": ev.id, "criteria": [c["name"] for c in criteria], "dataset": dataset, "runs": []}
    progress(name, out)
    for i in range(repeats):
        label = f"{name}:r{i + 1}"
        res = ledger.reserve(label, model_rows * GRADER_IN_PER_ROW, model_rows * GRADER_OUT_PER_ROW) \
            if model_rows else (0, 0)
        try:
            run = oai.evals.runs.create(eval_id=ev.id, name=f"{name}-r{i + 1}", data_source={
                "type": "jsonl", "source": {"type": "file_content", "content": [{"item": r} for r in rows]}})
        except Exception as e:  # noqa: BLE001 - recorded verbatim
            ledger.settle(label, res, None)
            out["runs"].append({"status": "create_failed", "error": str(e)[:600]})
            progress(name, out)
            break
        rec = {"run_id": run.id, "status": run.status}
        out["runs"].append(rec)
        progress(name, out)
        t0 = time.time()
        while run.status in ("queued", "in_progress", "running") and time.time() - t0 < 900:
            time.sleep(8)
            run = oai.evals.runs.retrieve(run_id=run.id, eval_id=ev.id)
        if run.status in ("queued", "in_progress", "running"):
            try:
                oai.evals.runs.cancel(run_id=run.id, eval_id=ev.id)
                rec["cancel_requested"] = True
            except Exception as e:  # noqa: BLE001
                rec["cancel_error"] = str(e)[:300]
            rec.update(status="timed_out", last_service_status=run.status)
            ledger.settle(label, res, None)
            progress(name, out)
            break
        usage = [u.model_dump() if hasattr(u, "model_dump") else u for u in (run.per_model_usage or [])]
        billed = [u for u in usage if u.get("model_name") != "azure_ai_evaluation"]  # avoid double counting
        ledger.settle(label, res, (sum(u.get("prompt_tokens", 0) or 0 for u in billed),
                                   sum(u.get("completion_tokens", 0) or 0 for u in billed)) if billed else None)
        rec.update(status=run.status, result_counts=run.result_counts.model_dump() if run.result_counts else None,
                   per_model_usage=usage, error=run.error.model_dump() if getattr(run, "error", None) else None,
                   duration_s=round(time.time() - t0, 1),
                   per_testing_criteria_results=[p.model_dump() for p in (run.per_testing_criteria_results or [])])
        try:
            rec["items"] = _items(oai, ev.id, run.id)  # also for failed runs: diagnostics live here
        except Exception as e:  # noqa: BLE001
            rec["items"], rec["items_error"] = [], str(e)[:300]
        rec["item_errors"] = [r.get("sample", {}).get("error") if isinstance(r.get("sample"), dict) else None
                              for it in rec["items"] for r in (it.get("results") or [])
                              if isinstance(r.get("sample"), dict) and r["sample"].get("error")][:5]
        progress(name, out)
        print(f"  {name} r{i + 1}: {run.status} {rec['result_counts']}", flush=True)
        if run.status != "completed":
            break
    return out


def operational_problems(results: dict) -> list[str]:
    """Service/incomplete problems (nonzero exit). Low scores and the expected negative-control rejection are not."""
    probs = []
    for check, e in results.items():
        for r in e.get("runs", []):
            if r.get("status") != "completed":
                probs.append(f"{check}:{r.get('run_id', '-')} {r.get('status')}")
            elif (r.get("result_counts") or {}).get("errored"):
                probs.append(f"{check}:{r['run_id']} errored={r['result_counts']['errored']}")
    return probs


def private_values() -> list[str]:
    acct = re.match(r"https://([^.]+)\.", os.environ.get("FOUNDRY_ENDPOINT", "https://x.")).group(1)
    return [os.environ.get(k, "") for k in ("FOUNDRY_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "CONTENT_SAFETY_ENDPOINT",
                                            "FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_SUBSCRIPTION_ID", "AZURE_TENANT_ID",
                                            "FOUNDRY_TENANT_ID", "FOUNDRY_RESOURCE_GROUP")] + [acct]


AUDIO_DIAGNOSIS = ("The cloud python-grader sandbox passes item values as strings; the first grader compared them "
                   "numerically (str > float raises TypeError) so every row was rejected as invalid user input. "
                   "Isolated with zero-token single-row probes; fixed by explicit float/bool coercion.")


def publish(record: dict) -> None:
    PUBLIC_OUT.parent.mkdir(parents=True, exist_ok=True)
    public = evals.summarize_public(json.loads(json.dumps(record, default=str)))
    sup = (record.get("superseded") or {}).get("audio_signal") or []
    if sup:
        public["superseded_audio_runs"] = {
            "diagnosis": AUDIO_DIAGNOSIS,
            "runs": [{"eval_id": s.get("eval_id"), "run_id": r.get("run_id"), "status": r.get("status"),
                      "error": (r.get("error") or {}).get("message")}
                     for s in (sup if isinstance(sup, list) else [sup]) for r in s.get("runs", [])]}
    public = evals.sanitize(public, private_values())
    PUBLIC_OUT.write_text(json.dumps(public, indent=1, allow_nan=False), encoding="utf-8")
    print(f"wrote {PUBLIC_OUT.relative_to(REPO)}")


def latest_raw() -> Path:
    raws = sorted(PRIVATE_DIR.glob("raw-*.json"))
    if not raws:
        raise SystemExit("no raw record under .sku2scene/evals; run with --yes first")
    return raws[-1]


def backfill(record: dict, grader: str) -> dict:
    """Older raw records predate routing rows / hashes in the record; recompute them deterministically (no network)."""
    if "routing_rows" not in record:
        record["routing_rows"] = evals.routing_rows(
            lambda f: json.loads((REPO / "briefs" / f).read_text(encoding="utf-8")))
    record.setdefault("hashes", {
        "media_graders_sha256": evals.sha256_json(evals.media_graders(grader)),
        "routing_graders_sha256": evals.sha256_json(evals.routing_graders(grader)),
        "observations_sha256": evals.sha256_json({k: v["observations"] for k, v in record["observations"].items()}),
        "note": "backfilled after the run from unchanged grader definitions and the recorded observations"})
    for check, e in record["evals"].items():
        if "dataset" not in e and e.get("runs"):
            e["dataset"] = {"kind": "inline file_content (not a registered Foundry dataset)",
                            "rows": (e["runs"][0].get("result_counts") or {}).get("total")}
    models = {u.get("model_name") for e in record["evals"].values() for r in e.get("runs", [])
              for u in (r.get("per_model_usage") or []) if u.get("model_name") != "azure_ai_evaluation"}
    record["grader_model"] = sorted(m for m in models if m)
    c = record.get("cost") or {}
    if "usage_not_reported_by_service" not in c:
        obs_in = sum((v.get("usage") or {}).get("input_tokens") or 0 for v in record["observations"].values())
        obs_out = sum((v.get("usage") or {}).get("output_tokens") or 0 for v in record["observations"].values())
        billed = [u for e in record["evals"].values() for r in e.get("runs", [])
                  for u in (r.get("per_model_usage") or []) if u.get("model_name") != "azure_ai_evaluation"]
        b_in = sum(u.get("prompt_tokens") or 0 for u in billed)
        b_out = sum(u.get("completion_tokens") or 0 for u in billed)
        unreported = [f"{k}:{r.get('run_id')}" for k, e in record["evals"].items() for r in e.get("runs", [])
                      if not any(u.get("model_name") != "azure_ai_evaluation" for u in (r.get("per_model_usage") or []))]
        record["cost"] = {**c, "as_logged_during_run_usd": c.get("estimated_usd_this_run"),
                          "correction": "the run-time ledger also summed the duplicate 'azure_ai_evaluation' usage "
                          "rows; recomputed from model rows only (Stage A + grader model)",
                          "input_tokens": obs_in + b_in, "output_tokens": obs_out + b_out,
                          "stage_a_tokens": [obs_in, obs_out], "stage_b_tokens": [b_in, b_out],
                          "estimated_usd_this_run": round(evals.estimate_usd(obs_in + b_in, obs_out + b_out)
                                                          + SPIKE_RESERVE_USD, 4),
                          "usage_not_reported_by_service": unreported}
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="actually call Azure (billable)")
    ap.add_argument("--max-usd", type=float, default=5.0)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--reuse-observations", action="store_true", help="reuse cached Stage A observations")
    ap.add_argument("--grader-model", default=None, help="grader deployment (default: AZURE_OPENAI_VISION_DEPLOYMENT)")
    ap.add_argument("--republish", action="store_true", help="rebuild the public JSON from the latest raw record "
                    "(no network)")
    ap.add_argument("--only-audio", action="store_true", help="re-run only the audio-signal python grader (no model "
                    "tokens) and merge it into the latest raw record")
    a = ap.parse_args()

    load_dotenv(REPO / ".env")
    if a.republish:
        record = backfill(json.loads(latest_raw().read_text(encoding="utf-8")),
                          a.grader_model or os.environ.get("AZURE_OPENAI_VISION_DEPLOYMENT", "brand-qa-vision"))
        publish(record)
        probs = operational_problems(record["evals"])
        print("operational problems:", probs or "none")
        return 1 if probs else 0

    clips, products, brands = load_inputs()
    rows = media_rows(clips, products, brands)
    routing = evals.routing_rows(lambda f: json.loads((REPO / "briefs" / f).read_text(encoding="utf-8")))
    est = plan_estimate(rows, routing, a.repeats, a.frames)
    print(json.dumps({"media_rows": len(rows), "routing_cases": len(routing), "repeats": a.repeats, **est}, indent=1))
    if not a.only_audio and est["estimate_usd"] > a.max_usd:
        print(f"estimate exceeds cap ${a.max_usd:.2f}; not running")
        return 2
    if not a.yes:
        print("plan only (no network). Re-run with --yes to call Azure.")
        return 0
    for k in ("FOUNDRY_PROJECT_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_VISION_DEPLOYMENT"):
        if not os.environ.get(k):
            raise SystemExit(f"{k} is not set")
    grader = a.grader_model or os.environ["AZURE_OPENAI_VISION_DEPLOYMENT"]
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)

    from azure.ai.projects import AIProjectClient
    from sku_to_scene.config import get_settings
    from sku_to_scene.credentials import create_credential
    oai = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                          credential=create_credential(get_settings())).get_openai_client()

    # Audio signal (local measurement, free); cloud python grader uses no model tokens.
    audio = {}
    for r in rows:
        c = r["clip"]
        if r["row_id"] == evals.NEGATIVE_CONTROL_ID:
            continue
        has = bool((c.get("media") or {}).get("has_audio"))
        req = str(c.get("audio") or "").startswith("native")
        m = measure_audio(r["video"]) if has else None
        audio[r["row_id"]] = {"has_audio": has, "audio_requested": req, **(m or {}),
                              "verdict": evals.audio_signal_verdict(has, req, m)}
    audio_rows = [{"row_id": k, "has_audio": v["has_audio"], "audio_requested": v["audio_requested"],
                   "integrated_lufs": v.get("integrated_lufs"), "true_peak_dbtp": v.get("true_peak_dbtp")}
                  for k, v in audio.items() if v["verdict"]["label"] != "not_applicable"]
    audio_criteria = [{"type": "python", "name": "audio_signal", "source": evals.AUDIO_PYTHON_GRADER,
                       "pass_threshold": 0.5}]

    if a.only_audio:
        raw_path = latest_raw()
        record = backfill(json.loads(raw_path.read_text(encoding="utf-8")), grader)
        ledger = Ledger(a.max_usd, carried_usd=record["cost"]["estimated_usd_this_run"] - SPIKE_RESERVE_USD)
        sup = record.setdefault("superseded", {})
        prev = sup.get("audio_signal")
        prev = prev if isinstance(prev, list) else ([prev] if prev else [])
        cur = record["evals"].get("audio_signal")
        if cur and all(cur.get("eval_id") != p.get("eval_id") for p in prev):
            prev.append(cur)
        sup["audio_signal"] = prev
        record["audio"] = audio
        record["evals"]["audio_signal"] = run_eval(oai, f"sku2scene-audio-{evals.AUDIO_RUBRIC_VERSION}", audio_rows,
                                                   audio_criteria, 1, ledger, lambda *_: None, model_rows=0)
        record["operational_status"] = operational_problems(record["evals"]) or "ok"
        raw_path.write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
        publish(record)
        return 1 if record["operational_status"] != "ok" else 0

    ledger = Ledger(a.max_usd)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    progress_path = PRIVATE_DIR / f"progress-{stamp}.json"
    progress_state: dict = {}

    def progress(name, out):
        progress_state[name] = {"eval_id": out["eval_id"], "runs": [{k: r.get(k) for k in ("run_id", "status")}
                                                                    for r in out["runs"]]}
        progress_path.write_text(json.dumps(progress_state, indent=1), encoding="utf-8")

    # Stage A.
    cache = json.loads(OBS_CACHE.read_text(encoding="utf-8")) if a.reuse_observations and OBS_CACHE.exists() else {}
    obs = {}
    for r in rows:
        if r["row_id"] in cache:
            obs[r["row_id"]] = {**cache[r["row_id"]], "reused": True}
            continue
        print(f"observe {r['row_id']}", flush=True)
        obs[r["row_id"]] = observe(r, a.frames, ledger)
        OBS_CACHE.write_text(json.dumps({**cache, **obs}, indent=1), encoding="utf-8")

    g = evals.media_graders(grader)

    def ds(check):
        return [{"row_id": r["row_id"], "stage": r["stage"], "product_name": r["product_name"],
                 "prompt": r["clip"].get("prompt", "")[:1200], "logo_rule": r["logo_rule"],
                 "expected_identity": r["expected_identity"],
                 "observations": json.dumps(obs[r["row_id"]]["observations"], ensure_ascii=False)[:12000]}
                for r in rows if r["applicability"][check] is None]

    record = {
        "schema": "sku2scene.foundry-evals/v1", "created_at": stamp, "dataset_version": evals.DATASET_VERSION,
        "versions": {"media_rubric": evals.MEDIA_RUBRIC_VERSION, "routing_cases": evals.ROUTING_CASES_VERSION,
                     "audio_rubric": evals.AUDIO_RUBRIC_VERSION, "observation_prompt": evals.OBSERVATION_PROMPT_VERSION},
        "hashes": {"media_graders_sha256": evals.sha256_json(g), "routing_graders_sha256":
                   evals.sha256_json(evals.routing_graders(grader)), "audio_grader_sha256":
                   evals.sha256_json(audio_criteria), "observations_sha256": evals.sha256_json(
                       {k: v["observations"] for k, v in obs.items()})},
        "design": "two-stage: direct vision observations (Stage A) -> Foundry Evals text graders (Stage B)",
        "grader_deployment": grader, "repeats": a.repeats, "frames_per_clip": a.frames,
        "applicability": {r["row_id"]: r["applicability"] for r in rows},
        "expected_identity": {r["row_id"]: r["expected_identity"] for r in rows},
        "stages": {r["row_id"]: r["stage"] for r in rows}, "routing_rows": routing,
        "observations": obs, "audio": audio, "evals": {}, "image_input_spikes": SPIKES,
    }
    raw_path = PRIVATE_DIR / f"raw-{stamp}.json"

    def save():
        record["cost"] = {"assumed_usd_per_m_input": evals.ASSUMED_USD_PER_M_INPUT,
                          "assumed_usd_per_m_output": evals.ASSUMED_USD_PER_M_OUTPUT, "input_tokens": ledger.inp,
                          "output_tokens": ledger.out, "spike_reservation_usd": SPIKE_RESERVE_USD,
                          "estimated_usd_this_run": ledger.usd(), "cap_usd": a.max_usd,
                          "pre_run_estimate_usd": est["estimate_usd"], "usage_not_reported_by_service": ledger.unreported}
        raw_path.write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")

    try:
        for check in ("concept_adherence", "product_identity", "brand_marks"):
            d = ds(check)
            record["evals"][check] = run_eval(oai, f"sku2scene-{check}-{evals.MEDIA_RUBRIC_VERSION}", d, [g[check]],
                                              a.repeats, ledger, progress, model_rows=len(d))
            save()
        record["evals"]["routing"] = run_eval(oai, f"sku2scene-routing-{evals.ROUTING_CASES_VERSION}", routing,
                                              evals.routing_graders(grader), a.repeats, ledger, progress,
                                              model_rows=len(routing))
        save()
        record["evals"]["audio_signal"] = run_eval(oai, f"sku2scene-audio-{evals.AUDIO_RUBRIC_VERSION}", audio_rows,
                                                   audio_criteria, 1, ledger, progress, model_rows=0)
    finally:
        record["operational_status"] = operational_problems(record["evals"]) or "ok"
        save()
    publish(record)
    print(f"estimated spend ${ledger.usd():.4f} (cap ${a.max_usd:.2f}); operational: {record['operational_status']}")
    return 1 if record["operational_status"] != "ok" else 0


if __name__ == "__main__":
    sys.exit(main())
