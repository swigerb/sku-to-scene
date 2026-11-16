"""Live-mode readiness report. Read-only: never provisions, registers features, or accepts terms."""

from __future__ import annotations

import importlib.util
import os
from typing import Any

from .config import get_settings, normalize_endpoint
from .media import have_ffmpeg
from .models import REGISTRY

BLOCKERS_DOC = "docs/foundry-setup.md"


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
        add(f"deployment {m.key}", explicit,
            f"{m.deployment_env}={s.deployment_for(m)}" + ("" if explicit else " (default name; set explicitly)"))
    has_identity = optional_module_available("azure.identity")
    add("azure-identity", has_identity or bool(s.api_key),
        "installed" if has_identity else ("api key mode" if s.api_key else "pip install -e .[live]"))
    add("ffmpeg", have_ffmpeg(), "needed for source pre-crop, PDP post-crop and QA frames")
    if check_auth and has_identity and not s.api_key:
        try:
            from azure.identity import DefaultAzureCredential

            DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
            add("entra token", True, "acquired token for https://cognitiveservices.azure.com/.default")
        except Exception as e:  # noqa: BLE001
            add("entra token", False, f"{type(e).__name__}: {str(e)[:160]}")
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
        "note": "This report cannot verify feature registration, terms acceptance or deployments; it checks local config only.",
    }
