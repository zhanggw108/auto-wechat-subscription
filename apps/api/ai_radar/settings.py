from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel


class ProviderConfigInput(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "1536x1024"
    quality: str = "high"
    output_format: str = "png"


class ProvidersSettingsInput(BaseModel):
    llm: ProviderConfigInput = ProviderConfigInput()
    image2: ProviderConfigInput = ProviderConfigInput()


class ProviderConfigPublic(BaseModel):
    base_url: str = ""
    model: str = ""
    configured: bool = False
    api_key_masked: str = ""
    size: str = "1536x1024"
    quality: str = "high"
    output_format: str = "png"


class ProvidersSettingsPublic(BaseModel):
    llm: ProviderConfigPublic
    image2: ProviderConfigPublic


class SettingsStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "settings.local.json"

    def load_private(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"llm": {}, "image2": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save_private(self, data: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def public(self) -> ProvidersSettingsPublic:
        private = self.load_private()
        return ProvidersSettingsPublic(
            llm=_public_config(private.get("llm", {}), include_image_fields=False),
            image2=_public_config(private.get("image2", {}), include_image_fields=True),
        )

    def update(self, incoming: ProvidersSettingsInput) -> ProvidersSettingsPublic:
        current = self.load_private()
        updated = {
            "llm": _merge_config(current.get("llm", {}), incoming.llm, include_image_fields=False),
            "image2": _merge_config(current.get("image2", {}), incoming.image2, include_image_fields=True),
        }
        self.save_private(updated)
        return self.public()


def _merge_config(existing: Dict[str, Any], incoming: ProviderConfigInput, include_image_fields: bool) -> Dict[str, str]:
    merged = {
        "base_url": incoming.base_url,
        "api_key": incoming.api_key or existing.get("api_key", ""),
        "model": incoming.model,
    }
    if include_image_fields:
        merged.update(
            {
                "size": incoming.size or existing.get("size", "1536x1024"),
                "quality": incoming.quality or existing.get("quality", "high"),
                "output_format": incoming.output_format or existing.get("output_format", "png"),
            }
        )
    return merged


def _public_config(config: Dict[str, Any], include_image_fields: bool) -> ProviderConfigPublic:
    public = ProviderConfigPublic(
        base_url=config.get("base_url", ""),
        model=config.get("model", ""),
        configured=bool(config.get("base_url") and config.get("api_key") and config.get("model")),
        api_key_masked=mask_key(config.get("api_key", "")),
    )
    if include_image_fields:
        public.size = config.get("size", "1536x1024")
        public.quality = config.get("quality", "high")
        public.output_format = config.get("output_format", "png")
    return public


def mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return value[0:2] + "..." + value[-2:]
    return value[0:3] + "..." + value[-4:]


def load_llm_config(root: Optional[Path]) -> Dict[str, str]:
    if root is None:
        return {}
    return SettingsStore(root).load_private().get("llm", {})


def load_image2_config(root: Optional[Path]) -> Dict[str, str]:
    if root is None:
        return {}
    return SettingsStore(root).load_private().get("image2", {})
