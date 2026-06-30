# 每日论文选题量化评分系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将每日 `long_articles` 从 LLM 自由选择改为代码量化评分排序，最终 5 条长文候选可审计、可解释、可复现。

**Architecture:** 新增 `apps/api/ai_radar/scoring.py` 作为独立评分边界，读取 `influence_sources.json`，对 `Paper` 计算 `PaperScore` 并选出前 5 篇。`DailyPipeline` 在生成 topic pack 前锁定这 5 篇，LLM 只生成展示文案，后端保留锁定论文来源和评分明细。

**Tech Stack:** FastAPI、Pydantic、pytest、React、TypeScript、Vitest、本地 JSON store。

---

## 文件结构

- Create: `apps/api/ai_radar/influence_sources.json`  
  维护高影响力机构、人物和域名名单。配置损坏时刷新失败。

- Create: `apps/api/ai_radar/scoring.py`  
  负责影响力配置读取、论文评分、历史重复惩罚、排序、评分报告 JSON 结构生成。

- Modify: `apps/api/ai_radar/models.py`  
  给 `TopicPackItem` 增加 `score_detail: Dict[str, object] = Field(default_factory=dict)`，兼容旧数据。

- Modify: `apps/api/ai_radar/pipeline.py`  
  在 topic pack 生成时锁定前 5 篇长文论文；LLM 只生成文案；写入 `long-article-scores.json`；保留 `ai_hotspots` 和 `arxiv_papers` 原逻辑。

- Modify: `apps/api/ai_radar/storage.py`  
  如果已有便捷写文件方法可复用，不新增；如果缺少 topic pack 目录写入方法，新增一个窄方法 `topic_pack_dir(date, version)`。

- Modify: `apps/web/src/api.ts`  
  给 `TopicPackItem` 类型增加可选 `score_detail`。

- Modify: `apps/web/src/App.tsx`  
  在长文候选卡片展示简短评分行；旧数据无评分时隐藏。

- Modify: `apps/web/src/App.test.tsx`  
  覆盖评分行展示和旧数据兼容。

- Create: `apps/api/tests/test_scoring.py`  
  评分器单元测试。

- Modify: `apps/api/tests/test_refresh.py`  
  覆盖 `/api/topic-packs/refresh` 长文锁定、评分明细、LLM 不能换论文、调试文件生成。

---

### Task 1: 增加 TopicPackItem 评分字段

**Files:**
- Modify: `apps/api/ai_radar/models.py`
- Modify: `apps/web/src/api.ts`
- Test: `apps/api/tests/test_refresh.py`

- [ ] **Step 1: 写后端模型兼容测试**

在 `apps/api/tests/test_refresh.py` 增加测试，放在 topic pack 相关测试附近：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py::test_topic_pack_item_score_detail_defaults_to_empty_dict -q
```

Expected: FAIL，错误包含 `TopicPackItem` 没有 `score_detail` 属性。

- [ ] **Step 3: 给 Pydantic 模型增加字段**

在 `apps/api/ai_radar/models.py` 的 `TopicPackItem` 中加入：

```python
    score_detail: Dict[str, object] = Field(default_factory=dict)
```

字段放在 `angle_hash` 后面，保持旧 JSON 数据可加载。

- [ ] **Step 4: 更新前端类型**

在 `apps/web/src/api.ts` 的 `TopicPackItem` 中加入：

```typescript
  score_detail?: Record<string, unknown>;
```

- [ ] **Step 5: 运行后端测试确认通过**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py::test_topic_pack_item_score_detail_defaults_to_empty_dict -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add apps/api/ai_radar/models.py apps/web/src/api.ts apps/api/tests/test_refresh.py
git commit -m "Add topic pack score detail field"
```

---

### Task 2: 新增影响力配置读取

**Files:**
- Create: `apps/api/ai_radar/influence_sources.json`
- Create: `apps/api/ai_radar/scoring.py`
- Test: `apps/api/tests/test_scoring.py`

- [ ] **Step 1: 写配置加载测试**

创建 `apps/api/tests/test_scoring.py`，写入：

```python
import json
from pathlib import Path

import pytest

from ai_radar.scoring import InfluenceConfigError, load_influence_config


def test_load_influence_config_reads_institutions_people_and_domains(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text(
        json.dumps(
            {
                "institutions": [{"name": "OpenAI", "aliases": ["openai"], "weight": 25}],
                "people": [{"name": "Yann LeCun", "aliases": ["yann lecun"], "weight": 20}],
                "source_domains": [{"domain": "openai.com", "weight": 18}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = load_influence_config(path)

    assert config.institutions[0].name == "OpenAI"
    assert config.people[0].aliases == ["yann lecun"]
    assert config.source_domains[0].domain == "openai.com"


def test_load_influence_config_reports_broken_json_path(tmp_path: Path):
    path = tmp_path / "influence_sources.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(InfluenceConfigError) as error:
        load_influence_config(path)

    assert str(path) in str(error.value)
    assert "JSON" in str(error.value)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_scoring.py -q
```

Expected: FAIL，错误包含 `No module named 'ai_radar.scoring'`。

- [ ] **Step 3: 创建影响力配置文件**

创建 `apps/api/ai_radar/influence_sources.json`：

```json
{
  "institutions": [
    {"name": "OpenAI", "aliases": ["openai"], "weight": 25},
    {"name": "Anthropic", "aliases": ["anthropic"], "weight": 24},
    {"name": "Google DeepMind", "aliases": ["google deepmind", "deepmind"], "weight": 25},
    {"name": "Google Research", "aliases": ["google research"], "weight": 22},
    {"name": "Meta AI", "aliases": ["meta ai", "facebook ai"], "weight": 22},
    {"name": "Microsoft Research", "aliases": ["microsoft research", "msr"], "weight": 22},
    {"name": "NVIDIA", "aliases": ["nvidia"], "weight": 21},
    {"name": "Apple", "aliases": ["apple machine learning", "apple"], "weight": 20},
    {"name": "xAI", "aliases": ["xai"], "weight": 20},
    {"name": "DeepSeek", "aliases": ["deepseek"], "weight": 22},
    {"name": "Qwen", "aliases": ["qwen", "alibaba qwen"], "weight": 20},
    {"name": "Alibaba", "aliases": ["alibaba", "alibaba damo"], "weight": 20},
    {"name": "ByteDance", "aliases": ["bytedance", "byte dance"], "weight": 20},
    {"name": "Tencent AI Lab", "aliases": ["tencent ai lab", "tencent"], "weight": 18},
    {"name": "Tsinghua University", "aliases": ["tsinghua university", "tsinghua"], "weight": 18},
    {"name": "Stanford", "aliases": ["stanford university", "stanford"], "weight": 18},
    {"name": "MIT", "aliases": ["mit", "massachusetts institute of technology"], "weight": 18},
    {"name": "UC Berkeley", "aliases": ["uc berkeley", "berkeley"], "weight": 18},
    {"name": "CMU", "aliases": ["carnegie mellon", "cmu"], "weight": 18}
  ],
  "people": [
    {"name": "Yann LeCun", "aliases": ["yann lecun", "lecun"], "weight": 20},
    {"name": "Geoffrey Hinton", "aliases": ["geoffrey hinton", "hinton"], "weight": 20},
    {"name": "Yoshua Bengio", "aliases": ["yoshua bengio", "bengio"], "weight": 20},
    {"name": "Ilya Sutskever", "aliases": ["ilya sutskever"], "weight": 20},
    {"name": "Andrej Karpathy", "aliases": ["andrej karpathy", "karpathy"], "weight": 18},
    {"name": "François Chollet", "aliases": ["françois chollet", "francois chollet", "chollet"], "weight": 18},
    {"name": "Demis Hassabis", "aliases": ["demis hassabis", "hassabis"], "weight": 18},
    {"name": "Fei-Fei Li", "aliases": ["fei-fei li", "feifei li"], "weight": 18},
    {"name": "Pieter Abbeel", "aliases": ["pieter abbeel", "abbeel"], "weight": 18},
    {"name": "Andrew Ng", "aliases": ["andrew ng"], "weight": 18}
  ],
  "source_domains": [
    {"domain": "openai.com", "weight": 18},
    {"domain": "anthropic.com", "weight": 18},
    {"domain": "deepmind.google", "weight": 18},
    {"domain": "ai.meta.com", "weight": 16},
    {"domain": "blogs.nvidia.com", "weight": 16},
    {"domain": "microsoft.com", "weight": 14},
    {"domain": "apple.com", "weight": 14},
    {"domain": "deepseek.com", "weight": 16},
    {"domain": "qwenlm.github.io", "weight": 14}
  ]
}
```

- [ ] **Step 4: 创建配置加载实现**

创建 `apps/api/ai_radar/scoring.py`，写入：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


class InfluenceConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class InfluenceEntry:
    name: str
    aliases: List[str]
    weight: int


@dataclass(frozen=True)
class SourceDomainEntry:
    domain: str
    weight: int


@dataclass(frozen=True)
class InfluenceConfig:
    institutions: List[InfluenceEntry]
    people: List[InfluenceEntry]
    source_domains: List[SourceDomainEntry]


def default_influence_config_path() -> Path:
    return Path(__file__).with_name("influence_sources.json")


def load_influence_config(path: Path | None = None) -> InfluenceConfig:
    config_path = path or default_influence_config_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InfluenceConfigError(f"影响力配置 JSON 解析失败: {config_path}: {error}") from error
    except OSError as error:
        raise InfluenceConfigError(f"影响力配置读取失败: {config_path}: {error}") from error

    return InfluenceConfig(
        institutions=[
            InfluenceEntry(
                name=str(item["name"]),
                aliases=[str(alias).lower() for alias in item.get("aliases", [])],
                weight=int(item.get("weight", 0)),
            )
            for item in payload.get("institutions", [])
        ],
        people=[
            InfluenceEntry(
                name=str(item["name"]),
                aliases=[str(alias).lower() for alias in item.get("aliases", [])],
                weight=int(item.get("weight", 0)),
            )
            for item in payload.get("people", [])
        ],
        source_domains=[
            SourceDomainEntry(domain=str(item["domain"]).lower(), weight=int(item.get("weight", 0)))
            for item in payload.get("source_domains", [])
        ],
    )
```

- [ ] **Step 5: 运行配置测试确认通过**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_scoring.py -q
```

Expected: PASS，2 passed。

- [ ] **Step 6: 提交**

```bash
git add apps/api/ai_radar/influence_sources.json apps/api/ai_radar/scoring.py apps/api/tests/test_scoring.py
git commit -m "Add influence source config loader"
```

---

### Task 3: 实现论文评分器

**Files:**
- Modify: `apps/api/ai_radar/scoring.py`
- Test: `apps/api/tests/test_scoring.py`

- [ ] **Step 1: 写评分测试**

追加到 `apps/api/tests/test_scoring.py`：

```python
from ai_radar.models import Paper, Signal
from ai_radar.scoring import score_papers


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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_scoring.py::test_score_papers_rewards_influential_institutions_and_methods apps/api/tests/test_scoring.py::test_score_papers_applies_history_penalty -q
```

Expected: FAIL，错误包含 `cannot import name 'score_papers'`。

- [ ] **Step 3: 实现评分数据结构和关键词**

追加到 `apps/api/ai_radar/scoring.py`：

```python
from dataclasses import asdict
from typing import Dict, Iterable, Mapping
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
```

- [ ] **Step 4: 实现评分函数**

继续追加到 `apps/api/ai_radar/scoring.py`：

```python
def score_papers(
    papers: List[Paper],
    signals: List[Signal],
    previous_items: List[Mapping[str, object]],
    config_path: Path | None = None,
) -> List[PaperScore]:
    config = load_influence_config(config_path)
    scores = [_score_one_paper(paper, signals, previous_items, config) for paper in papers if paper.pdf_url or paper.arxiv_id]
    return sorted(
        scores,
        key=lambda item: (
            -item.total_score,
            -int(item.score_detail["influence_score"]["value"]),
            -int(item.score_detail["experiment_strength"]["value"]),
            item.paper.published_at,
            item.paper.title.lower(),
        ),
    )


def _score_one_paper(
    paper: Paper,
    signals: List[Signal],
    previous_items: List[Mapping[str, object]],
    config: InfluenceConfig,
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
    freshness_and_heat = min(10, len(related_signals) * 3 + (2 if paper.published_at.startswith("2026-06-30") else 0))
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
    if history_penalty:
        reasons.append("历史重复惩罚")
    if low_ai_penalty:
        reasons.append("AI 相关性弱惩罚")

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
        "penalties": {"value": penalties, "reason": "；".join(reasons[-2:]) if penalties else "无扣分"},
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
    arxiv_abs = f"arxiv.org/abs/{paper.arxiv_id}".lower()
    arxiv_pdf = f"arxiv.org/pdf/{paper.arxiv_id}".lower()
    return [
        signal
        for signal in signals
        if paper.arxiv_id.lower() in signal.url.lower()
        or arxiv_abs in signal.url.lower()
        or arxiv_pdf in signal.url.lower()
        or signal.title.strip().lower() == paper.title.strip().lower()
    ]


def _match_entries(text: str, entries: List[InfluenceEntry]) -> tuple[List[str], int]:
    matched: List[str] = []
    score = 0
    for entry in entries:
        if any(alias and alias in text for alias in entry.aliases):
            matched.append(entry.name)
            score = max(score, entry.weight)
    return matched, score


def _match_domains(signals: List[Signal], entries: List[SourceDomainEntry]) -> tuple[List[str], int]:
    matched: List[str] = []
    score = 0
    for signal in signals:
        host = urlparse(signal.url).netloc.lower()
        for entry in entries:
            if entry.domain in host:
                matched.append(entry.domain)
                score = max(score, entry.weight)
    return sorted(set(matched)), score


def _history_penalty(paper: Paper, previous_items: List[Mapping[str, object]]) -> int:
    paper_urls = {paper.pdf_url.rstrip("/"), f"https://arxiv.org/abs/{paper.arxiv_id}".rstrip("/")}
    for item in previous_items:
        if str(item.get("arxiv_id") or "") == paper.arxiv_id:
            return 30
        source_urls = {str(url).rstrip("/") for url in item.get("source_urls", []) if str(url).strip()}
        if source_urls.intersection(paper_urls):
            return 30
    return 0
```

- [ ] **Step 5: 运行评分测试确认通过**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_scoring.py -q
```

Expected: PASS，4 passed。

- [ ] **Step 6: 提交**

```bash
git add apps/api/ai_radar/scoring.py apps/api/tests/test_scoring.py
git commit -m "Add quantitative paper scoring"
```

---

### Task 4: 在 topic pack 生成中锁定长文前 5 篇

**Files:**
- Modify: `apps/api/ai_radar/pipeline.py`
- Test: `apps/api/tests/test_refresh.py`

- [ ] **Step 1: 写 LLM 不能替换论文的集成测试**

在 `apps/api/tests/test_refresh.py` 增加：

```python
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


def test_topic_pack_long_articles_are_selected_by_scores_not_llm(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store, llm_provider=ReplacingLongArticleLLM())

    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="score locked")

    assert len(pack.long_articles) == 5
    assert all(item.arxiv_id != "9999.00001" for item in pack.long_articles)
    assert all(item.score_detail for item in pack.long_articles)
    totals = [item.score_detail["total_score"]["value"] for item in pack.long_articles]
    assert totals == sorted(totals, reverse=True)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py::test_topic_pack_long_articles_are_selected_by_scores_not_llm -q
```

Expected: FAIL，当前 `long_articles` 会使用 LLM 返回的 `9999.*` 论文。

- [ ] **Step 3: 修改 pipeline 导入评分器**

在 `apps/api/ai_radar/pipeline.py` 顶部加入：

```python
from .scoring import PaperScore, score_papers
```

- [ ] **Step 4: 增加历史条目收集和锁定长文生成**

在 `DailyPipeline` 类中添加私有方法，放在 `_create_topic_pack_version` 前：

```python
    def _previous_topic_pack_items(self, run_date: str) -> List[Dict[str, object]]:
        return [
            item.model_dump(mode="json")
            for pack in self.store.list_topic_pack_versions(run_date)
            for item in [*pack.long_articles, *pack.ai_hotspots, *pack.arxiv_papers]
        ]

    def _score_long_article_papers(self, run: DailyRun) -> List[PaperScore]:
        scores = score_papers(
            run.papers,
            run.signals,
            self._previous_topic_pack_items(run.date),
        )
        if len(scores) < 5:
            raise RuntimeError("可评分论文不足 5 篇")
        return scores

    def _locked_long_article_items(
        self,
        run_date: str,
        version: int,
        scores: List[PaperScore],
        llm_items: List[TopicPackItem],
        llm_response_id: str,
    ) -> List[TopicPackItem]:
        text_by_rank = {item.rank: item for item in llm_items}
        locked: List[TopicPackItem] = []
        for index, score in enumerate(scores[:5], start=1):
            paper = score.paper
            text_item = text_by_rank.get(index)
            title = text_item.title if text_item else paper.title
            summary = text_item.summary if text_item else paper.abstract[:280]
            angle = text_item.angle if text_item else "从问题、方法、实验和局限四个角度展开论文解读。"
            locked.append(
                self._make_topic_pack_item(
                    run_date=run_date,
                    version=version,
                    module="long_articles",
                    rank=index,
                    title=title,
                    summary=summary,
                    angle=angle,
                    source_urls=[f"https://arxiv.org/abs/{paper.arxiv_id}", paper.pdf_url],
                    arxiv_id=paper.arxiv_id,
                    llm_response_id=llm_response_id,
                    score_detail=_score_detail_for_topic_pack(score),
                )
            )
        return locked
```

- [ ] **Step 5: 增加 score detail 转换 helper**

在 `apps/api/ai_radar/pipeline.py` 文件底部工具函数区加入：

```python
def _score_detail_for_topic_pack(score: PaperScore) -> Dict[str, object]:
    return {
        "total_score": {"value": score.total_score, "reason": "按量化评分公式计算"},
        **score.score_detail,
        "selection_reasons": score.selection_reasons,
        "matched_institutions": score.matched_institutions,
        "matched_people": score.matched_people,
        "matched_source_domains": score.matched_source_domains,
        "matched_signals": score.matched_signals,
    }
```

- [ ] **Step 6: 扩展 _make_topic_pack_item 参数**

修改 `_make_topic_pack_item` 签名，增加默认参数：

```python
        score_detail: Dict[str, object] | None = None,
```

在返回 `TopicPackItem(...)` 时加入：

```python
            score_detail=score_detail or {},
```

- [ ] **Step 7: 在 _create_topic_pack_version 中锁定长文**

在 `_create_topic_pack_version` 中，`generated = ...` 后添加：

```python
        long_article_scores = self._score_long_article_papers(run)
```

把 `long_articles = ...` 那段替换为：

```python
        if generation_module in {"long_articles", "all"}:
            llm_long_articles = self._items_from_payload(
                run.date,
                next_version,
                "long_articles",
                generated.get("long_articles"),
                response_id,
            )
            long_articles = self._locked_long_article_items(
                run.date,
                next_version,
                long_article_scores,
                llm_long_articles,
                response_id,
            )
        else:
            long_articles = previous.long_articles if previous else []
```

不要改 `ai_hotspots` 和 `arxiv_papers` 的现有逻辑。

- [ ] **Step 8: 运行锁定测试确认通过**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py::test_topic_pack_long_articles_are_selected_by_scores_not_llm -q
```

Expected: PASS。

- [ ] **Step 9: 运行相关刷新测试**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py -q
```

Expected: PASS。

- [ ] **Step 10: 提交**

```bash
git add apps/api/ai_radar/pipeline.py apps/api/tests/test_refresh.py
git commit -m "Lock long articles to quantitative scores"
```

---

### Task 5: 保存完整评分报告文件

**Files:**
- Modify: `apps/api/ai_radar/scoring.py`
- Modify: `apps/api/ai_radar/storage.py`
- Modify: `apps/api/ai_radar/pipeline.py`
- Test: `apps/api/tests/test_refresh.py`

- [ ] **Step 1: 写调试文件测试**

在 `apps/api/tests/test_refresh.py` 增加：

```python
def test_topic_pack_refresh_writes_long_article_score_report(tmp_path: Path):
    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=TopicPackLLM())

    pack = pipeline.refresh_topic_pack("2026-06-20", module="all", reason="score report")

    report_path = tmp_path / "topic-packs" / "2026-06-20" / "v01" / "long-article-scores.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["topic_pack_id"] == pack.id
    assert len(payload["papers"]) >= 5
    assert payload["papers"][0]["rank"] == 1
    assert payload["papers"][0]["selected"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py::test_topic_pack_refresh_writes_long_article_score_report -q
```

Expected: FAIL，报告文件不存在。

- [ ] **Step 3: 在 scoring.py 增加报告构建函数**

追加：

```python
def build_score_report(topic_pack_id: str, scores: List[PaperScore]) -> Dict[str, object]:
    return {
        "topic_pack_id": topic_pack_id,
        "papers": [score.to_report_dict(rank=index, selected=index <= 5) for index, score in enumerate(scores, start=1)],
    }
```

- [ ] **Step 4: 在 storage.py 增加目录 helper**

如果 `JsonStore` 没有同等方法，在类中增加：

```python
    def topic_pack_dir(self, date: str, version: int) -> Path:
        path = self.root / "topic-packs" / date / f"v{version:02d}"
        path.mkdir(parents=True, exist_ok=True)
        return path
```

- [ ] **Step 5: 在 pipeline.py 写报告**

导入：

```python
from .scoring import PaperScore, build_score_report, score_papers
```

在 `_create_topic_pack_version` 创建 `pack` 并 `_validate_topic_pack(pack)` 之后、`self.store.add_topic_pack_version(pack)` 之前加入：

```python
        if generation_module in {"long_articles", "all"}:
            report_path = self.store.topic_pack_dir(run.date, next_version) / "long-article-scores.json"
            report_path.write_text(
                json.dumps(build_score_report(pack.id, long_article_scores), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
```

- [ ] **Step 6: 运行报告测试确认通过**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_refresh.py::test_topic_pack_refresh_writes_long_article_score_report -q
```

Expected: PASS。

- [ ] **Step 7: 运行相关测试**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/test_scoring.py apps/api/tests/test_refresh.py -q
```

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add apps/api/ai_radar/scoring.py apps/api/ai_radar/storage.py apps/api/ai_radar/pipeline.py apps/api/tests/test_refresh.py
git commit -m "Write long article score reports"
```

---

### Task 6: 前端展示评分摘要

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/App.test.tsx`

- [ ] **Step 1: 写前端展示测试**

在 `apps/web/src/App.test.tsx` 的 topic pack 相关测试中增加断言数据。给 `topicPack.long_articles[0]` 添加：

```typescript
score_detail: {
  total_score: { value: 87, reason: "按量化评分公式计算" },
  influence_score: { value: 25, reason: "命中 Google DeepMind" },
  method_substance: { value: 18, reason: "方法关键词命中 4 个" },
  experiment_strength: { value: 12, reason: "实验关键词命中 3 个" },
  selection_reasons: ["总分进入前 5", "命中高影响力机构"]
}
```

新增测试：

```typescript
it("shows score summary for scored long article candidates", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialTopicPack={topicPack}
    />
  );

  expect(screen.getByText("总分 87 | 影响力 25 | 方法 18 | 实验 12")).toBeInTheDocument();
  expect(screen.getByText("入选原因：总分进入前 5；命中高影响力机构")).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行前端测试确认失败**

Run:

```bash
npm run test --workspace apps/web -- --run App.test.tsx
```

Expected: FAIL，找不到评分摘要文本。

- [ ] **Step 3: 扩展 TypeScript 类型**

在 `apps/web/src/api.ts` 增加：

```typescript
export type TopicPackScoreDetail = {
  total_score?: ScoreItem;
  influence_score?: ScoreItem;
  method_substance?: ScoreItem;
  experiment_strength?: ScoreItem;
  selection_reasons?: string[];
  [key: string]: unknown;
};
```

并把 `TopicPackItem.score_detail` 改为：

```typescript
  score_detail?: TopicPackScoreDetail;
```

- [ ] **Step 4: 增加前端格式化函数**

在 `apps/web/src/App.tsx` 的 `TopicPackModulePanel` 前加入：

```typescript
function topicPackScoreSummary(item: TopicPackItem): { line: string; reasons: string } | null {
  const score = item.score_detail;
  if (!score?.total_score || typeof score.total_score.value !== "number") {
    return null;
  }
  const influence = typeof score.influence_score?.value === "number" ? score.influence_score.value : 0;
  const method = typeof score.method_substance?.value === "number" ? score.method_substance.value : 0;
  const experiment = typeof score.experiment_strength?.value === "number" ? score.experiment_strength.value : 0;
  const reasons = Array.isArray(score.selection_reasons) ? score.selection_reasons.join("；") : "";
  return {
    line: `总分 ${score.total_score.value} | 影响力 ${influence} | 方法 ${method} | 实验 ${experiment}`,
    reasons: reasons ? `入选原因：${reasons}` : ""
  };
}
```

- [ ] **Step 5: 在卡片中展示评分**

在 `TopicPackModulePanel` 的 `items.map` 中，`<small>{item.angle}</small>` 后加入：

```tsx
              {item.module === "long_articles" && topicPackScoreSummary(item) ? (
                <div className="topic-pack-item__score">
                  <strong>{topicPackScoreSummary(item)?.line}</strong>
                  {topicPackScoreSummary(item)?.reasons ? <span>{topicPackScoreSummary(item)?.reasons}</span> : null}
                </div>
              ) : null}
```

如果要避免重复调用，可以在 map 内第一行改成块体：

```tsx
{items.map((item) => {
  const scoreSummary = item.module === "long_articles" ? topicPackScoreSummary(item) : null;
  return (
    <article className="topic-pack-item" key={item.id}>
      ...
      {scoreSummary ? (
        <div className="topic-pack-item__score">
          <strong>{scoreSummary.line}</strong>
          {scoreSummary.reasons ? <span>{scoreSummary.reasons}</span> : null}
        </div>
      ) : null}
      ...
    </article>
  );
})}
```

使用第二种块体写法，避免重复计算。

- [ ] **Step 6: 增加 CSS**

在 `apps/web/src/styles.css` 加入：

```css
.topic-pack-item__score {
  display: grid;
  gap: 4px;
  margin: 10px 0;
  padding: 8px 10px;
  border-left: 3px solid #2563eb;
  background: rgba(37, 99, 235, 0.08);
  color: #1f2937;
}

.topic-pack-item__score strong {
  font-size: 13px;
  font-weight: 700;
}

.topic-pack-item__score span {
  font-size: 12px;
  line-height: 1.5;
  color: #4b5563;
}
```

- [ ] **Step 7: 运行前端测试确认通过**

Run:

```bash
npm run test --workspace apps/web -- --run App.test.tsx
```

Expected: PASS。

- [ ] **Step 8: 运行前端构建**

Run:

```bash
npm run build --workspace apps/web
```

Expected: build succeeds。

- [ ] **Step 9: 提交**

```bash
git add apps/web/src/api.ts apps/web/src/App.tsx apps/web/src/App.test.tsx apps/web/src/styles.css
git commit -m "Show long article score summaries"
```

---

### Task 7: 全链路回归和运行时验证

**Files:**
- Modify only if tests reveal bugs in previous tasks.

- [ ] **Step 1: 运行后端测试**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests -q
```

Expected: PASS。

- [ ] **Step 2: 运行前端测试**

Run:

```bash
npm run test --workspace apps/web -- --run
```

Expected: PASS。

- [ ] **Step 3: 运行前端构建**

Run:

```bash
npm run build --workspace apps/web
```

Expected: build succeeds。

- [ ] **Step 4: 手动刷新 topic pack**

确保后端使用当前代码启动：

```bash
PYTHONPATH=apps/api .venv/bin/python -m uvicorn ai_radar.api:app --host 127.0.0.1 --port 8000
```

另一个终端运行：

```bash
curl -s -X POST "http://127.0.0.1:8000/api/topic-packs/refresh" \
  -H "Content-Type: application/json" \
  --data '{"date":"2026-06-30","module":"all","reason":"quantitative scoring smoke"}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["id"], len(d["long_articles"]), [i["score_detail"]["total_score"]["value"] for i in d["long_articles"]])'
```

Expected:

```text
topic-pack-2026-06-30-vNN 5 [分数列表]
```

分数列表按降序排列。

- [ ] **Step 5: 检查评分报告**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
paths = sorted(Path("storage/topic-packs/2026-06-30").glob("v*/long-article-scores.json"))
latest = paths[-1]
payload = json.loads(latest.read_text(encoding="utf-8"))
print(latest)
print(payload["topic_pack_id"])
print(len(payload["papers"]))
print(payload["papers"][0]["selected"], payload["papers"][0]["total_score"])
PY
```

Expected: prints latest report path, topic pack id, at least 5 scored papers, first paper selected is `True`.

- [ ] **Step 6: 提交验证修复**

If Step 1-5 required code changes:

```bash
git add apps/api apps/web
git commit -m "Fix quantitative scoring integration"
```

If no code changes were needed, do not create an empty commit.

---

## 自检清单

- Spec coverage:
  - 可量化前 5：Task 3、Task 4。
  - 高影响力加权：Task 2、Task 3。
  - LLM 不能替换论文：Task 4。
  - score_detail：Task 1、Task 4、Task 6。
  - 完整评分调试文件：Task 5。
  - 前端轻量展示：Task 6。
  - 错误处理：Task 2、Task 4、Task 7。

- No placeholders:
  - 本计划不包含 TBD、TODO、待实现占位。
  - 每个代码任务都包含测试、运行命令、实现片段和预期结果。

- Type consistency:
  - 后端字段名统一为 `score_detail`。
  - 前端类型统一为 `TopicPackScoreDetail`。
  - 评分器输出统一为 `PaperScore.total_score` 和 `score_detail["..."]["value"]`。
