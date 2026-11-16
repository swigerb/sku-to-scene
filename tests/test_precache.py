import json
from dataclasses import replace

from scripts import precache
from sku_to_scene.router import Brief, route


def _setup(settings, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "example.mp4").write_bytes(b"previous simulated clip")
    (cache / "manifest.json").write_text(json.dumps({"clips": [
        {"id": "example", "file": "example.mp4", "provenance": "simulated"}]}))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"authentic source")
    brief = Brief(prompt="A cup of coffee", sku_id="NWC-LTO-PCB-16", stage="draft")
    decision = route(brief)
    monkeypatch.setattr(precache, "get_settings", lambda: replace(settings, mode="live", cache_dir=cache))
    monkeypatch.setattr(precache, "plan", lambda: [{"id": "example", "brief": brief, "decision": decision}])
    monkeypatch.setattr(precache.sys, "argv", ["precache.py", "--yes"])
    monkeypatch.setattr(precache, "generate_from_decision", lambda *_a, **_k: {
        "job_id": "real-job", "output": str(source), "provenance": "foundry", "elapsed_s": 12,
        "request_id": "real-request", "payload": {"model": "demo-deployment"}, "estimate": {}})
    return cache


def test_transcode_failure_does_not_relabel_or_replace_previous_cache(settings, tmp_path, monkeypatch):
    cache = _setup(settings, tmp_path, monkeypatch)

    def broken(source, dest):
        dest.write_bytes(b"partial encoding")
        raise RuntimeError("encoding failed")

    monkeypatch.setattr(precache, "transcode_preview", broken)
    assert precache.main() == 1
    assert (cache / "example.mp4").read_bytes() == b"previous simulated clip"
    assert json.loads((cache / "manifest.json").read_text())["clips"][0]["provenance"] == "simulated"
    assert not list(cache.glob("*.pending.mp4"))


def test_success_stores_real_screening_without_private_paths(settings, tmp_path, monkeypatch):
    cache = _setup(settings, tmp_path, monkeypatch)
    monkeypatch.setattr(precache, "transcode_preview", lambda source, dest: dest.write_bytes(source.read_bytes()))
    monkeypatch.setattr(precache, "probe", lambda _: {"has_audio": False})
    monkeypatch.setattr(precache.qa, "evaluate", lambda **_: {
        "evaluator": "azure-openai-vision", "measured": True, "scores": {"product_fidelity": 0.1},
        "verdict": "fail", "findings": ["wrong product"], "publish_approved": False,
        "video": "private path", "reference_image": "private reference"})
    assert precache.main() == 0
    entry = json.loads((cache / "manifest.json").read_text())["clips"][0]
    assert entry["provenance"] == "foundry" and entry["request_id"] == "real-request"
    assert entry["qa"]["verdict"] == "fail" and entry["qa"]["measured"]
    assert "video" not in entry["qa"] and "reference_image" not in entry["qa"]
    assert (cache / "example.mp4").read_bytes() == b"authentic source"
