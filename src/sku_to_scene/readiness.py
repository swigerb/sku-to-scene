"""Live-mode readiness report. Read-only: never provisions, registers features, or accepts terms."""

from __future__ import annotations

import importlib.util
import os
import uuid
from typing import Any

import httpx

from .config import get_settings, normalize_endpoint
from .foundry import TokenProvider
from .media import have_ffmpeg
from .models import REGISTRY

BLOCKERS_DOC = "docs/foundry-setup.md"


def probe_authorization(settings, headers: dict[str, str], http=None) -> tuple[bool, str]:
    """A nonexistent request checks data-plane access without generating billable media."""
    request_id = str(uuid.uuid4())
    url = f"{settings.model_base_url(REGISTRY['minimax-h3-max-turbo'])}/requests/{request_id}/status"
    response = (http or httpx).get(url, headers=headers, timeout=30)
    if response.status_code in (200, 404, 422):
        return True, f"authorized: nonexistent-request status probe returned HTTP {response.status_code}"
    if response.status_code in (401, 403):
        return False, ("authenticated but not authorized: assign Foundry User on the Foundry account and wait "
                       f"for RBAC propagation (HTTP {response.status_code}); no video submitted")
    return False, f"authorization unverified: nonexistent-request status probe returned HTTP {response.status_code}"


def optional_module_available(name: str) -> bool:
    """find_spec on a dotted name imports the parent and raises if the namespace (e.g. `azure`) is absent."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def readiness(check_auth: bool = False) -> dict[str, Any]:
    s = get_settings()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, required_for_live: bool = True) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail, "required_for_live": required_for_live})

    add("mode", True, f"SKU2SCENE_MODE={s.mode}", required_for_live=False)
    add("FOUNDRY_ENDPOINT", bool(s.endpoint),
        f"resource root {normalize_endpoint(s.endpoint)}" if s.endpoint else "not set")
    add("route prefix", True, s.route_prefix, required_for_live=False)
    for m in REGISTRY.values():
        explicit = m.deployment_env in os.environ
        add(f"deployment {m.key}", True,
            f"{m.deployment_env}={s.deployment_for(m)}" + ("" if explicit else " (default name)") +
            "; deployment existence not checked")
    has_identity = optional_module_available("azure.identity")
    add("azure-identity", has_identity or bool(s.api_key),
        "installed" if has_identity else ("api key mode" if s.api_key else "pip install -e .[live]"))
    add("ffmpeg", have_ffmpeg(), "needed for source pre-crop, PDP post-crop and QA frames")
    if check_auth and (has_identity or s.api_key):
        try:
            headers = TokenProvider(s.api_key, s).headers()
            add("authentication", True, "credential acquired; this alone does not establish data-plane access")
            if s.endpoint:
                ok, detail = probe_authorization(s, headers)
                add("authorization", ok, detail)
        except Exception as e:  # noqa: BLE001
            add("authentication / authorization", False, f"{type(e).__name__}; check local credential configuration")
    live_ready = all(c["ok"] for c in checks if c["required_for_live"])
    return {
        "mode": s.mode,
        "live_ready": live_ready,
        "checks": checks,
        "manual_prerequisites": [
            "Administrator reviews fal preview terms: fal services run outside Microsoft facilities, data egresses to "
            "fal, and Microsoft Product Terms / DPA / certifications do not apply to fal processing.",
            "Subscription preview feature Microsoft.CognitiveServices/Fal.EnableDeploy registered (Owner/Contributor).",
            "Foundry resource in a designated demo subscription; five deployments created (Foundry Owner).",
            "Caller has Cognitive Services User or Foundry User on the resource.",
            "Quota tier allows the RPM you need (free tier is 0 RPM).",
        ],
        "see": BLOCKERS_DOC,
        "note": "Feature registration, terms acceptance and deployments require administrator verification. "
                "With check_auth enabled, a free nonexistent-request probe separately checks data-plane authorization.",
    }
