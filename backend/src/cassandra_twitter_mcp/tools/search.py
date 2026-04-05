from __future__ import annotations

import json
from typing import Literal, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentAccessToken
from fastmcp.server.auth import AccessToken
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from cassandra_twitter_mcp.clients.grok import GrokClient
from cassandra_twitter_mcp.clients.x_api import XClient
from cassandra_twitter_mcp.config import Settings
from cassandra_twitter_mcp.tools._helpers import (
    get_email, resolve_grok_client, resolve_x_client,
)

SENTIMENT_SYSTEM_PROMPT = """You are a sentiment analyst. Analyze current X/Twitter discourse on the given topic.

First, determine the right axes for this topic. Choose 2-4 axes that capture the
distinct camps in the conversation. Examples:
- Stock/crypto → bullish, bearish (2 axes)
- Monetary policy → dovish, hawkish, wait-and-see (3 axes)
- Election/debate → one axis per major candidate or position (2-4 axes)
- Product launch → excited, skeptical, disappointed (3 axes)
- Policy debate → supportive, opposed, cautious (3 axes)
- Simple for/against → for, against (2 axes)

Only add a 3rd or 4th axis if there is genuinely a distinct camp with its own
language. Don't force extra axes — 2 is fine for most topics.

Return ONLY valid JSON with this exact structure:
{
  "summary": "2-3 sentence overall sentiment assessment",
  "axes": [
    {
      "label": "bullish",
      "keywords": ["word1", "word2", ...]
    },
    {
      "label": "bearish",
      "keywords": ["word1", "word2", ...]
    }
  ],
  "lean": "label of the dominant axis or mixed",
  "confidence": 0.0-1.0,
  "key_themes": ["theme1", "theme2", ...]
}

Rules for keywords:
- Exactly 12 keywords per axis, max 2 words each
- First 5 should be high-frequency generic words for that axis
  (e.g. for bullish: bullish, buy, calls, long, undervalued)
  (e.g. for dovish: dovish, cut rates, easing, stimulus, accomodative)
- Next 4 should be common action/reaction words people tweet with that sentiment
- Last 3 should be topic-specific words that people are actually using in tweets RIGHT NOW
- Every keyword must be a word someone would literally type in a tweet"""


def _parse_grok_json(text: str) -> dict:
    """Extract JSON from Grok response text."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
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
    parts = (f'"{k}"' if " " in k else k for k in keywords)
    return f'{base_query} ({" OR ".join(parts)})'


async def _sentiment_search(
    query: str,
    x_client: XClient,
    grok_client: GrokClient,
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

    axes = analysis.get("axes", [])
    if len(axes) < 2:
        return {"error": "Grok returned fewer than 2 axes", "analysis": analysis}
    axes = axes[:4]

    axis_queries: list[tuple[str, list[str], str]] = []
    for axis in axes:
        label = axis.get("label", "unknown")
        kw = axis.get("keywords", [])
        if not kw:
            continue
        axis_queries.append((label, kw, _build_keyword_query(query, kw)))

    if len(axis_queries) < 2:
        return {"error": "Not enough axes with keywords", "analysis": analysis}

    try:
        total_data = await x_client.get(
            "/tweets/counts/recent", {"query": query, "granularity": granularity}
        )
        axis_counts_data = []
        for _, _, aq in axis_queries:
            data = await x_client.get(
                "/tweets/counts/recent", {"query": aq, "granularity": granularity}
            )
            axis_counts_data.append(data)

        buckets = []
        for i, t_bucket in enumerate(total_data["data"]):
            tv = t_bucket["tweet_count"]
            bucket: dict = {
                "start": t_bucket["start"],
                "end": t_bucket["end"],
                "total": tv,
            }
            for (label, _, _), ac_data in zip(axis_queries, axis_counts_data):
                av = ac_data["data"][i]["tweet_count"]
                bucket[label] = av
                bucket[f"{label}_pct"] = round(av / tv * 100, 1) if tv else 0
            buckets.append(bucket)

        tt = total_data["meta"]["total_tweet_count"]
        totals: dict = {"total": tt}
        for (label, _, _), ac_data in zip(axis_queries, axis_counts_data):
            at = ac_data["meta"]["total_tweet_count"]
            totals[label] = at
            totals[f"{label}_pct"] = round(at / tt * 100, 1) if tt else 0

        result["counts"] = {
            "labels": [label for label, _, _ in axis_queries],
            "buckets": buckets,
            "totals": totals,
        }
    except httpx.HTTPStatusError as exc:
        result["counts"] = x_client.handle_error(exc)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        result["counts"] = x_client.handle_exception(exc)

    sample_size = max(1, min(sample_size, 20))
    for label, _, aq in axis_queries:
        try:
            tweets = await x_client.get(
                "/tweets/search/recent",
                x_client.tweet_params({"query": aq, "max_results": max(sample_size, 10)}),
            )
            result[f"{label}_sample"] = x_client.format_response(tweets)
        except httpx.HTTPStatusError as exc:
            result[f"{label}_sample"] = x_client.handle_error(exc)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            result[f"{label}_sample"] = x_client.handle_exception(exc)

    result["keywords_used"] = {
        label: kw for label, kw, _ in axis_queries
    }

    return result


def register(mcp: FastMCP, settings: Settings) -> None:
    _ro = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
    default_system_prompt = settings.grok_system_prompt

    @mcp.tool(annotations=_ro)
    async def search(
        query: str,
        ctx: Context,
        mode: Literal["grok", "sentiment"] = "grok",
        allowed_handles: Optional[list[str]] = None,
        excluded_handles: Optional[list[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        enable_video_understanding: bool = False,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        sentiment_granularity: str = "day",
        sentiment_sample_size: int = 5,
        token: AccessToken = CurrentAccessToken(),
    ) -> dict:
        """Search X/Twitter using Grok AI synthesis. Uses more resources than search_news.

        Consider search_news first — it is faster and cheaper. Only use this tool
        when you need Grok AI capabilities: opinion synthesis, discourse analysis,
        or quantitative sentiment.

        Mode details:
        - 'grok' (default): Grok AI synthesis. Searches X posts and returns a
          summarized answer with source citations. Good for opinions, discourse,
          and what people think.
        - 'sentiment': Multi-step pipeline — Grok keyword generation → volume counts
          over time per axis → sample tweets. Use for quantitative sentiment analysis
          (bull/bear split, mood).

        Args:
            query: Search query (natural language).
            mode: 'grok' (default) or 'sentiment'.
            allowed_handles: Whitelist of X usernames to restrict Grok search to (max 10).
            excluded_handles: X usernames to exclude from Grok results (max 10).
            from_date: Only include posts on or after this date (ISO 8601, e.g. '2026-02-01').
            to_date: Only include posts on or before this date (ISO 8601).
            enable_video_understanding: Let Grok analyse video clips in posts.
            system_prompt: Custom system prompt for Grok response style.
                Only used in grok mode (sentiment mode uses its own prompt).
            temperature: Sampling temperature for Grok (0-2).
            sentiment_granularity: Time bucket for sentiment counts: 'minute', 'hour',
                or 'day' (default: day). Only used in sentiment mode.
            sentiment_sample_size: Number of sample tweets per side (1-20, default 5).
                Only used in sentiment mode.
        """
        x_client = resolve_x_client(ctx)
        grok_client = resolve_grok_client(ctx)

        if mode == "sentiment":
            return await _sentiment_search(
                query,
                x_client,
                grok_client,
                granularity=sentiment_granularity,
                sample_size=sentiment_sample_size,
                allowed_handles=allowed_handles,
                excluded_handles=excluded_handles,
                from_date=from_date,
                to_date=to_date,
                enable_video_understanding=enable_video_understanding,
                temperature=temperature,
            )

        # -- Grok synthesis --
        try:
            return {
                "grok": await grok_client.search(
                    query,
                    allowed_handles=allowed_handles,
                    excluded_handles=excluded_handles,
                    from_date=from_date,
                    to_date=to_date,
                    enable_video_understanding=enable_video_understanding,
                    system_prompt=system_prompt or default_system_prompt,
                    temperature=temperature,
                )
            }
        except httpx.HTTPStatusError as exc:
            return {"grok": x_client.handle_error(exc)}
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            return {"grok": x_client.handle_exception(exc)}
