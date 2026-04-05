"""Shared helpers for resolving clients."""

from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context

from cassandra_twitter_mcp.client_cache import ClientCache
from cassandra_twitter_mcp.clients.grok import GrokClient
from cassandra_twitter_mcp.clients.personal import PersonalClient
from cassandra_twitter_mcp.clients.x_api import XClient

# Module-level fallbacks — set by create_mcp_server for gateway embedding
_fallback_cache: ClientCache | None = None
_fallback_settings = None


def set_fallback(cache: ClientCache, settings) -> None:
    global _fallback_cache, _fallback_settings
    _fallback_cache = cache
    _fallback_settings = settings


def get_email(token: AccessToken | None) -> str:
    if token is None:
        return ""
    return token.claims.get("email", "")


def get_credentials(token: AccessToken | None) -> dict[str, str]:
    if token is None:
        return {}
    return token.claims.get("credentials", {})


def get_cache(ctx: Context) -> ClientCache:
    if ctx.lifespan_context is not None:
        cache = ctx.lifespan_context.get("client_cache")
        if cache is not None:
            return cache
    if _fallback_cache is not None:
        return _fallback_cache
    raise ValueError("Client cache not initialized.")


def resolve_x_client(ctx: Context) -> XClient:
    """Resolve shared X API v2 client (deployment-level)."""
    client = get_cache(ctx).get_x_client()
    if client is None:
        raise ValueError("X_BEARER_TOKEN env var not set.")
    return client


def resolve_grok_client(ctx: Context) -> GrokClient:
    """Resolve shared Grok/xAI client (deployment-level)."""
    client = get_cache(ctx).get_grok_client()
    if client is None:
        raise ValueError("XAI_API_KEY env var not set.")
    return client


def resolve_personal_client(ctx: Context, token: AccessToken) -> PersonalClient:
    """Resolve per-user twitter-cli client from ACL credentials."""
    cache = get_cache(ctx)
    email = get_email(token)
    credentials = get_credentials(token)
    client = cache.get_personal_client(email, credentials)
    if client is None:
        raise ValueError(
            "Twitter cookies not configured. "
            "Set twitter_auth_token and twitter_ct0 in your credentials."
        )
    return client
