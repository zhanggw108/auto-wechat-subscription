from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_radar.models import Paper, Signal
from ai_radar.scoring import InfluenceConfigError, load_influence_config, score_papers


def test_load_influence_config_reads_institutions_people_and_domains(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text(
        json.dumps(
            {
                "institutions": [{"name": "OpenAI", "aliases": ["OpenAI"], "weight": 25}],
                "people": [{"name": "Yann LeCun", "aliases": ["Yann LeCun"], "weight": 20}],
                "source_domains": [{"domain": "OpenAI.COM", "weight": 18}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = load_influence_config(path)

    assert config.institutions[0].name == "OpenAI"
    assert config.institutions[0].aliases == ["openai"]
    assert config.institutions[0].weight == 25
    assert config.people[0].aliases == ["yann lecun"]
    assert config.people[0].weight == 20
    assert config.source_domains[0].domain == "openai.com"
    assert config.source_domains[0].weight == 18


def test_load_influence_config_reports_broken_structure_path(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text(
        json.dumps({"institutions": [{"name": "OpenAI"}], "people": [], "source_domains": []}),
        encoding="utf-8",
    )

    with pytest.raises(InfluenceConfigError) as error:
        load_influence_config(path)

    assert str(path) in str(error.value)
    assert "字段" in str(error.value)


def test_load_influence_config_reports_broken_json_path(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(InfluenceConfigError) as error:
        load_influence_config(path)

    assert str(path) in str(error.value)
    assert "JSON" in str(error.value)


def make_paper(
    arxiv_id: str,
    title: str,
    abstract: str,
    authors: list[str] | None = None,
    published_at: str = "2026-06-30T08:00:00Z",
) -> Paper:
    return Paper(
        id=f"paper-{arxiv_id}",
        arxiv_id=arxiv_id,
        title=title,
        authors=authors or ["Example Author"],
        abstract=abstract,
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        code_url=None,
        published_at=published_at,
        categories=["cs.AI"],
        method_summary=abstract,
        experiment_summary=abstract,
        limitations="",
        replication_value=70,
        extension_topics=[],
    )


def test_score_papers_rewards_influential_institutions_and_methods(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps(
            {
                "institutions": [{"name": "OpenAI", "aliases": ["openai"], "weight": 25}],
                "people": [],
                "source_domains": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    strong = make_paper(
        "2606.00001",
        "OpenAI Agent Benchmark with Large-Scale Ablation",
        "OpenAI introduces a framework and benchmark for agent evaluation with ablation and large-scale comparison.",
        authors=["OpenAI Research"],
    )
    weak = make_paper("2606.00002", "A Note on Sorting", "A short note without AI experiments.")

    scores = score_papers([weak, strong], signals=[], previous_items=[], config_path=config_path)

    assert scores[0].paper.arxiv_id == "2606.00001"
    assert scores[0].score_detail["influence_score"]["value"] == 25
    assert scores[0].total_score > scores[1].total_score
    assert "OpenAI" in scores[0].matched_institutions


def test_score_papers_applies_history_penalty(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps({"institutions": [], "people": [], "source_domains": []}),
        encoding="utf-8",
    )
    paper = make_paper(
        "2606.00003",
        "Agent Training Framework",
        "A framework for agent training with benchmark evaluation and ablation.",
    )
    previous_items = [{"arxiv_id": "2606.00003", "source_urls": ["https://arxiv.org/abs/2606.00003"], "dedupe_key": "old"}]

    scores = score_papers([paper], signals=[], previous_items=previous_items, config_path=config_path)

    assert scores[0].score_detail["penalties"]["value"] >= 20
    assert any("历史" in reason for reason in scores[0].selection_reasons)
