"""Live client for fal video models on Microsoft Foundry (async submit / poll / result / download).

Transport and auth follow the Learn article "Fal models on Microsoft Foundry (preview)":
POST {resource}/providers/falai/v1/{model_base}{route} with {"model": <deployment>, ...}
GET  {model_base}/requests/{id}/status   -> {"status": "IN_QUEUE|IN_PROGRESS|COMPLETED|..."}
GET  {model_base}/requests/{id}          -> {"video": {"url": ...}}
Auth: Microsoft Entra ID bearer token for https://cognitiveservices.azure.com/.default.
"""

from __future__ import annotations

import base64
import math
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from .config import Settings, normalize_endpoint
from .credentials import SCOPE, create_credential
from .models import ModelSpec

TERMINAL_FAILURES = {"FAILED", "CANCELED", "CANCELLED", "ERROR"}


class FoundryError(RuntimeError):
    pass


def image_to_data_uri(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


class TokenProvider:
    def __init__(self, api_key: str | None = None, settings: Settings | None = None):
        self.api_key = api_key
        self.settings = settings
        self._cred = None
        self._token = None

    def headers(self) -> dict[str, str]:
        if self.api_key:
            # Entra ID is the documented path; key auth uses the general Foundry 'api-key' header.
            return {"api-key": self.api_key}
        if self._token is None or self._token.expires_on - time.time() < 120:
            try:
                if self._cred is None:
                    self._cred = create_credential(self.settings)
            except ImportError as e:  # pragma: no cover - exercised only without the live extra
                raise FoundryError("Live mode needs azure-identity: pip install -e .[live]") from e
            self._token = self._cred.get_token(SCOPE)
        return {"Authorization": f"Bearer {self._token.token}"}


class FoundryVideoClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None, tokens: TokenProvider | None = None):
        self.s = settings
        self.http = http or httpx.Client(timeout=120)
        self.tokens = tokens or TokenProvider(settings.api_key, settings)
        resource = urlparse(normalize_endpoint(settings.endpoint or ""))
        self._foundry_origin = (resource.scheme, resource.hostname, resource.port or 443)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        # Only an explicit rate-limit rejection is safe to retry for a paid POST.
        # Network errors and 5xx responses may follow an accepted submit: never resubmit those.
        for attempt in range(4):
            response = self.http.request(method, url, **kwargs)
            if response.status_code != 429 or attempt == 3:
                return response
            try:
                delay = float(response.headers.get("retry-after", "60"))
                if not math.isfinite(delay) or delay < 0:
                    delay = 60
            except ValueError:
                delay = 60
            time.sleep(min(delay, 120))
        raise AssertionError("unreachable")

    def submit(self, m: ModelSpec, mode: str, payload: dict[str, Any]) -> str:
        url = f"{self.s.model_base_url(m)}{m.routes[mode]}"
        r = self._request("POST", url, json=payload,
                          headers={**self.tokens.headers(), "Content-Type": "application/json"})
        if r.status_code >= 400:
            raise FoundryError(f"Submit failed {r.status_code}: {r.text[:500]}")
        rid = r.json().get("request_id")
        if not rid:
            raise FoundryError(f"No request_id in response: {r.text[:300]}")
        return rid

    def status(self, m: ModelSpec, request_id: str) -> dict[str, Any]:
        r = self._job_get(f"{self.s.model_base_url(m)}/requests/{request_id}/status")
        if r.status_code >= 400:
            raise FoundryError(f"Status failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def result(self, m: ModelSpec, request_id: str) -> dict[str, Any]:
        r = self._job_get(f"{self.s.model_base_url(m)}/requests/{request_id}")
        if r.status_code >= 400:
            raise FoundryError(f"Result failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def _job_get(self, url: str) -> httpx.Response:
        deadline = time.monotonic() + 180
        delay = 3
        while True:
            response = self._request("GET", url, headers=self.tokens.headers(), params={"_poll": uuid.uuid4().hex})
            if response.status_code != 401:
                return response
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FoundryError("Job polling authorization still denied after 180s; verify Foundry User RBAC "
                                   "and recover the original request_id. Do not resubmit a potentially paid job.")
            time.sleep(min(delay, remaining))
            delay = min(delay + 2, 10)

    def wait(self, m: ModelSpec, request_id: str, on_status: Callable[[str], None] | None = None) -> dict[str, Any]:
        deadline = time.time() + self.s.timeout_s
        time.sleep(min(3, self.s.poll_interval_s))
        while time.time() < deadline:
            st = str(self.status(m, request_id).get("status", "")).upper()
            if on_status:
                on_status(st)
            if st == "COMPLETED":
                return self.result(m, request_id)
            if st in TERMINAL_FAILURES:
                raise FoundryError(f"Request {request_id} ended with status {st}")
            time.sleep(self.s.poll_interval_s)
        raise FoundryError(f"Timed out after {self.s.timeout_s}s waiting for {request_id}")

    def download(self, url: str, dest: Path, max_redirects: int = 5) -> Path:
        """Download a result. Redirects are followed manually and credentials are attached only to
        HTTPS requests on the Foundry resource origin (including port), so a bearer token or api-key is never forwarded
        cross-origin (e.g. to a signed storage URL)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        current = url
        for _ in range(max_redirects + 1):
            parsed = urlparse(current)
            same_origin = (parsed.scheme == "https" and
                           (parsed.scheme, parsed.hostname, parsed.port or 443) == self._foundry_origin)
            headers = self.tokens.headers() if same_origin else {}
            with self.http.stream("GET", current, headers=headers, follow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        raise FoundryError("Redirect without Location header")
                    current = str(httpx.URL(current).join(loc))
                    continue
                if r.status_code >= 400:
                    raise FoundryError(f"Download failed {r.status_code}")
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
                return dest
        raise FoundryError(f"Too many redirects downloading {url}")
