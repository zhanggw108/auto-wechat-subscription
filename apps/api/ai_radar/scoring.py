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

    return InfluenceConfig(
        institutions=[
            InfluenceEntry(
                name=str(item["name"]),
                aliases=[str(alias).lower() for alias in item.get("aliases", [])],
                weight=int(item.get("weight", 0)),
            )
            for item in data.get("institutions", [])
        ],
        people=[
            InfluenceEntry(
                name=str(item["name"]),
                aliases=[str(alias).lower() for alias in item.get("aliases", [])],
                weight=int(item.get("weight", 0)),
            )
            for item in data.get("people", [])
        ],
        source_domains=[
            SourceDomainEntry(
                domain=str(item["domain"]).lower(),
                weight=int(item.get("weight", 0)),
            )
            for item in data.get("source_domains", [])
        ],
    )
