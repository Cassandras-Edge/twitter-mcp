"""Shared helpers for resolving clients."""

from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context

from cassandra_twitter_mcp.acl import Enforcer
from cassandra_twitter_mcp.client_cache import ClientCache
from cassandra_twitter_mcp.clients.grok import GrokClient
from cassandra_twitter_mcp.clients.personal import PersonalClient
from cassandra_twitter_mcp.clients.x_api import XClient

SERVICE_ID = "twitter-mcp"


def get_email(token: AccessToken) -> str:
    return token.claims.get("email", "")


def get_credentials(token: AccessToken) -> dict[str, str]:
    return token.claims.get("credentials", {})


def check_acl(enforcer: Enforcer | None, email: str, tool_name: str) -> None:
    if enforcer is None:
        return
    result = enforcer.enforce(email, SERVICE_ID, tool_name)
    if not result.allowed:
        raise ValueError(f"Access denied: {result.reason}")


def get_cache(ctx: Context) -> ClientCache:
    return ctx.lifespan_context["client_cache"]


def get_enforcer(ctx: Context) -> Enforcer | None:
    return ctx.lifespan_context.get("enforcer")


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
