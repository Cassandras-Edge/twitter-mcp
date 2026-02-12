from __future__ import annotations

import httpx


class GrokClient:
    """Async client for xAI Responses API with X search."""

    BASE_URL = "https://api.x.ai/v1"

    def __init__(self, api_key: str, model: str = "grok-4-1-fast-non-reasoning") -> None:
        self._api_key = api_key
        self._model = model

    async def search(
        self,
        query: str,
        *,
        allowed_handles: list[str] | None = None,
        excluded_handles: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        enable_video_understanding: bool = False,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Run an X search via Grok and return synthesis with sources."""
        tool_config: dict = {
            "type": "x_search",
            "enable_image_understanding": True,
        }
        if allowed_handles:
            tool_config["allowed_x_handles"] = allowed_handles[:10]
        if excluded_handles:
            tool_config["excluded_x_handles"] = excluded_handles[:10]
        if from_date:
            tool_config["from_date"] = from_date
        if to_date:
            tool_config["to_date"] = to_date
        if enable_video_understanding:
            tool_config["enable_video_understanding"] = True

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        payload: dict = {
            "model": self._model,
            "input": messages,
            "tools": [tool_config],
        }
        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.BASE_URL}/responses",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return self._extract_response(resp.json())

    @staticmethod
    def _extract_response(raw: dict) -> dict:
        """Parse output blocks and url_citation annotations into text + sources."""
        text_parts: list[str] = []
        seen_urls: set[str] = set()
        citations: list[dict] = []

        for item in raw.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        text_parts.append(block.get("text", ""))
                        for ann in block.get("annotations", []):
                            if ann.get("type") == "url_citation":
                                url = ann.get("url", "")
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    citations.append({
                                        "title": ann.get("title", ""),
                                        "url": url,
                                    })

        text = "\n".join(text_parts).strip()

        if citations:
            sources = "\n".join(
                f"- [{c['title'] or c['url']}]({c['url']})" for c in citations
            )
            text = f"{text}\n\nSources:\n{sources}"

        return {"text": text, "sources": citations}
