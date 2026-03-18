"""FastMCP server for Cassandra Twitter MCP — unified Twitter/X tools with auth.

Three backends:
- X API v2 (bearer token): search_news, get_post_counts, get_user_tweets, get_tweet, get_thread, get_replies
- Grok AI (xAI key): search (synthesis + sentiment)
- twitter-cli (per-user cookies): my_feed, my_bookmarks, get_article, my_profile, personal_search
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from cassandra_twitter_mcp.auth import McpKeyAuthProvider
from cassandra_twitter_mcp.clients import XClient, GrokClient
from cassandra_twitter_mcp.clients.personal import PersonalClient
from cassandra_twitter_mcp.config import Settings
from cassandra_twitter_mcp.tools import register_all

logger = logging.getLogger(__name__)

SERVICE_ID = "twitter-mcp"


def create_mcp_server(settings: Settings) -> FastMCP:
    """Create and configure the FastMCP server with auth and all tools."""

    auth_provider = McpKeyAuthProvider(
        acl_url=settings.auth_url,
        acl_secret=settings.auth_secret,
        service_id=SERVICE_ID,
    ) if settings.auth_url and settings.auth_secret else None

    # Global API clients (deployment-level keys, shared across all users)
    x_client = XClient(settings.x_bearer_token, settings.x_timeout)
    grok_client = GrokClient(settings.xai_api_key, settings.grok_model)

    # Personal client (env-var cookies for local dev, or None in prod where
    # per-user cookies come from ACL credentials at request time)
    personal_client = None
    if settings.has_personal_env:
        try:
            personal_client = PersonalClient(settings.twitter_auth_token, settings.twitter_ct0)
            logger.info("Personal account tools enabled (env var cookies)")
        except Exception as exc:
            logger.warning("Personal account tools disabled: %s", exc)

    @asynccontextmanager
    async def lifespan(server):
        yield
        if auth_provider:
            auth_provider.close()

    mcp_kwargs: dict = {
        "name": "Cassandra Twitter",
        "instructions": (
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
        "lifespan": lifespan,
    }
    if auth_provider:
        mcp_kwargs["auth"] = auth_provider

    mcp = FastMCP(**mcp_kwargs)

    # Health check
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request):  # noqa: ANN001, ARG001
        from starlette.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse({"ok": True, "service": "cassandra-twitter-mcp"})

    # Register all tool modules
    register_all(
        mcp,
        x_client,
        grok_client,
        settings.grok_system_prompt,
        personal_client,
    )

    return mcp
