# 长文章生成优化实现计划

> **给执行 agent：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行本计划。所有步骤使用 `- [ ]` 复选框语法跟踪。

**目标：** 把“生成长文”改成强制读取论文全文、结构化生成中文专业解读、插入统一风格封面图和文中机制图，并在前端完整预览图文稿件。

**架构：** 新增一个后端长文章生成边界，负责全文解析、写作计划、正文生成、降 AI 味、图位组装和资产状态。现有 `DailyPipeline.refresh_module(..., "main")` 只调用这个边界，前端继续通过现有接口刷新稿件详情。PDF 解析先做适配层，优先支持可注入解析器和外部命令，避免把业务代码绑定到某个大型第三方项目。

**技术栈：** Python 3、FastAPI、Pydantic、httpx、pytest、React、TypeScript、Vitest、现有 `LLM Responses` 和 `image2` 适配器。

---

## 文件结构

- 新建：`apps/api/ai_radar/paper_parser.py`
  - 下载 PDF、调用可注入解析器、保存 `paper/fulltext.md`、`paper/figures/*`、`paper/parse.json`。
- 新建：`apps/api/ai_radar/long_article.py`
  - 定义写作计划、正文片段、图位、视觉风格模型；封装 LLM JSON 解析、降 AI 味、Markdown 组装。
- 修改：`apps/api/ai_radar/models.py`
  - 扩展 `DraftAsset`：`status`、`error`、`slot_id`、`insert_after_section_id`、`caption`、`source_refs`、`style_id`。
- 修改：`apps/api/ai_radar/pipeline.py`
  - 移除主文章本地兜底路径；`refresh_module(main)` 改用新长文生成器；HTML 渲染支持图片。
- 修改：`apps/web/src/api.ts`
  - 同步 `DraftAsset` 类型字段。
- 修改：`apps/web/src/App.tsx`
  - 阅读模式渲染 HTML 而不是 `pre`；Markdown 预览支持图片；素材区显示状态和错误。
- 修改：`apps/web/src/styles.css`
  - 图片预览、失败提示、素材状态的最小样式。
- 测试：`apps/api/tests/test_long_article.py`
  - 覆盖全文解析失败、LLM JSON 失败、图片失败保留正文、统一 `style_id`。
- 测试：`apps/api/tests/test_pipeline.py`
  - 更新旧兜底预期，主文章失败不再退回模板。
- 测试：`apps/web/src/App.test.tsx`
  - 覆盖图片预览、非 `pre` 阅读模式、素材状态。

---

## 任务 1: 扩展稿件资产模型

**文件：**
- 修改：`apps/api/ai_radar/models.py`
- 修改：`apps/web/src/api.ts`
- 测试：`apps/api/tests/test_long_article.py`

- [ ] **步骤 1: 写失败测试**

新建 `apps/api/tests/test_long_article.py`，内容为：

```python
from ai_radar.models import DraftAsset


def test_draft_asset_supports_generation_status_and_style_metadata():
    asset = DraftAsset(
        id="asset-draft-1-cover",
        draft_id="draft-1",
        kind="cover",
        prompt="画一张清晰抓眼的手绘风封面图",
        path="drafts/2026-06-30/topic/cover.png",
        status="failed",
        error="image2 超时",
        slot_id="cover",
        insert_after_section_id="",
        caption="公众号封面图",
        source_refs=["paper:section:method"],
        style_id="handdrawn-doodle-v1",
    )

    assert asset.status == "failed"
    assert asset.error == "image2 超时"
    assert asset.style_id == "handdrawn-doodle-v1"
    assert asset.source_refs == ["paper:section:method"]
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_draft_asset_supports_generation_status_and_style_metadata -q
```

预期：失败，错误包含未知字段或缺失字段。

- [ ] **步骤 3: 最小实现**

在 `apps/api/ai_radar/models.py` 中更新 `DraftAsset`：

```python
class DraftAsset(BaseModel):
    id: str
    draft_id: str
    kind: Literal["cover", "mechanism", "quote", "source_file"]
    prompt: str
    revised_prompt: Optional[str] = None
    path: str
    width: int = 1536
    height: int = 1024
    provider: str = "image2"
    provider_request_id: Optional[str] = None
    status: Literal["ready", "failed"] = "ready"
    error: str = ""
    slot_id: str = ""
    insert_after_section_id: str = ""
    caption: str = ""
    source_refs: List[str] = Field(default_factory=list)
    style_id: str = ""
    created_at: str
```

在 `apps/web/src/api.ts` 中更新 `DraftAsset`：

```ts
export type DraftAsset = {
  id: string;
  draft_id: string;
  kind: "cover" | "mechanism" | "quote" | "source_file";
  prompt: string;
  revised_prompt: string | null;
  path: string;
  width: number;
  height: number;
  provider: string;
  provider_request_id: string | null;
  status: "ready" | "failed";
  error: string;
  slot_id: string;
  insert_after_section_id: string;
  caption: string;
  source_refs: string[];
  style_id: string;
  created_at: string;
};
```

- [ ] **步骤 4: 确认测试通过**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_draft_asset_supports_generation_status_and_style_metadata -q
```

预期：通过。

- [ ] **步骤 5: 提交**

```bash
rtk git add apps/api/ai_radar/models.py apps/web/src/api.ts apps/api/tests/test_long_article.py
rtk git commit -m "Add draft asset status metadata"
```

---

## 任务 2: 新增论文全文解析适配层

**文件：**
- 新建：`apps/api/ai_radar/paper_parser.py`
- 测试：`apps/api/tests/test_long_article.py`

- [ ] **步骤 1: 写成功和失败测试**

追加到 `apps/api/tests/test_long_article.py`：

```python
from pathlib import Path

import pytest

from ai_radar.paper_parser import PaperParseError, PaperParser


class FakePDFResponse:
    content = b"%PDF-1.4 fake"

    def raise_for_status(self):
        return None


class FakeHTTPClient:
    def get(self, url):
        assert url == "https://arxiv.org/pdf/2501.04227"
        return FakePDFResponse()


def fake_parse_command(pdf_path: Path, output_dir: Path):
    assert pdf_path.name == "paper.pdf"
    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    (figures / "figure-1.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return {
        "title": "Agent Laboratory",
        "abstract": "This paper studies research agents.",
        "sections": [{"id": "method", "heading": "Method", "text": "Planner reviewer executor workflow."}],
        "figures": [{"id": "paper-fig-1", "path": "paper/figures/figure-1.png", "caption": "Workflow overview"}],
        "tables": [],
        "experiment_sections": ["method"],
        "limitation_sections": ["method"],
    }


def test_paper_parser_downloads_pdf_and_writes_parse_outputs(tmp_path: Path):
    parser = PaperParser(http_client=FakeHTTPClient(), parse_command=fake_parse_command)

    result = parser.parse_pdf("https://arxiv.org/pdf/2501.04227", tmp_path)

    assert result.fulltext_path == Path("paper/fulltext.md")
    assert result.parse_json_path == Path("paper/parse.json")
    assert result.figures[0]["caption"] == "Workflow overview"
    assert (tmp_path / "paper" / "paper.pdf").exists()
    assert (tmp_path / "paper" / "fulltext.md").read_text(encoding="utf-8").startswith("# Agent Laboratory")


def test_paper_parser_fails_when_parser_returns_no_sections(tmp_path: Path):
    parser = PaperParser(
        http_client=FakeHTTPClient(),
        parse_command=lambda pdf_path, output_dir: {"title": "Bad", "sections": [], "figures": [], "tables": []},
    )

    with pytest.raises(PaperParseError, match="no sections"):
        parser.parse_pdf("https://arxiv.org/pdf/2501.04227", tmp_path)
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_paper_parser_downloads_pdf_and_writes_parse_outputs apps/api/tests/test_long_article.py::test_paper_parser_fails_when_parser_returns_no_sections -q
```

预期：失败，错误包含 `ModuleNotFoundError: No module named 'ai_radar.paper_parser'`。

- [ ] **步骤 3: 最小实现**

新建 `apps/api/ai_radar/paper_parser.py`：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

import httpx


class PaperParseError(RuntimeError):
    pass


@dataclass
class ParsedPaper:
    title: str
    abstract: str
    sections: List[Dict[str, str]]
    figures: List[Dict[str, str]]
    tables: List[Dict[str, str]]
    fulltext_path: Path
    parse_json_path: Path


ParseCommand = Callable[[Path, Path], Dict[str, object]]


class PaperParser:
    def __init__(self, http_client=None, parse_command: ParseCommand | None = None):
        self.http_client = http_client or httpx.Client(timeout=60)
        self.parse_command = parse_command

    def parse_pdf(self, pdf_url: str, package_dir: Path) -> ParsedPaper:
        paper_dir = package_dir / "paper"
        paper_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = paper_dir / "paper.pdf"
        response = self.http_client.get(pdf_url)
        response.raise_for_status()
        pdf_path.write_bytes(response.content)

        if self.parse_command is None:
            raise PaperParseError("paper parser command is not configured")
        raw = self.parse_command(pdf_path, paper_dir)
        sections = raw.get("sections") if isinstance(raw, dict) else None
        if not isinstance(sections, list) or not sections:
            raise PaperParseError("paper parser returned no sections")

        title = str(raw.get("title") or "未命名论文")
        abstract = str(raw.get("abstract") or "")
        figures = raw.get("figures") if isinstance(raw.get("figures"), list) else []
        tables = raw.get("tables") if isinstance(raw.get("tables"), list) else []
        fulltext = self._render_fulltext(title, abstract, sections)
        fulltext_path = paper_dir / "fulltext.md"
        parse_json_path = paper_dir / "parse.json"
        fulltext_path.write_text(fulltext, encoding="utf-8")
        parse_json_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return ParsedPaper(
            title=title,
            abstract=abstract,
            sections=sections,
            figures=figures,
            tables=tables,
            fulltext_path=fulltext_path.relative_to(package_dir),
            parse_json_path=parse_json_path.relative_to(package_dir),
        )

    def _render_fulltext(self, title: str, abstract: str, sections: List[Dict[str, str]]) -> str:
        blocks = [f"# {title}"]
        if abstract:
            blocks.append(f"## Abstract\n\n{abstract}")
        for section in sections:
            heading = section.get("heading") or section.get("id") or "Section"
            text = section.get("text") or ""
            blocks.append(f"## {heading}\n\n{text}".strip())
        return "\n\n".join(blocks).strip() + "\n"
```

- [ ] **步骤 4: 确认测试通过**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_paper_parser_downloads_pdf_and_writes_parse_outputs apps/api/tests/test_long_article.py::test_paper_parser_fails_when_parser_returns_no_sections -q
```

预期：通过。

- [ ] **步骤 5: 提交**

```bash
rtk git add apps/api/ai_radar/paper_parser.py apps/api/tests/test_long_article.py
rtk git commit -m "Add paper fulltext parser adapter"
```

---

## 任务 3: 新增长文结构化生成器

**文件：**
- 新建：`apps/api/ai_radar/long_article.py`
- 测试：`apps/api/tests/test_long_article.py`

- [ ] **步骤 1: 写结构化生成测试**

追加到 `apps/api/tests/test_long_article.py`：

```python
from ai_radar.long_article import LongArticleGenerator
from ai_radar.models import Paper, ScoreItem, Topic
from ai_radar.paper_parser import ParsedPaper


class SequencedLLM:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def complete(self, instructions, input_text):
        self.calls.append((instructions, input_text))
        text = self.texts.pop(0)
        return type("Result", (), {"text": text, "response_id": "llm-test"})()


def make_topic_and_paper():
    topic = Topic(
        id="topic-agent-lab",
        slug="agent-lab",
        cluster_id="cluster-agent-lab",
        paper_id="paper-agent-lab",
        title="Agent Laboratory 这篇科研 Agent 论文真正贡献是什么？",
        angle="从论文问题、方法流程、实验可信度和局限切入。",
        article_type="long_paper",
        score_total=90,
        score_detail={
            "heat": ScoreItem(value=80, reason="hot"),
            "relevance": ScoreItem(value=90, reason="relevant"),
            "writeability": ScoreItem(value=90, reason="writeable"),
            "conversion": ScoreItem(value=90, reason="valuable"),
        },
        business_hook="解释科研 agent 的机制和实验边界。",
        source_count=1,
        evidence_risk="low",
        recommendation="适合做专业解读。",
        signal_ids=[],
        created_at="2026-06-30T00:00:00Z",
    )
    paper = Paper(
        id="paper-agent-lab",
        arxiv_id="2501.04227",
        title="Agent Laboratory: Using LLM Agents as Research Assistants",
        authors=["A"],
        abstract="Agent Laboratory studies research agents.",
        pdf_url="https://arxiv.org/pdf/2501.04227",
        code_url=None,
        published_at="2025-01-08T00:00:00Z",
        categories=["cs.AI"],
        method_summary="Planner, reviewer and executor collaborate.",
        experiment_summary="Human feedback improves quality.",
        limitations="Needs careful evaluation.",
        replication_value=88,
        extension_topics=["科研 agent 工作流"],
    )
    return topic, paper


def test_long_article_generator_returns_markdown_with_image_slots_and_shared_style(tmp_path: Path):
    topic, paper = make_topic_and_paper()
    parsed = ParsedPaper(
        title=paper.title,
        abstract=paper.abstract,
        sections=[{"id": "method", "heading": "Method", "text": "Planner reviewer executor workflow."}],
        figures=[{"id": "paper-fig-1", "path": "paper/figures/figure-1.png", "caption": "Original workflow"}],
        tables=[],
        fulltext_path=Path("paper/fulltext.md"),
        parse_json_path=Path("paper/parse.json"),
    )
    plan_json = """{
      "article_title": "Agent Laboratory 真正值得看的不是自动科研",
      "reader_promise": "读者能看懂科研 agent 的工作流和边界",
      "thesis": "它的价值在于把科研流程拆成可检查步骤",
      "visual_style": {
        "style_id": "handdrawn-doodle-v1",
        "line_style": "clean hand-drawn ink line",
        "palette": ["深墨色", "纸白", "强调蓝", "少量暖色"],
        "label_style": "短中文标签",
        "composition_rule": "留白充足，主体清晰"
      },
      "sections": [
        {"id": "method", "heading": "方法机制", "purpose": "解释方法", "source_refs": ["paper:section:method"], "must_include": ["planner", "reviewer"]}
      ],
      "figure_slots": [
        {"id": "fig-method-overview", "after_section_id": "method", "kind": "generated_mechanism", "purpose": "解释方法流程", "source_refs": ["paper:section:method"], "prompt_brief": "画出 planner reviewer executor", "caption": "方法机制图"}
      ],
      "quality_check": {"uses_fulltext": true, "has_method_explanation": true, "has_experiment_caveat": true, "has_limitations": true}
    }"""
    draft_json = """{
      "sections": [
        {"id": "method", "heading": "方法机制", "body": "这篇论文的方法不是把 agent 写得更玄，而是把文献综述、实验执行和报告写作拆成可检查的协作流程。方法、实验和局限都需要回到原文。"}
      ]
    }"""
    humanized_json = draft_json.replace("不是把 agent 写得更玄，而是", "关键不在于把 agent 包装得更玄，而在于")
    generator = LongArticleGenerator(llm_provider=SequencedLLM([plan_json, draft_json, humanized_json]))

    result = generator.generate(topic=topic, paper=paper, parsed_paper=parsed)

    assert "## 主文章：长论文解读" in result.markdown
    assert "![方法机制图](figures/fig-method-overview.png)" in result.markdown
    assert result.visual_style["style_id"] == "handdrawn-doodle-v1"
    assert result.figure_slots[0]["style_id"] == "handdrawn-doodle-v1"
    assert "值得关注不是因为热" not in result.markdown
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_long_article_generator_returns_markdown_with_image_slots_and_shared_style -q
```

预期：失败，错误包含 `ModuleNotFoundError: No module named 'ai_radar.long_article'`。

- [ ] **步骤 3: 最小实现**

新建 `apps/api/ai_radar/long_article.py`：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

from .models import Paper, Topic
from .paper_parser import ParsedPaper


class LongArticleError(RuntimeError):
    pass


@dataclass
class LongArticleResult:
    markdown: str
    visual_style: Dict[str, object]
    figure_slots: List[Dict[str, object]]
    response_ids: List[str]


class LongArticleGenerator:
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider

    def generate(self, topic: Topic, paper: Paper, parsed_paper: ParsedPaper) -> LongArticleResult:
        plan_result = self.llm_provider.complete(self._plan_instructions(), self._plan_input(topic, paper, parsed_paper))
        plan = self._json(plan_result.text, "writing plan")
        self._validate_plan(plan)
        draft_result = self.llm_provider.complete(self._draft_instructions(), json.dumps(plan, ensure_ascii=False))
        draft = self._json(draft_result.text, "article draft")
        human_result = self.llm_provider.complete(self._humanize_instructions(), json.dumps(draft, ensure_ascii=False))
        humanized = self._json(human_result.text, "humanized article")
        markdown = self._compose_markdown(plan, humanized)
        return LongArticleResult(
            markdown=markdown,
            visual_style=plan["visual_style"],
            figure_slots=self._slots_with_style(plan),
            response_ids=[
                getattr(plan_result, "response_id", ""),
                getattr(draft_result, "response_id", ""),
                getattr(human_result, "response_id", ""),
            ],
        )

    def _json(self, text: str, label: str) -> Dict[str, object]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            payload = json.loads(text[start:end])
        except Exception as error:
            raise LongArticleError(f"invalid {label} JSON: {error}") from error
        if not isinstance(payload, dict):
            raise LongArticleError(f"invalid {label} JSON: root must be object")
        return payload

    def _validate_plan(self, plan: Dict[str, object]) -> None:
        quality = plan.get("quality_check")
        if not isinstance(quality, dict) or not quality.get("uses_fulltext"):
            raise LongArticleError("writing plan did not use fulltext")
        for key in ("has_method_explanation", "has_experiment_caveat", "has_limitations"):
            if not quality.get(key):
                raise LongArticleError(f"writing plan missing {key}")
        if not plan.get("sections"):
            raise LongArticleError("writing plan missing sections")

    def _slots_with_style(self, plan: Dict[str, object]) -> List[Dict[str, object]]:
        style = plan.get("visual_style") if isinstance(plan.get("visual_style"), dict) else {}
        style_id = str(style.get("style_id") or "handdrawn-doodle-v1")
        slots = plan.get("figure_slots") if isinstance(plan.get("figure_slots"), list) else []
        return [dict(slot, style_id=style_id) for slot in slots if isinstance(slot, dict)]

    def _compose_markdown(self, plan: Dict[str, object], draft: Dict[str, object]) -> str:
        title = str(plan.get("article_title") or "论文深度解读")
        slots = self._slots_with_style(plan)
        sections = draft.get("sections") if isinstance(draft.get("sections"), list) else []
        blocks = ["# 今日 AI 论文与热点文章包", "## 主文章：长论文解读", f"### {title}"]
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("id") or "")
            heading = str(section.get("heading") or section_id or "正文")
            body = str(section.get("body") or "")
            blocks.append(f"### {heading}\n\n{body}")
            for slot in slots:
                if slot.get("after_section_id") == section_id:
                    caption = str(slot.get("caption") or "机制图")
                    path = f"figures/{slot.get('id')}.png"
                    blocks.append(f"![{caption}]({path})")
        return "\n\n".join(blocks).strip() + "\n"

    def _plan_instructions(self) -> str:
        return "你是严谨的中文 AI 论文解读编辑。只返回 JSON 写作计划，必须基于论文全文。"

    def _draft_instructions(self) -> str:
        return "你是中文公众号作者。只返回 JSON 正文片段，专业、严谨、面向读者。"

    def _humanize_instructions(self) -> str:
        return "你是中文编辑。降低 AI 味，保留事实、数字、论文名、引用和章节意图，只返回 JSON。"

    def _plan_input(self, topic: Topic, paper: Paper, parsed_paper: ParsedPaper) -> str:
        return json.dumps(
            {
                "topic": topic.model_dump(mode="json"),
                "paper": paper.model_dump(mode="json"),
                "parsed_paper": {
                    "title": parsed_paper.title,
                    "abstract": parsed_paper.abstract,
                    "sections": parsed_paper.sections,
                    "figures": parsed_paper.figures,
                    "tables": parsed_paper.tables,
                },
            },
            ensure_ascii=False,
        )
```

- [ ] **步骤 4: 确认测试通过**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_long_article_generator_returns_markdown_with_image_slots_and_shared_style -q
```

预期：通过。

- [ ] **步骤 5: 提交**

```bash
rtk git add apps/api/ai_radar/long_article.py apps/api/tests/test_long_article.py
rtk git commit -m "Add structured long article generator"
```

---

## 任务 4: 接入主文章刷新并移除长文本地兜底

**文件：**
- 修改：`apps/api/ai_radar/pipeline.py`
- 测试：`apps/api/tests/test_long_article.py`
- 测试：`apps/api/tests/test_llm_provider.py`
- 测试：`apps/api/tests/test_pipeline.py`

- [ ] **步骤 1: 写主流程失败测试**

追加到 `apps/api/tests/test_long_article.py`：

```python
from ai_radar.pipeline import DailyPipeline
from ai_radar.storage import JsonStore


class FakeImageProvider:
    def generate(self, prompt, output_path):
        from ai_radar.image_provider import ImageResult

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-image")
        return ImageResult(path=output_path, revised_prompt=prompt, provider_request_id="resp-test-image")


class FailingParser:
    def parse_pdf(self, pdf_url, package_dir):
        raise RuntimeError("PDF 解析失败")


def test_refresh_main_fails_without_fulltext_instead_of_using_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=SequencedLLM([]))
    pipeline.paper_parser = FailingParser()
    pipeline.run_daily("2026-06-20")
    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")

    with pytest.raises(RuntimeError, match="PDF 解析失败"):
        pipeline.refresh_module(draft.id, "main", "generate selected long article")

    article = (tmp_path / draft.markdown_path).read_text(encoding="utf-8")
    assert "待生成" in article
    assert "这篇论文到底想解决什么问题" not in article
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_refresh_main_fails_without_fulltext_instead_of_using_fallback -q
```

预期：失败，因为当前代码会捕获 LLM 问题并使用本地兜底模板。

- [ ] **步骤 3: 最小实现**

在 `apps/api/ai_radar/pipeline.py` 中：

1. 导入：

```python
from .long_article import LongArticleGenerator
from .paper_parser import PaperParser
```

2. 在 `DailyPipeline.__init__` 中添加：

```python
self.paper_parser = PaperParser(http_client=self.http_client)
```

3. 添加辅助函数：

```python
def _generate_publish_ready_long_article(self, draft: Draft, topic: Topic, paper: Paper):
    package_dir = self.store.root / Path(draft.markdown_path).parent
    parsed = self.paper_parser.parse_pdf(paper.pdf_url, package_dir)
    return LongArticleGenerator(self.llm_provider).generate(topic=topic, paper=paper, parsed_paper=parsed)
```

4. 在 `refresh_module` 中，对 `module == "main"` 的分支，用下面逻辑替换基于兜底模板的 `_generate_article_markdown(...)` 调用：

```python
if include_long_article and self.llm_provider and module == "main":
    if paper is None:
        raise RuntimeError("长文章生成需要绑定论文")
    long_article = self._generate_publish_ready_long_article(draft, topic, paper)
    generated_markdown = long_article.markdown
    generation_error = ""
```

保留 `replace_article_module(...)` 调用，确保次文章模块不被破坏。

- [ ] **步骤 4: 更新旧测试预期**

在 `apps/api/tests/test_llm_provider.py` 中，把“被拒绝的主文章会回退到兜底正文”的旧断言改成 `refresh_module(..., "main")` 会抛错。示例：

```python
with pytest.raises(RuntimeError):
    pipeline.refresh_module(draft.id, "main", "generate selected long article")
```

如果文件里还没有 `import pytest`，补上。

- [ ] **步骤 5: 确认测试通过**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py apps/api/tests/test_llm_provider.py apps/api/tests/test_pipeline.py -q
```

预期：通过。

- [ ] **步骤 6: 提交**

```bash
rtk git add apps/api/ai_radar/pipeline.py apps/api/tests/test_long_article.py apps/api/tests/test_llm_provider.py apps/api/tests/test_pipeline.py
rtk git commit -m "Require fulltext for long article generation"
```

---

## 任务 5: 生成统一风格封面和文中机制图，图片失败保留正文

**文件：**
- 修改：`apps/api/ai_radar/pipeline.py`
- 修改：`apps/api/ai_radar/long_article.py`
- 测试：`apps/api/tests/test_long_article.py`

- [ ] **步骤 1: 写图片失败保留正文测试**

追加到 `apps/api/tests/test_long_article.py`：

```python
class FailingImageProvider:
    def generate(self, prompt, output_path):
        raise RuntimeError("image2 超时")


def test_image_failure_keeps_long_article_and_marks_assets_failed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FailingImageProvider())
    topic, paper = make_topic_and_paper()
    draft_id = f"draft-2026-06-30-{topic.id}"
    from ai_radar.models import Draft, now_iso

    draft = Draft(
        id=draft_id,
        topic_id=topic.id,
        title=topic.title,
        subtitle=topic.angle,
        status="review",
        markdown_path="drafts/2026-06-30/agent-lab/article.md",
        html_path="drafts/2026-06-30/agent-lab/article-wechat.html",
        sources_path="drafts/2026-06-30/agent-lab/sources.md",
        checklist_path="drafts/2026-06-30/agent-lab/review-checklist.md",
        evidence_path="drafts/2026-06-30/agent-lab/evidence.json",
        topic_path="drafts/2026-06-30/agent-lab/topic.md",
        version=1,
        created_at=now_iso(),
        updated_at=now_iso(),
    )
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    slots = [{"id": "fig-method-overview", "kind": "generated_mechanism", "caption": "方法机制图", "prompt_brief": "画机制", "style_id": "handdrawn-doodle-v1", "after_section_id": "method", "source_refs": ["paper:section:method"]}]

    assets = pipeline._generate_long_article_assets(draft, topic, slots, {"style_id": "handdrawn-doodle-v1"})

    assert len(assets) == 2
    assert {asset.kind for asset in assets} == {"cover", "mechanism"}
    assert all(asset.status == "failed" for asset in assets)
    assert all(asset.style_id == "handdrawn-doodle-v1" for asset in assets)
    assert "image2 超时" in assets[0].error
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_image_failure_keeps_long_article_and_marks_assets_failed -q
```

预期：失败，因为 `_generate_long_article_assets` 还不存在。

- [ ] **步骤 3: 实现资产生成**

在 `apps/api/ai_radar/pipeline.py` 中添加：

```python
def _generate_long_article_assets(
    self,
    draft: Draft,
    topic: Topic,
    figure_slots: List[Dict[str, object]],
    visual_style: Dict[str, object],
) -> List[DraftAsset]:
    package_dir = self.store.root / Path(draft.markdown_path).parent
    style_id = str(visual_style.get("style_id") or "handdrawn-doodle-v1")
    assets: List[DraftAsset] = []
    cover_prompt = build_consistent_cover_prompt(topic, visual_style)
    assets.append(self._generate_asset_or_failure(draft, "cover", "cover", package_dir / "cover.png", cover_prompt, style_id, "公众号封面图", [], ""))
    for slot in figure_slots:
        if slot.get("kind") != "generated_mechanism":
            continue
        slot_id = str(slot.get("id") or "mechanism")
        prompt = build_consistent_mechanism_prompt(slot, visual_style)
        assets.append(
            self._generate_asset_or_failure(
                draft,
                "mechanism",
                slot_id,
                package_dir / "figures" / f"{slot_id}.png",
                prompt,
                style_id,
                str(slot.get("caption") or "机制图"),
                [str(item) for item in slot.get("source_refs", [])],
                str(slot.get("after_section_id") or ""),
            )
        )
    return assets
```

添加辅助函数：

```python
def _generate_asset_or_failure(
    self,
    draft: Draft,
    kind: str,
    slot_id: str,
    output_path: Path,
    prompt: str,
    style_id: str,
    caption: str,
    source_refs: List[str],
    insert_after_section_id: str,
) -> DraftAsset:
    relative_path = output_path.relative_to(self.store.root)
    try:
        result = generate_image_asset(output_path, prompt, rgb=(20, 140, 190), storage_root=self.store.root)
        return DraftAsset(
            id=f"asset-{draft.id}-{slot_id}",
            draft_id=draft.id,
            kind=kind,
            prompt=prompt,
            path=str(relative_path),
            revised_prompt=result.revised_prompt,
            provider=result.provider,
            provider_request_id=result.provider_request_id or None,
            status="ready",
            slot_id=slot_id,
            caption=caption,
            source_refs=source_refs,
            insert_after_section_id=insert_after_section_id,
            style_id=style_id,
            created_at=now_iso(),
        )
    except RuntimeError as error:
        return DraftAsset(
            id=f"asset-{draft.id}-{slot_id}",
            draft_id=draft.id,
            kind=kind,
            prompt=prompt,
            path=str(relative_path),
            status="failed",
            error=str(error),
            slot_id=slot_id,
            caption=caption,
            source_refs=source_refs,
            insert_after_section_id=insert_after_section_id,
            style_id=style_id,
            created_at=now_iso(),
        )
```

添加 prompt 构建函数：

```python
def build_consistent_cover_prompt(topic: Topic, visual_style: Dict[str, object]) -> str:
    return (
        "清晰、引人瞩目的公众号封面图。统一手绘涂鸦风，干净线条，留白充足，主体明确。"
        f"风格配置：{json.dumps(visual_style, ensure_ascii=False)}。"
        f"文章主题：{topic.title}。不要廉价渐变，不堆文字，只保留必要中文短标签。"
    )


def build_consistent_mechanism_prompt(slot: Dict[str, object], visual_style: Dict[str, object]) -> str:
    return (
        "中文机制解释图，统一手绘涂鸦风，干净线条，留白充足。"
        f"风格配置：{json.dumps(visual_style, ensure_ascii=False)}。"
        f"图的目的：{slot.get('purpose', '')}。"
        f"画面简述：{slot.get('prompt_brief', '')}。"
        "每张图只解释一个关键机制，避免小字堆满画面。"
    )
```

- [ ] **步骤 4: 将资产接入主文章刷新**

在 `refresh_module` 生成主文章 Markdown 后添加：

```python
    long_article = self._generate_publish_ready_long_article(draft, topic, paper)
    generated_markdown = long_article.markdown
    draft.assets = self._generate_long_article_assets(draft, topic, long_article.figure_slots, long_article.visual_style)
```

如果有资产生成失败：

```python
failed = [asset for asset in draft.assets if asset.status == "failed"]
if failed:
    generation_error = join_generation_errors(generation_error, *[f"{asset.caption}: {asset.error}" for asset in failed])
```

- [ ] **步骤 5: 确认测试通过**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py -q
```

预期：通过。

- [ ] **步骤 6: 提交**

```bash
rtk git add apps/api/ai_radar/pipeline.py apps/api/tests/test_long_article.py
rtk git commit -m "Generate consistent long article assets"
```

---

## 任务 6: Markdown/HTML 渲染支持图片

**文件：**
- 修改：`apps/api/ai_radar/pipeline.py`
- 测试：`apps/api/tests/test_long_article.py`

- [ ] **步骤 1: 写图片 HTML 测试**

追加到 `apps/api/tests/test_long_article.py`：

```python
from ai_radar.pipeline import markdown_to_wechat_html


def test_markdown_to_wechat_html_renders_images():
    html = markdown_to_wechat_html("## 方法机制\n\n![方法机制图](figures/fig-method-overview.png)\n\n正文")

    assert '<img src="figures/fig-method-overview.png" alt="方法机制图">' in html
    assert "<h2>方法机制</h2>" in html
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_markdown_to_wechat_html_renders_images -q
```

预期：失败，因为当前渲染器会把图片 Markdown 当普通段落输出。

- [ ] **步骤 3: 实现图片渲染**

在 `markdown_to_wechat_html` 的普通段落处理前添加：

```python
image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
if image_match:
    alt = html.escape(image_match.group(1))
    src = html.escape(image_match.group(2), quote=True)
    blocks.append(f'<figure><img src="{src}" alt="{alt}"><figcaption>{alt}</figcaption></figure>')
```

- [ ] **步骤 4: 确认测试通过**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests/test_long_article.py::test_markdown_to_wechat_html_renders_images -q
```

预期：通过。

- [ ] **步骤 5: 提交**

```bash
rtk git add apps/api/ai_radar/pipeline.py apps/api/tests/test_long_article.py
rtk git commit -m "Render images in WeChat HTML"
```

---

## 任务 7: 前端完整预览图片和资产状态

**文件：**
- 修改：`apps/web/src/App.tsx`
- 修改：`apps/web/src/styles.css`
- 测试：`apps/web/src/App.test.tsx`

- [ ] **步骤 1: 写前端测试**

追加到 `apps/web/src/App.test.tsx`：

```tsx
it("renders long article images in preview and shows failed asset status", () => {
  const detailWithImage = {
    ...draftDetail,
    markdown:
      "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n### 方法机制\n\n正文。\n\n![方法机制图](drafts/2026-06-20/agent-lab/figures/fig-method-overview.png)",
    html:
      '<article class="wechat-draft"><h2>主文章：长论文解读</h2><h3>方法机制</h3><p>正文。</p><figure><img src="drafts/2026-06-20/agent-lab/figures/fig-method-overview.png" alt="方法机制图"><figcaption>方法机制图</figcaption></figure></article>',
    draft: {
      ...draftDetail.draft,
      assets: [
        {
          id: "asset-cover",
          draft_id: draftDetail.draft.id,
          kind: "cover",
          prompt: "封面",
          revised_prompt: null,
          path: "drafts/2026-06-20/agent-lab/cover.png",
          width: 1536,
          height: 1024,
          provider: "image2",
          provider_request_id: null,
          status: "failed",
          error: "image2 超时",
          slot_id: "cover",
          insert_after_section_id: "",
          caption: "公众号封面图",
          source_refs: [],
          style_id: "handdrawn-doodle-v1",
          created_at: "2026-06-20T00:00:00Z"
        }
      ]
    }
  };

  render(<App initialRadar={radar} initialTopics={[topic]} initialDraftDetail={detailWithImage} />);

  const preview = screen.getByTestId("wechat-live-preview");
  expect(preview.querySelector("img")?.getAttribute("alt")).toBe("方法机制图");
  expect(screen.getByText("failed")).toBeInTheDocument();
  expect(screen.getByText("image2 超时")).toBeInTheDocument();
  expect(screen.getByText("handdrawn-doodle-v1")).toBeInTheDocument();
});
```

- [ ] **步骤 2: 确认测试失败**

运行：

```bash
rtk npm run test --workspace apps/web -- --run apps/web/src/App.test.tsx -t "renders long article images"
```

预期：失败，因为当前预览渲染器不会渲染图片标签，也不会展示资产字段。

- [ ] **步骤 3: 更新预览渲染**

在 `markdownToPreviewHtml` 的引用块处理前添加图片处理：

```ts
const imageMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
if (imageMatch) {
  return `<figure><img src="${escapeHtml(imageMatch[2])}" alt="${escapeHtml(imageMatch[1])}"><figcaption>${escapeHtml(imageMatch[1])}</figcaption></figure>`;
}
```

在阅读模式中把 `<pre>{activeArticleModule.body}</pre>` 替换为：

```tsx
<div className="article-rendered" dangerouslySetInnerHTML={{ __html: markdownToPreviewHtml(articleModuleToPreviewMarkdown(activeArticleModule)) }} />
```

在素材行中渲染：

```tsx
<span>{asset.status}</span>
{asset.style_id ? <code>{asset.style_id}</code> : null}
{asset.error ? <p role="alert">{asset.error}</p> : null}
{asset.caption ? <small>{asset.caption}</small> : null}
```

- [ ] **步骤 4: 最小样式**

在 `apps/web/src/styles.css` 中添加：

```css
.article-rendered figure,
.wechat-live-preview figure {
  margin: 18px 0;
}

.article-rendered img,
.wechat-live-preview img {
  display: block;
  width: 100%;
  max-width: 100%;
  border-radius: 6px;
}

.article-rendered figcaption,
.wechat-live-preview figcaption {
  margin-top: 8px;
  color: #667085;
  font-size: 13px;
}

.asset-row [role="alert"] {
  color: #b42318;
}
```

- [ ] **步骤 5: 确认测试通过**

运行：

```bash
rtk npm run test --workspace apps/web -- --run apps/web/src/App.test.tsx -t "renders long article images"
```

预期：通过。

- [ ] **步骤 6: 提交**

```bash
rtk git add apps/web/src/App.tsx apps/web/src/styles.css apps/web/src/App.test.tsx
rtk git commit -m "Preview long article images and asset status"
```

---

## 任务 8: 全量验证和文档同步

**文件：**
- 修改：`README.md`
- 修改：`docs/superpowers/specs/2026-06-30-long-article-generation-design.md`，仅当实现过程中发现设计文档必须修正时。

- [ ] **步骤 1: 更新 README 当前能力**

在 `README.md` 中，把长文章相关 bullet 更新为：

```markdown
- 主文章：用户点击“生成长文”后，必须读取论文全文；全文下载或解析失败时不生成本地兜底正文。
- 长文图片：封面图和文中机制图使用统一手绘/涂鸦风格；image2 失败时保留已生成正文，并在素材区标记失败。
```

- [ ] **步骤 2: 后端测试**

运行：

```bash
rtk .venv/bin/python -m pytest apps/api/tests -q
```

预期：通过。

- [ ] **步骤 3: 前端测试**

运行：

```bash
rtk npm run test --workspace apps/web -- --run
```

预期：通过。

- [ ] **步骤 4: 前端构建**

运行：

```bash
rtk npm run build
```

预期：通过。

- [ ] **步骤 5: 提交文档和验证修正**

```bash
rtk git add README.md docs/superpowers/specs/2026-06-30-long-article-generation-design.md
rtk git commit -m "Document long article generation behavior"
```

如果文档没有变化，则跳过提交。
