# cassandra-twitter-mcp

Consolidated Twitter/X MCP server. Two layers in one service:

1. **Public research** — news search, Grok AI synthesis, post analytics, trending topics via the X API v2 + Grok
2. **Personal account** — the user's own timeline, bookmarks, DMs, profile via [twitter-cli](https://pypi.org/project/twitter-cli/) using synced browser cookies

Everything is read-only. Personal tools are gated behind the caller's own cookies (stored as per-user credentials in the auth service) — never shared across users.

## Tools

### Public (X API + Grok AI)

| Tool | Purpose |
|------|---------|
| `search_news` | Curated news articles with summaries — fastest path for "what's happening" questions |
| `search` | Grok AI synthesis with citations — use for sentiment and opinion synthesis |
| `get_post_counts` | Volume over time — how often something is being talked about |
| `get_tweet` / `get_thread` / `get_replies` | Individual tweet / thread / replies |
| `get_user_tweets` | Recent tweets from a specific account |
| `get_article` | Pull a linked article's text |

### Personal (user cookies)

| Tool | Purpose |
|------|---------|
| `my_feed` | Your home timeline |
| `my_bookmarks` / `list_bookmark_folders` | Your bookmarks |
| `my_profile` | Your profile |
| `personal_search` | Search against your logged-in X account |
| `personal_tweet_detail` / `personal_user_posts` / `personal_user_profile` | Authenticated reads for tweets and users |

## Architecture

```
MCP client → twitter-mcp.cassandrasedge.com (CF Tunnel)
  → FastMCP sidecar (port 3003)
    ├─ McpKeyAuthProvider → /keys/validate (auth service)
    ├─ X API v2 + Grok (public tools)
    └─ twitter-cli (personal tools)
          ↑ cookies pulled per-request from auth service
```

## Config

| Env Var | Required | Description |
|---------|----------|-------------|
| `X_API_BEARER_TOKEN` | Yes | X API v2 bearer token |
| `GROK_API_KEY` | Yes | Grok API key for synthesis tools |
| `AUTH_URL` / `AUTH_SECRET` | Yes | Auth service wiring |
| `MCP_PORT` | No | Bind port (default `3003`) |

Per-user Twitter cookies are stored in the auth service as the `twitter` service credential — populated by the user via the portal's browser-extension cookie sync flow.

## Dev

```bash
cd backend
uv sync
X_API_BEARER_TOKEN=... GROK_API_KEY=... uv run cassandra-twitter-mcp
```

## Deploy

Auto-deploys on push to main via Woodpecker CI → BuildKit → local registry → ArgoCD (`cassandra-k8s/apps/twitter-mcp/`).

Part of the [Cassandra](https://github.com/Cassandras-Edge) stack.
