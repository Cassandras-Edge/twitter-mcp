from __future__ import annotations

import json
from typing import Literal, Optional

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from clients.x_api import XClient
from clients.grok import GrokClient

SENTIMENT_SYSTEM_PROMPT = """You are a sentiment analyst. Analyze current X/Twitter discourse on the given topic.

First, determine the right polarity framing for this topic:
- Financial/stock topics → bullish vs bearish
- Monetary policy → dovish vs hawkish
- Political/policy topics → supportive vs opposed
- Product/company topics → positive vs negative
- General topics → for vs against

Return ONLY valid JSON with this exact structure:
{
  "summary": "2-3 sentence overall sentiment assessment",
  "positive_label": "bullish",
  "negative_label": "bearish",
  "lean": "positive_label value" | "negative_label value" | "mixed",
  "confidence": 0.0-1.0,
  "positive_keywords": ["word1", "word2", ...],
  "negative_keywords": ["word1", "word2", ...],
  "key_themes": ["theme1", "theme2", ...]
}

Rules for keywords:
- Exactly 12 keywords per side, max 2 words each
- First 5 should be high-frequency generic words for that polarity
  (e.g. for stocks: bullish, buy, calls, long, undervalued / bearish, sell, puts, short, overvalued)
  (e.g. for policy: support, approve, needed, beneficial, progress / oppose, reject, harmful, dangerous, overreach)
- Next 4 should be common action/reaction words people tweet with that sentiment
- Last 3 should be topic-specific words that people are actually using in tweets RIGHT NOW
- Every keyword must be a word someone would literally type in a tweet"""


def _parse_grok_json(text: str) -> dict:
    """Extract JSON from Grok response text."""
    # Strip markdown fences if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    # Find first complete top-level JSON object via brace matching
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        if depth == 0:
            return json.loads(text[start : i + 1])
    raise json.JSONDecodeError("Unclosed JSON object", text, start)


def _build_keyword_query(base_query: str, keywords: list[str]) -> str:
    """Build an OR query from keywords, quoting multi-word phrases."""
    parts = (f'"{k}"' if " " in k else k for k in keywords)
    return f'{base_query} ({" OR ".join(parts)})'


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
        mode: Literal["both", "grok", "news", "sentiment"] = "both",
        max_news_results: int = 10,
        max_age_hours: Optional[int] = None,
        allowed_handles: Optional[list[str]] = None,
        excluded_handles: Optional[list[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        enable_video_understanding: bool = False,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        sentiment_granularity: str = "day",
        sentiment_sample_size: int = 5,
    ) -> dict:
        """Search X/Twitter using Grok AI synthesis and/or curated news articles.

        Default mode runs both Grok (sentiment synthesis with citations) and
        X News API (curated news articles) and returns combined results.

        Sentiment mode is a multi-step process:
        1. Grok analyzes the topic and suggests context-specific bullish/bearish keywords
        2. Runs volume counts over time split by bullish vs bearish using those keywords
        3. Fetches sample tweets from each side for qualitative context

        Args:
            query: Search query (natural language for Grok, keywords for news).
            mode: 'both' (default) runs Grok + news, 'grok' for synthesis only,
                  'news' for curated articles only, 'sentiment' for keyword-driven
                  sentiment analysis with volume breakdown and sample tweets.
            max_news_results: Max news articles to return (1-100, default 10).
                Only used in news/both modes.
            max_age_hours: Max age of news results in hours (1-720).
                Only used in news/both modes.
            allowed_handles: Whitelist of X usernames to restrict Grok search to (max 10).
                Only used in grok/both/sentiment modes.
            excluded_handles: X usernames to exclude from Grok results (max 10).
                Only used in grok/both/sentiment modes.
            from_date: Only include posts on or after this date (ISO 8601, e.g. '2026-02-01').
                Only used in grok/both/sentiment modes.
            to_date: Only include posts on or before this date (ISO 8601).
                Only used in grok/both/sentiment modes.
            enable_video_understanding: Let Grok analyse video clips in posts.
                Only used in grok/both/sentiment modes.
            system_prompt: Custom system prompt for Grok response style.
                Only used in grok/both modes (sentiment mode uses its own prompt).
            temperature: Sampling temperature for Grok (0-2).
                Only used in grok/both/sentiment modes.
            sentiment_granularity: Time bucket for sentiment counts: 'minute', 'hour',
                or 'day' (default: day). Only used in sentiment mode.
            sentiment_sample_size: Number of sample tweets per side (1-20, default 5).
                Only used in sentiment mode.
        """
        if mode == "sentiment":
            return await _sentiment_search(
                query,
                granularity=sentiment_granularity,
                sample_size=sentiment_sample_size,
                allowed_handles=allowed_handles,
                excluded_handles=excluded_handles,
                from_date=from_date,
                to_date=to_date,
                enable_video_understanding=enable_video_understanding,
                temperature=temperature,
            )

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

    async def _sentiment_search(
        query: str,
        *,
        granularity: str = "day",
        sample_size: int = 5,
        allowed_handles: list[str] | None = None,
        excluded_handles: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        enable_video_understanding: bool = False,
        temperature: float | None = None,
    ) -> dict:
        """Multi-step sentiment analysis: Grok keywords → counts + sample tweets."""
        result: dict = {}

        # -- Step 1: Grok analysis + keyword generation --
        try:
            grok_raw = await grok_client.search(
                f"Analyze sentiment on {query}",
                allowed_handles=allowed_handles,
                excluded_handles=excluded_handles,
                from_date=from_date,
                to_date=to_date,
                enable_video_understanding=enable_video_understanding,
                system_prompt=SENTIMENT_SYSTEM_PROMPT,
                temperature=temperature or 0.3,
            )
            analysis = _parse_grok_json(grok_raw["text"])
            result["analysis"] = analysis
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                return {"error": "Grok analysis failed", "detail": x_client.handle_error(exc)}
            return {"error": "Grok analysis failed", "detail": x_client.handle_exception(exc)}
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            return {"error": "Failed to parse Grok JSON", "detail": str(exc), "raw": grok_raw}

        pos_label = analysis.get("positive_label", "positive")
        neg_label = analysis.get("negative_label", "negative")
        pos_kw = analysis.get("positive_keywords", [])
        neg_kw = analysis.get("negative_keywords", [])

        if not pos_kw or not neg_kw:
            return {"error": "Grok returned no keywords", "analysis": analysis}

        pos_q = _build_keyword_query(query, pos_kw)
        neg_q = _build_keyword_query(query, neg_kw)

        # -- Step 2: Volume counts (total, positive, negative) --
        try:
            total_data = await x_client.get(
                "/tweets/counts/recent", {"query": query, "granularity": granularity}
            )
            pos_data = await x_client.get(
                "/tweets/counts/recent", {"query": pos_q, "granularity": granularity}
            )
            neg_data = await x_client.get(
                "/tweets/counts/recent", {"query": neg_q, "granularity": granularity}
            )

            counts = []
            for t, p, n in zip(total_data["data"], pos_data["data"], neg_data["data"]):
                tv, pv, nv = t["tweet_count"], p["tweet_count"], n["tweet_count"]
                counts.append({
                    "start": t["start"],
                    "end": t["end"],
                    "total": tv,
                    pos_label: pv,
                    neg_label: nv,
                    f"{pos_label}_pct": round(pv / tv * 100, 1) if tv else 0,
                    f"{neg_label}_pct": round(nv / tv * 100, 1) if tv else 0,
                })

            tt = total_data["meta"]["total_tweet_count"]
            pt = pos_data["meta"]["total_tweet_count"]
            nt = neg_data["meta"]["total_tweet_count"]

            result["counts"] = {
                "labels": [pos_label, neg_label],
                "buckets": counts,
                "totals": {
                    "total": tt,
                    pos_label: pt,
                    neg_label: nt,
                    f"{pos_label}_pct": round(pt / tt * 100, 1) if tt else 0,
                    f"{neg_label}_pct": round(nt / tt * 100, 1) if tt else 0,
                },
            }
        except httpx.HTTPStatusError as exc:
            result["counts"] = x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            result["counts"] = x_client.handle_exception(exc)

        # -- Step 3: Sample tweets from each side --
        sample_size = max(1, min(sample_size, 20))
        try:
            pos_tweets = await x_client.get(
                "/tweets/search/recent",
                x_client.tweet_params({"query": pos_q, "max_results": max(sample_size, 10)}),
            )
            result[f"{pos_label}_sample"] = x_client.format_response(pos_tweets)
        except httpx.HTTPStatusError as exc:
            result[f"{pos_label}_sample"] = x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            result[f"{pos_label}_sample"] = x_client.handle_exception(exc)

        try:
            neg_tweets = await x_client.get(
                "/tweets/search/recent",
                x_client.tweet_params({"query": neg_q, "max_results": max(sample_size, 10)}),
            )
            result[f"{neg_label}_sample"] = x_client.format_response(neg_tweets)
        except httpx.HTTPStatusError as exc:
            result[f"{neg_label}_sample"] = x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            result[f"{neg_label}_sample"] = x_client.handle_exception(exc)

        result["keywords_used"] = {
            pos_label: pos_kw,
            neg_label: neg_kw,
        }

        return result
