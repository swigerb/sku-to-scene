import importlib.util
import json
import math
from pathlib import Path

import pytest

from sku_to_scene import evals

REPO = Path(__file__).resolve().parents[1]
PUBLIC = REPO / "demo-cache" / "evaluations"


def _runner():
    spec = importlib.util.spec_from_file_location("run_foundry_evals", REPO / "scripts" / "run_foundry_evals.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_grader_answer_is_kept_distinct_from_service_normalized_fail():
    result = {"type": "label_model", "passed": False, "score": 0, "label": "fail", "reason": None,
              "sample": {"output": [{"content": json.dumps(
                  {"result": "partial", "steps": [{"description": "cup shown", "conclusion": "no street scene"}]})}]}}
    parsed = evals.parse_grader_output(result)
    assert parsed["service_label"] == "fail" and parsed["service_passed"] is False
    assert parsed["grader_label"] == "partial"
    assert parsed["reasons"] == ["cup shown no street scene"]


def test_disagreeing_repeats_are_split_for_human_review_not_majority_voted():
    c = evals._consensus(["violation", "consistent", "consistent"])
    assert c["label"] == "split" and c["needs_human_review"] is True
    assert c["label_counts"] == {"violation": 1, "consistent": 2}
    assert evals._consensus(["match"] * 3)["needs_human_review"] is False
    assert evals._consensus([None, None])["label"] is None


def test_non_finite_loudness_is_json_safe():
    m = evals.parse_ebur128("Summary:\n  Integrated loudness:\n    I:         -inf LUFS\n"
                            "  True peak:\n    Peak:       -inf dBFS")
    assert m["integrated_lufs"] == -math.inf
    json.dumps(evals.finite(m), allow_nan=False)
    assert evals.finite({"a": [float("nan")]}) == {"a": [None]}


@pytest.mark.parametrize("has_audio,requested,m,label", [
    (False, False, None, "not_applicable"),
    (False, True, None, "fail"),
    (True, True, {"integrated_lufs": -24.6, "true_peak_dbtp": 2.0}, "fail"),
    (True, False, {"integrated_lufs": -42.8, "true_peak_dbtp": -24.5}, "fail"),
    (True, False, {"integrated_lufs": -25.6, "true_peak_dbtp": -11.6}, "pass"),
])
def test_audio_signal_verdict_matches_cloud_python_grader(has_audio, requested, m, label):
    assert evals.audio_signal_verdict(has_audio, requested, m)["label"] == label
    ns: dict = {}
    exec(evals.AUDIO_PYTHON_GRADER, ns)
    # The cloud sandbox passes item values as strings.
    item = {"has_audio": str(has_audio), "audio_requested": str(requested),
            **{k: str(v) for k, v in (m or {}).items()}}
    assert ns["grade"]({}, item) == (0.0 if label == "fail" else 1.0)


def test_text_to_video_and_silent_clips_get_recorded_na_reasons():
    t2v = evals.applicability({"id": "lto-draft-2", "mode": "text-to-video", "media": {"has_audio": False}})
    assert t2v["concept_adherence"] is None
    assert t2v["product_identity"] and t2v["brand_marks"] and t2v["audio_signal"]
    i2v = evals.applicability({"id": "h", "mode": "image-to-video", "source_image": "x.png",
                               "audio": "native", "media": {"has_audio": True}})
    assert all(v is None for v in i2v.values())


def test_schema_marks_nullable_columns():
    s = evals.schema_for([{"a": 1.5, "b": None}, {"a": None, "b": "x"}])
    assert s["properties"]["a"]["type"] == ["number", "null"]
    assert s["properties"]["b"]["type"] == ["string", "null"]


def test_ledger_reserves_before_dispatch_and_keeps_unreported_reservations():
    runner = _runner()
    ledger = runner.Ledger(cap=0.06 + runner.SPIKE_RESERVE_USD)
    r = ledger.reserve("a", 10_000, 2_000)  # $0.02
    ledger.settle("a", r, None)  # service returned no usage
    assert ledger.unreported == ["a"] and ledger.usd() == pytest.approx(0.07)
    with pytest.raises(SystemExit, match="spend cap"):
        ledger.reserve("b", 40_000, 2_000)  # +$0.05 would exceed
    assert ledger.usd() == pytest.approx(0.07)


def test_failed_or_errored_runs_are_operational_problems_but_low_scores_are_not():
    runner = _runner()
    probs = runner.operational_problems({
        "concept": {"runs": [{"run_id": "r1", "status": "completed",
                              "result_counts": {"failed": 8, "passed": 0, "errored": 0}}]},
        "audio": {"runs": [{"run_id": "r2", "status": "failed", "result_counts": {}}]},
        "brand": {"runs": [{"run_id": "r3", "status": "completed", "result_counts": {"errored": 1}}]},
    })
    assert probs == ["audio:r2 failed", "brand:r3 errored=1"]


def test_published_evidence_is_finite_sanitized_and_keeps_human_blocker():
    raw = (PUBLIC / "foundry-evals-v1.json").read_text(encoding="utf-8")
    ev = json.loads(raw, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
    for leaked in ("services.ai.azure.com", "cognitiveservices.azure.com", "tenant_id", "subscription_id"):
        assert leaked not in raw
    assert ev["operational_status"] == "ok"
    assert ev["media"]["negative-control"]["checks"]["product_identity"]["label"] == "mismatch"
    assert ev["media"]["hero-home-kling"]["checks"]["brand_marks"]["needs_human_review"] is True
    hr = json.loads((PUBLIC / "human-review.json").read_text(encoding="utf-8"))
    hero = [f for f in hr["findings"] if f.get("clip") == "lto-hero-kling"]
    assert any(f.get("severity") == "publication blocker" for f in hero)
