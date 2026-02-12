from __future__ import annotations

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clients.x_api import XClient


def register(mcp: FastMCP, x_client: XClient) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=_ro)
    async def get_tweet(tweet_id: str) -> dict:
        """Get a single tweet by ID or URL.

        Args:
            tweet_id: Tweet ID or full URL (e.g. 'https://x.com/user/status/123')
        """
        try:
            tid = x_client.extract_tweet_id(tweet_id)
            params = x_client.tweet_params()
            data = await x_client.get(f"/tweets/{tid}", params)
            return x_client.format_response(data)
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)

    @mcp.tool(annotations=_ro)
    async def get_thread(tweet_id: str, max_results: int = 50) -> dict:
        """Get a tweet and its full conversation thread.

        Fetches the root tweet first, then all replies in the conversation.

        Args:
            tweet_id: Tweet ID or URL (any tweet in the thread)
            max_results: Max replies to fetch (10-100, default 50)
        """
        try:
            tid = x_client.extract_tweet_id(tweet_id)

            # Fetch the target tweet to get conversation_id
            params = x_client.tweet_params()
            tweet_data = await x_client.get(f"/tweets/{tid}", params)
            tweet = tweet_data.get("data", {})
            conv_id = tweet.get("conversation_id", tid)

            # Fetch the full conversation
            search_params = x_client.tweet_params({
                "query": f"conversation_id:{conv_id}",
                "max_results": max_results,
                "sort_order": "recency",
            })
            conv_data = await x_client.get("/tweets/search/recent", search_params)

            # Also fetch the root tweet if different from target
            root_response = None
            if conv_id != tid:
                root_data = await x_client.get(f"/tweets/{conv_id}", params)
                root_response = x_client.format_response(root_data)

            thread = x_client.format_response(conv_data)
            if root_response:
                thread["root_tweet"] = (
                    root_response["tweets"][0] if root_response["tweets"] else None
                )
            return thread
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)

    @mcp.tool(annotations=_ro)
    async def get_replies(tweet_id: str, max_results: int = 50) -> dict:
        """Get replies to a specific tweet.

        Args:
            tweet_id: Tweet ID or URL
            max_results: Max replies (10-100, default 50)
        """
        try:
            tid = x_client.extract_tweet_id(tweet_id)

            # Get conversation_id from the tweet
            params = x_client.tweet_params()
            tweet_data = await x_client.get(f"/tweets/{tid}", params)
            tweet = tweet_data.get("data", {})
            conv_id = tweet.get("conversation_id", tid)

            # Search for replies in conversation, excluding the original author
            search_params = x_client.tweet_params({
                "query": (
                    f"conversation_id:{conv_id} "
                    f"-from:{tweet.get('author_id', '')} is:reply"
                ),
                "max_results": max_results,
                "sort_order": "recency",
            })
            data = await x_client.get("/tweets/search/recent", search_params)
            return x_client.format_response(data)
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)
