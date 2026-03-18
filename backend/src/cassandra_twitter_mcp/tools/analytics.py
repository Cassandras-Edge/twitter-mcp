from __future__ import annotations

from typing import Optional

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cassandra_twitter_mcp.clients.x_api import XClient


def register(mcp: FastMCP, x_client: XClient) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=_ro)
    async def get_post_counts(
        query: str,
        granularity: str = "hour",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        """Get tweet volume counts for a query over time (last 7 days).

        Useful for gauging buzz, detecting spikes, and comparing topic volumes.

        Args:
            query: Search query (same operators as search)
            granularity: 'minute', 'hour', or 'day' (default: hour)
            start_time: ISO 8601 start time
            end_time: ISO 8601 end time
        """
        try:
            params: dict = {"query": query, "granularity": granularity}
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time
            data = await x_client.get("/tweets/counts/recent", params)
            return data
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)

    @mcp.tool(annotations=_ro)
    async def get_user_tweets(
        username: str,
        max_results: int = 10,
        exclude_replies: bool = False,
        exclude_retweets: bool = False,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        pagination_token: Optional[str] = None,
    ) -> dict:
        """Get recent tweets from a user's timeline.

        Args:
            username: X username (with or without @)
            max_results: Number of tweets (5-100, default 10)
            exclude_replies: Exclude reply tweets
            exclude_retweets: Exclude retweets
            start_time: ISO 8601 start time (e.g. '2024-01-01T00:00:00Z')
            end_time: ISO 8601 end time
            pagination_token: Token for next page of results
        """
        try:
            user_id = await x_client.resolve_user_id(username)
            excludes = []
            if exclude_replies:
                excludes.append("replies")
            if exclude_retweets:
                excludes.append("retweets")
            extra: dict = {"max_results": max_results}
            if excludes:
                extra["exclude"] = ",".join(excludes)
            if start_time:
                extra["start_time"] = start_time
            if end_time:
                extra["end_time"] = end_time
            if pagination_token:
                extra["pagination_token"] = pagination_token
            params = x_client.tweet_params(extra)
            data = await x_client.get(f"/users/{user_id}/tweets", params)
            return x_client.format_response(data)
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)
