from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest

from sku_to_scene import credentials, qa, readiness
from sku_to_scene.config import get_settings
from sku_to_scene.foundry import TokenProvider


def test_tenant_and_subscription_pin_cli_without_default_fallback(settings, monkeypatch):
    import azure.identity

    cli, default = Mock(), Mock()
    monkeypatch.setattr(azure.identity, "AzureCliCredential", cli)
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", default)
    s = replace(settings, tenant_id="demo-tenant", subscription_id="demo-subscription")
    assert credentials.create_credential(s) is cli.return_value
    cli.assert_called_once_with(subscription="demo-subscription")
    default.assert_not_called()


def test_tenant_only_pins_cli(settings, monkeypatch):
    import azure.identity

    cli = Mock()
    monkeypatch.setattr(azure.identity, "AzureCliCredential", cli)
    credentials.create_credential(replace(settings, tenant_id="demo-tenant", subscription_id=None))
    cli.assert_called_once_with(tenant_id="demo-tenant")


def test_unpinned_preserves_default_credential(settings, monkeypatch):
    import azure.identity

    default = Mock()
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", default)
    credentials.create_credential(replace(settings, tenant_id=None, subscription_id=None))
    default.assert_called_once_with(exclude_interactive_browser_credential=False)


def test_settings_tenant_precedence_and_fallback(settings, monkeypatch):
    monkeypatch.setenv("AZURE_TENANT_ID", "azure-tenant")
    monkeypatch.setenv("FOUNDRY_TENANT_ID", "")
    assert get_settings().tenant_id == "azure-tenant"
    monkeypatch.setenv("FOUNDRY_TENANT_ID", "foundry-tenant")
    assert get_settings().tenant_id == "foundry-tenant"


def test_token_provider_and_qa_use_shared_factory(settings, monkeypatch):
    cred = Mock()
    cred.get_token.return_value = SimpleNamespace(token="test-token", expires_on=9999999999)
    factory = Mock(return_value=cred)
    monkeypatch.setattr("sku_to_scene.foundry.create_credential", factory)
    assert TokenProvider(settings=settings).headers() == {"Authorization": "Bearer test-token"}
    factory.assert_called_once_with(settings)
    monkeypatch.setattr(qa, "create_credential", factory)
    assert qa._headers("AZURE_OPENAI_API_KEY") == {"Authorization": "Bearer test-token"}


@pytest.mark.parametrize("status, authorized", [(200, True), (404, True), (422, True),
                                               (401, False), (403, False), (429, False), (500, False)])
def test_authorization_probe_never_submits(settings, status, authorized):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    s = replace(settings, endpoint="https://demo.services.ai.azure.com")
    ok, detail = readiness.probe_authorization(s, {"Authorization": "Bearer test"}, client)
    assert ok is authorized
    assert len(seen) == 1 and seen[0].method == "GET"
    assert UUID(seen[0].url.path.split("/")[-2]).version == 4
    if status == 401:
        assert "Foundry User" in detail and "propagation" in detail


def test_authorization_probe_uses_fresh_url_to_avoid_cached_denial(settings):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    s = replace(settings, endpoint="https://demo.services.ai.azure.com")
    readiness.probe_authorization(s, {}, client)
    readiness.probe_authorization(s, {}, client)
    assert seen[0] != seen[1]


def test_readiness_separates_authentication_from_authorization(settings, monkeypatch):
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://demo.services.ai.azure.com")
    monkeypatch.setattr(readiness, "optional_module_available", lambda _: True)
    monkeypatch.setattr(readiness.TokenProvider, "headers", lambda _: {"Authorization": "Bearer test"})
    monkeypatch.setattr(readiness, "probe_authorization", lambda *_: (False, "awaiting RBAC propagation"))
    result = readiness.readiness(check_auth=True)
    checks = {c["check"]: c for c in result["checks"]}
    assert checks["authentication"]["ok"]
    assert not checks["authorization"]["ok"]
    assert not result["live_ready"]
