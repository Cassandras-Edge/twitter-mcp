from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


DEFAULT_SYSTEM_PROMPT = (
    "Prioritize breadth over depth. Surface as many distinct viewpoints, "
    "voices, and sources as possible rather than deeply analysing a few. "
    "Keep each point concise so you can cover more ground."
)


@dataclass(slots=True)
class Settings:
    x_bearer_token: str
    xai_api_key: str
    x_timeout: int = 30
    grok_model: str = "grok-4-1-fast-non-reasoning"
    grok_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    twitter_auth_token: str = ""
    twitter_ct0: str = ""

    @property
    def has_personal(self) -> bool:
        return bool(self.twitter_auth_token and self.twitter_ct0)


def load_settings() -> Settings:
    load_dotenv()

    x_bearer_token = os.getenv("X_BEARER_TOKEN", "").strip()
    if not x_bearer_token:
        raise RuntimeError(
            "X_BEARER_TOKEN is required. "
            "Get yours at https://developer.x.com/en/portal/dashboard"
        )

    xai_api_key = os.getenv("XAI_API_KEY", "").strip()
    if not xai_api_key:
        raise RuntimeError(
            "XAI_API_KEY is required. "
            "Get yours at https://console.x.ai"
        )

    raw_timeout = os.getenv("X_TIMEOUT")
    x_timeout = int(raw_timeout) if raw_timeout else 30

    grok_model = os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning")

    twitter_auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
    twitter_ct0 = os.getenv("TWITTER_CT0", "").strip()

    return Settings(
        x_bearer_token=x_bearer_token,
        xai_api_key=xai_api_key,
        x_timeout=x_timeout,
        grok_model=grok_model,
        twitter_auth_token=twitter_auth_token,
        twitter_ct0=twitter_ct0,
    )
