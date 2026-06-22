from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx


@dataclass
class ImageResult:
    path: Path
    revised_prompt: str
    provider_request_id: str
    provider: str = "image2"


class Image2Provider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        size: str = "1536x1024",
        quality: str = "high",
        output_format: str = "png",
        timeout_seconds: float = 4,
        connect_timeout_seconds: float = 2,
        client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.size = size
        self.quality = quality
        self.output_format = output_format
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds))

    @classmethod
    def from_env(cls, storage_root: Optional[Path] = None) -> Optional["Image2Provider"]:
        settings = {}
        if storage_root is not None:
            from .settings import load_image2_config

            settings = load_image2_config(storage_root)
        if os.getenv("IMAGE_PROVIDER", "image2") != "image2":
            return None
        base_url = settings.get("base_url") or os.getenv("IMAGE2_BASE_URL")
        api_key = settings.get("api_key") or os.getenv("IMAGE2_API_KEY")
        model = settings.get("model") or os.getenv("IMAGE2_RESPONSES_MODEL")
        if not base_url or not api_key or not model:
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            size=settings.get("size") or os.getenv("IMAGE2_SIZE", "1536x1024"),
            quality=settings.get("quality") or os.getenv("IMAGE2_QUALITY", "high"),
            output_format=settings.get("output_format") or os.getenv("IMAGE2_OUTPUT_FORMAT", "png"),
            timeout_seconds=float(settings.get("timeout_seconds") or os.getenv("IMAGE2_TIMEOUT_SECONDS", "90")),
            connect_timeout_seconds=float(settings.get("connect_timeout_seconds") or os.getenv("IMAGE2_CONNECT_TIMEOUT_SECONDS", "10")),
        )

    def generate(self, prompt: str, output_path: Path) -> ImageResult:
        response = self.client.post(
            f"{self.base_url}/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "input": prompt,
                "tools": [
                    {
                        "type": "image_generation",
                        "size": self.size,
                        "quality": self.quality,
                        "format": self.output_format,
                    }
                ],
                "tool_choice": {"type": "image_generation"},
            },
        )
        response.raise_for_status()
        payload = response.json()
        output = next(item for item in payload.get("output", []) if item.get("type") == "image_generation_call")
        image_bytes = base64.b64decode(output["result"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        return ImageResult(
            path=output_path,
            revised_prompt=output.get("revised_prompt", ""),
            provider_request_id=payload.get("id", ""),
        )
