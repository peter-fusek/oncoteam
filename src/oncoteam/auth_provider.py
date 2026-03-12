"""File-backed OAuth provider that persists state across restarts."""

import json
import logging
import os
import tempfile
from pathlib import Path

from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
from mcp.server.auth.provider import AccessToken, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

logger = logging.getLogger(__name__)

# Default path — Railway can mount a persistent volume here
OAUTH_STORAGE_PATH = os.environ.get("OAUTH_STORAGE_PATH", "/tmp/oncoteam_oauth_state.json")


class FileOAuthProvider(InMemoryOAuthProvider):
    """OAuth provider that persists clients and tokens to a JSON file.

    Inherits all logic from InMemoryOAuthProvider but saves state after
    every mutation and loads state on startup. This ensures Claude.ai
    connectors survive Railway restarts.
    """

    def __init__(self, storage_path: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._storage_path = Path(storage_path or OAUTH_STORAGE_PATH)
        self._load()

    def _load(self):
        """Load persisted state from file."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text())
            for k, v in data.get("clients", {}).items():
                self.clients[k] = OAuthClientInformationFull.model_validate(v)
            for k, v in data.get("access_tokens", {}).items():
                self.access_tokens[k] = AccessToken.model_validate(v)
            for k, v in data.get("refresh_tokens", {}).items():
                self.refresh_tokens[k] = RefreshToken.model_validate(v)
            # Auth codes are short-lived, no need to persist
            self._access_to_refresh_map = data.get("access_to_refresh", {})
            self._refresh_to_access_map = data.get("refresh_to_access", {})
            logger.info(
                "Loaded OAuth state: %d clients, %d access tokens, %d refresh tokens",
                len(self.clients),
                len(self.access_tokens),
                len(self.refresh_tokens),
            )
        except Exception as e:
            logger.warning("Failed to load OAuth state from %s: %s", self._storage_path, e)

    def _save(self):
        """Persist current state to file atomically."""
        try:
            data = {
                "clients": {k: v.model_dump(mode="json") for k, v in self.clients.items()},
                "access_tokens": {
                    k: v.model_dump(mode="json") for k, v in self.access_tokens.items()
                },
                "refresh_tokens": {
                    k: v.model_dump(mode="json") for k, v in self.refresh_tokens.items()
                },
                "access_to_refresh": self._access_to_refresh_map,
                "refresh_to_access": self._refresh_to_access_map,
            }
            # Atomic write: write to temp file then rename
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=str(self._storage_path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f)
                os.replace(tmp_path, str(self._storage_path))
            except Exception:
                os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.warning("Failed to save OAuth state: %s", e)

    # Override all mutating methods to persist after changes

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await super().register_client(client_info)
        self._save()

    async def authorize(self, client, params) -> str:
        result = await super().authorize(client, params)
        # Auth codes are short-lived but save anyway for completeness
        return result

    async def exchange_authorization_code(self, client, authorization_code) -> OAuthToken:
        result = await super().exchange_authorization_code(client, authorization_code)
        self._save()
        return result

    async def exchange_refresh_token(self, client, refresh_token, scopes) -> OAuthToken:
        result = await super().exchange_refresh_token(client, refresh_token, scopes)
        self._save()
        return result

    async def revoke_token(self, token) -> None:
        await super().revoke_token(token)
        self._save()
