"""Wrapper around twitter-cli's TwitterClient for personal account access.

Uses reverse-engineered X/Twitter GraphQL APIs with browser cookies.
Auth: TWITTER_AUTH_TOKEN + TWITTER_CT0 env vars.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Optional

from twitter_cli.graphql import FEATURES
from twitter_cli.parser import _deep_get, parse_timeline_response, parse_user_result

logger = logging.getLogger(__name__)

_PAGE_SIZE_MAX = 40


def _tweet_to_dict(tweet: Any) -> dict:
    """Convert a twitter_cli Tweet dataclass to a clean dict."""
    d = asdict(tweet)
    # Flatten author
    if "author" in d:
        d["author"] = {k: v for k, v in d["author"].items() if v}
    # Flatten metrics — drop zeros
    if "metrics" in d:
        d["metrics"] = {k: v for k, v in d["metrics"].items() if v}
    # Drop empty fields
    d = {k: v for k, v in d.items() if v is not None and v != "" and v != []}
    # Recurse into quoted_tweet
    if "quoted_tweet" in d and d["quoted_tweet"]:
        d["quoted_tweet"] = {k: v for k, v in d["quoted_tweet"].items()
                            if v is not None and v != "" and v != []}
    return d


def _profile_to_dict(profile: Any) -> dict:
    """Convert a twitter_cli UserProfile dataclass to a clean dict."""
    d = asdict(profile)
    return {k: v for k, v in d.items() if v is not None and v != "" and v != 0}


class PersonalClient:
    """Sync wrapper around twitter_cli.TwitterClient.

    twitter-cli is synchronous (uses curl_cffi). We wrap calls to run in
    an executor from async tool handlers.
    """

    def __init__(self, auth_token: str, ct0: str) -> None:
        from twitter_cli.client import TwitterClient
        self._client = TwitterClient(auth_token=auth_token, ct0=ct0)
        logger.info("PersonalClient initialized")

    def get_feed(self, feed_type: str = "foryou", count: int = 20) -> list[dict]:
        if feed_type == "following":
            tweets = self._client.fetch_following_feed(count=count)
        else:
            tweets = self._client.fetch_home_timeline(count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def get_bookmarks(self, count: int = 50) -> list[dict]:
        tweets = self._client.fetch_bookmarks(count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def get_bookmark_folders(self) -> list[dict]:
        folders = self._client.fetch_bookmark_folders()
        return [asdict(f) for f in folders]

    def get_bookmark_folder_tweets(self, folder_id: str, count: int = 50) -> list[dict]:
        tweets = self._client.fetch_bookmark_folder_timeline(folder_id, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def search(self, query: str, count: int = 20) -> list[dict]:
        tweets = self._client.fetch_search(query, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def get_user_profile(self, screen_name: str) -> dict:
        profile = self._client.fetch_user(screen_name)
        return _profile_to_dict(profile)

    def get_user_posts(self, screen_name: str, count: int = 20) -> list[dict]:
        profile = self._client.fetch_user(screen_name)
        tweets = self._client.fetch_user_tweets(profile.id, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def get_tweet_detail(self, tweet_id: str, count: int = 20) -> list[dict]:
        tweets = self._client.fetch_tweet_detail(tweet_id, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def get_article(self, tweet_id: str) -> dict:
        tweet = self._client.fetch_article(tweet_id)
        return _tweet_to_dict(tweet)

    def get_user_likes(self, screen_name: str, count: int = 20) -> list[dict]:
        profile = self._client.fetch_user(screen_name)
        tweets = self._client.fetch_user_likes(profile.id, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def get_my_likes(self, count: int = 20) -> list[dict]:
        me = self._client.fetch_me()
        tweets = self._client.fetch_user_likes(me.id, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    def whoami(self) -> dict:
        profile = self._client.fetch_me()
        return _profile_to_dict(profile)

    def get_followers(self, screen_name: str, count: int = 20) -> list[dict]:
        profile = self._client.fetch_user(screen_name)
        followers = self._client.fetch_followers(profile.id, count=count)
        return [_profile_to_dict(f) for f in followers]

    def get_following(self, screen_name: str, count: int = 20) -> list[dict]:
        profile = self._client.fetch_user(screen_name)
        following = self._client.fetch_following(profile.id, count=count)
        return [_profile_to_dict(f) for f in following]

    def get_list_timeline(self, list_id: str, count: int = 20) -> list[dict]:
        tweets = self._client.fetch_list_timeline(list_id, count=count)
        return [_tweet_to_dict(t) for t in tweets]

    # ── Cursor-paginated single-page fetchers ─────────────────────────
    # Each returns {"tweets": [...], "next_cursor": str|None} or
    # {"users": [...], "next_cursor": str|None}. next_cursor is None at end.

    def _timeline_page(
        self,
        operation_name: str,
        count: int,
        cursor: Optional[str],
        get_instructions,
        extra_variables: Optional[dict] = None,
        override_base: bool = False,
        field_toggles: Optional[dict] = None,
    ) -> dict:
        page_size = max(1, min(count, _PAGE_SIZE_MAX))
        if override_base:
            variables: dict[str, Any] = {"count": page_size}
        else:
            variables = {
                "count": page_size,
                "includePromotedContent": False,
                "latestControlAvailable": True,
                "requestContext": "launch",
            }
        if extra_variables:
            variables.update(extra_variables)
        if cursor:
            variables["cursor"] = cursor
        data = self._client._graphql_get(
            operation_name, variables, FEATURES, field_toggles=field_toggles,
        )
        tweets, next_cursor = parse_timeline_response(data, get_instructions)
        return {
            "tweets": [_tweet_to_dict(t) for t in tweets],
            "next_cursor": next_cursor,
        }

    def _user_list_page(
        self,
        operation_name: str,
        user_id: str,
        count: int,
        cursor: Optional[str],
        get_instructions,
    ) -> dict:
        page_size = max(1, min(count, _PAGE_SIZE_MAX))
        variables: dict[str, Any] = {
            "userId": user_id,
            "count": page_size,
            "includePromotedContent": False,
        }
        if cursor:
            variables["cursor"] = cursor
        data = self._client._graphql_get(operation_name, variables, FEATURES)
        instructions = get_instructions(data)
        users: list = []
        next_cursor: Optional[str] = None
        if instructions:
            for instruction in instructions:
                for entry in instruction.get("entries", []):
                    content = entry.get("content", {})
                    etype = content.get("entryType", "")
                    if etype == "TimelineTimelineItem":
                        item = content.get("itemContent", {})
                        user_results = _deep_get(item, "user_results", "result")
                        if user_results:
                            u = parse_user_result(user_results)
                            if u:
                                users.append(u)
                    elif etype == "TimelineTimelineCursor":
                        if content.get("cursorType") == "Bottom":
                            next_cursor = content.get("value")
        return {
            "users": [_profile_to_dict(u) for u in users],
            "next_cursor": next_cursor,
        }

    def get_feed_page(self, feed_type: str, count: int, cursor: Optional[str]) -> dict:
        op = "HomeLatestTimeline" if feed_type == "following" else "HomeTimeline"
        return self._timeline_page(
            op, count, cursor,
            lambda d: _deep_get(d, "data", "home", "home_timeline_urt", "instructions"),
        )

    def get_bookmarks_page(self, count: int, cursor: Optional[str]) -> dict:
        def get_instructions(data):
            i = _deep_get(data, "data", "bookmark_timeline", "timeline", "instructions")
            if i is None:
                i = _deep_get(data, "data", "bookmark_timeline_v2", "timeline", "instructions")
            return i
        return self._timeline_page("Bookmarks", count, cursor, get_instructions)

    def get_bookmark_folder_tweets_page(
        self, folder_id: str, count: int, cursor: Optional[str],
    ) -> dict:
        return self._timeline_page(
            "BookmarkFolderTimeline", count, cursor,
            lambda d: _deep_get(d, "data", "bookmark_collection_timeline", "timeline", "instructions"),
            extra_variables={"bookmark_collection_id": folder_id, "includePromotedContent": False},
            override_base=True,
        )

    def _user_likes_page_by_id(self, user_id: str, count: int, cursor: Optional[str]) -> dict:
        def get_instructions(data):
            i = _deep_get(data, "data", "user", "result", "timeline", "timeline", "instructions")
            if i is None:
                i = _deep_get(data, "data", "user", "result", "timeline_v2", "timeline", "instructions")
            return i
        return self._timeline_page(
            "Likes", count, cursor, get_instructions,
            extra_variables={
                "userId": user_id,
                "includePromotedContent": False,
                "withClientEventToken": False,
                "withBirdwatchNotes": False,
                "withVoice": True,
            },
            override_base=True,
        )

    def get_my_likes_page(self, count: int, cursor: Optional[str]) -> dict:
        me = self._client.fetch_me()
        return self._user_likes_page_by_id(me.id, count, cursor)

    def get_user_likes_page(
        self, screen_name: str, count: int, cursor: Optional[str],
    ) -> dict:
        profile = self._client.fetch_user(screen_name)
        return self._user_likes_page_by_id(profile.id, count, cursor)

    def get_user_posts_page(
        self, screen_name: str, count: int, cursor: Optional[str],
    ) -> dict:
        profile = self._client.fetch_user(screen_name)
        return self._timeline_page(
            "UserTweets", count, cursor,
            lambda d: _deep_get(d, "data", "user", "result", "timeline_v2", "timeline", "instructions"),
            extra_variables={
                "userId": profile.id,
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
                "withV2Timeline": True,
            },
        )

    def get_list_timeline_page(
        self, list_id: str, count: int, cursor: Optional[str],
    ) -> dict:
        return self._timeline_page(
            "ListLatestTweetsTimeline", count, cursor,
            lambda d: _deep_get(d, "data", "list", "tweets_timeline", "timeline", "instructions"),
            extra_variables={"listId": list_id},
            override_base=True,
        )

    def get_followers_page(
        self, screen_name: str, count: int, cursor: Optional[str],
    ) -> dict:
        profile = self._client.fetch_user(screen_name)
        return self._user_list_page(
            "Followers", profile.id, count, cursor,
            lambda d: _deep_get(d, "data", "user", "result", "timeline", "timeline", "instructions"),
        )

    def get_following_page(
        self, screen_name: str, count: int, cursor: Optional[str],
    ) -> dict:
        profile = self._client.fetch_user(screen_name)
        return self._user_list_page(
            "Following", profile.id, count, cursor,
            lambda d: _deep_get(d, "data", "user", "result", "timeline", "timeline", "instructions"),
        )

    def search_page(
        self, query: str, count: int, cursor: Optional[str], product: str = "Top",
    ) -> dict:
        return self._timeline_page(
            "SearchTimeline", count, cursor,
            lambda d: _deep_get(d, "data", "search_by_raw_query", "search_timeline", "timeline", "instructions"),
            extra_variables={"rawQuery": query, "querySource": "typed_query", "product": product},
            override_base=True,
        )
