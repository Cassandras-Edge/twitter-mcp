from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from cassandra_twitter_mcp.config import Settings


def register_all(mcp: FastMCP, settings: Settings) -> None:
    from .search import register as reg_search
    from .news import register as reg_news
    from .posts import register as reg_posts
    from .analytics import register as reg_analytics
    from .personal import register as reg_personal

    reg_search(mcp, settings)
    reg_news(mcp)
    reg_posts(mcp)
    reg_analytics(mcp)
    reg_personal(mcp)
