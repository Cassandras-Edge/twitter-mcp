"""
Consolidated Twitter MCP Server

Three backends unified in one server:
- X API v2 (bearer token): search_news, get_post_counts, get_user_tweets, get_tweet, get_thread, get_replies
- Grok AI (xAI key): search (synthesis + sentiment)
- twitter-cli (browser cookies): my_feed, my_bookmarks, get_article, my_profile, personal_search
"""

import logging

from config import load_settings
from clients import XClient, GrokClient, PersonalClient
from tools import register_all
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

settings = load_settings()

x_client = XClient(settings.x_bearer_token, settings.x_timeout)
grok_client = GrokClient(settings.xai_api_key, settings.grok_model)

personal_client = None
if settings.has_personal:
    try:
        personal_client = PersonalClient(settings.twitter_auth_token, settings.twitter_ct0)
        logger.info("Personal account tools enabled (twitter-cli)")
    except Exception as exc:
        logger.warning("Personal account tools disabled: %s", exc)

mcp = FastMCP(
    "Twitter",
    instructions=(
        "Consolidated Twitter/X server for financial research and personal account access. "
        "PREFER search_news as the default starting point — it is fast, cheap, "
        "and returns curated news articles with headlines and summaries. "
        "Only escalate to search (Grok AI) when you specifically need opinion "
        "synthesis, discourse analysis, or quantitative sentiment. "
        "Use get_post_counts for volume analytics, get_user_tweets for monitoring accounts, "
        "get_tweet/get_thread/get_replies for individual post analysis. "
        "Use my_feed for the user's personal Twitter timeline, my_bookmarks for saved tweets, "
        "and get_article for Twitter Articles (long-form content). "
        "All tools are read-only and idempotent."
    ),
)

register_all(mcp, x_client, grok_client, settings.grok_system_prompt, personal_client)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
