"""Client management.

X API and xAI clients use deployment-level env vars — shared across all users.
Personal clients (browser cookies) are per-user from ACL credentials, cached with TTL.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from cassandra_twitter_mcp.clients.grok import GrokClient
from cassandra_twitter_mcp.clients.personal import PersonalClient
from cassandra_twitter_mcp.clients.x_api import XClient

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 600


class _CacheEntry:
    __slots__ = ("value", "created_at")

    def __init__(self, value: Any) -> None:
        self.value = value
        self.created_at = time.monotonic()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > _CACHE_TTL_SECONDS


class ClientCache:
    """Shared X/xAI clients + per-user personal client cache."""

    def __init__(self) -> None:
        self._x_client: XClient | None = None
        self._grok_client: GrokClient | None = None
        self._personal_clients: dict[str, _CacheEntry] = {}

    def get_x_client(self, timeout: int = 30) -> XClient | None:
        if self._x_client is not None:
            return self._x_client
        bearer_token = os.environ.get("X_BEARER_TOKEN", "")
        if not bearer_token:
            return None
        self._x_client = XClient(bearer_token, timeout)
        return self._x_client

    def get_grok_client(self) -> GrokClient | None:
        if self._grok_client is not None:
            return self._grok_client
        api_key = os.environ.get("XAI_API_KEY", "")
        if not api_key:
            return None
        self._grok_client = GrokClient(api_key)
        return self._grok_client

    def get_personal_client(self, email: str, credentials: dict[str, str]) -> PersonalClient | None:
        auth_token = credentials.get("twitter_auth_token", "")
        ct0 = credentials.get("twitter_ct0", "")
        if not auth_token or not ct0:
            return None

        import hashlib
        cred_hash = hashlib.sha256(f"{auth_token}|{ct0}".encode()).hexdigest()[:12]
        key = f"{email}:{cred_hash}"

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
