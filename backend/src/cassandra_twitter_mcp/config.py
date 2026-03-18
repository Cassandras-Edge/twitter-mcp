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
    # All API keys are per-user (from ACL credentials), not deployment-level.
    # These settings are for server config only.

    grok_system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # Auth (ACL service)
    auth_url: str = ""
    auth_secret: str = ""
    auth_yaml_path: str = "/app/acl.yaml"

    # Server
    host: str = "0.0.0.0"
    mcp_port: int = 3003


def load_settings() -> Settings:
    return Settings(
        grok_system_prompt=os.environ.get("GROK_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        auth_url=os.environ.get("AUTH_URL", ""),
        auth_secret=os.environ.get("AUTH_SECRET", ""),
        auth_yaml_path=os.environ.get("AUTH_YAML_PATH", "/app/acl.yaml"),
        host=os.environ.get("HOST", "0.0.0.0"),
        mcp_port=int(os.environ.get("MCP_PORT", "3003")),
    )
