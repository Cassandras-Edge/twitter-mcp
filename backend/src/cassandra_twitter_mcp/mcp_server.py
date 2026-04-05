"""FastMCP server for Cassandra Twitter MCP — unified Twitter/X tools with auth.

Deployment-level (env vars): X_BEARER_TOKEN, XAI_API_KEY
Per-user (ACL credentials): twitter_auth_token, twitter_ct0 (browser cookies)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from cassandra_mcp_auth import AclMiddleware, DiscoveryTransform
from cassandra_twitter_mcp.auth import McpKeyAuthProvider, build_auth
from cassandra_twitter_mcp.client_cache import ClientCache
from cassandra_twitter_mcp.config import Settings

logger = logging.getLogger(__name__)

SERVICE_ID = "twitter-mcp"


def create_mcp_server(settings: Settings) -> FastMCP:
    """Create and configure the FastMCP server with auth and all tools."""

    auth_provider = None
    mcp_key_provider = None
    if settings.auth_url and settings.auth_secret:
        if settings.workos_client_id and settings.workos_authkit_domain and settings.base_url:
            auth_provider, mcp_key_provider = build_auth(
                acl_url=settings.auth_url,
                acl_secret=settings.auth_secret,
                service_id=SERVICE_ID,
                base_url=settings.base_url,
                workos_client_id=settings.workos_client_id,
                workos_authkit_domain=settings.workos_authkit_domain,
            )
        else:
            mcp_key_provider = McpKeyAuthProvider(
                acl_url=settings.auth_url,
                acl_secret=settings.auth_secret,
                service_id=SERVICE_ID,
            )
            auth_provider = mcp_key_provider

    client_cache = ClientCache()

    # Set fallback so tools work even without lifespan (gateway embedding)
    from cassandra_twitter_mcp.tools._helpers import set_fallback
    set_fallback(client_cache, settings)

    @asynccontextmanager
    async def lifespan(server):
        yield {
            "client_cache": client_cache,
            "settings": settings,
        }
        if mcp_key_provider:
            mcp_key_provider.close()

    # ACL middleware replaces per-tool check_acl() calls
    acl_mw = AclMiddleware(service_id=SERVICE_ID, acl_path=settings.auth_yaml_path)

    mcp_kwargs: dict = {
        "name": "Cassandra Twitter",
        "instructions": (
            "# Cassandra Twitter\n\n"
            "Twitter/X research + personal account access. Two layers: public "
            "research (X API v2 + Grok AI) and the user's own timeline/bookmarks "
            "(via synced browser cookies). All tools read-only.\n\n"
            "## When to use\n"
            "- **News & research** — curated articles, trending topics, ticker sentiment\n"
            "- **Volume analytics** — how often a topic/ticker is mentioned over time\n"
            "- **Account monitoring** — recent tweets from specific accounts\n"
            "- **Thread analysis** — read full threads, replies, long-form Articles\n"
            "- **Personal timeline** — the user's own feed, bookmarks, profile\n\n"
            "## Getting started\n"
            "Default to `search_news` first — fast, cheap, returns headlines + summaries. "
            "Escalate to `search` (Grok AI) only when you need opinion synthesis, discourse "
            "analysis, or quantitative sentiment. Use `get_post_counts` for volume analytics.\n\n"
            "## Discovery\n"
            "`tags()` → browse categories, `search(query, tags=[...])` → find tools, "
            "`get_schema(tools=[...])` → see params. Execution happens on a SEPARATE server (cassandra-gateway). Do NOT call `execute` here — this server only has discovery tools. Look up tool names/schemas here, then switch to the gateway server to call `execute(code)` with `call_tool(name, args)`."
        ),
        "lifespan": lifespan,
        "middleware": [acl_mw] if acl_mw._enabled else [],  # noqa: SLF001
    }
    if settings.code_mode:
        mcp_kwargs["transforms"] = [DiscoveryTransform(service_id=SERVICE_ID)]
    if auth_provider:
        mcp_kwargs["auth"] = auth_provider

    mcp = FastMCP(**mcp_kwargs)

    # Health check
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request):  # noqa: ANN001, ARG001
        from starlette.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse({"ok": True, "service": "cassandra-twitter-mcp"})

    # Register all tool modules
    from cassandra_twitter_mcp.tools import register_all  # noqa: PLC0415

    register_all(mcp, settings)

    return mcp
