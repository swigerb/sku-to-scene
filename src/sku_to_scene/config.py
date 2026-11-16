"""Runtime configuration from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .models import ModelSpec

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (no dependency). Existing environment variables win."""
    p = path or (REPO_ROOT / ".env")
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def normalize_endpoint(endpoint: str) -> str:
    """Accept a resource or project endpoint and return the resource root."""
    e = endpoint.strip().rstrip("/")
    e = re.sub(r"/api/projects/[^/]+$", "", e)
    e = re.sub(r"/providers/falai(/v\d+)?$", "", e)
    return e


@dataclass
class Settings:
    mode: str
    endpoint: str | None
    route_prefix: str
    api_key: str | None
    data_dir: Path
    cache_dir: Path
    mock_latency_scale: float
    poll_interval_s: float
    timeout_s: float
    tenant_id: str | None = None
    subscription_id: str | None = None

    @property
    def live(self) -> bool:
        return self.mode == "live"

    def deployment_for(self, m: ModelSpec) -> str:
        return os.environ.get(m.deployment_env, m.default_deployment)

    def model_base_url(self, m: ModelSpec) -> str:
        if not self.endpoint:
            raise RuntimeError("FOUNDRY_ENDPOINT is not set (required for SKU2SCENE_MODE=live)")
        return f"{normalize_endpoint(self.endpoint)}/{self.route_prefix.strip('/')}/{m.base_path}"


def get_settings() -> Settings:
    load_dotenv()
    data_dir = Path(os.environ.get("SKU2SCENE_DATA_DIR", REPO_ROOT / ".sku2scene"))
    return Settings(
        mode=os.environ.get("SKU2SCENE_MODE", "mock").strip().lower(),
        endpoint=os.environ.get("FOUNDRY_ENDPOINT") or None,
        route_prefix=os.environ.get("FOUNDRY_FAL_ROUTE_PREFIX", "providers/falai/v1"),
        api_key=os.environ.get("FOUNDRY_API_KEY") or None,
        data_dir=data_dir,
        cache_dir=Path(os.environ.get("SKU2SCENE_CACHE_DIR", REPO_ROOT / "demo-cache")),
        mock_latency_scale=float(os.environ.get("SKU2SCENE_MOCK_LATENCY_SCALE", "0.1")),
        poll_interval_s=float(os.environ.get("FOUNDRY_POLL_INTERVAL", "5")),
        timeout_s=float(os.environ.get("FOUNDRY_TIMEOUT", "600")),
        tenant_id=os.environ.get("FOUNDRY_TENANT_ID") or os.environ.get("AZURE_TENANT_ID") or None,
        subscription_id=os.environ.get("FOUNDRY_SUBSCRIPTION_ID") or None,
    )
