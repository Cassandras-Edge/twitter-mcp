from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentAccessToken
from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import TextContent, ToolAnnotations

from cassandra_twitter_mcp.clients.x_api import XClient
from cassandra_twitter_mcp.tools._helpers import (
    get_email, resolve_x_client,
)


def _clamp_total_results(max_results: int) -> int:
    return max(20, min(max_results, 300))


def _clamp_important_replies_count(count: int) -> int:
    return max(1, min(count, 20))


def _clamp_scan_limit(scan_limit: int) -> int:
    return max(20, min(scan_limit, 500))


def _tweet_sort_key(tweet: dict) -> tuple[datetime, str]:
    created_at = tweet.get("created_at")
    dt = datetime.min.replace(tzinfo=timezone.utc)
    if created_at:
        try:
            ts = created_at.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(ts)
            dt = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return dt, tweet.get("id", "")


def _collect_image_urls(tweets: list[dict]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for tweet in tweets:
        for media in tweet.get("media", []):
            candidates: list[str] = []
            if media.get("type") == "photo" and media.get("url"):
                candidates.append(media["url"])
            if media.get("type") in {"video", "animated_gif"} and media.get("preview_url"):
                candidates.append(media["preview_url"])
            for candidate in candidates:
                if candidate not in seen:
                    seen.add(candidate)
                    urls.append(candidate)
    return urls


def _engagement_score(tweet: dict) -> int:
    metrics = tweet.get("metrics") or {}
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    quotes = metrics.get("quote_count", 0)
    replies = metrics.get("reply_count", 0)
    # Bias toward replies/redistribution over passive likes.
    return likes + (retweets * 2) + (quotes * 2) + (replies * 3)


async def _build_image_blocks(
    image_urls: list[str],
    *,
    max_image_blocks: int,
) -> list:
    if max_image_blocks < 1 or not image_urls:
        return []

    blocks = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in image_urls[:max_image_blocks]:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue

            mime_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if not mime_type.startswith("image/"):
                continue
            if len(resp.content) > 5_000_000:
                continue

            image_format = mime_type.split("/", 1)[1] if "/" in mime_type else None
            image = Image(data=resp.content, format=image_format)
            blocks.append(image.to_image_content(mime_type=mime_type))
    return blocks


async def _fetch_important_replies(
    x_client: XClient,
    *,
    conv_id: str,
    root_author_id: str | None,
    count: int,
    scan_limit: int,
) -> tuple[list[dict], dict]:
    replies_by_id: dict[str, dict] = {}
    pages_fetched = 0
    next_token: str | None = None
    seen_tokens: set[str] = set()

    while len(replies_by_id) < scan_limit:
        remaining = scan_limit - len(replies_by_id)
        if remaining < 10:
            break

        query = f"conversation_id:{conv_id} is:reply"
        if root_author_id:
            query = f"{query} -from:{root_author_id}"

        search_params = x_client.tweet_params({
            "query": query,
            "max_results": min(100, remaining),
            "sort_order": "recency",
        })
        if next_token:
            search_params["next_token"] = next_token

        data = await x_client.get("/tweets/search/recent", search_params)
        pages_fetched += 1

        page = x_client.format_response(data)
        for tweet in page.get("tweets", []):
            tweet_id = tweet.get("id")
            if tweet_id:
                replies_by_id.setdefault(tweet_id, tweet)

        token = data.get("meta", {}).get("next_token")
        if not token or token in seen_tokens:
            next_token = None
            break
        seen_tokens.add(token)
        next_token = token

    ranked = sorted(
        replies_by_id.values(),
        key=lambda row: (_engagement_score(row), _tweet_sort_key(row)),
        reverse=True,
    )
    important = ranked[:count]
    for row in important:
        row["context_score"] = _engagement_score(row)

    meta = {
        "requested_count": count,
        "requested_scan_limit": scan_limit,
        "returned_count": len(important),
        "scanned_reply_count": len(replies_by_id),
        "pages_fetched": pages_fetched,
        "has_more": next_token is not None,
    }
    if next_token:
        meta["next_token"] = next_token
    return important, meta


def register(mcp: FastMCP) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=_ro)
    async def get_tweet(
        tweet_id: str,
        ctx: Context,
        include_image_content: bool = False,
        max_image_blocks: int = 4,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict | ToolResult:
        """Get a single tweet by ID or URL.

        Args:
            tweet_id: Tweet ID or full URL (e.g. 'https://x.com/user/status/123')
            include_image_content: Include MCP image blocks for embedded media (photos
                and video previews). Defaults to false.
            max_image_blocks: Max number of image blocks to embed when
                include_image_content=true (default 4, max 12).
        """
        x_client = resolve_x_client(ctx)
        try:
            tid = x_client.extract_tweet_id(tweet_id)
            params = x_client.tweet_params()
            data = await x_client.get(f"/tweets/{tid}", params)
            tweet = x_client.format_response(data)
            if not include_image_content:
                return tweet

            image_urls = _collect_image_urls(tweet.get("tweets", []))
            image_blocks = await _build_image_blocks(
                image_urls,
                max_image_blocks=max(1, min(max_image_blocks, 12)),
            )
            if not image_blocks:
                return tweet

            content = [
                TextContent(type="text", text=f"Embedded media for tweet {tid}."),
                *image_blocks,
            ]
            return ToolResult(content=content, structured_content=tweet)
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)

    @mcp.tool(annotations=_ro)
    async def get_thread(
        tweet_id: str,
        ctx: Context,
        max_results: int = 120,
        important_replies_count: int = 5,
        important_replies_scan_limit: int = 200,
        include_image_content: bool = False,
        max_image_blocks: int = 6,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict | ToolResult:
        """Get the original author's full thread chain for a conversation.

        Fetches the root tweet, then paginates through tweets in the same
        conversation from the root author only.

        Args:
            tweet_id: Tweet ID or URL (any tweet in the thread)
            max_results: Total tweets cap to return across paginated requests
                for the author chain (default 120, range 20-300).
            important_replies_count: Number of high-signal non-author replies to include
                as context (default 5, range 1-20).
            important_replies_scan_limit: Number of recent non-author replies to scan
                before ranking (default 200, range 20-500).
            include_image_content: Include MCP image blocks for embedded media (photos
                and video previews). Defaults to false.
            max_image_blocks: Max number of image blocks to embed when
                include_image_content=true (default 6, max 12).
        """
        x_client = resolve_x_client(ctx)
        try:
            tid = x_client.extract_tweet_id(tweet_id)
            capped_results = _clamp_total_results(max_results)
            capped_important_replies = _clamp_important_replies_count(important_replies_count)
            capped_scan_limit = _clamp_scan_limit(important_replies_scan_limit)

            # Fetch target tweet to resolve the conversation.
            params = x_client.tweet_params()
            tweet_data = await x_client.get(f"/tweets/{tid}", params)
            tweet = tweet_data.get("data", {})
            conv_id = tweet.get("conversation_id", tid)

            # Fetch root tweet to identify thread author.
            root_data = tweet_data
            if conv_id != tid:
                root_data = await x_client.get(f"/tweets/{conv_id}", params)
            root_response = x_client.format_response(root_data)
            root_tweet = root_response["tweets"][0] if root_response["tweets"] else None
            root_author_id = (root_tweet or {}).get("author", {}).get("id") or tweet.get("author_id")

            # Paginate author-only chain in this conversation.
            tweets_by_id: dict[str, dict] = {}
            pages_fetched = 0
            next_token: str | None = None
            seen_tokens: set[str] = set()

            while len(tweets_by_id) < capped_results:
                remaining = capped_results - len(tweets_by_id)
                if remaining < 10:
                    break
                query = f"conversation_id:{conv_id}"
                if root_author_id:
                    query = f"{query} from:{root_author_id}"

                search_params = x_client.tweet_params({
                    "query": query,
                    "max_results": min(100, remaining),
                    "sort_order": "recency",
                })
                if next_token:
                    search_params["next_token"] = next_token

                conv_data = await x_client.get("/tweets/search/recent", search_params)
                pages_fetched += 1

                page = x_client.format_response(conv_data)
                for row in page.get("tweets", []):
                    row_id = row.get("id")
                    if row_id:
                        tweets_by_id[row_id] = row

                token = conv_data.get("meta", {}).get("next_token")
                if not token or token in seen_tokens:
                    next_token = None
                    break
                seen_tokens.add(token)
                next_token = token

            # Guarantee root and target are present, even when not in recent search window.
            target_response = x_client.format_response(tweet_data)
            if target_response["tweets"]:
                tweets_by_id.setdefault(tid, target_response["tweets"][0])
            if root_tweet:
                tweets_by_id.setdefault(root_tweet["id"], root_tweet)

            tweets = sorted(tweets_by_id.values(), key=_tweet_sort_key)
            important_replies, important_replies_meta = await _fetch_important_replies(
                x_client,
                conv_id=conv_id,
                root_author_id=root_author_id,
                count=capped_important_replies,
                scan_limit=capped_scan_limit,
            )
            thread: dict = {
                "tweets": tweets,
                "important_replies": important_replies,
                "root_tweet": root_tweet,
                "target_tweet": tweets_by_id.get(tid),
                "meta": {
                    "conversation_id": conv_id,
                    "root_author_id": root_author_id,
                    "thread_mode": "author_chain",
                    "requested_max_results": capped_results,
                    "returned_results": len(tweets),
                    "pages_fetched": pages_fetched,
                    "has_more": next_token is not None,
                    "important_replies": important_replies_meta,
                },
            }
            if next_token:
                thread["meta"]["next_token"] = next_token

            if not include_image_content:
                return thread

            image_urls = _collect_image_urls(tweets + important_replies)
            image_blocks = await _build_image_blocks(
                image_urls,
                max_image_blocks=max(1, min(max_image_blocks, 12)),
            )
            if not image_blocks:
                return thread

            summary = (
                f"Author thread chain for conversation {conv_id} "
                f"({len(tweets)} chain tweets, {len(important_replies)} important replies, "
                f"{len(image_blocks)} embedded image blocks)."
            )
            content = [TextContent(type="text", text=summary), *image_blocks]
            return ToolResult(content=content, structured_content=thread)
        except httpx.HTTPStatusError as exc:
            return x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return x_client.handle_exception(exc)

    @mcp.tool(annotations=_ro)
    async def get_replies(
        tweet_id: str,
        ctx: Context,
        max_results: int = 50,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get replies to a specific tweet.

        Args:
            tweet_id: Tweet ID or URL
            max_results: Max replies (10-100, default 50)
        """
        x_client = resolve_x_client(ctx)
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
