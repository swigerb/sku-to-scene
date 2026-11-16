import math
import threading

import pytest

from conftest import write_png
from sku_to_scene import qa, readiness, reroll as rr
from sku_to_scene.pipeline import get_job, save_job

TH = {"logo_integrity": 0.8, "label_legibility": 0.7, "product_fidelity": 0.8, "prompt_adherence": 0.7}
GOOD = {"logo_integrity": 0.9, "label_legibility": 0.9, "product_fidelity": 0.9, "prompt_adherence": 0.9}


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
