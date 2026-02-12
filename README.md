# Twitter MCP Server

Consolidated Twitter/X MCP server for financial research. Merges **Grok AI synthesis** (xAI Responses API) and **X API v2** into a single server with 6 tools.

## Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `search` | Grok + API | Sentiment synthesis + curated news (4 modes) |
| `get_post_counts` | API v2 | Buzz quantification over time |
| `get_user_tweets` | API v2 | Monitor trusted accounts |
| `get_tweet` | API v2 | Single tweet lookup with full metadata |
| `get_thread` | API v2 | Expand multi-tweet threads |
| `get_replies` | API v2 | Sentiment sampling on high-engagement posts |

## Search Modes

The `search` tool supports 4 modes via the `mode` parameter:

### `both` (default)
Runs Grok synthesis + X News API in sequence. Returns qualitative analysis with citations and curated news articles.

### `grok`
Grok-only synthesis. xAI searches X autonomously, analyzes posts, and returns a summarized answer with deduplicated source links.

### `news`
X News API only. Returns curated news articles matching the query.

### `sentiment`
Multi-step sentiment analysis pipeline:

```
┌─────────────────────────────────────────────────┐
│  Step 1: Grok Analysis                          │
│  Grok searches X, reads current discourse,      │
│  and returns structured JSON:                   │
│  - Summary + confidence score                   │
│  - 2-4 sentiment axes with labels               │
│  - 12 keywords per axis (3 tiers)               │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  Step 2: Volume Counts                          │
│  Runs X API /tweets/counts/recent for:          │
│  - Total volume (base query)                    │
│  - Per-axis volume (query + axis keywords)      │
│  Returns time-bucketed breakdown with %          │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  Step 3: Sample Tweets                          │
│  Fetches actual tweets matching each axis's     │
│  keywords for qualitative context.              │
└─────────────────────────────────────────────────┘
```

**Dynamic axes** — Grok determines the right framing for each topic:
- Stocks → `bullish`, `bearish`
- Fed policy → `dovish`, `hawkish`, `wait-and-see`
- Policy debates → `supportive`, `opposed`, `cautious`
- Product launches → `excited`, `skeptical`, `disappointed`

**Keyword tiers** (12 per axis):
1. **Anchors (5):** High-frequency generic words (e.g. `bullish, buy, calls, long, undervalued`)
2. **Action words (4):** Common fintwit reaction words (e.g. `rally, breakout, moon, accumulate`)
3. **Topic-specific (3):** Words Grok sees in current tweets (e.g. `Blackwell, Jensen, AI demand`)

## Setup

```bash
# Install
uv sync

# Configure
cp .env.example .env
# Edit .env with your tokens
```

### Environment Variables

| Variable | Required | Default | Source |
|----------|----------|---------|--------|
| `X_BEARER_TOKEN` | Yes | — | [developer.x.com](https://developer.x.com/en/portal/dashboard) |
| `XAI_API_KEY` | Yes | — | [console.x.ai](https://console.x.ai) |
| `X_TIMEOUT` | No | 30 | — |
| `GROK_MODEL` | No | `grok-4-1-fast-non-reasoning` | — |

## Claude Code MCP Config

```json
{
  "mcpServers": {
    "twitter": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/twitter-mcp", "python", "server.py"]
    }
  }
}
```

## Architecture

```
twitter-mcp/
├── server.py              # Entry point: load config, init clients, register tools
├── config.py              # Settings dataclass (both tokens)
├── clients/
│   ├── x_api.py           # Async X API v2 client
│   └── grok.py            # Async xAI Responses API client
└── tools/
    ├── search.py           # Merged search (4 modes: both, grok, news, sentiment)
    ├── posts.py            # get_tweet, get_thread, get_replies
    └── analytics.py        # get_post_counts, get_user_tweets
```

Both clients are fully async (`httpx.AsyncClient`), creating a new connection per request. All tools are annotated as read-only and idempotent.
