import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_release", ROOT / "scripts" / "render_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_reservation_counts_completed_and_uncertain_calls():
    journal = {"calls": {"old": {"reserved_usd": 3.9, "status": "completed"}}}
    release.reserve(journal, "qa", 0.1)
    with pytest.raises(ValueError, match="exhausted"):
        release.reserve(journal, "extra", 0.001)
    assert "extra" not in journal["calls"]
    with pytest.raises(ValueError, match="already reserved"):
        release.reserve(journal, "qa", 0.01)


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -0.1, 0, True])
def test_release_refuses_unpriced_or_invalid_reservations(amount):
    journal = {"calls": {}}
    with pytest.raises(ValueError):
        release.reserve(journal, "unpriced", amount)
    assert not journal["calls"]


def test_release_paid_post_never_retries_rate_limit():
    class Http:
        calls = 0

        def request(self, method, url, **kwargs):
            self.calls += 1
            return type("Response", (), {"status_code": 429})()

    client = object.__new__(release.SingleSubmit)
    client.http = Http()
    assert client._request("POST", "https://example.invalid").status_code == 429
    assert client.http.calls == 1
