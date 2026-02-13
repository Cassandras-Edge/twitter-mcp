from __future__ import annotations

from typing import Optional

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clients.x_api import XClient


def register(mcp: FastMCP, x_client: XClient) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=_ro)
    async def search_news(
        query: str,
        max_results: int = 10,
        max_age_hours: Optional[int] = None,
    ) -> dict:
        """Search X/Twitter for curated news articles.

        Returns headlines, summaries, categories, and related posts from the
        X News API. Use this when the user wants NEWS, headlines, or articles —
        not tweets or opinions.

        Args:
            query: Keywords to search for in news articles.
            max_results: Max news articles to return (1-100, default 10).
            max_age_hours: Max age of news results in hours (1-720).
        """
        try:
            extra: dict = {"query": query, "max_results": max_results}
            if max_age_hours:
                extra["max_age_hours"] = max_age_hours
            params = x_client.news_params(extra)
            data = await x_client.get("/news/search", params)
            return x_client.format_news_response(data)
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)
