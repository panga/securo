# Plan: Store Provider Client ID with Bank Connection

## Goal
Allow multiple Pluggy client configurations per deployment by storing the provider's `client_id` in the `BankConnection.settings` JSON column. This enables different connections to use different Pluggy client credentials (e.g., different commercial agreements, sandbox vs production, or per-workspace isolation).

## Scope / Affected Areas

| Area | Files | Changes |
|------|-------|---------|
| Config | `backend/app/core/config.py` | Support multiple Pluggy clients via comma-separated env vars |
| Provider Factory | `backend/app/providers/__init__.py` | Modify `get_provider` to accept client_id/client_secret |
| Pluggy Provider | `backend/app/providers/pluggy.py` | Accept client_id/secret in `__init__`, use in `_ensure_api_key` |
| Connection Service | `backend/app/services/connection_service.py` | Pass client_id through connect token creation, callback, and sync |
| API Routes | `backend/app/api/bank_connections.py` | Add client_id to connect-token, oauth-url, and available-clients endpoints |

## Approach (Concrete Ordered Steps)

### 1. Config: Multiple Pluggy Clients ✅ DONE
- Change `pluggy_client_id` and `pluggy_client_secret` in `Settings` to accept comma-separated lists
- Parse into `List[str]` properties: `pluggy_client_ids`, `pluggy_client_secrets`
- Validate equal lengths at startup
- Keep single-value env vars working (backward compatible)
- Default: first pair (index 0) used when no explicit selection

### 2. Provider Factory Refactor
- Change `get_provider(name: str) -> BankProvider` to `get_provider(name: str, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> BankProvider`
- Provider classes accept optional `client_id`/`client_secret` in `__init__`
- If not provided, fall back to global settings (first configured client for Pluggy)
- Update `_auto_register_providers` to register base classes without instantiating

### 3. Pluggy Provider Update
- Add `__init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None)`
- Store instance variables, use them in `_ensure_api_key` instead of global settings
- Keep global settings as fallback when instance vars are None (uses first configured client)

### 4. Connection Service - Connect Token Creation
In `create_connect_token` and `get_oauth_url`:
- Accept optional `client_id` parameter
- Pass `client_id` to provider's `create_connect_token`
- Store the used `client_id` in OAuth state for callback retrieval

### 5. Connection Service - Callback Flow
In `handle_oauth_callback`:
- Retrieve `client_id` from OAuth state
- Store it on the new `BankConnection.settings["provider_client_id"]`
- Use it when calling `get_provider` for initial sync

### 6. Connection Service - Sync Flow
In `sync_connection`:
- Read `client_id` from `connection.settings.get("provider_client_id")`
- When calling `get_provider(connection.provider)`, pass the `client_id`
- Provider instance will use connection-specific credentials

### 7. API Endpoints
- `POST /api/bank-connections/connect-token`: Accept optional `client_id` in request body
- `GET /api/bank-connections/oauth-url`: Accept optional `client_id` in query params
- `GET /api/bank-connections/available-clients`: Return list of configured Pluggy clients (last 4 digits of client_id as label) — only when >1 client configured

## Validation

| Step | Verification |
|------|--------------|
| Config | Startup with single client (legacy env) works; with multiple clients works; mismatched lengths fails fast |
| Provider Factory | Test `get_provider("pluggy", "custom_id", "secret")` returns instance using custom creds |
| Pluggy Provider | Mock HTTP calls; verify `_ensure_api_key` uses instance creds over global |
| Connection Creation | E2E: connect a bank via widget with custom client_id; verify stored in `settings.provider_client_id` |
| Sync | E2E: sync connection with custom client_id; verify provider uses correct credentials |
| Backward Compat | Existing connections (no `provider_client_id` in settings) still work with global settings (first client) |
| Available Clients API | Returns list with labels like "••••1234" when >1 client; empty/404 when 1 client |

## Decisions (Resolved)

1. **Client ID source**: Passed from frontend during connection flow (user selects when >1 client configured)
2. **Secret storage**: Only `client_id` stored in `settings.provider_client_id`; secret resolved from config mapping by index
3. **Provider scope**: Only Pluggy for now
4. **OAuth state size**: Acceptable to store client_id in state
5. **Storage**: Use `BankConnection.settings` JSON column (no migration needed)
6. **Frontend UX**: Show client selector only when >1 Pluggy client configured; label shows last 4 digits of client_id (e.g., "••••1234")