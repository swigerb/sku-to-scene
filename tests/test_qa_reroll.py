import json
import math
import threading
from pathlib import Path

import pytest

from conftest import write_png
from sku_to_scene import qa, readiness, reroll as rr
from sku_to_scene.pipeline import get_job, save_job

TH = {"logo_integrity": 0.8, "label_legibility": 0.7, "product_fidelity": 0.8, "prompt_adherence": 0.7}
GOOD = {"logo_integrity": 0.9, "label_legibility": 0.9, "product_fidelity": 0.9, "prompt_adherence": 0.9}
EVIDENCE = {c: {"expected": "The specified product", "observed": "Visible product matches",
                "frame_indices": [1]} for c in qa.CHECKS}
ITEM = "The specified product"
ITEMS = [{"item": ITEM, "present": True, "correct_identity": True, "fully_in_frame": True,
          "observed": "Visible product matches", "frame_indices": [1]}]


@pytest.mark.parametrize("scores", [
    {"logo_integrity": 1},                              # partial set used to pass
    GOOD | {"product_fidelity": math.nan},
    GOOD | {"prompt_adherence": 1.5},
    GOOD | {"label_legibility": -0.1},
    GOOD | {"logo_integrity": "0.9"},
    GOOD | {"logo_integrity": True},
    ["not", "a", "dict"],
])
def test_incomplete_or_malformed_scores_never_pass(scores):
    d = qa.decide(scores, TH, None)
    assert d["verdict"] == "manual_review" and d["score_problems"]


def test_complete_scores_pass_or_fail():
    assert qa.decide(GOOD, TH, None)["verdict"] == "pass"
    d = qa.decide(GOOD | {"product_fidelity": 0.5}, TH, None)
    assert d["verdict"] == "fail" and d["failed_checks"] == ["product_fidelity"]


def test_evaluator_error_is_error_not_approval():
    assert qa.decide(GOOD, TH, None, evaluator_error="boom")["verdict"] == "error"


def test_content_safety_failure_fails():
    cs = [{"frame": "f", "categories": [{"category": "Violence", "severity": 4}]}]
    assert "content_safety" in qa.decide(GOOD, TH, cs)["failed_checks"]


@pytest.fixture
def vision(settings, monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aoai.example.com")
    monkeypatch.setenv("AZURE_OPENAI_VISION_DEPLOYMENT", "vision")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    frame = write_png(tmp_path / "f1.png", 4, 4)
    monkeypatch.setattr(qa, "have_ffmpeg", lambda: True)
    monkeypatch.setattr(qa, "extract_frames", lambda *_a, **_k: [frame])
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    return video


def test_vision_input_includes_approved_reference_image(vision, monkeypatch):
    sent = {}

    def fake(frames, brand, prompt, sku, checks):
        sent["images"] = [str(f) for f in ([qa.catalog.image_path(sku)] + frames)]
        return {"scores": GOOD}

    # Exercise the real request builder too: capture the HTTP body.
    captured = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"scores": {"logo_integrity": 1}}'}}]}

    def post(url, headers, json, timeout):
        captured["content"] = json["messages"][0]["content"]
        return R()

    monkeypatch.setattr(qa.httpx, "post", post)
    res = qa.evaluate(video_path=str(vision), sku="NWC-LTO-PCB-16", prompt="pour")
    imgs = [c for c in captured["content"] if c["type"] == "image_url"]
    assert len(imgs) == 2  # approved reference + 1 generated frame
    assert "approved PIM reference" in captured["content"][0]["text"]
    # Partial evaluator output -> manual review, never approval.
    assert res["verdict"] == "manual_review" and res["publish_approved"] is False


def test_vision_failure_is_error(vision, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("503")

    monkeypatch.setattr(qa.httpx, "post", boom)
    res = qa.evaluate(video_path=str(vision), sku="NWC-LTO-PCB-16")
    assert res["verdict"] == "error" and res["publish_approved"] is False


def test_real_qa_uses_persisted_prompt_and_requires_human_signoff(vision, settings, monkeypatch):
    seen = []

    def scorer(frames, brand, prompt, sku, checks, **_):
        seen.append(prompt)
        return {"scores": GOOD, "findings": ["screening only"], "hallucinated_objects": [],
                "check_evidence": EVIDENCE, "required_items": ITEMS}

    monkeypatch.setattr(qa, "_vision_scores", scorer)
    save_job(settings, {"job_id": "real-qa", "output": str(vision), "prompt": "The original creative prompt",
                        "label": "Not the creative prompt"})
    result = qa.evaluate(job_id="real-qa", sku="NWC-LTO-PCB-16", settings=settings, required_items=[ITEM])
    assert seen == ["The original creative prompt"]
    assert result["verdict"] == "pass" and result["automated_checks_passed"]
    assert result["human_signoff_required"] and not result["publish_approved"]
    stored = get_job("real-qa", settings)["qa"]
    assert stored["scores"] == GOOD and stored["findings"] == ["screening only"]
    assert stored["check_evidence"] == EVIDENCE and stored["evaluator_version"] == "brand-qa-vision-v3"
    assert "video" not in stored and "reference_image" not in stored


def test_rehearsal_switch_blocks_cloud_evaluators(vision, monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_ENDPOINT", "https://safety.example.com")
    monkeypatch.setenv("SKU2SCENE_QA_EVALUATORS", "off")

    def no_network(*_a, **_k):
        raise AssertionError("cloud evaluator called while SKU2SCENE_QA_EVALUATORS=off")

    monkeypatch.setattr(qa.httpx, "post", no_network)
    result = qa.evaluate(video_path=str(vision), sku="NWC-LTO-PCB-16")
    assert result["verdict"] == "manual_review" and not result["measured"]
    assert result["content_safety"] is None and not result["publish_approved"]


def test_malformed_content_safety_is_error_not_approval(vision, monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_ENDPOINT", "https://safety.example.com")
    monkeypatch.setenv("CONTENT_SAFETY_KEY", "test")
    monkeypatch.setattr(qa, "_vision_scores", lambda *_: {
        "scores": GOOD, "check_evidence": EVIDENCE, "findings": [], "hallucinated_objects": []})
    monkeypatch.setattr(qa.httpx, "post", lambda *_a, **_k: type(
        "Response", (), {"raise_for_status": lambda _: None, "json": lambda _: {"categoriesAnalysis": []}})())
    result = qa.evaluate(video_path=str(vision), sku="NWC-LTO-PCB-16")
    assert result["verdict"] == "error" and not result["publish_approved"]


def test_text_qa_request_contains_full_requirements_and_group_comparison(vision, monkeypatch):
    captured = {}
    prompt = "Four groups, six product props and three packaging boxes, including a mug and cloth."

    def post(url, **kwargs):
        captured.update(kwargs["json"])
        body = json.dumps({"scores": GOOD, "check_evidence": EVIDENCE, "findings": [], "hallucinated_objects": [],
                           "required_items": ITEMS})
        return type("Response", (), {"raise_for_status": lambda _: None,
                    "json": lambda _: {"choices": [{"message": {"content": body}}]}})()

    monkeypatch.setattr(qa.httpx, "post", post)
    result = qa.evaluate(video_path=str(vision), sku="PWS-KIT-01", prompt=prompt, required_items=[ITEM])
    content = captured["messages"][0]["content"]
    text = content[0]["text"]
    for required in ("#44416F", "Plain indigo and white boxes without text",
                     "coffee kit, cleaning supplies, ergonomic chair, printer paper", prompt,
                     "Distinguish product groups", "specific mismatch", "frame_indices"):
        assert required in text
    assert len(content) == 2  # no invented PIM reference for a text-only SKU
    assert result["verdict"] == "pass" and not result["publish_approved"]


@pytest.mark.parametrize("evidence", [
    None, {c: EVIDENCE[c] for c in qa.CHECKS if c != "product_fidelity"},
    EVIDENCE | {"findings": ["The mug is cropped"], "hallucinated_objects": []},
    EVIDENCE | {"product_fidelity": {"expected": "", "observed": "match", "frame_indices": [1]}},
    EVIDENCE | {"product_fidelity": {"expected": "product", "observed": "match", "frame_indices": [2]}},
    EVIDENCE | {"product_fidelity": {"expected": "product", "observed": "match", "frame_indices": [True]}},
])
def test_untraceable_grounded_scores_cannot_approve(vision, monkeypatch, evidence):
    monkeypatch.setattr(qa, "_vision_scores", lambda *_, **kw: {
        "scores": GOOD, "check_evidence": evidence, "findings": [], "hallucinated_objects": [], "required_items": ITEMS})
    result = qa.evaluate(video_path=str(vision), sku="PWS-KIT-01", required_items=[ITEM])
    assert result["verdict"] == "error" and not result["publish_approved"]
    assert qa.evidence_summary(result)["evaluation_error"] is True


@pytest.mark.parametrize("findings", [None, "cropped mug", [None], [""]])
def test_grounded_findings_cannot_silently_disappear(vision, monkeypatch, findings):
    monkeypatch.setattr(qa, "_vision_scores", lambda *_, **kw: {
        "scores": GOOD, "check_evidence": EVIDENCE, "findings": findings, "hallucinated_objects": [],
        "required_items": ITEMS})
    result = qa.evaluate(video_path=str(vision), sku="PWS-KIT-01", required_items=[ITEM])
    assert result["verdict"] == "error" and not result["publish_approved"]


def test_recorded_diagnostic_rejects_misnested_findings_without_rescoring(vision, monkeypatch):
    evidence = json.loads((Path(__file__).resolve().parents[1] / "demo-cache" / "qa" /
                           "proseware-s5-v2.json").read_text())
    recorded = evidence["recorded_diagnostic_result"]
    monkeypatch.setattr(qa, "_vision_scores", lambda *_, **kw: recorded)
    result = qa.evaluate(video_path=str(vision), sku="PWS-KIT-01", required_items=[ITEM])
    assert result["verdict"] == "error"
    assert "exactly the four checks" in result["evaluator_error"]
    assert not result["automated_checks_passed"] and not result["publish_approved"]
    assert evidence["original_qa"]["verdict"] == "fail"


@pytest.mark.parametrize("defect", ["present", "correct_identity", "fully_in_frame"])
def test_required_item_defects_fail_even_when_judge_scores_are_high(vision, monkeypatch, defect):
    item = {**ITEMS[0], defect: False, "observed": "Wrong object, absent or cropped"}
    monkeypatch.setattr(qa, "_vision_scores", lambda *_, **kw: {
        "scores": GOOD, "check_evidence": EVIDENCE, "findings": [], "hallucinated_objects": [],
        "required_items": [item]})
    result = qa.evaluate(video_path=str(vision), sku="PWS-KIT-01", required_items=[ITEM])
    assert result["raw_scores"] == GOOD
    assert result["thresholds"] == TH
    assert result["scores"]["product_fidelity"] == 0.79
    assert result["verdict"] == "fail" and not result["publish_approved"]
    assert result["identity_guard"]["blocked_items"] == [ITEM]


@pytest.mark.parametrize("items", [[], ITEMS * 2, [{**ITEMS[0], "item": "Not requested"}],
                                     [{**ITEMS[0], "correct_identity": "false"}]])
def test_incomplete_or_malformed_item_inventory_is_not_approval(vision, monkeypatch, items):
    monkeypatch.setattr(qa, "_vision_scores", lambda *_, **kw: {
        "scores": GOOD, "check_evidence": EVIDENCE, "findings": [], "hallucinated_objects": [],
        "required_items": items})
    result = qa.evaluate(video_path=str(vision), sku="PWS-KIT-01", required_items=[ITEM])
    assert result["verdict"] == "error" and not result["publish_approved"]


def test_readiness_survives_missing_azure_namespace(settings, monkeypatch):
    def raise_mnf(name, *a, **k):
        raise ModuleNotFoundError("No module named 'azure'")

    monkeypatch.setattr(readiness.importlib.util, "find_spec", raise_mnf)
    r = readiness.readiness()
    ident = next(c for c in r["checks"] if c["check"] == "azure-identity")
    assert ident["ok"] is False


# ------------------------------------------------------------------ bounded re-roll
def _failed_job(s, job_id="kling-v3-pro-root0001"):
    job = {"job_id": job_id, "model": "kling-v3-pro", "mode": "image-to-video", "aspect_ratio": "9:16",
           "sku": "NWC-LTO-PCB-16", "prompt": "pour", "audio": True, "estimate": {"seconds": 8},
           "qa": {"verdict": "fail", "reroll": {"model": "ltx-2.5-pro", "mode": "image-to-video"}}}
    save_job(s, job)
    return job


@pytest.fixture
def fake_gen(settings, monkeypatch):
    calls = []

    def gen(model, prompt, image, duration, **kw):
        calls.append((model, duration))
        job = {"job_id": f"{model}-c{len(calls):07d}", "model": model, "mode": kw["mode"],
               "aspect_ratio": kw["aspect_ratio"], "sku": kw["sku"], "prompt": prompt, "audio": kw["audio"],
               "estimate": {"seconds": 8, "estimate_usd": 1.0}, "provenance": "simulated"}
        save_job(settings, job)
        return job

    monkeypatch.setattr(rr, "generate_video", gen)
    return calls


def test_reroll_requires_fail_verdict(settings, fake_gen):
    job = _failed_job(settings)
    job["qa"]["verdict"] = "manual_review"
    save_job(settings, job)
    with pytest.raises(rr.RerollRefused):
        rr.reroll(job["job_id"], evaluate=False, settings=settings)
    assert fake_gen == []


def test_same_parent_cannot_be_rerolled_twice(settings, fake_gen):
    job = _failed_job(settings)
    child = rr.reroll(job["job_id"], evaluate=False, settings=settings)
    assert child["reroll_attempt"] == 1 and fake_gen == [("ltx-2.5-pro", 8)]
    with pytest.raises(rr.RerollRefused, match="already re-rolled"):
        rr.reroll(job["job_id"], evaluate=False, settings=settings)
    assert get_job(job["job_id"], settings)["rerolled_by"] == child["job_id"]


def test_chain_cap_enforced_at_root(settings, fake_gen):
    job = _failed_job(settings)
    c1 = rr.reroll(job["job_id"], max_rerolls=2, evaluate=False, settings=settings)
    c1 = get_job(c1["job_id"], settings) | {"qa": {"verdict": "fail",
                                                    "reroll": {"model": "kling-v3-pro", "mode": "image-to-video"}}}
    save_job(settings, c1)
    c2 = rr.reroll(c1["job_id"], max_rerolls=2, evaluate=False, settings=settings)
    assert c2["reroll_root"] == job["job_id"] and c2["reroll_attempt"] == 2
    c2 = get_job(c2["job_id"], settings) | {"qa": {"verdict": "fail",
                                                    "reroll": {"model": "ltx-2.5-pro", "mode": "image-to-video"}}}
    save_job(settings, c2)
    with pytest.raises(rr.RerollRefused, match="exhausted"):
        rr.reroll(c2["job_id"], max_rerolls=99, evaluate=False, settings=settings)  # clamped to MAX_REROLLS
    assert len(fake_gen) == 2


def test_failed_submit_still_consumes_reservation(settings, monkeypatch):
    job = _failed_job(settings)

    def boom(*_a, **_k):
        raise RuntimeError("timeout after submit")

    monkeypatch.setattr(rr, "generate_video", boom)
    with pytest.raises(RuntimeError):
        rr.reroll(job["job_id"], evaluate=False, settings=settings)
    st = rr.chain_state(job["job_id"], settings)
    assert [r["status"] for r in st["reservations"]] == ["failed"]
    with pytest.raises(rr.RerollRefused):
        rr.reroll(job["job_id"], evaluate=False, settings=settings)


def test_concurrent_rerolls_reserve_once(settings, fake_gen):
    job = _failed_job(settings)
    results = []

    def go():
        try:
            results.append(rr.reroll(job["job_id"], evaluate=False, settings=settings)["job_id"])
        except rr.RerollRefused:
            results.append("refused")

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("refused") == 5 and len(fake_gen) == 1
