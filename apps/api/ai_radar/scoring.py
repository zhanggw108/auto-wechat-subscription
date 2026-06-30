from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class InfluenceConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class InfluenceEntry:
    name: str
    aliases: list[str]
    weight: int


@dataclass(frozen=True)
class SourceDomainEntry:
    domain: str
    weight: int


@dataclass(frozen=True)
class InfluenceConfig:
    institutions: list[InfluenceEntry]
    people: list[InfluenceEntry]
    source_domains: list[SourceDomainEntry]


def default_influence_config_path() -> Path:
    return Path(__file__).with_name("influence_sources.json")


def load_influence_config(path: Path | None = None) -> InfluenceConfig:
    config_path = path or default_influence_config_path()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InfluenceConfigError(f"Failed to load JSON influence config at {config_path}: {error}") from error

    try:
        if not isinstance(data, dict):
            raise ValueError("顶层必须是对象")

        institutions = data["institutions"]
        people = data["people"]
        source_domains = data["source_domains"]
        if not all(isinstance(items, list) for items in (institutions, people, source_domains)):
            raise ValueError("institutions/people/source_domains 必须是 list")

        return InfluenceConfig(
            institutions=[
                InfluenceEntry(
                    name=str(item["name"]),
                    aliases=[str(alias).strip().lower() for alias in _require_aliases(item)],
                    weight=int(item["weight"]),
                )
                for item in institutions
            ],
            people=[
                InfluenceEntry(
                    name=str(item["name"]),
                    aliases=[str(alias).strip().lower() for alias in _require_aliases(item)],
                    weight=int(item["weight"]),
                )
                for item in people
            ],
            source_domains=[
                SourceDomainEntry(
                    domain=str(item["domain"]).strip().lower(),
                    weight=int(item["weight"]),
                )
                for item in source_domains
            ],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InfluenceConfigError(f"配置结构或字段错误 at {config_path}: {error}") from error


def _require_aliases(item: object) -> list[object]:
    aliases = item["aliases"]  # type: ignore[index]
    if not isinstance(aliases, list):
        raise ValueError("aliases 必须是 list")
    return aliases
