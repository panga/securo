from functools import lru_cache
from os import getenv
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Use the same environment variable that systemd uses: https://systemd.io/CREDENTIALS/
# If not defined, defaults to docker secrets defaults (https://docs.docker.com/compose/how-tos/use-secrets/)
CREDENTIALS_DIRECTORY: list[Path] = [
    Path(p) for p in getenv("CREDENTIALS_DIRECTORY", "/run/secrets").split(":") if p
]


class Settings(BaseSettings):
    # App
    app_name: str = "Securo"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/securo"

    # Auth
    secret_key: SecretStr = SecretStr("change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Pluggy
    # Support multiple clients via comma-separated values.
    # Single value (legacy) works for backward compatibility.
    # When multiple clients configured, the first pair (index 0) is the default.
    pluggy_client_id: str = ""
    pluggy_client_secret: SecretStr = SecretStr("")
    # Empty means "derive from FRONTEND_URL" (see BankProvider.redirect_uri).
    # Set explicitly only when the URL registered in the provider dashboard
    # differs from where the app is served.
    pluggy_oauth_redirect_uri: str = ""

    @property
    def pluggy_client_ids(self) -> list[str]:
        """Return list of configured Pluggy client IDs."""
        if not self.pluggy_client_id:
            return []
        return [cid.strip() for cid in self.pluggy_client_id.split(",") if cid.strip()]

    @property
    def pluggy_client_secrets(self) -> list[str]:
        """Return list of configured Pluggy client secrets."""
        if not self.pluggy_client_secret:
            return []
        secret_val = self.pluggy_client_secret.get_secret_value()
        if not secret_val:
            return []
        return [s.strip() for s in secret_val.split(",") if s.strip()]

    @property
    def pluggy_client_count(self) -> int:
        """Return number of configured Pluggy client pairs."""
        ids = self.pluggy_client_ids
        secrets = self.pluggy_client_secrets
        if len(ids) != len(secrets):
            raise ValueError(
                f"PLUGGY_CLIENT_ID has {len(ids)} values but PLUGGY_CLIENT_SECRET has {len(secrets)}. "
                "They must have the same number of comma-separated values."
            )
        return len(ids)

    def get_pluggy_client(self, index: int = 0) -> tuple[str, str] | None:
        """Get client_id and secret for a specific index (default 0). Returns None if not configured."""
        if self.pluggy_client_count == 0:
            return None
        if index < 0 or index >= self.pluggy_client_count:
            raise IndexError(f"Pluggy client index {index} out of range (0-{self.pluggy_client_count - 1})")
        return self.pluggy_client_ids[index], self.pluggy_client_secrets[index]

    # Enable Banking (European PSD2 banks)
    enable_banking_app_id: str = ""
    enable_banking_private_key: SecretStr = SecretStr("")  # raw PEM; supports \n-escaped envs
    enable_banking_private_key_file: str = ""  # path to PEM file; takes precedence
    enable_banking_api_url: str = "https://api.enablebanking.com"
    enable_banking_oauth_redirect_uri: str = ""  # empty derives from FRONTEND_URL

    # SimpleFIN Bridge (US/intl banks, paste-a-token flow). Off by default.
    # The bridge URL defaults to the beta/sandbox host so users can test with
    # the demo token; flip to https://bridge.simplefin.org for production.
    simplefin_enabled: bool = False
    simplefin_api_url: str = "https://beta-bridge.simplefin.org"

    # Frontend
    frontend_url: str = "http://localhost:5173"

    # WebAuthn / passkeys
    webauthn_rp_name: str = "Securo"
    # Empty means the RP ID follows the domain the browser is on, which is what
    # most deployments want. Set it to pin passkeys to one domain (e.g.
    # securo.example.com); requests from other origins are then rejected.
    webauthn_rp_id: str = ""
    # Empty means the expected origin follows the browser. Only set this when the
    # app is reached at exactly one origin and you want it enforced.
    webauthn_origin: str = ""
    webauthn_challenge_ttl_seconds: int = 300

    # Defaults
    default_currency: str = "USD"  # fallback currency when user preference is unavailable

    # FX Rates
    openexchangerates_app_id: str = ""
    supported_currencies: str = "USD,EUR,GBP,BRL,CAD,AUD,CHF,ARS,JPY,MXN,INR,SEK,DKK,NOK,PLN,CZK,HUF,RON,CRC,IDR,COP,CLP,DOP,RUB,GTQ,PHP,UAH"  # comma-separated list
    fx_sync_mode: str = "on_demand"  # "on_demand" or "scheduled"

    # Storage
    storage_provider: str = "local"  # "local" or "s3"
    storage_local_path: str = "./data/attachments"
    storage_max_file_size_mb: int = 10
    storage_allowed_extensions: str = "jpg,jpeg,png,webp,gif,heic,pdf"
    storage_max_attachments_per_transaction: int = 10

    # S3 Storage (for future use)
    storage_s3_bucket: str = ""
    storage_s3_region: str = ""
    storage_s3_access_key: SecretStr = SecretStr("")
    storage_s3_secret_key: SecretStr = SecretStr("")
    storage_s3_endpoint_url: str = ""  # for S3-compatible services (MinIO, DigitalOcean Spaces)

    # Registration
    registration_enabled: bool = True

    # OIDC login (works with Authentik, Pocket ID, and other standard OIDC providers)
    oidc_enabled: bool = False
    oidc_provider_name: str = "OIDC"
    oidc_discovery_url: str = (
        ""  # e.g. https://auth.example.com/application/o/securo/.well-known/openid-configuration
    )
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")
    oidc_redirect_uri: str = ""  # defaults to {FRONTEND_URL}/api/auth/oidc/callback
    oidc_scopes: str = "openid email profile"
    oidc_auto_register: bool = True
    oidc_existing_user_link_mode: str = "disabled"  # disabled|verified_email|email
    oidc_require_verified_email: bool = True
    oidc_sync_roles: bool = False
    oidc_roles_claim: str = "groups"
    oidc_admin_roles: str = ""  # comma-separated provider roles/groups that grant Securo admin
    oidc_workspace_role_map: str = ""  # JSON: {"provider-role": "owner|editor|viewer"}

    # Celery
    redis_url: str = "redis://localhost:6379/0"

    # Logo size for market-priced asset icons. The logo URL is built from
    # the company website we get from the market-price provider; no API
    # key or third-party account is required. Defaults to 128×128 which
    # is what Google's favicon service caps at before upscaling.
    logo_size: int = 128

    # Brazilian Treasury bond prices (official Tesouro Transparente CSV).
    # On by default since most users are Brazilian; the official CSV is only
    # fetched when someone actually searches a bond, and the UI pre-warm is
    # gated to Brazilian users, so non-Brazilian installs pay ~zero cost.
    # Set TESOURO_DIRETO_ENABLED=false to fully disable (e.g. to avoid the
    # external dependency on the Brazilian government endpoint).
    tesouro_direto_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", secrets_dir=CREDENTIALS_DIRECTORY)


@lru_cache
def get_settings() -> Settings:
    return Settings()
