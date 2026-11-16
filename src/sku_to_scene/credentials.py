"""Shared Entra credential selection; tenant pinning never falls back to browser login."""

from .config import Settings, get_settings

SCOPE = "https://cognitiveservices.azure.com/.default"


def create_credential(settings: Settings | None = None):
    from azure.identity import AzureCliCredential, DefaultAzureCredential

    s = settings or get_settings()
    if s.subscription_id:
        # Azure CLI rejects --tenant together with --subscription.
        return AzureCliCredential(subscription=s.subscription_id)
    if s.tenant_id:
        return AzureCliCredential(tenant_id=s.tenant_id)
    return DefaultAzureCredential(exclude_interactive_browser_credential=False)
