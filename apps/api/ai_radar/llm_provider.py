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
        timeout_seconds: float = 8,
        client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
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
        timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))
        return cls(base_url=base_url, api_key=api_key, model=model, timeout_seconds=timeout_seconds)

    def complete(self, instructions: str, input_text: str) -> LLMResult:
        response = self.client.post(
            f"{self.base_url}/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "instructions": instructions, "input": input_text},
        )
        response.raise_for_status()
        payload = response.json()
        return LLMResult(text=extract_response_text(payload), response_id=payload.get("id", ""))


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
