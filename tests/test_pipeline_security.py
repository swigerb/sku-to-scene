import httpx
import pytest

from conftest import write_png
from sku_to_scene import pipeline
from sku_to_scene.config import get_settings
from sku_to_scene.foundry import FoundryVideoClient, TokenProvider
from sku_to_scene.models import get_model
from sku_to_scene.pipeline import CacheMismatch, ProcessingUnavailable, generate_video


@pytest.fixture
def live(settings, monkeypatch):
    monkeypatch.setenv("SKU2SCENE_MODE", "live")
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://res.services.ai.azure.com")
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key")
    return get_settings()


class NoSubmit:
    def __init__(self, *_a, **_k):
        pass

    def submit(self, *_a, **_k):
        raise AssertionError("billable submit must not happen")


def test_live_precrop_without_ffmpeg_fails_before_submit(live, monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "have_ffmpeg", lambda: False)
    monkeypatch.setattr(pipeline, "FoundryVideoClient", NoSubmit)
    img = write_png(tmp_path / "tall.png", 20, 30)  # 2:3, target 16:9
    with pytest.raises(ProcessingUnavailable):
        generate_video("kling-v3-pro", "p", str(img), 5, aspect_ratio="16:9", settings=live)


def test_live_postcrop_without_ffmpeg_fails_before_submit(live, monkeypatch):
    monkeypatch.setattr(pipeline, "have_ffmpeg", lambda: False)
    monkeypatch.setattr(pipeline, "FoundryVideoClient", NoSubmit)
    with pytest.raises(ProcessingUnavailable):
        generate_video("ltx-2.5-fast", "p", None, 6, aspect_ratio="1:1", settings=live)


def test_live_source_already_matching_aspect_needs_no_ffmpeg(live, monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "have_ffmpeg", lambda: False)
    calls = {}

    class Fake:
        def __init__(self, *_a, **_k):
            pass

        def submit(self, m, mode, payload):
            calls["payload"] = payload
            return "rid-1"

        def wait(self, *_a, **_k):
            return {"video": {"url": "https://res.services.ai.azure.com/out.mp4"}}

        def download(self, url, dest):
            dest.write_bytes(b"mp4")
            return dest

    monkeypatch.setattr(pipeline, "FoundryVideoClient", Fake)
    img = write_png(tmp_path / "wide.png", 32, 18)
    job = generate_video("kling-v3-pro", "p", str(img), 5, aspect_ratio="16:9", settings=live)
    assert job["provenance"] == "foundry" and job["status"] == "completed"
    assert calls["payload"]["start_image_url"].startswith("data:image/png")


def test_cache_requires_sku_association(settings, monkeypatch):
    monkeypatch.setattr(pipeline, "have_ffmpeg", lambda: False)
    # Same model/mode/aspect as the LTO hero, but another SKU: must not be served.
    assert pipeline._find_cached(settings, None, "kling-v3-pro", "image-to-video", "9:16", "CTP-DRL-20V-BL") is None
    assert pipeline._find_cached(settings, None, "kling-v3-pro", "image-to-video", "9:16", None) is None
    hit = pipeline._find_cached(settings, None, "kling-v3-pro", "image-to-video", "9:16", "NWC-LTO-PCB-16")
    assert hit["id"] == "lto-hero-kling"


@pytest.mark.parametrize("key, sku", [("lto-hero-kling", "CTP-DRL-20V-BL"), ("lto-hero-kling", None),
                                      ("does-not-exist", "NWC-LTO-PCB-16")])
def test_cache_key_metadata_mismatch_raises(settings, key, sku):
    with pytest.raises(CacheMismatch):
        pipeline._find_cached(settings, key, "kling-v3-pro", "image-to-video", "9:16", sku)


def _client(handler, live):
    return FoundryVideoClient(live, http=httpx.Client(transport=httpx.MockTransport(handler)),
                              tokens=TokenProvider("secret-key"))


def test_download_never_forwards_credentials_cross_origin(live, tmp_path):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.host, req.headers.get("api-key"), req.headers.get("authorization")))
        if req.url.host == "res.services.ai.azure.com":
            return httpx.Response(302, headers={"location": "https://blob.example.net/v.mp4?sig=abc"})
        return httpx.Response(200, content=b"video")

    out = _client(handler, live).download("https://res.services.ai.azure.com/files/v.mp4", tmp_path / "v.mp4")
    assert out.read_bytes() == b"video"
    assert seen[0] == ("res.services.ai.azure.com", "secret-key", None)
    assert seen[1] == ("blob.example.net", None, None)


def test_download_no_credentials_on_http_or_foreign_initial_url(live, tmp_path):
    seen = []

    def handler(req):
        seen.append(req.headers.get("api-key"))
        return httpx.Response(200, content=b"v")

    c = _client(handler, live)
    c.download("https://fal.media/files/v.mp4", tmp_path / "a.mp4")
    c.download("http://res.services.ai.azure.com/v.mp4", tmp_path / "b.mp4")
    c.download("https://res.services.ai.azure.com:8443/v.mp4", tmp_path / "c.mp4")
    assert seen == [None, None, None]


def test_submit_retries_explicit_429_with_retry_after(live, monkeypatch):
    seen, sleeps = [], []

    def handler(req):
        seen.append(req)
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "30"})
        return httpx.Response(200, json={"request_id": "accepted-once"})

    monkeypatch.setattr("sku_to_scene.foundry.time.sleep", sleeps.append)
    assert _client(handler, live).submit(get_model("minimax-h3-max-turbo"), "text-to-video", {}) == "accepted-once"
    assert len(seen) == 2 and sleeps == [30]


@pytest.mark.parametrize("status", [500, 502, 503])
def test_submit_never_retries_uncertain_server_errors(live, status):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(status, text="uncertain acceptance")

    with pytest.raises(RuntimeError, match="Submit failed"):
        _client(handler, live).submit(get_model("minimax-h3-max-turbo"), "text-to-video", {})
    assert len(seen) == 1


def test_submit_rate_limit_retry_is_bounded(live, monkeypatch):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(429, headers={"Retry-After": "0"})

    monkeypatch.setattr("sku_to_scene.foundry.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="429"):
        _client(handler, live).submit(get_model("minimax-h3-max-turbo"), "text-to-video", {})
    assert len(seen) == 4


def test_status_and_result_bypass_stale_gateway_cache(live):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"status": "COMPLETED"})

    client = _client(handler, live)
    model = get_model("minimax-h3-max-turbo")
    client.status(model, "existing-request")
    client.status(model, "existing-request")
    client.result(model, "existing-request")
    assert len({r.url.params["_poll"] for r in seen}) == 3
    assert all(r.method == "GET" and "existing-request" in r.url.path for r in seen)


def test_post_submit_transient_401_retries_get_only(live, monkeypatch):
    seen, sleeps = [], []

    def handler(req):
        seen.append(req)
        if len(seen) <= 2:
            return httpx.Response(401, json={"error": {"code": "PermissionDenied"}})
        return httpx.Response(200, json={"status": "COMPLETED"})

    monkeypatch.setattr("sku_to_scene.foundry.time.sleep", sleeps.append)
    assert _client(handler, live).status(get_model("minimax-h3-max-turbo"), "paid-request")["status"] == "COMPLETED"
    assert sleeps == [3, 5]
    assert all(r.method == "GET" for r in seen)
    assert len({r.url.params["_poll"] for r in seen}) == 3


def test_post_submit_auth_retry_expires_without_resubmit(live, monkeypatch):
    clock = iter((0, 181))
    monkeypatch.setattr("sku_to_scene.foundry.time.monotonic", lambda: next(clock))
    client = _client(lambda _: httpx.Response(401), live)
    with pytest.raises(RuntimeError, match="Do not resubmit"):
        client.result(get_model("minimax-h3-max-turbo"), "paid-request")
