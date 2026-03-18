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
    check_acl, get_email, get_enforcer, resolve_personal_client,
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
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get your personal Twitter/X home feed.

        Returns tweets from your timeline — either the algorithmic 'For You'
        feed or your 'Following' feed (chronological).

        Args:
            feed_type: 'foryou' (algorithmic, default) or 'following' (chronological).
            count: Number of tweets to fetch (default 20, max ~100).
        """
        check_acl(get_enforcer(ctx), get_email(token), "my_feed")
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 100))
        tweets = await _run(personal_client.get_feed, feed_type, count)
        return {"feed_type": feed_type, "count": len(tweets), "tweets": tweets}

    @mcp.tool(annotations=_ro)
    async def my_bookmarks(
        ctx: Context,
        count: int = 50,
        folder_id: Optional[str] = None,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get your saved Twitter/X bookmarks.

        Returns your bookmarked tweets, optionally from a specific bookmark folder.

        Args:
            count: Number of bookmarks to fetch (default 50).
            folder_id: Optional bookmark folder ID. Use list_bookmark_folders to get IDs.
        """
        check_acl(get_enforcer(ctx), get_email(token), "my_bookmarks")
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 200))
        if folder_id:
            tweets = await _run(personal_client.get_bookmark_folder_tweets, folder_id, count)
            return {"folder_id": folder_id, "count": len(tweets), "tweets": tweets}
        tweets = await _run(personal_client.get_bookmarks, count)
        return {"count": len(tweets), "tweets": tweets}

    @mcp.tool(annotations=_ro)
    async def list_bookmark_folders(
        ctx: Context,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """List your Twitter/X bookmark folders."""
        check_acl(get_enforcer(ctx), get_email(token), "list_bookmark_folders")
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
        check_acl(get_enforcer(ctx), get_email(token), "get_article")
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
        check_acl(get_enforcer(ctx), get_email(token), "my_profile")
        personal_client = resolve_personal_client(ctx, token)
        profile = await _run(personal_client.whoami)
        return {"profile": profile}

    @mcp.tool(annotations=_ro)
    async def personal_search(
        query: str,
        ctx: Context,
        count: int = 20,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Search tweets using your personal Twitter/X account.

        Unlike the API-based search tools, this uses your authenticated session
        and may return different results (including results from private accounts
        you follow).

        Args:
            query: Search query string.
            count: Number of results (default 20).
        """
        check_acl(get_enforcer(ctx), get_email(token), "personal_search")
        personal_client = resolve_personal_client(ctx, token)
        count = max(1, min(count, 100))
        tweets = await _run(personal_client.search, query, count)
        return {"query": query, "count": len(tweets), "tweets": tweets}

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
        check_acl(get_enforcer(ctx), get_email(token), "personal_user_profile")
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        profile = await _run(personal_client.get_user_profile, screen_name)
        return {"profile": profile}

    @mcp.tool(annotations=_ro)
    async def personal_user_posts(
        screen_name: str,
        ctx: Context,
        count: int = 20,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Get a user's recent tweets via your authenticated session.

        Args:
            screen_name: Twitter handle (with or without @).
            count: Number of tweets (default 20).
        """
        check_acl(get_enforcer(ctx), get_email(token), "personal_user_posts")
        personal_client = resolve_personal_client(ctx, token)
        screen_name = screen_name.lstrip("@").strip()
        count = max(1, min(count, 100))
        tweets = await _run(personal_client.get_user_posts, screen_name, count)
        return {"screen_name": screen_name, "count": len(tweets), "tweets": tweets}

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
        check_acl(get_enforcer(ctx), get_email(token), "personal_tweet_detail")
        personal_client = resolve_personal_client(ctx, token)
        tweet_id = tweet_id.strip()
        count = max(1, min(count, 100))
        tweets = await _run(personal_client.get_tweet_detail, tweet_id, count)
        return {"tweet_id": tweet_id, "count": len(tweets), "tweets": tweets}
