"""FastMCP server for Cassandra Twitter MCP — unified Twitter/X tools with auth.

Deployment-level (env vars): X_BEARER_TOKEN, XAI_API_KEY
Per-user (ACL credentials): twitter_auth_token, twitter_ct0 (browser cookies)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from cassandra_twitter_mcp.acl import Enforcer, load_enforcer
from cassandra_twitter_mcp.auth import McpKeyAuthProvider, build_auth
from cassandra_twitter_mcp.client_cache import ClientCache
from cassandra_twitter_mcp.config import Settings

logger = logging.getLogger(__name__)

SERVICE_ID = "twitter-mcp"


def create_mcp_server(settings: Settings) -> FastMCP:
    """Create and configure the FastMCP server with auth and all tools."""

    auth_provider, mcp_key_provider = build_auth(
        acl_url=settings.auth_url,
        acl_secret=settings.auth_secret,
        service_id=SERVICE_ID,
        base_url=settings.base_url,
        workos_client_id=settings.workos_client_id,
        workos_authkit_domain=settings.workos_authkit_domain,
        workos_api_key=settings.workos_api_key,
    )

    acl_path = Path(settings.auth_yaml_path)
    enforcer = load_enforcer(acl_path) if acl_path.exists() else None

    client_cache = ClientCache()

    @asynccontextmanager
    async def lifespan(server):
        yield {
            "client_cache": client_cache,
            "enforcer": enforcer,
            "settings": settings,
        }
        if mcp_key_provider:
            mcp_key_provider.close()

    mcp = FastMCP(
        name="Cassandra Twitter",
        instructions=(
            "Consolidated Twitter/X server for financial research and personal account access. "
            "PREFER search_news as the default starting point — it is fast, cheap, "
            "and returns curated news articles with headlines and summaries. "
            "Only escalate to search (Grok AI) when you specifically need opinion "
            "synthesis, discourse analysis, or quantitative sentiment. "
            "Use get_post_counts for volume analytics, get_user_tweets for monitoring accounts, "
            "get_tweet/get_thread/get_replies for individual post analysis. "
            "Use my_feed for the user's personal Twitter timeline, my_bookmarks for saved tweets, "
            "and get_article for Twitter Articles (long-form content). "
            "All tools are read-only and idempotent."
        ),
        lifespan=lifespan,
        auth=auth_provider,
    )

    # Health check
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request):  # noqa: ANN001, ARG001
        from starlette.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse({"ok": True, "service": "cassandra-twitter-mcp"})

    # Register all tool modules
    from cassandra_twitter_mcp.tools import register_all  # noqa: PLC0415

    register_all(mcp, settings)

    return mcp
