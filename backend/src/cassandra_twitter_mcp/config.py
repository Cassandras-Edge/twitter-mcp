"""Settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_SYSTEM_PROMPT = (
    "Prioritize breadth over depth. Surface as many distinct viewpoints, "
    "voices, and sources as possible rather than deeply analysing a few. "
    "Keep each point concise so you can cover more ground."
)


@dataclass(slots=True)
class Settings:
    # Global API keys (deployment-level, not per-user)
    x_bearer_token: str
    xai_api_key: str
    x_timeout: int = 30
    grok_model: str = "grok-4-1-fast-non-reasoning"
    grok_system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # Per-user Twitter cookies (for local dev only — in prod these come from ACL credentials)
    twitter_auth_token: str = ""
    twitter_ct0: str = ""

    # Auth (ACL service)
    auth_url: str = ""
    auth_secret: str = ""
    auth_yaml_path: str = "/app/acl.yaml"

    # Server
    host: str = "0.0.0.0"
    mcp_port: int = 3003

    @property
    def has_personal_env(self) -> bool:
        """Whether Twitter cookies are set via env vars (local dev mode)."""
        return bool(self.twitter_auth_token and self.twitter_ct0)


def load_settings() -> Settings:
    x_bearer_token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not x_bearer_token:
        raise RuntimeError(
            "X_BEARER_TOKEN is required. "
            "Get yours at https://developer.x.com/en/portal/dashboard"
        )

    xai_api_key = os.environ.get("XAI_API_KEY", "").strip()
    if not xai_api_key:
        raise RuntimeError(
            "XAI_API_KEY is required. "
            "Get yours at https://console.x.ai"
        )

    raw_timeout = os.environ.get("X_TIMEOUT")
    x_timeout = int(raw_timeout) if raw_timeout else 30

    return Settings(
        x_bearer_token=x_bearer_token,
        xai_api_key=xai_api_key,
        x_timeout=x_timeout,
        grok_model=os.environ.get("GROK_MODEL", "grok-4-1-fast-non-reasoning"),
        twitter_auth_token=os.environ.get("TWITTER_AUTH_TOKEN", "").strip(),
        twitter_ct0=os.environ.get("TWITTER_CT0", "").strip(),
        auth_url=os.environ.get("AUTH_URL", ""),
        auth_secret=os.environ.get("AUTH_SECRET", ""),
        auth_yaml_path=os.environ.get("AUTH_YAML_PATH", "/app/acl.yaml"),
        host=os.environ.get("HOST", "0.0.0.0"),
        mcp_port=int(os.environ.get("MCP_PORT", "3003")),
    )
