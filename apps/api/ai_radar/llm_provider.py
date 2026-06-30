from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx


@dataclass
class LLMResult:
    text: str
    response_id: str


class ResponsesLLMProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        provider: str = "relay",
        timeout_seconds: float = 240,
        max_retries: int = 0,
        client: Optional[httpx.Client] = None,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_retries = max(0, max_retries)
        self.client = client or httpx.Client(timeout=timeout_seconds)

    @classmethod
    def from_env(cls, storage_root: Optional[Path] = None) -> Optional["ResponsesLLMProvider"]:
        settings = {}
        if storage_root is not None:
            from .settings import load_llm_config

            settings = load_llm_config(storage_root)
        base_url = settings.get("base_url") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        api_key = settings.get("api_key") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = settings.get("model") or os.getenv("LLM_RESPONSES_MODEL") or os.getenv("OPENAI_RESPONSES_MODEL")
        if not base_url or not api_key or not model:
            return None
        timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "240"))
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            provider=settings.get("provider", "relay"),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def complete(self, instructions: str, input_text: str) -> LLMResult:
        last_error: httpx.HTTPError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post(
                    self._request_path(),
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=self._request_body(instructions, input_text),
                )
                break
            except (httpx.TimeoutException, httpx.TransportError) as error:
                last_error = error
                if attempt >= self.max_retries:
                    raise
        else:
            raise RuntimeError(f"LLM request failed: {last_error}")
        response.raise_for_status()
        payload = response.json()
        if self.provider == "deepseek":
            return LLMResult(text=extract_chat_completion_text(payload), response_id=payload.get("id", ""))
        return LLMResult(text=extract_response_text(payload), response_id=payload.get("id", ""))

    def _request_path(self) -> str:
        if self.provider == "deepseek":
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/responses"

    def _request_body(self, instructions: str, input_text: str) -> dict:
        if self.provider == "deepseek":
            return {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
                "response_format": {"type": "json_object"},
            }
        return {"model": self.model, "instructions": instructions, "input": input_text}


def extract_response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts = []
    for item in payload.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        elif isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def extract_chat_completion_text(payload: dict) -> str:
    for choice in payload.get("choices", []):
        message = choice.get("message", {})
        if isinstance(message.get("content"), str):
            return message["content"].strip()
    return ""
