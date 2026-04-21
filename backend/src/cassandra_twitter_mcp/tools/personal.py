"""Personal Twitter/X account tools via twitter-cli (cookie-based).

Per-user cookies (twitter_auth_token, twitter_ct0) come from ACL credentials.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Literal, Optional

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentAccessToken
from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from cassandra_twitter_mcp.tools._helpers import (
    get_email, resolve_personal_client,
)


def register(mcp: FastMCP) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    async def _run(fn, *args, **kwargs):
        """Run sync twitter-cli call in executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    @mcp.tool(annotations=_ro)
    async def my_feed(
        ctx: Context,
        feed_type: Literal["foryou", "following"] = "foryou",
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get your personal Twitter/X home feed (single page).

        Returns one page of tweets from your timeline — either the algorithmic
        'For You' feed or your chronological 'Following' feed. To fetch more,
        call again with the returned `next_cursor`.

        Args:
            feed_type: 'foryou' (algorithmic, default) or 'following' (chronological).
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
                    Omit to start from the top of the feed.
        """
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_feed_page, feed_type, count, cursor)
        return {
            "feed_type": feed_type,
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def my_bookmarks(
        ctx: Context,
        count: int = 20,
        folder_id: Optional[str] = None,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get your saved Twitter/X bookmarks (single page).

        Returns one page of bookmarks, optionally from a specific folder. Call
        again with the returned `next_cursor` to fetch the next page.

        Args:
            count: Page size (default 20, max 40).
            folder_id: Optional bookmark folder ID. Use list_bookmark_folders to get IDs.
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 40))
        if folder_id:
            page = await _run(
                personal_client.get_bookmark_folder_tweets_page, folder_id, count, cursor,
            )
            return {
                "folder_id": folder_id,
                "count": len(page["tweets"]),
                "tweets": page["tweets"],
                "next_cursor": page["next_cursor"],
            }
        page = await _run(personal_client.get_bookmarks_page, count, cursor)
        return {
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def my_likes(
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get tweets you've liked on Twitter/X (single page).

        Returns one page of your liked tweets in reverse-chronological order.
        Call again with the returned `next_cursor` to fetch the next page.

        Args:
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_my_likes_page, count, cursor)
        return {
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def list_bookmark_folders(
        ctx: Context,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """List your Twitter/X bookmark folders."""
        personal_client = resolve_personal_client(ctx, token)
        folders = await _run(personal_client.get_bookmark_folders)
        return {"count": len(folders), "folders": folders}

    @mcp.tool(annotations=_ro)
    async def get_article(
        tweet_id: str,
        ctx: Context,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a Twitter Article (long-form content) as markdown.

        Twitter Articles are long-form posts that some users publish on the
        platform. This extracts the full article title and body text.

        Args:
            tweet_id: The tweet ID containing the article.
        """
        personal_client = resolve_personal_client(ctx, token)
        tweet_id = tweet_id.strip()
        article = await _run(personal_client.get_article, tweet_id)
        return {"article": article}

    @mcp.tool(annotations=_ro)
    async def my_profile(
        ctx: Context,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get your own Twitter/X profile information.

        Returns your username, bio, follower/following counts, etc.
        """
        personal_client = resolve_personal_client(ctx, token)
        profile = await _run(personal_client.whoami)
        return {"profile": profile}

    @mcp.tool(annotations=_ro)
    async def personal_search(
        query: str,
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        product: Literal["Top", "Latest", "People", "Photos", "Videos"] = "Top",
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Search tweets using your personal Twitter/X account (single page).

        Uses your authenticated session and may return different results
        (including from private accounts you follow). Call again with the
        returned `next_cursor` to fetch the next page.

        Args:
            query: Search query string.
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
            product: Search tab — Top, Latest, People, Photos, Videos.
        """
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 40))
        page = await _run(personal_client.search_page, query, count, cursor, product)
        return {
            "query": query,
            "product": product,
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def personal_user_profile(
        screen_name: str,
        ctx: Context,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a Twitter/X user's profile via your authenticated session.

        May show more info than the API-based version for users you follow.

        Args:
            screen_name: Twitter handle (with or without @).
        """
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        profile = await _run(personal_client.get_user_profile, screen_name)
        return {"profile": profile}

    @mcp.tool(annotations=_ro)
    async def personal_user_posts(
        screen_name: str,
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a user's recent tweets via your authenticated session (single page).

        Args:
            screen_name: Twitter handle (with or without @).
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_user_posts_page, screen_name, count, cursor)
        return {
            "screen_name": screen_name,
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def personal_user_likes(
        screen_name: str,
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a user's liked tweets via your authenticated session (single page).

        Note: X made likes private by default in 2024. Returns results only for
        accounts whose likes are public (or your own — use my_likes for that).

        Args:
            screen_name: Twitter handle (with or without @).
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_user_likes_page, screen_name, count, cursor)
        return {
            "screen_name": screen_name,
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def personal_user_followers(
        screen_name: str,
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a user's followers via your authenticated session (single page).

        Args:
            screen_name: Twitter handle (with or without @).
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_followers_page, screen_name, count, cursor)
        return {
            "screen_name": screen_name,
            "count": len(page["users"]),
            "followers": page["users"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def personal_user_following(
        screen_name: str,
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get the accounts a user follows via your authenticated session (single page).

        Args:
            screen_name: Twitter handle (with or without @).
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_following_page, screen_name, count, cursor)
        return {
            "screen_name": screen_name,
            "count": len(page["users"]),
            "following": page["users"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def personal_list_timeline(
        list_id: str,
        ctx: Context,
        count: int = 20,
        cursor: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get tweets from a Twitter/X List timeline (single page).

        Lists are curated collections of accounts. Pass the numeric list ID
        (visible in the list URL: x.com/i/lists/<list_id>).

        Args:
            list_id: Numeric Twitter List ID.
            count: Page size (default 20, max 40).
            cursor: Pagination cursor from a previous call's `next_cursor`.
        """
        personal_client = resolve_personal_client(ctx, token)
        list_id = list_id.strip()
        count = max(1, min(count, 40))
        page = await _run(personal_client.get_list_timeline_page, list_id, count, cursor)
        return {
            "list_id": list_id,
            "count": len(page["tweets"]),
            "tweets": page["tweets"],
            "next_cursor": page["next_cursor"],
        }

    @mcp.tool(annotations=_ro)
    async def personal_tweet_detail(
        tweet_id: str,
        ctx: Context,
        count: int = 20,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a tweet and its reply thread via your authenticated session.

        Returns the tweet and its conversation context including replies.

        Args:
            tweet_id: Tweet ID.
            count: Max replies to include (default 20).
        """
        personal_client = resolve_personal_client(ctx, token)
        tweet_id = tweet_id.strip()
        count = max(1, min(count, 500))
        tweets = await _run(personal_client.get_tweet_detail, tweet_id, count)
        return {"tweet_id": tweet_id, "count": len(tweets), "tweets": tweets}
