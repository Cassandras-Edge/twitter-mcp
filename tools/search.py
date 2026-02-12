from __future__ import annotations

from typing import Literal, Optional

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clients.x_api import XClient
from clients.grok import GrokClient


def register(
    mcp: FastMCP,
    x_client: XClient,
    grok_client: GrokClient,
    default_system_prompt: str,
) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=_ro)
    async def search(
        query: str,
        mode: Literal["both", "grok", "news"] = "both",
        max_news_results: int = 10,
        max_age_hours: Optional[int] = None,
        allowed_handles: Optional[list[str]] = None,
        excluded_handles: Optional[list[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        enable_video_understanding: bool = False,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        """Search X/Twitter using Grok AI synthesis and/or curated news articles.

        Default mode runs both Grok (sentiment synthesis with citations) and
        X News API (curated news articles) and returns combined results.

        Args:
            query: Search query (natural language for Grok, keywords for news).
            mode: 'both' (default) runs Grok + news, 'grok' for synthesis only,
                  'news' for curated articles only.
            max_news_results: Max news articles to return (1-100, default 10).
                Only used in news/both modes.
            max_age_hours: Max age of news results in hours (1-720).
                Only used in news/both modes.
            allowed_handles: Whitelist of X usernames to restrict Grok search to (max 10).
                Only used in grok/both modes.
            excluded_handles: X usernames to exclude from Grok results (max 10).
                Only used in grok/both modes.
            from_date: Only include posts on or after this date (ISO 8601, e.g. '2026-02-01').
                Only used in grok/both modes.
            to_date: Only include posts on or before this date (ISO 8601).
                Only used in grok/both modes.
            enable_video_understanding: Let Grok analyse video clips in posts.
                Only used in grok/both modes.
            system_prompt: Custom system prompt for Grok response style.
                Only used in grok/both modes.
            temperature: Sampling temperature for Grok (0-2).
                Only used in grok/both modes.
        """
        result: dict = {}

        # -- Grok synthesis --
        if mode in ("both", "grok"):
            try:
                grok_result = await grok_client.search(
                    query,
                    allowed_handles=allowed_handles,
                    excluded_handles=excluded_handles,
                    from_date=from_date,
                    to_date=to_date,
                    enable_video_understanding=enable_video_understanding,
                    system_prompt=system_prompt or default_system_prompt,
                    temperature=temperature,
                )
                result["grok"] = grok_result
            except httpx.HTTPStatusError as exc:
                result["grok"] = x_client.handle_error(exc)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                result["grok"] = x_client.handle_exception(exc)

        # -- News articles --
        if mode in ("both", "news"):
            try:
                extra: dict = {"query": query, "max_results": max_news_results}
                if max_age_hours:
                    extra["max_age_hours"] = max_age_hours
                params = x_client.news_params(extra)
                data = await x_client.get("/news/search", params)
                result["news"] = x_client.format_news_response(data)
            except httpx.HTTPStatusError as exc:
                result["news"] = x_client.handle_error(exc)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                result["news"] = x_client.handle_exception(exc)

        return result
