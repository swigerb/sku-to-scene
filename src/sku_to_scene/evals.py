"""Foundry Evaluations for SKU to Scene: offline-testable datasets, applicability rules and sanitizers.

Design (disclosed in docs/foundry-evaluations-plan.md):

* Stage A - direct vision observation. The existing ``brand-qa-vision`` chat deployment looks at the approved PIM
  reference (when the render used one) plus sampled frames and writes neutral, factual observations. Foundry Evals
  rejected native image input for grader models in this account (recorded spikes), so images never reach the grader.
* Stage B - Foundry Evaluations. Cloud ``label_model`` graders score the Stage A text against grounded expectations
  (prompt, stage, brand rules). Routing is evaluated separately from media, with no media at all. Audio is a
  signal-level check only (stream present, loudness, true peak); it says nothing about whether sounds match visuals.

Nothing here makes network calls; ``scripts/run_foundry_evals.py`` does, and only with an explicit ``--yes``.
Historical QA verdicts in demo-cache/manifest.json are never modified.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict
from typing import Any

from .router import Brief, route

DATASET_VERSION = "sku2scene-evals-v1"
MEDIA_RUBRIC_VERSION = "media-rubric-v1"
ROUTING_CASES_VERSION = "routing-cases-v1"
AUDIO_RUBRIC_VERSION = "audio-signal-v1"
OBSERVATION_PROMPT_VERSION = "observation-v1"

# Conservative assumed token prices for estimates and the spend cap (not a bill; real rates are lower or similar).
ASSUMED_USD_PER_M_INPUT = 1.0
ASSUMED_USD_PER_M_OUTPUT = 5.0

# audio-signal-v1: playback-comfort band chosen for this demo, plus a common streaming true-peak ceiling.
AUDIO_TRUE_PEAK_MAX_DBTP = -1.0
AUDIO_INTEGRATED_LUFS_RANGE = (-30.0, -10.0)

MEDIA_CHECKS = ("concept_adherence", "product_identity", "brand_marks", "audio_signal")
NEGATIVE_CONTROL_ID = "negative-control"
NEGATIVE_CONTROL_REFERENCE_SKU = "CTP-DRL-20V-BL"
NEGATIVE_CONTROL_SOURCE_CLIP = "lto-hero-kling"

_T2V_NA = ("text-to-video render: no approved PIM image was an input, so identity and brand marks are judged at the "
           "final image-to-video stage, not here")


def applicability(clip: dict[str, Any]) -> dict[str, str | None]:
    """Per-check applicability for a cached clip. ``None`` = applies; a string = the N/A reason.

    N/A is a deterministic rule recorded alongside results; it is never counted as a pass.
    """
    i2v = clip.get("mode") == "image-to-video" and bool(clip.get("source_image"))
    has_audio = bool((clip.get("media") or {}).get("has_audio"))
    audio_requested = str(clip.get("audio") or "").startswith("native")
    if has_audio or audio_requested:
        audio_na = None
    else:
        audio_na = "no audio track in the file and audio was not requested for this render"
    return {
        "concept_adherence": None,
        "product_identity": None if i2v else _T2V_NA,
        "brand_marks": None if i2v else _T2V_NA,
        "audio_signal": audio_na,
    }


def stage_of(clip: dict[str, Any]) -> str:
    return "concept draft" if clip["id"].startswith("lto-draft-") else "final render"


# ---------------------------------------------------------------- Stage A (observation prompt)

def observation_prompt(product_name: str | None, has_reference: bool) -> str:
    ref = ("The FIRST image is the approved catalog (PIM) reference photo. The remaining images are frames sampled "
           "in order from a generated video. " if has_reference else
           "All images are frames sampled in order from a generated video; there is no reference photo. ")
    return (
        "You are a careful visual observer. Describe ONLY what is visible; do not judge quality, do not score, do not "
        "guess at intent. " + ref +
        (f"The catalog product name is: {product_name}. " if product_name else "") +
        'Return JSON: {"reference": null or {"product_type": str, "form_and_packaging": str, "colors": [str], '
        '"visible_text_and_marks": [str]}, "frames": [{"index": int, "scene": str, "products_visible": [str], '
        '"visible_text_and_marks": [str], "people": str, "motion_or_action": str, "visual_artifacts": [str]}], '
        '"comparison_notes": str (neutral factual similarities and differences between the frames and the reference; '
        'empty string if no reference), "scene_summary": str}. Transcribe visible text exactly; write "illegible" '
        "when text is present but unreadable."
    )


# ---------------------------------------------------------------- audio signal (local measurement)

_I_RE = re.compile(r"I:\s+(-?\d+(?:\.\d+)?|-inf)\s+LUFS")
_LRA_RE = re.compile(r"LRA:\s+(-?\d+(?:\.\d+)?)\s+LU")
_TP_RE = re.compile(r"True peak:\s+Peak:\s+(-?\d+(?:\.\d+)?|-inf)\s+dBFS", re.S)


def parse_ebur128(stderr: str) -> dict[str, float | None]:
    """Parse the summary block of ``ffmpeg -af ebur128=peak=true -f null -`` output."""
    summary = stderr[stderr.rfind("Summary:"):] if "Summary:" in stderr else stderr

    def num(rx: re.Pattern[str]) -> float | None:
        m = rx.search(summary)
        if not m:
            return None
        return float("-inf") if m.group(1) == "-inf" else float(m.group(1))

    return {"integrated_lufs": num(_I_RE), "loudness_range_lu": num(_LRA_RE), "true_peak_dbtp": num(_TP_RE)}


def audio_signal_verdict(has_audio: bool, requested: bool, m: dict[str, float | None] | None) -> dict[str, Any]:
    """audio-signal-v1. Signal-level only: says nothing about whether the sounds match the visuals."""
    reasons: list[str] = []
    if not has_audio:
        if requested:
            return {"label": "fail", "reasons": ["native audio was requested but the file has no audio stream"]}
        return {"label": "not_applicable", "reasons": ["no audio stream; audio was not requested"]}
    m = m or {}
    i, tp = m.get("integrated_lufs"), m.get("true_peak_dbtp")
    lo, hi = AUDIO_INTEGRATED_LUFS_RANGE
    if i is None or tp is None:
        return {"label": "fail", "reasons": ["loudness measurement unavailable"]}
    if tp > AUDIO_TRUE_PEAK_MAX_DBTP:
        reasons.append(f"true peak {tp:+.1f} dBTP exceeds {AUDIO_TRUE_PEAK_MAX_DBTP:+.1f} dBTP (clipping risk)")
    if i < lo:
        reasons.append(f"integrated loudness {i:.1f} LUFS is below {lo:.0f} LUFS (very quiet)")
    if i > hi:
        reasons.append(f"integrated loudness {i:.1f} LUFS is above {hi:.0f} LUFS (very loud)")
    if reasons:
        return {"label": "fail", "reasons": reasons}
    return {"label": "pass", "reasons": [f"{i:.1f} LUFS integrated, {tp:+.1f} dBTP true peak"]}


# The cloud python-grader sandbox delivers item values as strings (verified by probe), so coerce explicitly.
AUDIO_PYTHON_GRADER = f'''def grade(sample, item) -> float:
    def flag(v):
        return str(v).strip().lower() in ("true", "1")
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    if not flag(item.get("has_audio")):
        return 0.0 if flag(item.get("audio_requested")) else 1.0
    i = num(item.get("integrated_lufs"))
    tp = num(item.get("true_peak_dbtp"))
    if i is None or tp is None or i != i or tp != tp:
        return 0.0
    ok = tp <= {AUDIO_TRUE_PEAK_MAX_DBTP} and {AUDIO_INTEGRATED_LUFS_RANGE[0]} <= i <= {AUDIO_INTEGRATED_LUFS_RANGE[1]}
    return 1.0 if ok else 0.0
'''


def finite(x: Any) -> Any:
    """JSON-safe numbers: browsers reject -Infinity/NaN, so non-finite floats become None (recursively)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: finite(v) for k, v in x.items()}
    if isinstance(x, list):
        return [finite(v) for v in x]
    return x


# ---------------------------------------------------------------- routing cases (no media)

_BRIEF_FILES = {
    "qsr-lto-hero": "qsr-lto-pumpkin-cold-brew.json",
    "apparel-pdp": "apparel-pdp-lookbook.json",
    "home-drill": "home-improvement-drill.json",
    "home-patio-layout": "home-patio-layout.json",
    "grocery-endcap": "grocery-flu-season-endcap.json",
    "electronics-text-audio": "electronics-laptop-text.json",
}

# Grounded expectations: the requested routing table (README / docs/model-routing.md), not the router's own output.
ROUTING_EXPECTATIONS: list[dict[str, Any]] = [
    {"case_id": "qsr-lto-hero", "brief_file": _BRIEF_FILES["qsr-lto-hero"], "expected_model": "kling-v3-pro",
     "expected_mode": "image-to-video", "rule": "Approved hero image + native audio -> Kling v3 Pro"},
    {"case_id": "apparel-pdp", "brief_file": _BRIEF_FILES["apparel-pdp"], "expected_model": "kling-v3-pro",
     "expected_mode": "image-to-video", "rule": "Approved PIM image, fabric physics -> Kling v3 Pro"},
    {"case_id": "home-drill", "brief_file": _BRIEF_FILES["home-drill"], "expected_model": "kling-v3-pro",
     "expected_mode": "image-to-video", "rule": "Complex physical interaction from a PIM image -> Kling v3 Pro"},
    {"case_id": "home-patio-layout", "brief_file": _BRIEF_FILES["home-patio-layout"],
     "expected_model": "minimax-h3-max", "expected_mode": "text-to-video",
     "rule": "Strict multi-object layout -> MiniMax H3 Max"},
    {"case_id": "grocery-endcap", "brief_file": _BRIEF_FILES["grocery-endcap"],
     "expected_model": "minimax-h3-max-turbo", "expected_mode": "image-to-video",
     "rule": "High-volume weekly promos -> MiniMax H3 Max Turbo (half the H3 Max per-second rate)"},
    {"case_id": "electronics-text-audio", "brief_file": _BRIEF_FILES["electronics-text-audio"],
     "expected_model": "ltx-2.5-pro", "expected_mode": "text-to-video",
     "rule": "Text brief, final render with synchronized audio -> LTX-2.5 Pro"},
    {"case_id": "draft-no-audio", "brief": {"prompt": "Storyboard draft of a fall cold brew cup on a cafe counter",
                                            "channel": "tiktok", "stage": "draft"},
     "expected_model": "minimax-h3-max-turbo", "expected_mode": "text-to-video",
     "rule": "Drafting / A-B testing -> fast tier (Turbo first without audio)"},
    {"case_id": "draft-with-audio", "brief": {"prompt": "Storyboard draft: iced cold brew pour with ice clinking",
                                              "channel": "tiktok", "stage": "draft", "needs_audio": True},
     "expected_model": "ltx-2.5-fast", "expected_mode": "text-to-video",
     "rule": "Drafting with synchronized audio -> LTX-2.5 Fast"},
    {"case_id": "pim-strict-layout", "brief": {"prompt": "Endcap layout: exactly three bundles left to right",
                                               "channel": "signage", "source": "pim_image",
                                               "image_path": "assets/products/woodgrove-wellness-bundle.png",
                                               "strict_layout": True},
     "expected_model": "minimax-h3-max", "expected_mode": "image-to-video",
     "rule": "Strict adherence to multi-object layout -> MiniMax H3 Max"},
]


def routing_rows(load_brief) -> list[dict[str, Any]]:
    """Rows comparing the router's actual decision with the grounded expectation for each case.

    ``load_brief(filename) -> dict`` is injected so tests can run without touching the briefs folder.
    """
    rows = []
    for case in ROUTING_EXPECTATIONS:
        raw = load_brief(case["brief_file"]) if "brief_file" in case else dict(case["brief"])
        brief = Brief.from_dict(raw)
        d = route(brief)
        b = asdict(brief)
        rows.append({
            "case_id": case["case_id"],
            "brief_summary": (f"stage={b['stage']}; source={b['source']}; channel={b['channel']}; "
                              f"needs_audio={b['needs_audio']}; strict_layout={b['strict_layout']}; "
                              f"physical_interaction={b['physical_interaction']}; volume={b['volume']}"),
            "brief_prompt": b["prompt"][:600],
            "rule": case["rule"],
            "expected_model": case["expected_model"],
            "expected_mode": case["expected_mode"],
            "actual_model": d.model,
            "actual_mode": d.mode,
            "actual_rationale": " | ".join(d.rationale),
        })
    return rows


# ---------------------------------------------------------------- Stage B grader definitions

def _label_grader(name: str, model: str, system: str, user: str, labels: list[str], passing: list[str]) -> dict:
    return {
        "type": "label_model", "name": name, "model": model,
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "labels": labels, "passing_labels": passing,
    }


def media_graders(model: str) -> dict[str, dict]:
    obs = "Visual observations (written by a separate vision model from sampled frames):\n{{item.observations}}"
    return {
        "concept_adherence": _label_grader(
            "concept_adherence", model,
            "You grade whether a generated retail video matches its creative brief, judged ONLY from written visual "
            "observations. Be stage-aware: a concept draft is judged on scene, action, mood and product category, not "
            "on final brand logo or label fidelity. A final render must also show the specific product and the "
            "requested scene. Elements that a few still frames cannot show (sound, subtle motion) are not failures. "
            "Answer 'pass' when the core requested scene and product are clearly present, 'partial' when the core is "
            "present but a requested element is missing or contradicted, 'fail' when the core scene or product is "
            "absent. Start with one sentence of reasoning, then the label.",
            "Stage: {{item.stage}}\nProduct: {{item.product_name}}\nBrief prompt: {{item.prompt}}\n\n" + obs,
            ["pass", "partial", "fail"], ["pass"]),
        "product_identity": _label_grader(
            "product_identity", model,
            "You decide whether the product shown in generated video frames is the SAME catalog product as the "
            "approved reference photo, using ONLY the written observations of both. Same product means same product "
            "type, form/packaging and colorway; background and camera changes do not matter. Answer 'match', "
            "'mismatch' or 'uncertain' (only when the observations genuinely do not allow a decision). Start with one "
            "sentence of reasoning, then the label.",
            "Catalog product: {{item.product_name}}\n\n" + obs,
            ["match", "mismatch", "uncertain"], ["match"]),
        "brand_marks": _label_grader(
            "brand_marks", model,
            "You check brand marks (logos, wordmarks, labels) in generated video frames against the approved "
            "reference photo and the brand's logo rule, using ONLY the written observations. 'consistent': marks "
            "visible in the reference appear in the frames without misspelling or distortion, and no marks are "
            "invented. 'not_visible': the reference marks cannot be seen in the frames (occluded, too small or "
            "cropped) but nothing contradicts them. 'violation': a mark is misspelled, distorted, recolored or "
            "invented, or the brand rule is broken. Start with one sentence of reasoning, then the label.",
            "Brand logo rule: {{item.logo_rule}}\nCatalog product: {{item.product_name}}\n\n" + obs,
            ["consistent", "not_visible", "violation"], ["consistent"]),
    }


def routing_graders(model: str) -> list[dict]:
    return [
        {"type": "string_check", "name": "model_matches_expected", "input": "{{item.actual_model}}",
         "reference": "{{item.expected_model}}", "operation": "eq"},
        {"type": "string_check", "name": "mode_matches_expected", "input": "{{item.actual_mode}}",
         "reference": "{{item.expected_mode}}", "operation": "eq"},
        _label_grader(
            "rationale_grounded", model,
            "You audit a video-model router. Given the brief attributes, the routing rule the business expects, and "
            "the router's own rationale, decide whether the rationale cites the brief attributes that actually drive "
            "the expected rule and does not invent requirements. Answer 'grounded' or 'ungrounded'. Start with one "
            "sentence of reasoning, then the label.",
            "Brief attributes: {{item.brief_summary}}\nBrief prompt: {{item.brief_prompt}}\n"
            "Expected rule: {{item.rule}}\nRouter chose: {{item.actual_model}} ({{item.actual_mode}})\n"
            "Router rationale: {{item.actual_rationale}}",
            ["grounded", "ungrounded"], ["grounded"]),
    ]


def schema_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for r in rows:
        for k, v in r.items():
            if v is None:
                continue
            t = "boolean" if isinstance(v, bool) else "number" if isinstance(v, (int, float)) else "string"
            props.setdefault(k, {"type": t})
    for r in rows:
        for k in r:
            props.setdefault(k, {"type": "string"})
    for k in props:
        if any(r.get(k) is None for r in rows):
            t = props[k]["type"]
            props[k] = {"type": t if isinstance(t, list) else [t, "null"]}
    return {"type": "object", "properties": props, "required": sorted(k for k in props if all(k in r for r in rows))}


# ---------------------------------------------------------------- cost and sanitizing

def estimate_usd(input_tokens: int, output_tokens: int) -> float:
    return round(input_tokens / 1e6 * ASSUMED_USD_PER_M_INPUT + output_tokens / 1e6 * ASSUMED_USD_PER_M_OUTPUT, 4)


_DROP_KEYS = {"report_url", "created_by", "owner", "data_source"}
_HOST_RE = re.compile(r"https?://[A-Za-z0-9.-]+\.(?:azure\.com|azure\.net|microsoft\.com)[^\s'\"<>)]*")
_GUIDISH_KEYS = {"subscription_id", "tenant_id", "resource_group", "user", "email"}


def sanitize(obj: Any, private: list[str] | tuple[str, ...] = ()) -> Any:
    """Remove private Azure identifiers before publishing: hosts, report URLs, creators and known secret values."""
    secrets = [p for p in private if p and len(p) >= 4]

    def clean_str(s: str) -> str:
        s = _HOST_RE.sub("<redacted-azure-url>", s)
        for p in secrets:
            s = s.replace(p, "<redacted>")
        return s

    if isinstance(obj, dict):
        return {k: sanitize(v, secrets) for k, v in obj.items() if k not in _DROP_KEYS and k not in _GUIDISH_KEYS}
    if isinstance(obj, list):
        return [sanitize(v, secrets) for v in obj]
    if isinstance(obj, str):
        return clean_str(obj)
    return obj


# ---------------------------------------------------------------- result parsing and public summary

def sha256_json(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                                 default=str).encode("utf-8")).hexdigest()


def parse_grader_output(result: dict[str, Any]) -> dict[str, Any]:
    """Split one Evals result into the service verdict and the grader's own structured answer.

    For ``label_model`` the service reports ``label`` as pass/fail against ``passing_labels`` and leaves ``reason``
    empty; the label the grader actually chose (e.g. ``partial``) and its reasoning steps live in
    ``sample.output[0].content`` as JSON. Both are kept, distinctly.
    """
    out = {"service_passed": result.get("passed"), "service_score": result.get("score"),
           "service_label": result.get("label"), "grader_label": None, "reasons": []}
    sample = result.get("sample") or {}
    for msg in sample.get("output") or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if not content:
            continue
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            out["reasons"].append(str(content)[:400])
            continue
        out["grader_label"] = parsed.get("result")
        for step in parsed.get("steps") or []:
            text = " ".join(x for x in (step.get("description"), step.get("conclusion")) if x)
            if text:
                out["reasons"].append(text[:600])
    if out["grader_label"] is None and result.get("type") in ("string_check", "python"):
        out["grader_label"] = "pass" if result.get("passed") else "fail"
    return out


def _consensus(labels: list[str | None]) -> dict[str, Any]:
    """Unanimous label, or ``split`` (never majority-voted into approval) flagged for human review."""
    vals = [x for x in labels if x is not None]
    if not vals:
        return {"label": None, "agreement": None, "needs_human_review": True}
    counts = Counter(vals)
    label, n = counts.most_common(1)[0]
    unanimous = n == len(labels)
    return {"label": label if unanimous else "split", "agreement": f"{n}/{len(labels)} {label}",
            "label_counts": dict(counts), "needs_human_review": not unanimous}


def summarize_public(raw: dict[str, Any]) -> dict[str, Any]:
    """Compact, sanitizable public record built from the private raw record (no network)."""
    evals_raw = raw["evals"]
    runs, per_row = {}, {}
    for check, e in evals_raw.items():
        runs[check] = {"eval_id": e.get("eval_id"), "criteria": e.get("criteria"), "dataset": e.get("dataset"),
                       "runs": [{k: r.get(k) for k in ("run_id", "status", "result_counts", "per_model_usage", "error",
                                                       "duration_s", "item_errors")} for r in e.get("runs", [])]}
        for rep, r in enumerate(e.get("runs", [])):
            for it in r.get("items") or []:
                rid = it["item"].get("row_id") or it["item"].get("case_id")
                for res in it.get("results") or []:
                    slot = per_row.setdefault((check, rid, res.get("name")), [])
                    slot.append({"repeat": rep + 1, "run_id": r.get("run_id"), **parse_grader_output(res)})

    def media_check(row_id: str, check: str) -> dict[str, Any]:
        na = raw["applicability"][row_id][check]
        if na:
            return {"applicable": False, "na_reason": na}
        reps = per_row.get((check, row_id, check), [])
        return {"applicable": True, "repeats": reps, **_consensus([x["grader_label"] for x in reps]),
                "service_passed": [x["service_passed"] for x in reps]}

    media = {}
    for row_id, stage in raw["stages"].items():
        checks = {c: media_check(row_id, c) for c in ("concept_adherence", "product_identity", "brand_marks")}
        a = raw.get("audio", {}).get(row_id)
        if row_id == NEGATIVE_CONTROL_ID:
            checks["audio_signal"] = {"applicable": False, "na_reason": raw["applicability"][row_id]["audio_signal"]}
        elif not a or a["verdict"]["label"] == "not_applicable":
            checks["audio_signal"] = {"applicable": False,
                                      "na_reason": raw["applicability"][row_id]["audio_signal"]
                                      or "no audio stream; audio was not requested"}
        else:
            cloud = per_row.get(("audio_signal", row_id, "audio_signal"), [])
            verdict = (_consensus([x["grader_label"] for x in cloud]) if cloud
                       else {"label": a["verdict"]["label"], "agreement": "local only"})
            checks["audio_signal"] = {"applicable": True, "scope": "signal only (stream, loudness, true peak); not "
                                      "semantic or sync", "local": a["verdict"],
                                      "measurements": {k: a.get(k) for k in ("integrated_lufs", "true_peak_dbtp",
                                                                             "loudness_range_lu")},
                                      "cloud": cloud, **verdict}
        obs = raw["observations"].get(row_id, {})
        media[row_id] = {"stage": stage, "expected_identity": raw["expected_identity"][row_id], "checks": checks,
                         "observation": {"scene_summary": (obs.get("observations") or {}).get("scene_summary"),
                                         "comparison_notes": (obs.get("observations") or {}).get("comparison_notes"),
                                         "request_id": obs.get("request_id"), "usage": obs.get("usage"),
                                         "frames": obs.get("frames"), "reference_image": obs.get("reference_image"),
                                         "deployment": obs.get("deployment"), "model": obs.get("model"),
                                         "observations_sha256": sha256_json(obs.get("observations"))}}
    nc = media.get(NEGATIVE_CONTROL_ID, {}).get("checks", {}).get("product_identity", {})
    routing = {}
    for (check, rid, name), reps in per_row.items():
        if check != "routing":
            continue
        routing.setdefault(rid, {})[name] = {"repeats": reps, **_consensus([x["grader_label"] for x in reps])}
    for row in raw.get("routing_rows", []):
        if row["case_id"] in routing:
            routing[row["case_id"]]["case"] = {k: row[k] for k in ("rule", "expected_model", "expected_mode",
                                                                   "actual_model", "actual_mode")}
    return finite({
        "schema": "sku2scene.foundry-evals.public/v1", "created_at": raw["created_at"],
        "design": raw["design"], "versions": raw["versions"], "hashes": raw.get("hashes"),
        "grader_deployment": raw["grader_deployment"], "grader_model": raw.get("grader_model"),
        "repeats": raw["repeats"], "frames_per_clip": raw["frames_per_clip"],
        "runs": runs, "media": media, "routing": routing,
        "negative_control": {"source_clip": NEGATIVE_CONTROL_SOURCE_CLIP,
                             "reference_sku": NEGATIVE_CONTROL_REFERENCE_SKU, "expected_label": "mismatch",
                             "observed": nc.get("label"), "agreement": nc.get("agreement"),
                             "expected_behavior_met": nc.get("label") == "mismatch"},
        "image_input_spikes": raw["image_input_spikes"], "cost": raw["cost"],
        "operational_status": raw.get("operational_status"),
    })
