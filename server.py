"""
Consolidated Twitter MCP Server

Merges Grok AI synthesis + X API v2 into a single server with 7 focused tools
for financial research: search, search_news, get_post_counts, get_user_tweets,
get_tweet, get_thread, get_replies.
"""

from config import load_settings
from clients import XClient, GrokClient
from tools import register_all
from fastmcp import FastMCP

settings = load_settings()

x_client = XClient(settings.x_bearer_token, settings.x_timeout)
grok_client = GrokClient(settings.xai_api_key, settings.grok_model)

mcp = FastMCP(
    "Twitter",
    instructions=(
        "Consolidated Twitter/X server for financial research. "
        "Use search for Grok AI synthesis (opinions, discourse, general research) "
        "or sentiment analysis (bull/bear split, mood). "
        "Use search_news for news headlines and articles. "
        "Use get_post_counts for volume analytics, get_user_tweets for monitoring accounts, "
        "get_tweet/get_thread/get_replies for individual post analysis. "
        "All tools are read-only and idempotent."
    ),
)

register_all(mcp, x_client, grok_client, settings.grok_system_prompt)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
