"""Live client for fal video models on Microsoft Foundry (async submit / poll / result / download).

Transport and auth follow the Learn article "Fal models on Microsoft Foundry (preview)":
POST {resource}/providers/falai/v1/{model_base}{route} with {"model": <deployment>, ...}
GET  {model_base}/requests/{id}/status   -> {"status": "IN_QUEUE|IN_PROGRESS|COMPLETED|..."}
GET  {model_base}/requests/{id}          -> {"video": {"url": ...}}
Auth: Microsoft Entra ID bearer token for https://cognitiveservices.azure.com/.default.
"""

from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from .config import Settings, normalize_endpoint
from .models import ModelSpec

SCOPE = "https://cognitiveservices.azure.com/.default"
TERMINAL_FAILURES = {"FAILED", "CANCELED", "CANCELLED", "ERROR"}


class FoundryError(RuntimeError):
    pass


def image_to_data_uri(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


class TokenProvider:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._cred = None
        self._token = None

    def headers(self) -> dict[str, str]:
        if self.api_key:
            # Entra ID is the documented path; key auth uses the general Foundry 'api-key' header.
            return {"api-key": self.api_key}
        if self._token is None or self._token.expires_on - time.time() < 120:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as e:  # pragma: no cover - exercised only without the live extra
                raise FoundryError("Live mode needs azure-identity: pip install -e .[live]") from e
            if self._cred is None:
                self._cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
            self._token = self._cred.get_token(SCOPE)
        return {"Authorization": f"Bearer {self._token.token}"}


class FoundryVideoClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None, tokens: TokenProvider | None = None):
        self.s = settings
        self.http = http or httpx.Client(timeout=120)
        self.tokens = tokens or TokenProvider(settings.api_key)
        self._foundry_host = urlparse(normalize_endpoint(settings.endpoint or "")).hostname

    def submit(self, m: ModelSpec, mode: str, payload: dict[str, Any]) -> str:
        url = f"{self.s.model_base_url(m)}{m.routes[mode]}"
        r = self.http.post(url, json=payload, headers={**self.tokens.headers(), "Content-Type": "application/json"})
        if r.status_code >= 400:
            raise FoundryError(f"Submit failed {r.status_code}: {r.text[:500]}")
        rid = r.json().get("request_id")
        if not rid:
            raise FoundryError(f"No request_id in response: {r.text[:300]}")
        return rid

    def status(self, m: ModelSpec, request_id: str) -> dict[str, Any]:
        r = self.http.get(f"{self.s.model_base_url(m)}/requests/{request_id}/status", headers=self.tokens.headers())
        if r.status_code >= 400:
            raise FoundryError(f"Status failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def result(self, m: ModelSpec, request_id: str) -> dict[str, Any]:
        r = self.http.get(f"{self.s.model_base_url(m)}/requests/{request_id}", headers=self.tokens.headers())
        if r.status_code >= 400:
            raise FoundryError(f"Result failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def wait(self, m: ModelSpec, request_id: str, on_status: Callable[[str], None] | None = None) -> dict[str, Any]:
        deadline = time.time() + self.s.timeout_s
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
        HTTPS requests on the Foundry resource host, so a bearer token or api-key is never forwarded
        cross-origin (e.g. to a signed storage URL)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        current = url
        for _ in range(max_redirects + 1):
            parsed = urlparse(current)
            same_origin = parsed.scheme == "https" and parsed.hostname == self._foundry_host
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
