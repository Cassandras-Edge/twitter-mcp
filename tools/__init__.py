from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clients.x_api import XClient
    from clients.grok import GrokClient
    from fastmcp import FastMCP


def register_all(
    mcp: FastMCP,
    x_client: XClient,
    grok_client: GrokClient,
    default_system_prompt: str,
) -> None:
    from .search import register as reg_search
    from .news import register as reg_news
    from .posts import register as reg_posts
    from .analytics import register as reg_analytics

    reg_search(mcp, x_client, grok_client, default_system_prompt)
    reg_news(mcp, x_client)
    reg_posts(mcp, x_client)
    reg_analytics(mcp, x_client)
