from __future__ import annotations

import re
import time

import httpx


class XClient:
    """Async client for X API v2. All tools call through this."""

    BASE_URL = "https://api.x.com/2"

    TWEET_FIELDS = (
        "author_id,created_at,public_metrics,conversation_id,"
        "referenced_tweets,entities,lang,note_tweet,reply_settings,attachments"
    )
    USER_FIELDS = (
        "id,name,username,profile_image_url,verified,verified_type,"
        "description,public_metrics,created_at,location,url"
    )
    MEDIA_FIELDS = (
        "media_key,type,url,preview_image_url,width,height,alt_text,"
        "duration_ms,variants"
    )
    EXPANSIONS = (
        "author_id,referenced_tweets.id,referenced_tweets.id.author_id,"
        "attachments.media_keys"
    )
    NEWS_FIELDS = (
        "category,cluster_posts_results,contexts,disclaimer,"
        "hook,id,keywords,name,summary,updated_at"
    )

    def __init__(self, bearer_token: str, timeout: int = 30) -> None:
        self._bearer_token = bearer_token
        self._timeout = timeout
        self._user_id_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Low-level
    # ------------------------------------------------------------------

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self._bearer_token}"},
            timeout=self._timeout,
        ) as client:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Param builders
    # ------------------------------------------------------------------

    def tweet_params(self, extra: dict | None = None) -> dict:
        params: dict = {
            "tweet.fields": self.TWEET_FIELDS,
            "user.fields": self.USER_FIELDS,
            "media.fields": self.MEDIA_FIELDS,
            "expansions": self.EXPANSIONS,
        }
        if extra:
            params.update(extra)
        return params

    def user_params(self, extra: dict | None = None) -> dict:
        params: dict = {"user.fields": self.USER_FIELDS}
        if extra:
            params.update(extra)
        return params

    def news_params(self, extra: dict | None = None) -> dict:
        params: dict = {"news.fields": self.NEWS_FIELDS}
        if extra:
            params.update(extra)
        return params

    # ------------------------------------------------------------------
    # Response formatting
    # ------------------------------------------------------------------

    def build_users_map(self, includes: dict | None) -> dict:
        if not includes:
            return {}
        return {u["id"]: u for u in includes.get("users", [])}

    def build_media_map(self, includes: dict | None) -> dict:
        if not includes:
            return {}
        return {
            m["media_key"]: m
            for m in includes.get("media", [])
            if m.get("media_key")
        }

    def format_media(self, media: dict) -> dict:
        result: dict = {
            "media_key": media.get("media_key"),
            "type": media.get("type"),
        }
        if url := media.get("url"):
            result["url"] = url
        if preview := media.get("preview_image_url"):
            result["preview_url"] = preview
        if width := media.get("width"):
            result["width"] = width
        if height := media.get("height"):
            result["height"] = height
        if alt_text := media.get("alt_text"):
            result["alt_text"] = alt_text
        if duration_ms := media.get("duration_ms"):
            result["duration_ms"] = duration_ms
        if variants := media.get("variants"):
            filtered = []
            for variant in variants:
                if not variant.get("url"):
                    continue
                filtered.append({
                    "url": variant.get("url"),
                    "content_type": variant.get("content_type"),
                    "bit_rate": variant.get("bit_rate"),
                })
            if filtered:
                result["variants"] = filtered
        return result

    def format_tweet(self, tweet: dict, users_map: dict, media_map: dict) -> dict:
        author = users_map.get(tweet.get("author_id"), {})
        result: dict = {
            "id": tweet.get("id"),
            "text": tweet.get("text"),
            "created_at": tweet.get("created_at"),
            "conversation_id": tweet.get("conversation_id"),
            "author": {
                "id": author.get("id"),
                "name": author.get("name"),
                "username": author.get("username"),
                "verified": author.get("verified"),
            } if author else {"id": tweet.get("author_id")},
            "metrics": tweet.get("public_metrics"),
        }
        # Include long-form text if present
        note = tweet.get("note_tweet")
        if note and note.get("text"):
            result["text"] = note["text"]
        # Referenced tweets (replies, quotes, retweets)
        if refs := tweet.get("referenced_tweets"):
            result["referenced_tweets"] = refs
            reply_to = next(
                (r.get("id") for r in refs if r.get("type") == "replied_to"),
                None,
            )
            if reply_to:
                result["reply_to_tweet_id"] = reply_to
        # Media attachments (images, video, GIF)
        media_keys = tweet.get("attachments", {}).get("media_keys", [])
        if media_keys:
            media = []
            for media_key in media_keys:
                if m := media_map.get(media_key):
                    media.append(self.format_media(m))
                else:
                    media.append({"media_key": media_key})
            result["media"] = media
        # Entities (URLs, hashtags, mentions, cashtags)
        if entities := tweet.get("entities"):
            urls = entities.get("urls")
            if urls:
                result["urls"] = [
                    {"url": u.get("expanded_url"), "title": u.get("title")}
                    for u in urls
                    if u.get("expanded_url")
                ]
            hashtags = entities.get("hashtags")
            if hashtags:
                result["hashtags"] = [h["tag"] for h in hashtags]
            cashtags = entities.get("cashtags")
            if cashtags:
                result["cashtags"] = [c["tag"] for c in cashtags]
        return result

    def format_response(self, data: dict) -> dict:
        """Flatten a standard v2 response (data + includes + meta) into a clean structure."""
        includes = data.get("includes")
        users_map = self.build_users_map(includes)
        media_map = self.build_media_map(includes)

        raw = data.get("data")
        if raw is None:
            return {"tweets": [], "meta": data.get("meta", {})}

        if isinstance(raw, list):
            tweets = [self.format_tweet(t, users_map, media_map) for t in raw]
        else:
            tweets = [self.format_tweet(raw, users_map, media_map)]

        result: dict = {"tweets": tweets}
        if meta := data.get("meta"):
            result["meta"] = meta
        return result

    def format_news(self, news: dict) -> dict:
        """Format a single news object into a clean structure."""
        result: dict = {
            "id": news.get("id"),
            "name": news.get("name"),
            "summary": news.get("summary"),
            "category": news.get("category"),
            "hook": news.get("hook"),
            "updated_at": news.get("updated_at"),
        }
        if keywords := news.get("keywords"):
            result["keywords"] = keywords
        if contexts := news.get("contexts"):
            result["contexts"] = contexts
        if cluster_posts := news.get("cluster_posts_results"):
            result["related_posts"] = cluster_posts
        if disclaimer := news.get("disclaimer"):
            result["disclaimer"] = disclaimer
        return result

    def format_news_response(self, data: dict) -> dict:
        """Format a news search/lookup response."""
        raw = data.get("data")
        if raw is None:
            return {"news": [], "meta": data.get("meta", {})}
        if isinstance(raw, list):
            news = [self.format_news(n) for n in raw]
        else:
            news = [self.format_news(raw)]
        result: dict = {"news": news}
        if meta := data.get("meta"):
            result["meta"] = meta
        return result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    _URL_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/.+/status/(\d+)")

    def extract_tweet_id(self, input_val: str) -> str:
        """Extract tweet ID from a URL or return the raw ID."""
        match = self._URL_PATTERN.search(input_val)
        if match:
            return match.group(1)
        return input_val.strip()

    async def resolve_user_id(self, username: str) -> str:
        """Resolve a username to a user ID, with caching."""
        username = username.lstrip("@").lower()
        if username in self._user_id_cache:
            return self._user_id_cache[username]
        data = await self.get(f"/users/by/username/{username}", self.user_params())
        user = data.get("data")
        if not user:
            raise ValueError(f"User @{username} not found")
        self._user_id_cache[username] = user["id"]
        return user["id"]

    def handle_error(self, exc: httpx.HTTPStatusError) -> dict:
        """Build a consistent error dict from an HTTP error."""
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text
        result: dict = {
            "error": True,
            "status": exc.response.status_code,
            "detail": body,
        }
        if exc.response.status_code == 429:
            reset = exc.response.headers.get("x-rate-limit-reset")
            if reset:
                try:
                    reset_ts = int(reset)
                    wait_seconds = max(0, reset_ts - int(time.time()))
                    result["rate_limit_reset"] = reset_ts
                    result["retry_after_seconds"] = wait_seconds
                except ValueError:
                    pass
        return result

    def handle_exception(self, exc: Exception) -> dict:
        """Handle non-HTTP exceptions (network errors, timeouts)."""
        if isinstance(exc, httpx.ConnectError):
            return {"error": True, "status": 0, "detail": f"Connection failed: {exc}"}
        if isinstance(exc, httpx.TimeoutException):
            return {"error": True, "status": 0, "detail": f"Request timed out: {exc}"}
        return {"error": True, "status": 0, "detail": str(exc)}
