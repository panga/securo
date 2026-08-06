from app.providers.base import (
    AccountData,
    BankProvider,
    ConnectTokenData,
    ConnectionData,
    HoldingData,
    InstitutionData,
    InstitutionListData,
    ProviderUserActionRequired,
    RefreshOutcome,
    SessionExpiredError,
    TransactionData,
)

# Registry of available providers.
_PROVIDERS: dict[str, type[BankProvider]] = {}

# All known providers the system supports (extensible for future connectors).
KNOWN_PROVIDERS = [
    {
        "name": "pluggy",
        "display_name": "Pluggy",
        "description": "Open finance provider for Brazilian banks",
        "flow_type": "widget",
        "requires_institution_select": False,
        "supports_asset_sync": True,
    },
    {
        "name": "enable_banking",
        "display_name": "Enable Banking",
        "description": "European banks via PSD2 open banking",
        "flow_type": "oauth",
        "requires_institution_select": True,
        "supports_asset_sync": False,
    },
    {
        "name": "simplefin",
        "display_name": "SimpleFIN",
        "description": "US and international banks via SimpleFIN Bridge",
        "flow_type": "token",
        "requires_institution_select": False,
        "supports_asset_sync": True,
    },
]


def register_provider(name: str, cls: type[BankProvider]) -> None:
    """Register a bank provider implementation."""
    _PROVIDERS[name] = cls


def _resolve_pluggy_client(client_id: str | None) -> tuple[str | None, str | None]:
    """Resolve Pluggy client_id and secret from config when only client_id is provided.

    When a client_id is passed but no secret, we look up the matching secret
    from the comma-separated config by index. Returns (client_id, client_secret)
    or (None, None) when no client_id is given.
    Raises ValueError if client_id is provided but not found in config.
    """
    if not client_id:
        return None, None
    from app.core.config import get_settings
    settings = get_settings()
    ids = settings.pluggy_client_ids
    secrets = settings.pluggy_client_secrets
    try:
        idx = ids.index(client_id)
    except ValueError:
        raise ValueError(
            f"Pluggy client_id '{client_id}' is not configured. "
            f"Available: {ids}"
        )
    if idx < len(secrets):
        return client_id, secrets[idx]
    return client_id, None


def get_provider(name: str, client_id: str | None = None, client_secret: str | None = None) -> BankProvider:
    """Get an instance of a registered bank provider by name.

    For Pluggy, optional client_id/client_secret can override the global config.
    When only client_id is provided, the matching secret is resolved from config.
    """
    provider_class = _PROVIDERS.get(name)
    if not provider_class:
        available = ", ".join(_PROVIDERS.keys()) or "(none)"
        raise ValueError(f"Unknown provider: {name}. Available: {available}")
    # For Pluggy: resolve secret from config if only client_id is provided
    if name == "pluggy" and client_id and not client_secret:
        client_id, client_secret = _resolve_pluggy_client(client_id)
    return provider_class(client_id=client_id, client_secret=client_secret)


def list_providers() -> list[dict[str, str]]:
    """Return info about all registered providers."""
    return [
        {"name": name, "flow_type": cls(client_id=None, client_secret=None).flow_type}
        for name, cls in _PROVIDERS.items()
    ]


def all_known_providers() -> list[dict]:
    """Return all known providers with a configured flag."""
    from app.core.config import get_settings
    settings = get_settings()
    result = []
    for p in KNOWN_PROVIDERS:
        entry = {**p, "configured": p["name"] in _PROVIDERS}
        # Expose available Pluggy clients when >1 is configured
        if p["name"] == "pluggy":
            client_ids = settings.pluggy_client_ids
            if len(client_ids) > 1:
                entry["available_clients"] = [
                    {"client_id": cid, "label": f"••••{cid[-4:]}"}
                    for cid in client_ids
                ]
        result.append(entry)
    return result


def _auto_register_providers() -> None:
    """Auto-register providers when credentials are configured."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.pluggy_client_id and settings.pluggy_client_secret:
        from app.providers.pluggy import PluggyProvider
        register_provider("pluggy", PluggyProvider)

    eb_has_key = bool(
        settings.enable_banking_private_key or settings.enable_banking_private_key_file
    )
    if settings.enable_banking_app_id and eb_has_key:
        from app.providers.enable_banking import EnableBankingProvider
        register_provider("enable_banking", EnableBankingProvider)

    if settings.simplefin_enabled:
        from app.providers.simplefin import SimpleFinProvider
        register_provider("simplefin", SimpleFinProvider)


_auto_register_providers()


_storage_provider = None


def get_storage_provider():
    """Get the configured storage provider (singleton)."""
    global _storage_provider
    if _storage_provider is None:
        from app.core.config import get_settings

        settings = get_settings()
        if settings.storage_provider == "local":
            from app.providers.local_storage import LocalStorageProvider

            _storage_provider = LocalStorageProvider()
        else:
            raise NotImplementedError(
                f"Storage provider '{settings.storage_provider}' is not yet implemented. "
                "Supported: 'local'"
            )
    return _storage_provider


__all__ = [
    "BankProvider",
    "AccountData",
    "TransactionData",
    "ConnectionData",
    "ConnectTokenData",
    "HoldingData",
    "InstitutionData",
    "InstitutionListData",
    "ProviderUserActionRequired",
    "RefreshOutcome",
    "SessionExpiredError",
    "register_provider",
    "get_provider",
    "list_providers",
    "all_known_providers",
    "get_storage_provider",
]
