import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_radar.api import create_app
from ai_radar.models import Paper, Signal
from ai_radar.pipeline import DailyPipeline
from ai_radar.sample_data import seed_papers
from ai_radar.storage import JsonStore


def _fake_long_articles_for_prompt(input_text: str) -> list[dict[str, object]]:
    locked = json.loads(input_text).get("locked_long_articles") or []
    papers = list(locked or json.loads(input_text).get("papers") or [])
    while len(papers) < 5:
        index = len(papers) + 1
        papers.append(
            {
                "arxiv_id": f"2606.9900{index}",
                "title": f"补充论文 {index}",
            }
        )
    return [
        {
            "title": f"第{index}篇高分论文的中文深度解读",
            "summary": f"这篇论文适合做长文，因为它的问题设定、方法设计和实验材料都足够展开，核心论文编号是 {paper['arxiv_id']}。",
            "angle": "重点写研究问题为什么重要、方法机制如何成立、实验结果是否可靠，以及局限会怎样影响后续工作。",
            "source_urls": [f"https://arxiv.org/abs/{paper['arxiv_id']}"],
            "arxiv_id": paper["arxiv_id"],
        }
        for index, paper in enumerate(papers[:5], start=1)
    ]


def _scoreable_test_papers(run_date: str) -> list[Paper]:
    papers = seed_papers(run_date)
    return papers + [
        papers[0].model_copy(
            update={
                "id": f"paper-score-lock-{index}",
                "arxiv_id": f"2606.9100{index}",
                "title": f"Supplemental Agent Note {index}",
                "authors": [f"Supplemental Author {index}"],
                "abstract": "A short agent note.",
                "pdf_url": f"https://arxiv.org/pdf/2606.9100{index}",
                "categories": ["cs.AI"],
                "method_summary": "Agent note.",
                "experiment_summary": "Short note.",
                "limitations": "Supplemental fixture only.",
                "replication_value": 1,
                "extension_topics": [],
            }
        )
        for index in range(1, 9)
    ]


@pytest.fixture(autouse=True)
def scoreable_seed_papers(monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.seed_papers", _scoreable_test_papers)


class TopicPackLLM:
    def __init__(self):
        self.calls = []

    def complete(self, instructions: str, input_text: str):
        self.calls.append({"instructions": instructions, "input_text": input_text})

        text = """
{
  "long_articles": [],
  "ai_hotspots": [
    {
      "title": "Agent eval 开始强调轨迹而不是单轮答案",
      "summary": "新的 agent 评测讨论把过程、grader 和人工复核放到中心。",
      "angle": "适合作为观察 agent 评测方法转向的热点短评。",
      "source_urls": ["https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents"]
    },
    {
      "title": "Context engineering 让 prompt 技巧退到幕后",
      "summary": "有效 agent 越来越依赖状态、工具、检索和 trace。",
      "angle": "可转化为论文系统设计章节的写法。",
      "source_urls": ["https://www.anthropic.com/engineering/building-effective-agents"]
    },
    {
      "title": "开源评测工具继续影响模型评测实践",
      "summary": "OpenAI Evals 仍适合做回归式模型检查的基线。",
      "angle": "可以从 grader、数据集和回归检查理解评测系统。",
      "source_urls": ["https://github.com/openai/evals"]
    },
    {
      "title": "LangGraph 把 agent 工程拉回状态管理",
      "summary": "它提供了可验证 workflow 和持久执行参考。",
      "angle": "适合解释为什么 agent 论文不能只展示 demo。",
      "source_urls": ["https://github.com/langchain-ai/langgraph"]
    },
    {
      "title": "AgentBench 仍是交互式 agent 评测参照物",
      "summary": "多环境任务能暴露长期推理和指令遵循失败。",
      "angle": "适合扩展成评测综述的小节。",
      "source_urls": ["https://arxiv.org/abs/2308.03688"]
    }
  ],
  "arxiv_papers": [
    {
      "title": "Agent Laboratory: Using LLM Agents as Research Assistants",
      "summary": "把科研流程拆成文献综述、实验和报告写作。",
      "angle": "值得后续展开成长文，重点看人类反馈和实验边界。",
      "source_urls": ["https://arxiv.org/abs/2501.04227"],
      "arxiv_id": "2501.04227"
    },
    {
      "title": "Retrieval Augmented Generation or Long-Context LLMs?",
      "summary": "比较 RAG 与长上下文，并提出路由式折中。",
      "angle": "适合观察消融实验和成本分析。",
      "source_urls": ["https://arxiv.org/abs/2407.16833"],
      "arxiv_id": "2407.16833"
    },
    {
      "title": "AgentBench: Evaluating LLMs as Agents",
      "summary": "用交互环境评测 LLM agent。",
      "angle": "适合观察 agent 评测任务设计。",
      "source_urls": ["https://arxiv.org/abs/2308.03688"],
      "arxiv_id": "2308.03688"
    },
    {
      "title": "Self-Route for Efficient Long Context QA",
      "summary": "用模型自我判断在检索和长上下文间路由。",
      "angle": "可改写为成本敏感型 RAG 实验。",
      "source_urls": ["https://arxiv.org/abs/2407.16833"],
      "arxiv_id": "2407.16833v2"
    },
    {
      "title": "Trace-based Agent Evaluation Survey",
      "summary": "聚焦 agent 过程日志和评价器可靠性。",
      "angle": "适合作为综述型论文材料。",
      "source_urls": ["https://example.com/trace-agent-eval"],
      "arxiv_id": "2606.00001"
    }
  ]
}
"""
        payload = json.loads(text)
        payload["long_articles"] = _fake_long_articles_for_prompt(input_text)
        text = json.dumps(payload, ensure_ascii=False)
        if len(self.calls) > 1:
            replacements = [
                "Agent eval 开始强调轨迹而不是单轮答案",
                "Context engineering 让 prompt 技巧退到幕后",
                "开源评测工具继续影响模型评测实践",
                "LangGraph 把 agent 工程拉回状态管理",
                "AgentBench 仍是交互式 agent 评测参照物",
                "适合作为观察 agent 评测方法转向的热点短评。",
                "可转化为论文系统设计章节的写法。",
                "可以从 grader、数据集和回归检查理解评测系统。",
                "适合解释为什么 agent 论文不能只展示 demo。",
                "适合扩展成评测综述的小节。",
            ]
            for value in replacements:
                text = text.replace(value, f"刷新后的{value}")

        return type("Result", (), {"response_id": "resp-topic-pack-1", "text": text})()


class AcademicTopicPackLLM:
    def __init__(self):
        self.calls = []

    def complete(self, instructions: str, input_text: str):
        self.calls.append({"instructions": instructions, "input_text": input_text})
        text = """
{
  "long_articles": [],
  "ai_hotspots": [
    {
      "title": "开源项目 swarmauri-sdk 更新",
      "summary": "GitHub 项目展示了 AI agent SDK 的工程动态。",
      "angle": "作为开发者生态热点观察，不作为长文论文解读。",
      "source_urls": ["https://github.com/swarmauri/swarmauri-sdk"]
    },
    {
      "title": "OpenAI 官方博客更新",
      "summary": "官方博客提供模型部署相关动态。",
      "angle": "适合作为行业热点简短判断。",
      "source_urls": ["https://openai.com/index/example"]
    },
    {
      "title": "AI 产品发布引发开发者讨论",
      "summary": "产品动态可作为热点，不进入论文深度解读。",
      "angle": "观察产品和开发者生态变化。",
      "source_urls": ["https://example.com/product"]
    },
    {
      "title": "多模态工具链继续升温",
      "summary": "工具链变化影响模型应用开发。",
      "angle": "适合简要概述。",
      "source_urls": ["https://example.com/multimodal-tooling"]
    },
    {
      "title": "AI 安全评测讨论增加",
      "summary": "社区开始关注部署前评测。",
      "angle": "作为热点观察。",
      "source_urls": ["https://example.com/safety-evals"]
    }
  ],
  "arxiv_papers": [
    {
      "title": "DiffusionGemma",
      "summary": "扩散式语言模型论文，值得进入论文速报。",
      "angle": "看方法贡献和实验设置。",
      "source_urls": ["https://arxiv.org/abs/2606.20560"],
      "arxiv_id": "2606.20560"
    },
    {
      "title": "Execution-State Capsules",
      "summary": "端侧物理 AI serving 论文。",
      "angle": "看系统机制和延迟实验。",
      "source_urls": ["https://arxiv.org/abs/2606.20537"],
      "arxiv_id": "2606.20537"
    },
    {
      "title": "Multimodal Reasoning Benchmark",
      "summary": "多模态推理评测论文。",
      "angle": "看评测设计。",
      "source_urls": ["https://arxiv.org/abs/2606.20001"],
      "arxiv_id": "2606.20001"
    },
    {
      "title": "AI Safety Deployment Simulation",
      "summary": "AI safety 评测论文。",
      "angle": "看部署前模拟实验。",
      "source_urls": ["https://arxiv.org/abs/2606.20002"],
      "arxiv_id": "2606.20002"
    },
    {
      "title": "Efficient Transformer Training",
      "summary": "训练效率论文。",
      "angle": "看训练方法和实验。",
      "source_urls": ["https://arxiv.org/abs/2606.20003"],
      "arxiv_id": "2606.20003"
    }
  ]
}
"""
        payload = json.loads(text)
        payload["long_articles"] = _fake_long_articles_for_prompt(input_text)
        text = json.dumps(payload, ensure_ascii=False)
        return type("Result", (), {"response_id": "resp-academic-topic-pack", "text": text})()


class UrlOnlyTopicPackLLM:
    def complete(self, instructions: str, input_text: str):
        payload = json.loads(TopicPackLLM().complete(instructions, input_text).text)
        for index, item in enumerate(payload["arxiv_papers"]):
            item["url"] = item["source_urls"][0]
            item.pop("source_urls")
            if index % 2 == 0 and "arxiv.org" in item["url"]:
                item.pop("arxiv_id")
        return type("Result", (), {"response_id": "resp-topic-pack-url-only", "text": json.dumps(payload, ensure_ascii=False)})()


class ReplacingLongArticleLLM:
    def complete(self, instructions: str, input_text: str):
        payload = json.loads(TopicPackLLM().complete(instructions, input_text).text)
        payload["long_articles"] = [
            {
                "title": f"模型试图替换论文 {index}",
                "summary": "这条应该只贡献文案，不能替换锁定论文。",
                "angle": "测试锁定论文来源。",
                "source_urls": [f"https://arxiv.org/abs/9999.0000{index}"],
                "arxiv_id": f"9999.0000{index}",
            }
            for index in range(1, 6)
        ]
        return type("Result", (), {"response_id": "replace-test", "text": json.dumps(payload, ensure_ascii=False)})()


class WrongArxivLongArticleLLM:
    def complete(self, instructions: str, input_text: str):
        payload = json.loads(TopicPackLLM().complete(instructions, input_text).text)
        payload["long_articles"][0]["source_urls"] = ["https://arxiv.org/abs/9999.00001"]
        payload["long_articles"][0]["arxiv_id"] = "9999.00001"
        return type("Result", (), {"response_id": "wrong-arxiv-test", "text": json.dumps(payload, ensure_ascii=False)})()


class MissingLongArticlesLLM:
    def complete(self, instructions: str, input_text: str):
        payload = json.loads(TopicPackLLM().complete(instructions, input_text).text)
        payload.pop("long_articles")
        return type("Result", (), {"response_id": "missing-long-articles", "text": json.dumps(payload, ensure_ascii=False)})()


class MissingHotspotsLLM:
    def complete(self, instructions: str, input_text: str):
        payload = json.loads(TopicPackLLM().complete(instructions, input_text).text)
        payload.pop("ai_hotspots")
        return type("Result", (), {"response_id": "missing-hotspots", "text": json.dumps(payload, ensure_ascii=False)})()


def test_refresh_status_counts_down_to_11_before_daily_refresh(tmp_path: Path):
    pipeline = DailyPipeline(JsonStore(tmp_path))

    status = pipeline.refresh_status(now=datetime(2026, 6, 20, 10, 30))

    assert status.date == "2026-06-20"
    assert status.refresh_time == "11:00"
    assert status.today_refreshed is False
    assert status.next_refresh_at == "2026-06-20T11:00:00"
    assert status.seconds_until_next_refresh == 1800


def test_due_refresh_runs_once_after_11_and_skips_when_already_refreshed(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store)

    first = pipeline.refresh_if_due(now=datetime(2026, 6, 20, 11, 5))
    second = pipeline.refresh_if_due(now=datetime(2026, 6, 20, 11, 6))

    assert first.today_refreshed is True
    assert second.today_refreshed is True
    assert store.get_run("2026-06-20") is not None
    assert store.get_refresh("2026-06-20")["last_refresh_at"] == "2026-06-20T11:05:00"


def test_due_refresh_generates_llm_topic_pack_when_provider_is_configured(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)

    status = pipeline.refresh_if_due(now=datetime(2026, 6, 20, 11, 5))

    assert status.today_refreshed is True
    pack = store.current_topic_pack("2026-06-20")
    assert pack is not None
    assert pack.version == 1
    assert pack.refreshed_module == "all"
    assert pack.llm_response_id == "resp-topic-pack-1"
    assert len(pack.long_articles) == 5
    assert all(item.source_urls for item in pack.long_articles)
    assert "all" in llm.calls[0]["input_text"]
    assert store.get_refresh("2026-06-20")["topic_pack_id"] == pack.id


def test_topic_pack_item_score_detail_defaults_to_empty_dict():
    from ai_radar.models import TopicPackItem

    item = TopicPackItem(
        id="topic-pack-item-test",
        module="long_articles",
        title="Test Paper",
        summary="Summary",
        angle="Angle",
        source_urls=["https://arxiv.org/abs/2606.00001"],
        arxiv_id="2606.00001",
        rank=1,
        dedupe_key="test-paper",
        angle_hash="angle-hash",
    )

    assert item.score_detail == {}


def test_current_topic_pack_backfills_long_article_topic_ids_from_sources(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    pipeline.refresh_topic_pack("2026-06-20", module="all", reason="missing topic ids")

    stored = store.current_topic_pack("2026-06-20")
    assert stored is not None
    assert [item.topic_id for item in stored.long_articles] == [None, None, None, None, None]

    current = pipeline.ensure_topic_pack("2026-06-20")

    assert current.long_articles[0].topic_id == "topic-agent-lab"
    assert current.long_articles[1].topic_id == "topic-long-context-rag"


def test_current_topic_pack_creates_selectable_topics_for_llm_only_long_articles(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="llm only item")
    rewritten = pack.model_copy(
        update={
            "id": "topic-pack-2026-06-20-v99",
            "version": 99,
            "long_articles": [
                pack.long_articles[0].model_copy(
                    update={
                        "title": "一个 LLM 新生成但不在 topic 列表里的长文章选题",
                        "arxiv_id": None,
                        "topic_id": None,
                        "source_urls": ["https://example.com/llm-only-source"],
                    }
                )
            ]
            + pack.long_articles[1:],
        }
    )
    store.add_topic_pack_version(rewritten)

    current = pipeline.ensure_topic_pack("2026-06-20")

    assert current.long_articles[0].topic_id
    topic = pipeline.get_topic(current.long_articles[0].topic_id)
    assert topic.title == "一个 LLM 新生成但不在 topic 列表里的长文章选题"
    assert topic.article_type == "long_paper"


def test_current_topic_pack_rejects_legacy_three_item_pack(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="initial")
    legacy = pack.model_copy(update={"id": "topic-pack-2026-06-20-v99", "version": 99, "long_articles": pack.long_articles[:3]})
    store.add_topic_pack_version(legacy)

    try:
        pipeline.ensure_topic_pack("2026-06-20")
    except KeyError:
        pass
    else:
        raise AssertionError("incomplete topic pack should not be returned")


def test_topic_pack_refresh_replaces_legacy_three_item_pack(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="initial")
    legacy = pack.model_copy(update={"id": "topic-pack-2026-06-20-v99", "version": 99, "long_articles": pack.long_articles[:3]})
    store.add_topic_pack_version(legacy)

    current = pipeline.refresh_topic_pack("2026-06-20", module="long_articles", reason="repair")

    assert current.version == 100
    assert len(current.long_articles) == 5


def test_topic_pack_accepts_url_fields_for_paper_sources(tmp_path: Path):
    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=UrlOnlyTopicPackLLM())

    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="url fields")

    assert len(pack.arxiv_papers) == 5
    assert pack.arxiv_papers[0].source_urls == ["https://arxiv.org/abs/2501.04227"]
    assert pack.arxiv_papers[0].arxiv_id == "2501.04227"


def test_topic_pack_long_articles_are_selected_by_scores_not_llm(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store, llm_provider=ReplacingLongArticleLLM())

    with pytest.raises(RuntimeError, match="LLM response missing usable long_articles copy"):
        pipeline.refresh_topic_pack("2026-06-20", module="all", reason="score locked")


def test_topic_pack_rejects_missing_llm_copy_for_locked_paper(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store, llm_provider=WrongArxivLongArticleLLM())

    with pytest.raises(RuntimeError, match="LLM response missing usable long_articles copy"):
        pipeline.refresh_topic_pack("2026-06-20", module="all", reason="reject mismatched llm copy")


def test_topic_pack_all_refresh_fails_when_long_articles_missing(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store, llm_provider=MissingLongArticlesLLM())

    with pytest.raises(RuntimeError, match="LLM response missing usable long_articles copy"):
        pipeline.refresh_topic_pack("2026-06-20", module="all", reason="partial schema")


def test_topic_pack_all_refresh_returns_partial_pack_when_secondary_module_missing(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store, llm_provider=MissingHotspotsLLM())

    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="partial hotspots")
    current = pipeline.ensure_topic_pack("2026-06-20")

    assert pack.status == "partial"
    assert current.id == pack.id
    assert len(pack.long_articles) == 5
    assert pack.ai_hotspots == []
    assert len(pack.arxiv_papers) == 5
    assert all(item.score_detail for item in pack.long_articles)


def test_topic_pack_scores_penalize_cross_day_history(tmp_path: Path, monkeypatch):
    def high_score_seed(run_date: str) -> list[Paper]:
        papers = _scoreable_test_papers(run_date)
        return [
            *papers,
            papers[0].model_copy(
                update={
                    "id": "paper-cross-day-history",
                    "arxiv_id": "2606.99999",
                    "title": "OpenAI Agent Benchmark with Large-Scale Ablation",
                    "authors": ["OpenAI Research"],
                    "abstract": "OpenAI introduces a framework and benchmark for agent evaluation with ablation and large-scale comparison.",
                    "pdf_url": "https://arxiv.org/pdf/2606.99999",
                    "categories": ["cs.AI"],
                    "method_summary": "Agent evaluation framework.",
                    "experiment_summary": "Benchmark comparison and ablation experiments.",
                }
            ),
        ]

    monkeypatch.setattr("ai_radar.pipeline.seed_papers", high_score_seed)
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store, llm_provider=TopicPackLLM())
    pipeline.refresh_topic_pack("2026-06-29", module="all", reason="day one")

    pack = pipeline.refresh_topic_pack("2026-06-30", module="all", reason="day two")

    report_path = tmp_path / "topic-packs" / "2026-06-30" / "v01" / "long-article-scores.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    item = next(item for item in report["papers"] if item["arxiv_id"] == "2606.99999")
    assert item["score_detail"]["penalties"]["value"] >= 20


def test_topic_pack_refresh_writes_long_article_score_report(tmp_path: Path):
    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=TopicPackLLM())

    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="score report")

    report_path = tmp_path / "topic-packs" / "2026-06-20" / "v01" / "long-article-scores.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["topic_pack_id"] == pack.id
    assert len(payload["papers"]) >= 5
    first_paper = payload["papers"][0]
    assert first_paper["rank"] == 1
    assert first_paper["selected"] is True
    assert first_paper["arxiv_id"]
    assert first_paper["score_detail"]
    assert first_paper["selection_reasons"]
    assert isinstance(first_paper["total_score"], (int, float))
    if len(payload["papers"]) == 5:
        assert payload["papers"][4]["selected"] is True


def test_initial_ai_hotspots_refresh_does_not_require_scoreable_long_articles(tmp_path: Path, monkeypatch):
    with monkeypatch.context() as context:
        context.setattr("ai_radar.pipeline.seed_papers", seed_papers)
        pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=TopicPackLLM())

        pack = pipeline.refresh_topic_pack("2026-06-20", module="ai_hotspots", reason="first hotspot refresh")

    assert pack.refreshed_module == "ai_hotspots"
    assert len(pack.long_articles) == 5
    assert len(pack.ai_hotspots) == 5
    assert len(pack.arxiv_papers) == 5
    assert any(item.title == "Agent eval 开始强调轨迹而不是单轮答案" for item in pack.ai_hotspots)
    assert not (tmp_path / "topic-packs" / "2026-06-20" / "v01" / "long-article-scores.json").exists()


def test_topic_pack_generation_sends_compact_real_source_context_to_llm(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    extra_signals = [
        Signal(
            id=f"signal-extra-{index}",
            source_id="source-ai-news-radar",
            kind="news",
            title=f"Extra AI signal {index}",
            summary="This is a long extra signal summary about agent evaluation and reproducible experiments.",
            url=f"https://example.com/extra-{index}",
            published_at="2026-06-20T08:00:00Z",
            tags=["agents", "evals"],
            heat=60 + (index % 20),
            entities={"companies": ["Example"], "topics": ["agent evaluation"]},
        )
        for index in range(80)
    ]
    store.upsert_many("signals", extra_signals)

    pipeline.refresh_topic_pack("2026-06-20", module="all", reason="compact context")

    payload = json.loads(llm.calls[0]["input_text"])
    assert len(payload["signals"]) <= 30
    assert len(payload["papers"]) <= 10
    assert len(payload["topics"]) <= 10
    assert set(payload["signals"][0]) == {"kind", "title", "summary", "url", "heat", "tags"}
    assert "entities" not in payload["signals"][0]


def test_topic_pack_prompt_enforces_academic_paper_first_modules(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = AcademicTopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    pipeline.run_daily("2026-06-20")

    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="academic paper first")

    assert all(item.arxiv_id for item in pack.long_articles)
    assert all(any("arxiv.org" in url for url in item.source_urls) for item in pack.long_articles)
    assert any("github.com" in url for item in pack.ai_hotspots for url in item.source_urls)
    assert not any("github.com" in url for item in pack.long_articles for url in item.source_urls)
    assert all(item.arxiv_id for item in pack.arxiv_papers)
    assert "学术价值" in llm.calls[0]["instructions"]
    assert "GitHub" in llm.calls[0]["instructions"]


def test_refresh_status_uses_beijing_time_for_timezone_aware_input(tmp_path: Path):
    pipeline = DailyPipeline(JsonStore(tmp_path))

    status = pipeline.refresh_status(now=datetime(2026, 6, 20, 2, 30, tzinfo=timezone.utc))

    assert status.date == "2026-06-20"
    assert status.refresh_time == "11:00"
    assert status.today_refreshed is False
    assert status.next_refresh_at == "2026-06-20T11:00:00"
    assert status.seconds_until_next_refresh == 1800


def test_due_refresh_records_beijing_date_and_time_for_utc_input(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store)

    status = pipeline.refresh_if_due(now=datetime(2026, 6, 20, 3, 5, tzinfo=timezone.utc))

    assert status.today_refreshed is True
    assert store.get_run("2026-06-20") is not None
    assert store.get_refresh("2026-06-20")["last_refresh_at"] == "2026-06-20T11:05:00"


def test_manual_refresh_today_rebuilds_today_with_a_new_recommended_topic(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store)
    original = pipeline.run_daily("2026-06-20")

    refreshed = pipeline.refresh_today(now=datetime(2026, 6, 20, 14, 30))

    assert refreshed.date == "2026-06-20"
    assert refreshed.selected_topic.id != original.selected_topic.id
    assert refreshed.draft.id == f"draft-2026-06-20-{refreshed.selected_topic.id}"
    assert store.get_run("2026-06-20")["selected_topic_id"] == refreshed.selected_topic.id
    assert store.get_refresh("2026-06-20")["last_refresh_at"] == "2026-06-20T14:30:00"
    assert store.get_refresh("2026-06-20")["reason"] == "manual topic refresh"


def test_topic_pack_refresh_creates_new_version_for_one_module_and_records_history(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    pipeline = DailyPipeline(store, llm_provider=llm)
    initial = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="首次生成今日选题")

    refreshed = pipeline.refresh_topic_pack("2026-06-20", module="ai_hotspots", reason="换一个热点角度")

    assert refreshed.version == initial.version + 1
    assert refreshed.trigger == "manual"
    assert refreshed.refreshed_module == "ai_hotspots"
    assert refreshed.previous_version_id == initial.id
    assert refreshed.llm_response_id == "resp-topic-pack-1"
    assert len(llm.calls) == 2
    assert "ai_hotspots" in llm.calls[1]["input_text"]
    assert "换一个热点角度" in llm.calls[1]["input_text"]
    assert "历史" in llm.calls[1]["input_text"]
    assert [item.title for item in refreshed.long_articles] == [item.title for item in initial.long_articles]
    assert [item.title for item in refreshed.arxiv_papers] == [item.title for item in initial.arxiv_papers]
    assert [item.title for item in refreshed.ai_hotspots] != [item.title for item in initial.ai_hotspots]
    assert len(refreshed.long_articles) == 5
    assert len(refreshed.ai_hotspots) == 5
    assert len(refreshed.arxiv_papers) == 5

    versions = store.list_topic_pack_versions("2026-06-20")
    assert [version.version for version in versions] == [1, 2]
    assert (tmp_path / "topic-packs" / "2026-06-20" / "v02" / "topic-pack.json").exists()


def test_topic_pack_refresh_can_rebuild_live_sources_even_when_daily_run_exists(tmp_path: Path):
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2606.29999v1</id>
        <updated>2026-06-20T08:20:00Z</updated>
        <published>2026-06-20T08:20:00Z</published>
        <title>Fresh Manual Refresh Paper</title>
        <summary>Fresh paper context for manual topic pack refresh.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.29999" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.29998v1</id>
        <updated>2026-06-20T08:21:00Z</updated>
        <published>2026-06-20T08:21:00Z</published>
        <title>Fresh Manual Refresh Paper Two</title>
        <summary>Fresh paper context about language model evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.29998" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.29997v1</id>
        <updated>2026-06-20T08:22:00Z</updated>
        <published>2026-06-20T08:22:00Z</published>
        <title>Fresh Manual Refresh Paper Three</title>
        <summary>Fresh paper context about multimodal reasoning evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.29997" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.29996v1</id>
        <updated>2026-06-20T08:23:00Z</updated>
        <published>2026-06-20T08:23:00Z</published>
        <title>Fresh Manual Refresh Paper Four</title>
        <summary>Fresh paper context about agent training and evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.29996" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.29995v1</id>
        <updated>2026-06-20T08:24:00Z</updated>
        <published>2026-06-20T08:24:00Z</published>
        <title>Fresh Manual Refresh Paper Five</title>
        <summary>Fresh paper context about inference safety evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.29995" />
      </entry>
    </feed>
    """
    rss_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>fresh-rss-item</guid>
        <title>Fresh Manual RSS Item</title>
        <link>https://example.com/fresh-rss-item</link>
        <description>Fresh RSS context for manual refresh.</description>
        <pubDate>Sat, 20 Jun 2026 08:30:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "arxiv" in url:
            return httpx.Response(200, text=arxiv_xml)
        if "api.github.com" in url:
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, text=rss_xml)

    store = JsonStore(tmp_path)
    llm = TopicPackLLM()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store, http_client=client, llm_provider=llm)
    pipeline.run_daily("2026-06-20")

    pipeline.refresh_topic_pack("2026-06-20", module="all", reason="manual topic module refresh", fresh_sources=True)

    payload = json.loads(llm.calls[0]["input_text"])
    assert any(item["title"] == "Fresh Manual Refresh Paper" for item in payload["papers"])
    assert any(item["title"] == "Fresh Manual RSS Item" for item in payload["signals"])
    assert any(topic.title == "Fresh Manual Refresh Paper" for topic in store.list_topics())


def test_topic_pack_refresh_fails_without_llm_instead_of_using_default_topics(tmp_path: Path):
    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=None)

    try:
        pipeline.refresh_topic_pack("2026-06-20", module="all", reason="必须真实生成")
    except RuntimeError as error:
        assert "LLM provider is required" in str(error)
    else:
        raise AssertionError("refresh_topic_pack should fail when LLM is not configured")

    assert JsonStore(tmp_path).list_topic_pack_versions("2026-06-20") == []


def test_topic_pack_refresh_api_accepts_specific_module(tmp_path: Path):
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2606.28888v1</id>
        <updated>2026-06-20T08:20:00Z</updated>
        <published>2026-06-20T08:20:00Z</published>
        <title>API Topic Pack Refresh Paper</title>
        <summary>Fresh source context for the API topic pack refresh.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.28888" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.28887v1</id>
        <updated>2026-06-20T08:21:00Z</updated>
        <published>2026-06-20T08:21:00Z</published>
        <title>API Topic Pack Refresh Paper Two</title>
        <summary>Fresh source context about language model evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.28887" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.28886v1</id>
        <updated>2026-06-20T08:22:00Z</updated>
        <published>2026-06-20T08:22:00Z</published>
        <title>API Topic Pack Refresh Paper Three</title>
        <summary>Fresh source context about multimodal reasoning evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.28886" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.28885v1</id>
        <updated>2026-06-20T08:23:00Z</updated>
        <published>2026-06-20T08:23:00Z</published>
        <title>API Topic Pack Refresh Paper Four</title>
        <summary>Fresh source context about agent training and evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.28885" />
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2606.28884v1</id>
        <updated>2026-06-20T08:24:00Z</updated>
        <published>2026-06-20T08:24:00Z</published>
        <title>API Topic Pack Refresh Paper Five</title>
        <summary>Fresh source context about inference safety evaluation benchmark experiments.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.28884" />
      </entry>
    </feed>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "arxiv" in url:
            return httpx.Response(200, text=arxiv_xml)
        if "api.github.com" in url:
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, text="<rss version='2.0'><channel></channel></rss>")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    app = create_app(storage_root=tmp_path, auto_refresh_on_startup=False, http_client=http_client)
    app.state.pipeline.llm_provider = TopicPackLLM()
    client = TestClient(app)

    refreshed = client.post(
        "/api/topic-packs/refresh",
        json={"date": "2026-06-20", "module": "long_articles", "reason": "不满意今日长文章"},
    )

    assert refreshed.status_code == 200
    payload = refreshed.json()
    assert payload["version"] == 1
    assert payload["refreshed_module"] == "long_articles"
    assert len(payload["long_articles"]) == 5
    assert len(payload["ai_hotspots"]) >= 5
    assert len(payload["arxiv_papers"]) >= 5


def test_current_topic_pack_returns_404_before_llm_generation(tmp_path: Path):
    client = TestClient(create_app(storage_root=tmp_path, auto_refresh_on_startup=False))

    response = client.get("/api/topic-packs/current?date=2026-06-20")

    assert response.status_code == 404
    assert response.json()["detail"] == "Topic pack not generated yet"


def test_module_refresh_archives_existing_package_before_rewrite(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store)
    run = pipeline.run_daily("2026-06-20")
    original = (tmp_path / run.draft.markdown_path).read_text(encoding="utf-8")

    refreshed = pipeline.refresh_module(run.draft.id, "hotspots", reason="manual refresh")

    assert refreshed.id == run.draft.id
    assert refreshed.version == 2
    assert refreshed.last_rerun_stage == "refresh:hotspots"
    history_files = list((tmp_path / "drafts" / "2026-06-20" / run.selected_topic.slug / "history").glob("**/article.md"))
    assert history_files
    assert history_files[0].read_text(encoding="utf-8") == original


def test_module_refresh_replaces_only_requested_module(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store)
    run = pipeline.run_daily("2026-06-20")
    custom_markdown = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

用户已经手工确认过的主文章内容。

## 次文章 1：AI 热点

旧热点内容。

## 次文章 2：arXiv 高热度文章速报

旧 arXiv 内容。

## 来源清单

- old source
"""
    store.write_text(run.draft.markdown_path, custom_markdown)

    pipeline.refresh_module(run.draft.id, "hotspots", reason="manual refresh")

    refreshed_markdown = store.read_text(run.draft.markdown_path)
    assert "用户已经手工确认过的主文章内容。" in refreshed_markdown
    assert "旧热点内容。" not in refreshed_markdown
    assert "旧 arXiv 内容。" in refreshed_markdown


def test_refresh_api_exposes_status_due_refresh_and_module_refresh(tmp_path: Path):
    client = TestClient(create_app(storage_root=tmp_path))

    status = client.get("/api/refresh/status?now=2026-06-20T10:30:00")
    assert status.status_code == 200
    assert status.json()["seconds_until_next_refresh"] == 1800

    due = client.post("/api/refresh/due?now=2026-06-20T11:05:00")
    assert due.status_code == 200
    assert due.json()["today_refreshed"] is True

    radar = client.get("/api/radar/today?date=2026-06-20").json()
    manual = client.post("/api/refresh/today?now=2026-06-20T14:30:00")
    assert manual.status_code == 200
    assert manual.json()["selected_topic"]["id"] != radar["recommended_topic"]["id"]

    radar = client.get("/api/radar/today?date=2026-06-20").json()
    refreshed = client.post(f"/api/drafts/{radar['draft']['id']}/refresh-module", json={"module": "arxiv"})
    assert refreshed.status_code == 200
    assert refreshed.json()["last_rerun_stage"] == "refresh:arxiv"


def test_api_startup_does_not_refresh_by_default(tmp_path: Path):
    app = create_app(storage_root=tmp_path, startup_now=datetime(2026, 6, 20, 11, 5))

    with TestClient(app):
        assert JsonStore(tmp_path).get_run("2026-06-20") is None


def test_api_startup_auto_refreshes_once_when_service_starts_after_11(tmp_path: Path):
    app = create_app(
        storage_root=tmp_path,
        auto_refresh_on_startup=True,
        startup_now=datetime(2026, 6, 20, 11, 5),
    )

    with TestClient(app):
        store = JsonStore(tmp_path)
        assert store.get_run("2026-06-20") is not None
        assert store.get_refresh("2026-06-20")["last_refresh_at"] == "2026-06-20T11:05:00"
