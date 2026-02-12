"""
Consolidated Twitter MCP Server

Merges Grok AI synthesis + X API v2 into a single server with 6 focused tools
for financial research: search, get_post_counts, get_user_tweets, get_tweet,
get_thread, get_replies.
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
        "Use search (default mode: both) for Grok sentiment synthesis + curated news, "
        "get_post_counts for volume analytics, get_user_tweets for monitoring accounts, "
        "get_tweet/get_thread/get_replies for individual post analysis. "
        "All tools are read-only and idempotent.\n\n"
        "MODE SELECTION for search tool:\n"
        "- User wants NEWS / headlines / articles → mode='news'\n"
        "- User wants opinions / discourse / what people think → mode='grok'\n"
        "- User wants sentiment / bull-bear split / mood → mode='sentiment'\n"
        "- General research → mode='both' (default)"
    ),
)

register_all(mcp, x_client, grok_client, settings.grok_system_prompt)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
