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
            "Use this when the user wants to know what people are saying. Twitter is "
            "where news breaks, opinions form, and narratives spread — this service "
            "gives you real-time access to all of it.\n\n"
            "Think of this server when the user asks about:\n"
            "- What's happening with a company, topic, or person right now\n"
            "- Public sentiment or discourse around something\n"
            "- Breaking news or trending topics\n"
            "- What a specific account has been posting\n"
            "- The user's own Twitter feed, bookmarks, or profile\n\n"
            "The service has two layers. Public research tools use the X API and "
            "Grok AI — these work for any topic. Personal account tools use the "
            "user's synced browser cookies to access their own timeline and bookmarks. "
            "Everything is read-only.\n\n"
            "Start with `search_news` for most questions — it's fast and returns "
            "curated articles with summaries. Escalate to `search` (Grok AI) when "
            "you need opinion synthesis or quantitative sentiment. Use `get_post_counts` "
            "to see how often something is being talked about over time.\n\n"
            "## How this works\n\n"
            "This is a DISCOVERY server — it tells you what tools exist and how to "
            "call them. To actually execute a tool, use the cassandra-gateway server.\n\n"
            "### Step 1: Find tools (this server)\n"
            "Call `cass_twitter_search` to look up tools and get their full parameter schemas.\n\n"
            "```\n"
            "cass_twitter_search(\n"
            "  query: str,           # what you're looking for, e.g. 'news' or 'bookmarks'\n"
            "  tags: list[str]=None, # optional tag filter\n"
            "  detail: str='full',   # 'brief' for names only, 'detailed' for markdown, 'full' for JSON schemas\n"
            "  limit: int=None       # max results\n"
            ")\n"
            "```\n\n"
            "### Step 2: Execute tools (cassandra-gateway server)\n"
            "Take the tool name and params from step 1, then call `cass_gateway_run` "
            "on the cassandra-gateway server:\n\n"
            "```\n"
            "cass_gateway_run(code=\"return await call_tool('search_news', {'query': 'AAPL'})\")\n"
            "```"
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
