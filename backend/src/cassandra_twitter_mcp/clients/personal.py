"""Wrapper around twitter-cli's TwitterClient for personal account access.

Uses reverse-engineered X/Twitter GraphQL APIs with browser cookies.
Auth: TWITTER_AUTH_TOKEN + TWITTER_CT0 env vars.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

logger = logging.getLogger(__name__)


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
