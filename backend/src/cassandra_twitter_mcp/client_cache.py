"""Per-user client cache with TTL.

All API keys and cookies are per-user credentials from ACL. This module
caches client instances so we don't re-create them on every tool call.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from cassandra_twitter_mcp.clients.x_api import XClient
from cassandra_twitter_mcp.clients.grok import GrokClient
from cassandra_twitter_mcp.clients.personal import PersonalClient

logger = logging.getLogger(__name__)

# Cache entries expire after 10 minutes
_CACHE_TTL_SECONDS = 600


class _CacheEntry:
    __slots__ = ("value", "created_at")

    def __init__(self, value: Any) -> None:
        self.value = value
        self.created_at = time.monotonic()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > _CACHE_TTL_SECONDS


class ClientCache:
    """Caches per-user client instances keyed by (email, credential_hash)."""

    def __init__(self) -> None:
        self._x_clients: dict[str, _CacheEntry] = {}
        self._grok_clients: dict[str, _CacheEntry] = {}
        self._personal_clients: dict[str, _CacheEntry] = {}

    def _cache_key(self, email: str, *credential_values: str) -> str:
        """Build cache key from email + credential values.

        If credentials change (e.g. rotated token), the old entry is
        naturally evicted since the key won't match.
        """
        # Use a simple hash to avoid storing raw credentials in keys
        import hashlib
        cred_hash = hashlib.sha256("|".join(credential_values).encode()).hexdigest()[:12]
        return f"{email}:{cred_hash}"

    def get_x_client(self, email: str, credentials: dict[str, str], timeout: int = 30) -> XClient | None:
        bearer_token = credentials.get("x_bearer_token", "")
        if not bearer_token:
            return None

        key = self._cache_key(email, bearer_token)
        entry = self._x_clients.get(key)
        if entry and not entry.is_expired():
            return entry.value

        client = XClient(bearer_token, timeout)
        self._x_clients[key] = _CacheEntry(client)
        self._evict_expired(self._x_clients)
        return client

    def get_grok_client(self, email: str, credentials: dict[str, str]) -> GrokClient | None:
        api_key = credentials.get("xai_api_key", "")
        if not api_key:
            return None

        key = self._cache_key(email, api_key)
        entry = self._grok_clients.get(key)
        if entry and not entry.is_expired():
            return entry.value

        client = GrokClient(api_key)
        self._grok_clients[key] = _CacheEntry(client)
        self._evict_expired(self._grok_clients)
        return client

    def get_personal_client(self, email: str, credentials: dict[str, str]) -> PersonalClient | None:
        auth_token = credentials.get("twitter_auth_token", "")
        ct0 = credentials.get("twitter_ct0", "")
        if not auth_token or not ct0:
            return None

        key = self._cache_key(email, auth_token, ct0)
        entry = self._personal_clients.get(key)
        if entry and not entry.is_expired():
            return entry.value

        try:
            client = PersonalClient(auth_token, ct0)
            self._personal_clients[key] = _CacheEntry(client)
            self._evict_expired(self._personal_clients)
            return client
        except Exception as exc:
            logger.warning("Failed to create PersonalClient for %s: %s", email, exc)
            return None

    @staticmethod
    def _evict_expired(cache: dict[str, _CacheEntry]) -> None:
        expired = [k for k, v in cache.items() if v.is_expired()]
        for k in expired:
            del cache[k]
