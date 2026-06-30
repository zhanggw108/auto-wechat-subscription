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
    weak = make_paper(
        "2606.00002",
        "Agent Evaluation Note",
        "A short agent note with lightweight evaluation but no major experiments.",
    )

    scores = score_papers([weak, strong], signals=[], previous_items=[], config_path=config_path)

    assert scores[0].paper.arxiv_id == "2606.00001"
    assert scores[0].score_detail["influence_score"]["value"] == 25
    assert scores[0].total_score > scores[1].total_score
    assert "OpenAI" in scores[0].matched_institutions


def test_score_papers_filters_zero_score_weak_papers(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps({"institutions": [], "people": [], "source_domains": []}),
        encoding="utf-8",
    )
    strong = make_paper(
        "2606.00001",
        "Agent Benchmark with Large-Scale Ablation",
        "A framework for agent evaluation with ablation and large-scale comparison.",
    )
    weak = make_paper(
        "2606.00002",
        "A Note on Sorting",
        "Brief note.",
        authors=["Unaffiliated Author"],
    )

    scores = score_papers([weak, strong], signals=[], previous_items=[], config_path=config_path)

    assert [score.paper.arxiv_id for score in scores] == ["2606.00001"]


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


def test_score_papers_rewards_run_date_freshness(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps({"institutions": [], "people": [], "source_domains": []}),
        encoding="utf-8",
    )
    paper = make_paper(
        "2607.00001",
        "Agent Training Framework",
        "A framework for agent training with benchmark evaluation and ablation.",
        published_at="2026-07-01T08:00:00Z",
    )

    scores = score_papers([paper], signals=[], previous_items=[], config_path=config_path, run_date="2026-07-01")

    assert scores[0].score_detail["freshness_and_heat"]["value"] == 2


def test_source_domain_matching_requires_host_boundary(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps(
            {
                "institutions": [],
                "people": [],
                "source_domains": [{"domain": "openai.com", "weight": 18}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paper = make_paper(
        "2606.00004",
        "Agent Training Framework",
        "A framework for agent training with benchmark evaluation and ablation.",
    )
    bad_signal = Signal(
        id="signal-bad",
        source_id="rss",
        kind="paper",
        title=paper.title,
        summary="",
        url="https://notopenai.com/research",
        published_at="2026-06-30T09:00:00Z",
        heat=10,
    )
    good_signal = bad_signal.model_copy(update={"id": "signal-good", "url": "https://research.openai.com/post"})

    bad_score = score_papers([paper], signals=[bad_signal], previous_items=[], config_path=config_path)[0]
    good_score = score_papers([paper], signals=[good_signal], previous_items=[], config_path=config_path)[0]

    assert bad_score.matched_source_domains == []
    assert good_score.matched_source_domains == ["openai.com"]


def test_history_penalty_normalizes_arxiv_versions(tmp_path: Path):
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
    previous_items = [{"arxiv_id": "2606.00003v2", "source_urls": [], "dedupe_key": "old"}]

    scores = score_papers([paper], signals=[], previous_items=previous_items, config_path=config_path)

    assert scores[0].score_detail["penalties"]["value"] >= 20


def test_history_penalty_matches_current_dedupe_key(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps({"institutions": [], "people": [], "source_domains": []}),
        encoding="utf-8",
    )
    paper = make_paper(
        "2606.00007v2",
        "Agent Training Framework",
        "A framework for agent training with benchmark evaluation and ablation.",
    )
    previous_items = [
        {
            "arxiv_id": "",
            "source_urls": [],
            "dedupe_key": "agent training framework|2606.00007|https://arxiv.org/abs/2606.00007|https://arxiv.org/pdf/2606.00007",
        }
    ]

    scores = score_papers([paper], signals=[], previous_items=previous_items, config_path=config_path)

    assert scores[0].score_detail["penalties"]["value"] >= 20


def test_history_penalty_matches_pipeline_abs_only_dedupe_key(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps({"institutions": [], "people": [], "source_domains": []}),
        encoding="utf-8",
    )
    paper = make_paper(
        "2606.00007v2",
        "Agent Training Framework",
        "A framework for agent training with benchmark evaluation and ablation.",
    )
    previous_items = [
        {
            "arxiv_id": "",
            "source_urls": [],
            "dedupe_key": "agent training framework|2606.00007v2|https://arxiv.org/abs/2606.00007v2",
        }
    ]

    scores = score_papers([paper], signals=[], previous_items=previous_items, config_path=config_path)

    assert scores[0].score_detail["penalties"]["value"] >= 20


def test_signal_matching_normalizes_arxiv_versions_in_urls(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps({"institutions": [], "people": [], "source_domains": []}),
        encoding="utf-8",
    )
    paper = make_paper(
        "2606.00006v2",
        "Agent Training Framework",
        "A framework for agent training with benchmark evaluation and ablation.",
    )
    signal = Signal(
        id="signal-arxiv",
        source_id="rss",
        kind="paper",
        title="Different title",
        summary="",
        url="https://arxiv.org/abs/2606.00006",
        published_at="2026-06-30T09:00:00Z",
        heat=10,
    )

    scores = score_papers([paper], signals=[signal], previous_items=[], config_path=config_path)

    assert scores[0].matched_signals == ["signal-arxiv"]


def test_short_alias_requires_word_boundary(tmp_path: Path):
    config_path = tmp_path / "influence_sources.json"
    config_path.write_text(
        json.dumps(
            {
                "institutions": [{"name": "MIT", "aliases": ["mit"], "weight": 25}],
                "people": [],
                "source_domains": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paper = make_paper(
        "2606.00005",
        "Submit Agent Benchmark",
        "A framework for agent training with benchmark evaluation and ablation.",
    )

    scores = score_papers([paper], signals=[], previous_items=[], config_path=config_path)

    assert scores[0].matched_institutions == []
