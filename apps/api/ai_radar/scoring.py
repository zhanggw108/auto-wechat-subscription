from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping
from urllib.parse import urlparse

from .models import Paper, Signal


AI_KEYWORDS = (
    "llm",
    "language model",
    "multimodal",
    "agent",
    "reasoning",
    "training",
    "inference",
    "safety",
    "coding",
    "robot",
    "evaluation",
    "benchmark",
    "ai4science",
    "diffusion",
    "alignment",
    "interpretability",
    "模型",
    "智能体",
    "评测",
)

METHOD_KEYWORDS = (
    "framework",
    "architecture",
    "training",
    "distillation",
    "optimization",
    "regularization",
    "benchmark",
    "dataset",
    "theory",
    "simulation",
    "evaluation",
    "pipeline",
    "system",
)

EXPERIMENT_KEYWORDS = (
    "evaluation",
    "benchmark",
    "ablation",
    "comparison",
    "human study",
    "real-world",
    "large-scale",
    "sota",
    "empirical",
    "user study",
)


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


@dataclass(frozen=True)
class PaperScore:
    paper: Paper
    total_score: int
    score_detail: Dict[str, Dict[str, object]]
    selection_reasons: List[str]
    matched_institutions: List[str]
    matched_people: List[str]
    matched_source_domains: List[str]
    matched_signals: List[str]

    def to_report_dict(self, rank: int, selected: bool) -> Dict[str, object]:
        return {
            "rank": rank,
            "selected": selected,
            "paper_id": self.paper.id,
            "arxiv_id": self.paper.arxiv_id,
            "title": self.paper.title,
            "total_score": self.total_score,
            "score_detail": self.score_detail,
            "selection_reasons": self.selection_reasons,
            "matched_institutions": self.matched_institutions,
            "matched_people": self.matched_people,
            "matched_source_domains": self.matched_source_domains,
            "matched_signals": self.matched_signals,
            "pdf_url": self.paper.pdf_url,
        }


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


def score_papers(
    papers: List[Paper],
    signals: List[Signal],
    previous_items: List[Mapping[str, object]],
    config_path: Path | None = None,
    run_date: str | None = None,
) -> List[PaperScore]:
    config = load_influence_config(config_path)
    freshness_date = run_date or _latest_published_date(papers, signals)
    scores = [
        _score_one_paper(paper, signals, previous_items, config, freshness_date)
        for paper in papers
        if paper.pdf_url or paper.arxiv_id
    ]
    return sorted(
        scores,
        key=lambda item: (
            -item.total_score,
            -int(item.score_detail["influence_score"]["value"]),
            -int(item.score_detail["experiment_strength"]["value"]),
            -_timestamp(item.paper.published_at),
            item.paper.title.lower(),
        ),
    )


def _score_one_paper(
    paper: Paper,
    signals: List[Signal],
    previous_items: List[Mapping[str, object]],
    config: InfluenceConfig,
    freshness_date: str,
) -> PaperScore:
    text = " ".join([paper.title, paper.abstract, " ".join(paper.categories), " ".join(paper.authors)]).lower()
    related_signals = _matched_signals(paper, signals)
    signal_text = " ".join([signal.title + " " + signal.summary + " " + signal.url for signal in related_signals]).lower()
    combined = f"{text} {signal_text}"

    relevance_hits = _count_hits(combined, AI_KEYWORDS)
    method_hits = _count_hits(combined, METHOD_KEYWORDS)
    experiment_hits = _count_hits(combined, EXPERIMENT_KEYWORDS)
    matched_institutions, institution_score = _match_entries(combined, config.institutions)
    matched_people, people_score = _match_entries(combined, config.people)
    matched_domains, domain_score = _match_domains(related_signals, config.source_domains)
    history_penalty = _history_penalty(paper, previous_items)

    research_relevance = min(25, 8 + relevance_hits * 3)
    method_substance = min(20, 4 + method_hits * 3)
    experiment_strength = min(15, 3 + experiment_hits * 3)
    influence_score = min(25, institution_score + people_score + domain_score)
    freshness_and_heat = min(
        10,
        len(related_signals) * 3 + (2 if freshness_date and paper.published_at.startswith(freshness_date) else 0),
    )
    writeability = min(5, 2 + int(bool(method_hits)) + int(bool(experiment_hits)) + int(len(paper.abstract) > 300))
    low_ai_penalty = 20 if relevance_hits == 0 else 0
    penalties = min(50, history_penalty + low_ai_penalty)
    total = max(
        0,
        min(
            100,
            research_relevance
            + method_substance
            + experiment_strength
            + influence_score
            + freshness_and_heat
            + writeability
            - penalties,
        ),
    )

    penalty_reasons = []
    if history_penalty:
        penalty_reasons.append("历史重复惩罚")
    if low_ai_penalty:
        penalty_reasons.append("AI 相关性弱惩罚")

    reasons = [f"总分 {total}"]
    if matched_institutions:
        reasons.append("命中高影响力机构：" + "、".join(matched_institutions))
    if matched_people:
        reasons.append("命中高影响力人物：" + "、".join(matched_people))
    if matched_domains:
        reasons.append("命中高影响力信源：" + "、".join(matched_domains))
    if method_hits:
        reasons.append(f"方法信号 {method_hits} 个")
    if experiment_hits:
        reasons.append(f"实验信号 {experiment_hits} 个")
    reasons.extend(penalty_reasons)

    detail = {
        "total_score": {"value": total, "reason": "按量化评分公式计算"},
        "research_relevance": {"value": research_relevance, "reason": f"AI 关键词命中 {relevance_hits} 个"},
        "method_substance": {"value": method_substance, "reason": f"方法关键词命中 {method_hits} 个"},
        "experiment_strength": {"value": experiment_strength, "reason": f"实验关键词命中 {experiment_hits} 个"},
        "influence_score": {
            "value": influence_score,
            "reason": "；".join([*matched_institutions, *matched_people, *matched_domains]) or "未命中高影响力来源",
        },
        "freshness_and_heat": {"value": freshness_and_heat, "reason": f"关联信号 {len(related_signals)} 条"},
        "writeability": {"value": writeability, "reason": "按摘要长度、方法和实验信号估算"},
        "penalties": {"value": penalties, "reason": "；".join(penalty_reasons) if penalty_reasons else "无扣分"},
    }

    return PaperScore(
        paper=paper,
        total_score=total,
        score_detail=detail,
        selection_reasons=reasons,
        matched_institutions=matched_institutions,
        matched_people=matched_people,
        matched_source_domains=matched_domains,
        matched_signals=[signal.id for signal in related_signals],
    )


def _count_hits(text: str, keywords: Iterable[str]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _matched_signals(paper: Paper, signals: List[Signal]) -> List[Signal]:
    arxiv_id = _normalize_arxiv_id(paper.arxiv_id)
    title = paper.title.strip().lower()
    return [
        signal
        for signal in signals
        if (arxiv_id and _normalize_arxiv_id(signal.url) == arxiv_id) or signal.title.strip().lower() == title
    ]


def _match_entries(text: str, entries: List[InfluenceEntry]) -> tuple[List[str], int]:
    matched: List[str] = []
    score = 0
    for entry in entries:
        if any(_alias_matches(text, alias) for alias in entry.aliases):
            matched.append(entry.name)
            score = max(score, entry.weight)
    return matched, score


def _match_domains(signals: List[Signal], entries: List[SourceDomainEntry]) -> tuple[List[str], int]:
    matched: List[str] = []
    score = 0
    for signal in signals:
        host = (urlparse(signal.url).hostname or "").lower().rstrip(".")
        for entry in entries:
            domain = entry.domain.lower().rstrip(".")
            if host == domain or host.endswith("." + domain):
                matched.append(entry.domain)
                score = max(score, entry.weight)
    return sorted(set(matched)), score


def _history_penalty(paper: Paper, previous_items: List[Mapping[str, object]]) -> int:
    paper_arxiv_id = _normalize_arxiv_id(paper.arxiv_id)
    paper_urls = {paper.pdf_url.rstrip("/"), f"https://arxiv.org/abs/{paper.arxiv_id}".rstrip("/")}
    paper_dedupe_keys = _paper_dedupe_keys(paper)
    for item in previous_items:
        if paper_arxiv_id and _normalize_arxiv_id(str(item.get("arxiv_id") or "")) == paper_arxiv_id:
            return 30
        if _normalize_dedupe(str(item.get("dedupe_key") or "")) in paper_dedupe_keys:
            return 30
        raw_urls = item.get("source_urls", [])
        source_urls = {str(url).rstrip("/") for url in raw_urls if str(url).strip()} if isinstance(raw_urls, list) else set()
        source_arxiv_ids = {_normalize_arxiv_id(url) for url in source_urls}
        if paper_arxiv_id and paper_arxiv_id in source_arxiv_ids:
            return 30
        if source_urls.intersection(paper_urls):
            return 30
    return 0


def _latest_published_date(papers: List[Paper], signals: List[Signal]) -> str:
    dates = [item.published_at[:10] for item in [*papers, *signals] if item.published_at[:10]]
    return max(dates) if dates else ""


def _normalize_arxiv_id(value: str) -> str:
    token = value.strip().lower().removeprefix("arxiv:")
    if "arxiv.org/" in token:
        token = urlparse(token).path.rstrip("/").split("/")[-1]
    token = token.removesuffix(".pdf")
    return re.sub(r"v\d+$", "", token)


def _normalize_dedupe(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _paper_dedupe_keys(paper: Paper) -> set[str]:
    arxiv_ids = {paper.arxiv_id, _normalize_arxiv_id(paper.arxiv_id)}
    return {
        _normalize_dedupe("|".join(parts))
        for arxiv_id in arxiv_ids
        if arxiv_id
        for parts in (
            [paper.title, arxiv_id, f"https://arxiv.org/abs/{arxiv_id}"],
            [paper.title, arxiv_id, f"https://arxiv.org/abs/{arxiv_id}", paper.pdf_url],
            [paper.title, arxiv_id, f"https://arxiv.org/abs/{arxiv_id}", f"https://arxiv.org/pdf/{arxiv_id}"],
        )
    }


def _alias_matches(text: str, alias: str) -> bool:
    return bool(alias and re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text))


def _timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
