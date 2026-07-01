from pathlib import Path

import pytest

from ai_radar.models import EvidenceItem, Paper, ScoreItem, Signal, Topic, TopicPackItem, TopicPackVersion
from ai_radar.pipeline import (
    DailyPipeline,
    article_main_is_chinese,
    build_article_markdown,
    build_cover_prompt,
    main_article_is_publish_ready,
    secondary_module_is_publish_ready,
    article_illustration_specs,
)
from ai_radar.pipeline import visual_asset_specs
from ai_radar.storage import JsonStore


class FakeImageProvider:
    def __init__(self, png: bytes = b"\x89PNG\r\n\x1a\nfake-image"):
        self.png = png

    def generate(self, prompt: str, output_path: Path, size=None):
        from ai_radar.image_provider import ImageResult

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.png)
        return ImageResult(path=output_path, revised_prompt=prompt, provider_request_id="resp-test-image")


class FailingImageProvider:
    def generate(self, prompt: str, output_path: Path, size=None):
        raise RuntimeError("image relay unavailable")


class BadArticleLLM:
    def complete(self, instructions: str, input_text: str):
        class Result:
            text = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### Agent Laboratory 会不会改变 AI 论文实验设计？

旧的错误 LLM 输出。

## 次文章 1：AI 热点

- 来源：https://example.com/bad

## 次文章 2：arXiv 高热度文章速报

- arXiv:2606.20101

## 来源清单

- [bad](https://example.com/bad)
"""

        return Result()


class FallbackCopyingLLM:
    def complete(self, instructions: str, input_text: str):
        fallback = input_text.split("本地 fallback 草稿，可参考结构但不要照抄:", 1)[1].strip()

        class Result:
            text = fallback
            response_id = "fallback-copy"

        return Result()


class BadSecondaryArticleLLM:
    def complete(self, instructions: str, input_text: str):
        class Result:
            text = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### 长上下文模型来了，RAG 为什么还没有过时？

LLM 生成的主文章。

## 次文章 1：AI 热点

- **热点 A**：这还是素材清单。

## 次文章 2：arXiv 高热度文章速报

- **论文 A**：这也还是素材清单。

## 来源清单

- [source](https://example.com/source)
"""

        return Result()


class GoodMainBadSecondaryLLM:
    def complete(self, instructions: str, input_text: str):
        class Result:
            text = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### LLM 生成的长论文解读

这是一篇合格的中文主文章，它围绕论文问题、方法贡献、实验可信度和局限展开。

这段内容足够长，能够通过中文主文章校验，并且不应该因为次文章格式不好而被丢弃。

### 方法贡献

这里继续用中文解释方法贡献、实验边界和近期为什么值得读。

## 次文章 1：AI 热点

- 这是坏的 bullet 输出

## 次文章 2：arXiv 高热度文章速报

- 这也是坏的 bullet 输出

## 来源清单

- source
"""
            response_id = "good-main-bad-secondary"

        return Result()


class CapturingNarrativeLLM:
    def __init__(self):
        self.calls = []

    def complete(self, instructions: str, input_text: str):
        self.calls.append((instructions, input_text))

        class Result:
            text = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### 这篇论文应该按评测复盘来读

这是一篇合格的中文主文章，会说明研究问题、方法贡献、实验可信度和局限边界。

### 它真正测出的不是完成率

这里继续解释方法、实验和局限，并给出作者判断，避免模板化标题。

## 次文章 1：AI 热点

- 忽略

## 次文章 2：arXiv 高热度文章速报

- 忽略

## 来源清单

- 忽略
"""
            response_id = "captured-narrative"

        return Result()


class InternalContentLLM:
    def complete(self, instructions: str, input_text: str):
        class Result:
            text = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### 合格标题

这是一篇中文主文章，会说明研究问题、方法贡献、实验可信度和局限边界。

### 配图建议

image2 封面图应该这样画。

## 次文章 1：AI 热点

- 忽略

## 次文章 2：arXiv 高热度文章速报

- 忽略

## 来源清单

- 忽略
"""
            response_id = "internal-content"

        return Result()


class GoodAgentLabLLM:
    def complete(self, instructions: str, input_text: str):
        class Result:
            text = """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### Agent Laboratory 会不会改变 AI 论文实验设计？

Agent Laboratory 的价值，不在于把科研完全自动化，而在于把论文问题、方法流程、实验可信度和局限拆成可检查的工作流。arXiv:2501.04227 给出的核心信号是，研究流程里从想法到实验再到写作的多个环节，都可以被 agent 分工和记录下来。

### 方法贡献

方法贡献在于它把 hypothesis、实验执行、结果整理和写作串成一个可追踪流程，而不是只展示一个聊天式 demo。这样读者可以更清楚地判断哪些步骤真的被模型完成，哪些步骤仍然需要人类研究者把关。

### 实验可信度

实验可信度要看两件事：第一，任务是否足够贴近真实科研流程；第二，失败案例是否被完整记录。论文的问题意识是成立的，但不能因此推导出科研判断已经可以外包给模型。

### 局限和近期为什么值得读

这篇论文值得近期阅读，是因为 Agent 工具正在进入研究、工程和内容生产流程。它的局限也很清楚：模型可能生成看似完整但证据不足的实验解释，人工审查仍然是必要环节。

### 我的判断

这篇论文适合写成一篇带判断的工程论文解读：它的价值在于把科研流程拆成可观察步骤，风险在于读者容易把流程自动化误读成科研判断自动化。

## 次文章 1：AI 热点

- 忽略

## 次文章 2：arXiv 高热度文章速报

- 忽略

## 来源清单

- 忽略
"""
            response_id = "good-agent-lab"

        return Result()


class DisconnectingLLM:
    def complete(self, instructions: str, input_text: str):
        raise RuntimeError("RemoteProtocolError: Server disconnected without sending a response.")


class SecondaryModuleLLM:
    def __init__(self):
        self.calls = []

    def complete(self, instructions: str, input_text: str):
        self.calls.append((instructions, input_text))
        if "AI 热点" in instructions:
            text = """## 次文章 1：AI 热点

### 1. LLM 生成的热点判断一

今天这组热点更适合当成行业信号，而不是单条新闻。

最值得关注的是测试热点，因为它能帮助读者判断工具链和开发者生态正在怎么变化。

文章来源：https://example.com/hotspot-1

### 2. LLM 生成的热点判断二

这条消息不应该被写成营销稿，而应该落回到研究、产品和工程实践的影响。

文章来源：https://example.com/hotspot

### 3. LLM 生成的热点判断三

如果后续要展开，可以继续看它是否影响评测、复现和应用部署。

文章来源：https://example.com/hotspot-3

### 4. LLM 生成的热点判断四

我的判断是，这类变化值得持续跟踪，但不要把短期热度写成确定趋势。

文章来源：https://example.com/hotspot-4

### 5. LLM 生成的热点判断五

最后一条热点也要保留独立判断，确保刷新不会把素材合并成少数几段。

文章来源：https://example.com/hotspot-5
"""
        else:
            text = """## 次文章 2：arXiv 高热度文章速报

### 1. LLM 生成的 arXiv 阅读顺序一

原文标题：Test Paper

第一篇是 Test Paper，arXiv:2606.00001，它把一个具体问题拆成了可以比较的实验设置。

这篇适合已经熟悉相关方向的读者先读，重点看问题定义、对照方法和指标口径。

文章来源：https://arxiv.org/pdf/2606.00001

### 2. LLM 生成的 arXiv 阅读顺序二

原文标题：Second Test Paper

第二篇可以作为延伸阅读，用来观察同一方向里不同方法的实验边界，并判断是否值得后续展开成长论文解读。

我的判断是，速报不应该写成论文目录，而应该告诉读者先读哪篇、为什么读、是否值得后续展开。

文章来源：https://arxiv.org/pdf/2606.00002
"""
        return type("Result", (), {"text": text, "response_id": "secondary-1"})()


class CapturingSecondaryModuleLLM:
    def __init__(self):
        self.calls = []

    def complete(self, instructions: str, input_text: str):
        self.calls.append((instructions, input_text))
        headings = "\n\n".join(
            f"### {index}. 热点选题 {index} 的独立判断\n\n"
            f"这是第 {index} 条热点的中文判断，它会说明为什么值得关注，并且不会把多个热点合并成一段。\n\n"
            f"文章来源：https://example.com/hotspot-{index}"
            for index in range(1, 8)
        )
        text = f"""## 次文章 1：AI 热点

{headings}
"""
        return type("Result", (), {"text": text, "response_id": "secondary-7"})()


class CapturingArxivModuleLLM:
    def __init__(self):
        self.calls = []

    def complete(self, instructions: str, input_text: str):
        self.calls.append((instructions, input_text))
        headings = "\n\n".join(
            f"### {index}. arXiv 选题 {index} 的独立判断\n\n"
            f"原文标题：今日 arXiv 论文 {index}\n\n"
            f"这是第 {index} 篇论文的中文判断，会说明方向、贡献、实验亮点和是否值得后续展开。\n\n"
            f"文章来源：https://arxiv.org/pdf/2606.9100{index}"
            for index in range(1, 8)
        )
        text = f"""## 次文章 2：arXiv 高热度文章速报

{headings}
"""
        return type("Result", (), {"text": text, "response_id": "arxiv-7"})()


class BadSecondaryModuleLLM:
    def complete(self, instructions: str, input_text: str):
        return type("Result", (), {"text": "## 次文章 2：arXiv 高热度文章速报\n\n- 这还是素材清单。\n"})()


class RewritingHotspotSourceLLM:
    def complete(self, instructions: str, input_text: str):
        headings = "\n\n".join(
            f"### {index}. 当天热点话题 {index}\n\n"
            f"这是第 {index} 条热点判断。\n\n"
            f"文章来源：https://rewritten.example.com/{index}"
            for index in range(1, 8)
        )
        return type("Result", (), {"text": f"## 次文章 1：AI 热点\n\n{headings}", "response_id": "rewrite-source"})()


def markdown_section(markdown: str, marker: str) -> str:
    start = markdown.find(marker)
    assert start >= 0
    end = markdown.find("\n## ", start + len(marker))
    if end < 0:
        end = len(markdown)
    return markdown[start:end]


def test_daily_pipeline_generates_topic_pool_and_draft_package(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)

    run = pipeline.run_daily(date="2026-06-20")

    assert 5 <= len(run.topics) <= 10
    assert run.selected_topic.article_type == "long_paper"
    assert run.selected_topic.status == "selected"
    assert run.draft.topic_id == run.selected_topic.id
    assert run.draft.status == "review"
    assert run.draft.version == 1

    score = run.selected_topic.score_detail
    assert set(score.keys()) == {"heat", "relevance", "writeability", "conversion"}
    assert all(0 <= item.value <= 100 for item in score.values())
    assert all(item.reason for item in score.values())

    package_dir = tmp_path / "drafts" / "2026-06-20" / run.selected_topic.slug
    expected_files = [
        "article.md",
        "article-wechat.html",
        "sources.md",
        "review-checklist.md",
        "evidence.json",
        "topic.md",
    ]

    for relative in expected_files:
        assert (package_dir / relative).exists(), relative

    article = (package_dir / "article.md").read_text(encoding="utf-8")
    assert "主文章：长论文解读" in article
    assert "待生成" in article
    assert "点击“生成长文”后" in article
    assert "次文章 1：AI 热点" in article
    assert "次文章 2：arXiv 高热度文章速报" in article
    assert "来源清单" in article
    assert "系统会围绕这篇论文生成中文深度解读" in article

    html = (package_dir / "article-wechat.html").read_text(encoding="utf-8")
    assert "<article" in html
    assert "wechat-draft" in html

    checklist = (package_dir / "review-checklist.md").read_text(encoding="utf-8")
    assert "- [ ] 标题是否准确，不夸大" in checklist
    assert "- [ ] HTML 复制到公众号后台是否正常" in checklist

    assert run.draft.assets == []


def test_pipeline_creates_pending_workshop_draft_for_user_selected_topic(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    pipeline.run_daily(date="2026-06-20")

    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")

    assert draft.topic_id == "topic-long-context-rag"
    assert draft.status == "review"
    assert draft.assets == []

    package_dir = tmp_path / draft.markdown_path
    article = package_dir.read_text(encoding="utf-8")
    assert "主文章：长论文解读" in article
    assert "长上下文与 RAG 的论文争论，核心其实是成本和路由" in article
    assert "待生成" in article
    assert "点击“生成长文”后，系统会围绕这篇论文生成中文深度解读" in article
    assert "适合本科生、硕士研究生重点阅读" not in article
    assert "次文章 1：AI 热点" in article
    assert "次文章 2：arXiv 高热度文章速报" in article

    topic = pipeline.get_topic("topic-long-context-rag")
    assert topic.status == "drafted"


def test_secondary_articles_are_publish_ready_not_source_bullets(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    pipeline.run_daily(date="2026-06-20")

    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")
    article = store.read_text(draft.markdown_path)
    hotspots = markdown_section(article, "## 次文章 1：AI 热点")
    arxiv = markdown_section(article, "## 次文章 2：arXiv 高热度文章速报")

    for section in (hotspots, arxiv):
        body_lines = [line for line in section.splitlines() if line.strip()]
        assert len(body_lines) >= 5
        assert any(line.startswith("### ") for line in body_lines)
        assert not any(line.startswith("- ") for line in body_lines)
        assert "这一栏已自动整理" not in section
        assert "我的判断：它值得关注的地方" not in section

    assert "今天这几条消息，我建议你不要当新闻看" in hotspots
    assert "文章来源：" in hotspots
    assert len([line for line in arxiv.splitlines() if line.startswith("### ")]) == 2
    assert arxiv.count("原文标题：") == 2
    assert arxiv.count("文章来源：") == 2
    assert "### 1. Agent Laboratory: Using LLM Agents as Research Assistants" in arxiv
    assert "### 2. Retrieval Augmented Generation or Long-Context LLMs?" in arxiv
    assert "今天这组论文，我建议先按学术价值来读" not in arxiv
    html = store.read_text(draft.html_path)
    assert "<h3>今天这几条消息，我建议你不要当新闻看</h3>" in html
    assert "<h3>1. Agent Laboratory: Using LLM Agents as Research Assistants</h3>" in html
    assert "<p>### " not in html


def test_secondary_module_accepts_compact_publishable_natural_paragraphs():
    section = """## 次文章 1：AI 热点

### 这些工具更新的信号，比新闻本身更值得留意

今天这几个仓库动态，单独看都是常规更新，但把它们放在一起，能看出 AI 开发生态正在发生方向性变化。marimo 把可复现实验和 AI 友好的编辑体验重新组合，提示交互式编程环境正在从探索草稿转向可生产的工程资产。

Harvard 的机器学习系统开放教材则说明，系统工程知识正在被结构化地沉淀出来。Strix 把 AI 安全评估推向工具层，AutoGPT 的持续活跃则说明自主代理仍有社区热度，但不能被误读成能力已经完全落地。

把这些信号合在一起看，工具链模块化、知识结构化、安全评估工程化和低门槛代理体验，正在并行重塑 AI 开发的日常实践。
"""

    assert secondary_module_is_publish_ready(section)


def test_bad_llm_secondary_bullet_output_falls_back_to_publish_ready_articles(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=BadSecondaryArticleLLM())
    pipeline.run_daily(date="2026-06-20")

    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")
    article = store.read_text(draft.markdown_path)
    hotspots = markdown_section(article, "## 次文章 1：AI 热点")
    arxiv = markdown_section(article, "## 次文章 2：arXiv 高热度文章速报")

    assert "LLM 生成的主文章" not in article
    assert not any(line.startswith("- ") for line in hotspots.splitlines())
    assert not any(line.startswith("- ") for line in arxiv.splitlines())
    assert "今天这几条消息，我建议你不要当新闻看" in hotspots
    assert "### 1. Agent Laboratory: Using LLM Agents as Research Assistants" in arxiv
    assert "今天这组论文，我建议先按学术价值来读" not in arxiv


def test_agent_laboratory_publish_package_uses_verified_sources(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    pipeline.run_daily(date="2026-06-22")

    draft = pipeline.draft_topic("topic-agent-lab", date="2026-06-22")
    draft = pipeline.refresh_module(draft.id, "main", "generate selected long article")

    article = store.read_text(draft.markdown_path)
    html = store.read_text(draft.html_path)
    sources = store.read_text(draft.sources_path)
    evidence = store.read_text(draft.evidence_path)
    combined = "\n".join([article, html, sources, evidence])

    assert "https://arxiv.org/abs/2501.04227" in combined
    assert "https://arxiv.org/pdf/2501.04227" in combined
    assert "https://github.com/SamuelSchmidgall/AgentLaboratory" in combined
    assert "arXiv:2501.04227" in article
    assert "论文问题、方法流程、实验可信度和局限" in article
    assert "方法贡献" in article
    assert "我的判断" in article
    assert "example.com" not in combined
    assert "2606.20101" not in combined
    assert "github.com/example" not in combined
    assert "Rerun note" not in combined
    assert "待 LLM" not in article
    assert "The guidance" not in article
    assert "The paper reports" not in article


def test_live_arxiv_fallback_article_is_publishable_chinese_without_connector_placeholders():
    abstract = (
        "Mainstream LLM serving systems reuse prefix work mainly through paged or radix key-value (KV) caches. "
        "This is highly effective for high-throughput serving, but it manages only one positional fragment of "
        "execution state. We study low-latency, small-batch, on-device physical-AI serving, where interactive "
        "LLM agents and robot policies repeatedly branch, reset, interrupt, and re-enter under tight budgets."
    )
    topic = Topic(
        id="topic-live-2606-20537",
        slug="execution-state-capsules",
        cluster_id="cluster-live",
        paper_id="paper-2606-20537",
        title="Execution-State Capsules: Graph-Bound Execution-State Checkpoint and Restore for Low-Latency, Small-Batch, On-Device Physical-AI Serving",
        angle=abstract,
        article_type="long_paper",
        score_total=88,
        score_detail={
            "heat": ScoreItem(value=88, reason="来自 arXiv 实时信源。"),
            "relevance": ScoreItem(value=90, reason="与端侧 LLM serving 和物理 AI 有关。"),
            "writeability": ScoreItem(value=86, reason="摘要足以形成论文解读入口。"),
            "conversion": ScoreItem(value=84, reason="可延伸到系统机制和实验可信度分析。"),
        },
        business_hook="判断是否适合展开成端侧 LLM serving 的系统论文深度解读。",
        source_count=1,
        evidence_risk="medium",
        recommendation=abstract,
        signal_ids=["signal-live-2606-20537"],
        created_at="2026-06-22T07:50:00Z",
    )
    paper = Paper(
        id="paper-2606-20537",
        arxiv_id="2606.20537",
        title=topic.title,
        authors=["A. Researcher"],
        abstract=abstract,
        pdf_url="https://arxiv.org/pdf/2606.20537",
        published_at="2026-06-18T00:00:00Z",
        categories=["cs.LG"],
        method_summary="待 LLM/人工解析：MVP connector 已保留论文摘要和 PDF 链接。",
        experiment_summary="待 LLM/人工解析：需要阅读论文实验章节后补充。",
        limitations="待 LLM/人工解析：发布前必须人工确认局限性。",
        replication_value=72,
        extension_topics=["基于该论文摘要提炼核心研究问题", "围绕方法贡献和实验可信度设计解读角度"],
    )
    signal = Signal(
        id="signal-live-2606-20537",
        source_id="arxiv-cs-ai",
        kind="paper",
        title=topic.title,
        summary=abstract,
        url="https://arxiv.org/abs/2606.20537",
        published_at="2026-06-18T00:00:00Z",
        tags=["arxiv"],
        heat=88,
    )
    evidence = [
        EvidenceItem(
            id="evidence-live-1",
            topic_id=topic.id,
            source_url=signal.url,
            source_title=topic.title,
            claim=abstract,
            snippet=abstract,
            confidence="high",
            risk_note="实验结论需要人工阅读 PDF 后确认细节和指标。",
            created_at="2026-06-22T07:50:00Z",
        )
    ]

    article = build_article_markdown(topic, paper, evidence, [], [paper])
    main = markdown_section(article, "## 主文章：长论文解读")

    assert article_main_is_chinese(article)
    assert "> Mainstream LLM serving systems" not in main
    assert "待 LLM" not in article
    assert "MVP connector" not in article
    assert "Agent 论文和工具越来越多以后" not in main
    assert "research流程里最容易被低估" not in main
    assert "端侧" in main or "低延迟" in main
    assert "arXiv:2606.20537" in main


def test_pipeline_reruns_specific_draft_stage_without_losing_previous_package(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.regenerate_draft(run.draft.id, stage="wechat", reason="copy preview")

    assert updated.id == run.draft.id
    assert updated.version == 2
    assert updated.html_path == run.draft.html_path
    assert "wechat" in updated.last_rerun_stage


def test_pipeline_reruns_text_stages_with_targeted_content_changes(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    original_markdown = store.read_text(run.draft.markdown_path)

    titled = pipeline.regenerate_draft(run.draft.id, stage="title", reason="make it sharper")
    title_markdown = store.read_text(titled.markdown_path)

    assert titled.version == 2
    assert titled.title != run.draft.title
    assert title_markdown.splitlines()[0].startswith("# ")
    assert title_markdown != original_markdown
    assert titled.title in markdown_section(title_markdown, "## 主文章：长论文解读")
    assert "Rerun note" not in title_markdown

    outlined = pipeline.regenerate_draft(run.draft.id, stage="outline", reason="tighten the lead")
    outline_markdown = store.read_text(outlined.markdown_path)
    outline_main = markdown_section(outline_markdown, "## 主文章：长论文解读")

    assert outlined.version == 3
    assert "### 编辑导语" in outline_main
    assert "tighten the lead" in outline_main
    assert "Rerun note" not in outline_markdown

    articled = pipeline.regenerate_draft(run.draft.id, stage="article", reason="full rewrite")
    article_markdown = store.read_text(articled.markdown_path)

    assert articled.version == 4
    assert article_markdown != original_markdown
    assert "## 主文章：长论文解读" in article_markdown
    assert "待选择" not in article_markdown
    assert "Agent Laboratory 会不会改变 AI 论文实验设计" in article_markdown
    assert "方法贡献" in article_markdown
    assert "重跑编辑札记" in article_markdown
    assert "论文问题" in article_markdown
    assert "Rerun note" not in article_markdown


def test_pipeline_style_rerun_only_rewrites_main_article(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    article_draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    original_markdown = store.read_text(article_draft.markdown_path)
    original_main = markdown_section(original_markdown, "## 主文章：长论文解读")
    original_hotspots = markdown_section(original_markdown, "## 次文章 1：AI 热点")
    original_arxiv = markdown_section(original_markdown, "## 次文章 2：arXiv 高热度文章速报")

    styled = pipeline.regenerate_draft(article_draft.id, stage="style", reason="less report tone")
    styled_markdown = store.read_text(styled.markdown_path)
    styled_main = markdown_section(styled_markdown, "## 主文章：长论文解读")
    styled_hotspots = markdown_section(styled_markdown, "## 次文章 1：AI 热点")
    styled_arxiv = markdown_section(styled_markdown, "## 次文章 2：arXiv 高热度文章速报")

    assert styled.version == 3
    assert styled.last_rerun_stage == "style"
    assert styled_main != original_main
    assert "Agent Laboratory" in styled_main
    assert styled_hotspots == original_hotspots
    assert styled_arxiv == original_arxiv


def test_pipeline_style_rerun_changes_non_agent_topics_when_fallback_is_identical(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    pipeline.run_daily(date="2026-06-20")
    draft = pipeline.draft_topic("topic-context-engineering", date="2026-06-20")
    original_markdown = store.read_text(draft.markdown_path)
    original_main = markdown_section(original_markdown, "## 主文章：长论文解读")
    original_hotspots = markdown_section(original_markdown, "## 次文章 1：AI 热点")
    original_arxiv = markdown_section(original_markdown, "## 次文章 2：arXiv 高热度文章速报")

    styled = pipeline.regenerate_draft(draft.id, stage="style", reason="make it less templated")
    styled_markdown = store.read_text(styled.markdown_path)
    styled_main = markdown_section(styled_markdown, "## 主文章：长论文解读")
    styled_hotspots = markdown_section(styled_markdown, "## 次文章 1：AI 热点")
    styled_arxiv = markdown_section(styled_markdown, "## 次文章 2：arXiv 高热度文章速报")

    assert styled.version == draft.version + 1
    assert styled.last_rerun_stage == "style"
    assert styled_markdown != original_markdown
    assert styled_main != original_main
    assert "风格重跑札记" in styled_main
    assert styled_hotspots == original_hotspots
    assert styled_arxiv == original_arxiv


def test_pipeline_reruns_review_stage_refreshes_checklist(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")
    original_checklist = store.read_text(run.draft.checklist_path)

    reviewed = pipeline.regenerate_draft(run.draft.id, stage="review", reason="final factual pass")
    checklist = store.read_text(reviewed.checklist_path)

    assert reviewed.version == 2
    assert reviewed.last_rerun_stage == "review"
    assert checklist != original_checklist
    assert "重跑审核" in checklist
    assert "final factual pass" in checklist


def test_pipeline_reruns_image_stage_creates_assets_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.regenerate_draft(run.draft.id, stage="cover", reason="need visual")

    assert updated.last_rerun_stage == "cover"
    assert any(asset.kind == "cover" for asset in updated.assets)
    cover = next(asset for asset in updated.assets if asset.kind == "cover")
    assert cover.provider == "image2"
    assert cover.provider_request_id == "resp-test-image"
    assert (tmp_path / cover.path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_pipeline_reruns_visuals_without_touching_mechanism_asset(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    monkeypatch.setattr("ai_radar.pipeline.extract_paper_figures", lambda *args, **kwargs: [])
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")
    mechanism = next(asset for asset in updated.assets if asset.kind == "mechanism")
    mechanism.prompt = "原机制图提示词"
    store.update_draft(updated)

    rerun = pipeline.regenerate_draft(updated.id, stage="visuals", reason="article hard parts only")

    assert next(asset for asset in rerun.assets if asset.kind == "mechanism").prompt == "原机制图提示词"
    assert any(asset.kind == "inline_illustration" for asset in rerun.assets)


def test_pipeline_reruns_visuals_removes_legacy_fixed_inline_assets(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    monkeypatch.setattr("ai_radar.pipeline.extract_paper_figures", lambda *args, **kwargs: [])
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")
    mechanism = next(asset for asset in updated.assets if asset.kind == "mechanism")
    mechanism.prompt = "原机制图提示词"
    updated.assets.extend(
        [
            mechanism.model_copy(update={"id": f"asset-{updated.id}-experiment-flow", "kind": "inline_illustration", "path": f"{Path(updated.markdown_path).parent}/figures/experiment-flow.png"}),
            mechanism.model_copy(update={"id": f"asset-{updated.id}-limitation-map", "kind": "inline_illustration", "path": f"{Path(updated.markdown_path).parent}/figures/limitation-map.png"}),
        ]
    )
    store.update_draft(updated)

    rerun = pipeline.regenerate_draft(updated.id, stage="visuals", reason="article hard parts only")

    assert next(asset for asset in rerun.assets if asset.kind == "mechanism").prompt == "原机制图提示词"
    assert not any("experiment-flow" in asset.path or "limitation-map" in asset.path for asset in rerun.assets)
    assert any(asset.kind == "inline_illustration" for asset in rerun.assets)


def test_pipeline_reruns_visuals_clears_previous_visual_errors_on_success(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    monkeypatch.setattr("ai_radar.pipeline.extract_paper_figures", lambda *args, **kwargs: [])
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")
    updated.generation_error = "replay-simulator: Image2 generation failed: 502"
    store.update_draft(updated)

    rerun = pipeline.regenerate_draft(updated.id, stage="visuals", reason="retry article visuals")

    assert rerun.generation_error == ""


def test_refresh_main_module_generates_only_main_article_content(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    before_markdown = store.read_text(run.draft.markdown_path)
    before_hotspots = before_markdown.split("## 次文章 1：AI 热点", 1)[1].split("## 次文章 2：arXiv 高热度文章速报", 1)[0]
    before_arxiv = before_markdown.split("## 次文章 2：arXiv 高热度文章速报", 1)[1]

    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    after_markdown = store.read_text(updated.markdown_path)
    after_hotspots = after_markdown.split("## 次文章 1：AI 热点", 1)[1].split("## 次文章 2：arXiv 高热度文章速报", 1)[0]
    after_arxiv = after_markdown.split("## 次文章 2：arXiv 高热度文章速报", 1)[1]
    main_section = after_markdown.split("## 主文章：长论文解读", 1)[1].split("## 次文章 1：AI 热点", 1)[0]

    assert updated.last_rerun_stage == "refresh:main"
    assert "待选择" not in main_section
    assert "Agent Laboratory 会不会改变 AI 论文实验设计" in main_section
    assert "方法贡献" in main_section
    assert "我的判断" in main_section
    assert "配图建议" not in main_section
    assert "image2" not in main_section
    assert after_hotspots == before_hotspots
    assert after_arxiv == before_arxiv


def test_refresh_main_module_generates_image2_assets_for_deep_paper_analysis(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    monkeypatch.setattr("ai_radar.pipeline.extract_paper_figures", lambda *args, **kwargs: [])
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    assert {asset.kind for asset in updated.assets} >= {"cover", "mechanism", "inline_illustration"}
    generated_assets = [asset for asset in updated.assets if asset.kind != "source_file"]
    assert all(asset.provider == "image2" for asset in generated_assets)
    assert all(asset.provider_request_id == "resp-test-image" for asset in generated_assets)
    assert (tmp_path / next(asset.path for asset in updated.assets if asset.kind == "cover")).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (tmp_path / next(asset.path for asset in updated.assets if asset.kind == "mechanism")).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    article = store.read_text(updated.markdown_path)
    main = markdown_section(article, "## 主文章：长论文解读")
    assert "配图建议" not in main
    assert "image2" not in main


def test_refresh_main_module_generates_hand_drawn_assets_with_insert_positions(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    monkeypatch.setattr("ai_radar.pipeline.extract_paper_figures", lambda *args, **kwargs: [])
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    assert {asset.kind for asset in updated.assets} >= {"cover", "mechanism", "inline_illustration"}
    assert len([asset for asset in updated.assets if asset.kind == "inline_illustration"]) >= 1
    assert all("手绘" in asset.prompt or "涂鸦" in asset.prompt for asset in updated.assets)
    assert all(asset.insert_after for asset in updated.assets if asset.kind != "source_file")
    assert any("机制总览" in asset.prompt for asset in updated.assets)
    assert any("中文释义" in asset.prompt for asset in updated.assets)
    assert not any("experiment-flow" in asset.path or "limitation-map" in asset.path for asset in updated.assets)
    assert not any("experiment plan" in asset.prompt.lower() or "to be filled" in asset.prompt.lower() for asset in updated.assets)


def test_article_illustration_specs_follow_hard_parts_in_article():
    markdown = """## 主文章：长论文解读

### 长自主循环是常态

编码智能体会连续读文件、写代码、跑命令、读报错，再进入下一轮修复。

### 上下文极长，但输出很短

一次调用会携带数万 token 的历史、代码和工具结果，但回复可能只是一个很短的下一步动作。

### 工具调用呈现重尾分布

Bash、读文件和编译命令的延迟差异很大，调度器需要预测哪些工具会阻塞智能体循环。

### 前缀缓存命中率高但不完美

系统提示和历史上下文大多重复，但人工打断和上下文分叉会让 KV 缓存链断开。
"""

    specs = article_illustration_specs(markdown, limit=5)

    assert 3 <= len(specs) <= 5
    prompts = "\n".join(str(spec["prompt"]) for spec in specs)
    assert "长自主循环" in prompts
    assert "上下文极长，但输出很短" in prompts
    assert "工具调用呈现重尾分布" in prompts
    assert "前缀缓存命中率高但不完美" in prompts
    assert all("中文释义" in str(spec["prompt"]) for spec in specs)
    assert not any("???" in str(spec["prompt"]) or "to be filled" in str(spec["prompt"]).lower() for spec in specs)


def test_article_illustration_specs_are_based_on_current_article_not_fixed_keywords():
    markdown = """## 主文章：长论文解读

### 扩散模型的训练信号为什么会变稀疏

这篇文章解释图像生成模型在少样本场景下，训练信号如何从密集监督变成局部修正。

### 评测指标为什么不能只看平均分

模型在边缘样本上的失败模式，会比总体均值更能说明部署风险。
"""

    specs = article_illustration_specs(markdown, limit=2)

    assert len(specs) == 2
    prompts = "\n".join(str(spec["prompt"]) for spec in specs)
    assert "扩散模型的训练信号为什么会变稀疏" in prompts
    assert "评测指标为什么不能只看平均分" in prompts
    assert "编码智能体" not in prompts
    assert "负载重放" not in prompts


def test_cover_prompt_requires_clear_chinese_cover_without_english_labels():
    topic = Topic(
        id="topic-linguistic-firewall",
        slug="linguistic-firewall",
        cluster_id="cluster-visual",
        paper_id=None,
        title="Linguistic Firewall: Multi-agent routing with geometric defense",
        angle="解释多智能体系统如何用语言规则和几何边界拦截不可靠请求。",
        article_type="long_paper",
        score_total=82,
        score_detail={
            "heat": ScoreItem(value=80, reason="高热论文。"),
            "relevance": ScoreItem(value=82, reason="适合 AI 论文解读。"),
            "writeability": ScoreItem(value=84, reason="有明确机制。"),
            "conversion": ScoreItem(value=78, reason="适合公众号封面。"),
        },
        business_hook="判断语言防火墙是否值得工程团队关注。",
        source_count=1,
        evidence_risk="medium",
        recommendation="适合用中文讲清楚核心概念。",
        signal_ids=[],
        created_at="2026-07-01T00:00:00Z",
    )

    prompt = build_cover_prompt(topic)

    assert "语言防火墙" in prompt
    assert "只允许中文可见文字" in prompt
    assert "不要出现英文" in prompt
    assert "单一主视觉" in prompt
    assert "2.35:1" in prompt
    assert topic.title not in prompt


def test_cover_asset_spec_uses_wechat_cover_ratio():
    topic = Topic(
        id="topic-cover-ratio",
        slug="cover-ratio",
        cluster_id="cluster-cover-ratio",
        paper_id=None,
        title="封面比例",
        angle="封面比例调整",
        article_type="long_paper",
        score_total=80,
        score_detail={},
        business_hook="封面比例调整",
        source_count=1,
        evidence_risk="low",
        recommendation="封面比例调整",
        signal_ids=[],
        created_at="2026-07-01T00:00:00Z",
    )

    cover = visual_asset_specs(topic, None)[0]

    assert cover["size"] == "1504x640"
    assert (cover["width"], cover["height"]) == (1504, 640)


def test_refresh_main_module_adds_extracted_paper_figure_asset(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())

    def fake_extract(*args, **kwargs):
        return [
            {
                "path": "drafts/2026-06-20/agent-lab/figures/paper-figure-1.png",
                "insert_after": "### 方法贡献",
                "prompt": "论文原图截图：PDF 第 1 页",
            }
        ]

    monkeypatch.setattr("ai_radar.pipeline.extract_paper_figures", fake_extract)
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    source = next(asset for asset in updated.assets if asset.kind == "source_file")
    assert source.provider == "paper_pdf"
    assert source.insert_after == "### 方法贡献"
    assert source.path == "drafts/2026-06-20/agent-lab/figures/paper-figure-1.png"


def test_refresh_main_module_passes_selected_narrative_to_llm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    llm = CapturingNarrativeLLM()
    pipeline = DailyPipeline(store=store, llm_provider=llm)
    run = pipeline.run_daily(date="2026-06-20")

    pipeline.refresh_module(run.draft.id, "main", reason="manual module refresh", narrative_type="evaluation_review")

    assert llm.calls
    assert "评测复盘型" in llm.calls[0][0]
    assert "旧评测哪里失真" in llm.calls[0][0]


def test_refresh_main_module_rejects_internal_production_content(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=InternalContentLLM())
    run = pipeline.run_daily(date="2026-06-20")
    before = store.read_text(run.draft.markdown_path)

    with pytest.raises(RuntimeError, match="forbidden internal content"):
        pipeline.refresh_module(run.draft.id, "main", reason="manual module refresh", narrative_type="evaluation_review")

    assert store.read_text(run.draft.markdown_path) == before


def test_main_article_publish_ready_allows_non_template_narrative_titles():
    markdown = """## 主文章：长论文解读

### 旧评测为什么会失真

这篇文章围绕代码智能体在多轮协作里的真实表现展开。旧基准把需求当成一次性交付，模型只要读完任务说明、修改仓库、提交结果，就能得到一个看似清楚的分数。但真实用户往往不会一开始就把目标说完整，需求会随着输出逐步浮现，评测如果忽略这个过程，就会高估智能体的协作能力。

### 新评测到底测出了什么

SWE-Interact 把用户模拟器放进任务流程，让需求在多轮对话里逐步释放。这样测到的不只是代码能不能改对，还包括模型能不能记住早期约束、吸收后续反馈、避免推翻已经做对的部分。强模型在这种设定里仍会出现过度代理、遗忘约束和技术失误，弱模型则更容易在模糊开场下放弃。

### 我的判断

这类评测的价值在于，它把交互式目标发现变成了独立能力轴。后续产品如果只优化单轮完成率，很可能继续制造乐观错觉；真正可用的代码智能体，需要能把用户反馈积累成稳定任务状态，并在多轮修订中保持目标一致。
"""
    assert "方法" not in markdown
    assert "局限" not in markdown
    assert main_article_is_publish_ready(markdown)


def test_refresh_main_module_fails_without_llm_provider(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=None)
    run = pipeline.run_daily(date="2026-06-20")
    before = store.read_text(run.draft.markdown_path)
    package_dir = tmp_path / Path(run.draft.markdown_path).parent

    with pytest.raises(RuntimeError, match="LLM provider is required"):
        pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    unchanged = pipeline.get_draft(run.draft.id)
    assert unchanged.version == run.draft.version
    assert store.read_text(run.draft.markdown_path) == before
    assert not (package_dir / "history").exists()


def test_failed_article_rerun_does_not_archive_or_advance_version(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=None)
    run = pipeline.run_daily(date="2026-06-20")
    package_dir = tmp_path / Path(run.draft.markdown_path).parent

    with pytest.raises(RuntimeError, match="LLM provider is required"):
        pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")

    unchanged = pipeline.get_draft(run.draft.id)
    assert unchanged.version == run.draft.version
    assert unchanged.last_rerun_stage == run.draft.last_rerun_stage
    assert not (package_dir / "history").exists()


def test_refresh_main_module_fails_when_llm_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=DisconnectingLLM())
    run = pipeline.run_daily(date="2026-06-20")
    before = store.read_text(run.draft.markdown_path)

    with pytest.raises(RuntimeError, match="LLM article generation failed"):
        pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    assert store.read_text(run.draft.markdown_path) == before


def test_refresh_main_module_fails_when_llm_output_copies_fallback_template(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=FallbackCopyingLLM())
    run = pipeline.run_daily(date="2026-06-20")
    before = store.read_text(run.draft.markdown_path)

    with pytest.raises(RuntimeError, match="copied local fallback"):
        pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    assert store.read_text(run.draft.markdown_path) == before


def test_refresh_main_module_keeps_article_when_visual_asset_generation_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FailingImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodMainBadSecondaryLLM())
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    article = store.read_text(updated.markdown_path)
    assert "LLM 生成的长论文解读" in article
    assert updated.last_rerun_stage == "refresh:main"
    assert "Image2 generation failed" in updated.generation_error
    assert "image relay unavailable" in updated.generation_error


def test_refresh_main_module_accepts_good_main_even_when_llm_secondary_modules_are_bad(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodMainBadSecondaryLLM())
    run = pipeline.run_daily(date="2026-06-20")
    before_markdown = store.read_text(run.draft.markdown_path)
    before_hotspots = markdown_section(before_markdown, "## 次文章 1：AI 热点")
    before_arxiv = markdown_section(before_markdown, "## 次文章 2：arXiv 高热度文章速报")

    updated = pipeline.refresh_module(run.draft.id, "main", reason="generate selected module")

    markdown = store.read_text(updated.markdown_path)
    main = markdown_section(markdown, "## 主文章：长论文解读")
    assert "LLM 生成的长论文解读" in main
    assert "坏的 bullet 输出" not in markdown
    assert markdown_section(markdown, "## 次文章 1：AI 热点").strip() == before_hotspots.strip()
    assert markdown_section(markdown, "## 次文章 2：arXiv 高热度文章速报").strip() == before_arxiv.strip()
    assert updated.generation_error == ""


def test_refresh_hotspots_module_uses_llm_without_touching_other_modules(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = SecondaryModuleLLM()
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    pipeline.llm_provider = llm
    original_markdown = store.read_text(draft.markdown_path)
    original_main = markdown_section(original_markdown, "## 主文章：长论文解读")
    original_arxiv = markdown_section(original_markdown, "## 次文章 2：arXiv 高热度文章速报")

    updated = pipeline.refresh_module(draft.id, "hotspots", reason="refresh AI hotspots")

    markdown = store.read_text(updated.markdown_path)
    hotspots = markdown_section(markdown, "## 次文章 1：AI 热点")
    assert "LLM 生成的热点判断" in hotspots
    assert markdown_section(markdown, "## 主文章：长论文解读").strip() == original_main.strip()
    assert markdown_section(markdown, "## 次文章 2：arXiv 高热度文章速报").strip() == original_arxiv.strip()
    assert "只改写 AI 热点模块" in llm.calls[0][0]
    assert updated.generation_error == ""


def test_refresh_hotspots_module_uses_non_paper_signals_not_arxiv_topic_pack_items(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    pack_items = [
        TopicPackItem(
            id=f"pack-hotspot-{index}",
            module="ai_hotspots",
            title=f"论文式热点选题 {index}",
            summary=f"论文式热点摘要 {index}",
            angle=f"论文式热点角度 {index}",
            source_urls=[f"https://arxiv.org/abs/2606.9000{index}"],
            arxiv_id=f"2606.9000{index}",
            rank=index,
            dedupe_key=f"hotspot-{index}",
            angle_hash=f"hash-{index}",
        )
        for index in range(1, 8)
    ]
    store.add_topic_pack_version(
        TopicPackVersion(
            id="topic-pack-2026-06-20-v01",
            date="2026-06-20",
            version=1,
            trigger="manual",
            refreshed_module="ai_hotspots",
            long_articles=[],
            ai_hotspots=pack_items,
            arxiv_papers=[],
            created_at="2026-06-20T08:00:00Z",
        )
    )
    store.upsert_many(
        "signals",
        [
            Signal(
                id=f"non-paper-hotspot-{index}",
                source_id="source-ai-news-radar",
                kind="news",
                title=f"非论文热点 {index}",
                summary=f"非论文热点摘要 {index}",
                url=f"https://example.com/news-{index}",
                published_at="2026-06-20T08:00:00Z",
                tags=["news"],
                heat=100 - index,
                entities={},
            )
            for index in range(1, 8)
        ],
    )
    llm = CapturingSecondaryModuleLLM()
    pipeline.llm_provider = llm

    pipeline.refresh_module(draft.id, "hotspots", reason="refresh AI hotspots")

    input_text = llm.calls[0][1]
    material = input_text.split("必须满足:", 1)[0]
    assert material.count("非论文热点 ") == 7
    assert "论文式热点选题" not in material
    assert "arxiv.org/abs/2606.9000" not in material
    assert "输出 7 条" in input_text
    assert "### 1." in input_text
    assert "逐条覆盖全部热点素材" in input_text
    assert "本地 fallback 模块" not in input_text


def test_refresh_hotspots_module_uses_current_topic_pack_ai_hotspots_when_valid(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    pack_items = [
        TopicPackItem(
            id=f"pack-valid-hotspot-{index}",
            module="ai_hotspots",
            title=f"当天热点话题 {index}",
            summary=f"当天热点摘要 {index}",
            angle=f"当天热点角度 {index}",
            source_urls=[f"https://example.com/topic-hotspot-{index}"],
            rank=index,
            dedupe_key=f"valid-hotspot-{index}",
            angle_hash=f"valid-hash-{index}",
        )
        for index in range(1, 8)
    ]
    store.add_topic_pack_version(
        TopicPackVersion(
            id="topic-pack-2026-06-20-v02",
            date="2026-06-20",
            version=2,
            trigger="manual",
            refreshed_module="ai_hotspots",
            long_articles=[],
            ai_hotspots=pack_items,
            arxiv_papers=[],
            created_at="2026-06-20T08:00:00Z",
        )
    )
    store.upsert_many(
        "signals",
        [
            Signal(
                id=f"old-signal-hotspot-{index}",
                source_id="source-ai-news-radar",
                kind="news",
                title=f"旧信号热点 {index}",
                summary=f"旧信号摘要 {index}",
                url=f"https://example.com/old-signal-{index}",
                published_at="2026-06-20T08:00:00Z",
                tags=["news"],
                heat=100 - index,
                entities={},
            )
            for index in range(1, 8)
        ],
    )
    llm = CapturingSecondaryModuleLLM()
    pipeline.llm_provider = llm

    pipeline.refresh_module(draft.id, "hotspots", reason="refresh AI hotspots")

    input_text = llm.calls[0][1]
    material = input_text.split("必须满足:", 1)[0]
    assert material.count("当天热点话题 ") == 7
    assert "旧信号热点" not in material
    assert "https://example.com/topic-hotspot-1" in material
    assert "输出 7 条" in input_text


def test_refresh_hotspots_module_keeps_topic_pack_source_urls_when_llm_rewrites_them(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    pack_items = [
        TopicPackItem(
            id=f"pack-valid-hotspot-{index}",
            module="ai_hotspots",
            title=f"当天热点话题 {index}",
            summary=f"当天热点摘要 {index}",
            angle=f"当天热点角度 {index}",
            source_urls=[f"https://example.com/topic-hotspot-{index}"],
            rank=index,
            dedupe_key=f"valid-hotspot-{index}",
            angle_hash=f"valid-hash-{index}",
        )
        for index in range(1, 8)
    ]
    store.add_topic_pack_version(
        TopicPackVersion(
            id="topic-pack-2026-06-20-v02",
            date="2026-06-20",
            version=2,
            trigger="manual",
            refreshed_module="ai_hotspots",
            long_articles=[],
            ai_hotspots=pack_items,
            arxiv_papers=[],
            created_at="2026-06-20T08:00:00Z",
        )
    )
    pipeline.llm_provider = RewritingHotspotSourceLLM()

    updated = pipeline.refresh_module(draft.id, "hotspots", reason="refresh AI hotspots")

    hotspots = markdown_section(store.read_text(updated.markdown_path), "## 次文章 1：AI 热点")
    assert "https://rewritten.example.com" not in hotspots
    assert hotspots.count("https://example.com/topic-hotspot-") == 7


def test_refresh_secondary_module_keeps_previous_main_generation_error_on_success(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = SecondaryModuleLLM()
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")
    run.draft.generation_error = "previous main failure"
    store.update_draft(run.draft)
    pipeline.llm_provider = llm

    updated = pipeline.refresh_module(run.draft.id, "hotspots", reason="refresh AI hotspots")

    assert updated.generation_error == "previous main failure"


def test_refresh_arxiv_module_clears_previous_arxiv_generation_error_on_success(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = SecondaryModuleLLM()
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")
    run.draft.generation_error = "LLM arxiv response failed publishability validation; used fallback module."
    store.update_draft(run.draft)
    pipeline.llm_provider = llm

    updated = pipeline.refresh_module(run.draft.id, "arxiv", reason="refresh arxiv")

    assert updated.generation_error == ""


def test_refresh_arxiv_module_uses_llm_without_touching_other_modules(tmp_path: Path):
    store = JsonStore(tmp_path)
    llm = SecondaryModuleLLM()
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    pipeline.llm_provider = llm
    original_markdown = store.read_text(draft.markdown_path)
    original_main = markdown_section(original_markdown, "## 主文章：长论文解读")
    original_hotspots = markdown_section(original_markdown, "## 次文章 1：AI 热点")

    updated = pipeline.refresh_module(draft.id, "arxiv", reason="refresh arxiv brief")

    markdown = store.read_text(updated.markdown_path)
    arxiv = markdown_section(markdown, "## 次文章 2：arXiv 高热度文章速报")
    assert "LLM 生成的 arXiv 阅读顺序" in arxiv
    assert markdown_section(markdown, "## 主文章：长论文解读").strip() == original_main.strip()
    assert markdown_section(markdown, "## 次文章 1：AI 热点").strip() == original_hotspots.strip()
    assert "只改写 arXiv 速报模块" in llm.calls[0][0]
    assert updated.generation_error == ""


def test_refresh_arxiv_module_uses_all_topic_pack_arxiv_papers(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    arxiv_items = [
        TopicPackItem(
            id=f"pack-arxiv-{index}",
            module="arxiv_papers",
            title=f"今日 arXiv 论文 {index}",
            summary=f"今日 arXiv 摘要 {index}",
            angle=f"今日 arXiv 角度 {index}",
            source_urls=[f"https://arxiv.org/abs/2606.9100{index}"],
            arxiv_id=f"2606.9100{index}",
            rank=index,
            dedupe_key=f"arxiv-{index}",
            angle_hash=f"arxiv-hash-{index}",
        )
        for index in range(1, 8)
    ]
    store.add_topic_pack_version(
        TopicPackVersion(
            id="topic-pack-2026-06-20-v02",
            date="2026-06-20",
            version=2,
            trigger="manual",
            refreshed_module="arxiv_papers",
            long_articles=[],
            ai_hotspots=[],
            arxiv_papers=arxiv_items,
            created_at="2026-06-20T08:00:00Z",
        )
    )
    store.upsert_many(
        "papers",
        [
            Paper(
                id=f"paper-pack-arxiv-{index}",
                arxiv_id=f"2606.9100{index}",
                title=f"今日 arXiv 论文 {index}",
                authors=["A. Researcher"],
                abstract=f"今日 arXiv 摘要 {index}",
                pdf_url=f"https://arxiv.org/pdf/2606.9100{index}",
                published_at="2026-06-20T00:00:00Z",
                categories=["cs.AI"],
                method_summary=f"今日 arXiv 方法 {index}",
                experiment_summary=f"今日 arXiv 实验 {index}",
                limitations=f"今日 arXiv 局限 {index}",
                replication_value=50 + index,
                extension_topics=[f"今日 arXiv 延展 {index}"],
            )
            for index in range(1, 8)
        ],
    )
    llm = CapturingArxivModuleLLM()
    pipeline.llm_provider = llm

    pipeline.refresh_module(draft.id, "arxiv", reason="refresh arxiv brief")

    input_text = llm.calls[0][1]
    material = input_text.split("必须满足:", 1)[0]
    arxiv_material = material.split("素材:", 1)[1]
    assert material.count("今日 arXiv 论文 ") == 7
    assert "Agent Laboratory" not in arxiv_material
    assert "输出 7 篇" in input_text
    assert "逐篇覆盖全部 arXiv 论文素材" in input_text
    assert "原文标题" in input_text
    assert "文章来源" in input_text
    assert "### 1." in input_text
    assert "挑 3-5 篇" not in input_text
    assert "本地 fallback 模块" not in input_text


def test_refresh_secondary_module_fails_without_overwriting_when_llm_output_is_invalid(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=GoodAgentLabLLM())
    run = pipeline.run_daily(date="2026-06-20")
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    before = store.read_text(draft.markdown_path)
    pipeline.llm_provider = BadSecondaryModuleLLM()

    with pytest.raises(RuntimeError, match="LLM arxiv response failed publishability validation"):
        pipeline.refresh_module(draft.id, "arxiv", reason="refresh arxiv brief")

    assert store.read_text(draft.markdown_path) == before


def test_refresh_secondary_modules_leave_visible_change_when_generated_content_matches(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=SecondaryModuleLLM())
    run = pipeline.run_daily(date="2026-06-20")
    pipeline.llm_provider = GoodAgentLabLLM()
    draft = pipeline.regenerate_draft(run.draft.id, stage="article", reason="write first")
    pipeline.llm_provider = SecondaryModuleLLM()
    original_markdown = store.read_text(draft.markdown_path)
    original_main = markdown_section(original_markdown, "## 主文章：长论文解读")
    original_arxiv = markdown_section(original_markdown, "## 次文章 2：arXiv 高热度文章速报")

    first_hotspots = pipeline.refresh_module(draft.id, "hotspots", reason="refresh visible hotspots")
    before_second_hotspots = store.read_text(first_hotspots.markdown_path)
    refreshed_hotspots = pipeline.refresh_module(draft.id, "hotspots", reason="refresh visible hotspots again")
    hotspots_markdown = store.read_text(refreshed_hotspots.markdown_path)
    refreshed_hotspots_section = markdown_section(hotspots_markdown, "## 次文章 1：AI 热点")

    assert refreshed_hotspots.last_rerun_stage == "refresh:hotspots"
    assert hotspots_markdown != before_second_hotspots
    assert "AI 热点刷新札记" in refreshed_hotspots_section
    assert markdown_section(hotspots_markdown, "## 主文章：长论文解读") == original_main
    assert markdown_section(hotspots_markdown, "## 次文章 2：arXiv 高热度文章速报") == original_arxiv

    first_arxiv = pipeline.refresh_module(draft.id, "arxiv", reason="refresh visible arxiv")
    before_second_arxiv = store.read_text(first_arxiv.markdown_path)
    refreshed_arxiv = pipeline.refresh_module(draft.id, "arxiv", reason="refresh visible arxiv again")
    arxiv_markdown = store.read_text(refreshed_arxiv.markdown_path)
    refreshed_arxiv_section = markdown_section(arxiv_markdown, "## 次文章 2：arXiv 高热度文章速报")

    assert refreshed_arxiv.last_rerun_stage == "refresh:arxiv"
    assert arxiv_markdown != before_second_arxiv
    assert "arXiv 速报刷新札记" in refreshed_arxiv_section


def test_pipeline_reruns_image_stage_without_corrupting_png(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ai_radar.pipeline.Image2Provider.from_env", lambda storage_root=None: FakeImageProvider())
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    pipeline.run_daily(date="2026-06-20")
    draft = pipeline.draft_topic("topic-agent-lab", date="2026-06-20")

    updated = pipeline.regenerate_draft(draft.id, stage="cover", reason="new visual angle")
    cover = next(asset for asset in updated.assets if asset.kind == "cover")
    cover_path = tmp_path / cover.path
    after = cover_path.read_bytes()

    assert updated.last_rerun_stage == "cover"
    assert after.startswith(b"\x89PNG\r\n\x1a\n")
    assert after != b""
