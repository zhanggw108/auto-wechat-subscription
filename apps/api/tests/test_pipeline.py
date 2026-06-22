from pathlib import Path

from ai_radar.pipeline import DailyPipeline
from ai_radar.storage import JsonStore


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
    assert "待选择" in article
    assert "次文章 1：AI 热点" in article
    assert "次文章 2：arXiv 高热度文章速报" in article
    assert "来源清单" in article
    assert "这部分不会自动生成" in article

    html = (package_dir / "article-wechat.html").read_text(encoding="utf-8")
    assert "<article" in html
    assert "wechat-draft" in html

    checklist = (package_dir / "review-checklist.md").read_text(encoding="utf-8")
    assert "- [ ] 标题是否准确，不夸大" in checklist
    assert "- [ ] HTML 复制到公众号后台是否正常" in checklist

    assert run.draft.assets == []


def test_pipeline_generates_long_article_for_user_selected_topic(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    pipeline.run_daily(date="2026-06-20")

    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")

    assert draft.topic_id == "topic-long-context-rag"
    assert draft.status == "review"
    assert draft.assets == []

    package_dir = tmp_path / draft.markdown_path
    article = package_dir.read_text(encoding="utf-8")
    draft_dir = package_dir.parent
    assert (draft_dir / "cover.prompt.txt").exists()
    assert (draft_dir / "figures/mechanism.prompt.txt").exists()
    assert "主文章：长论文解读" in article
    assert "长上下文模型来了，RAG 为什么还没有过时？" in article
    assert "适合本科生、硕士研究生重点阅读" in article
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
        assert len(body_lines) >= 8
        assert any(line.startswith("### ") for line in body_lines)
        assert not any(line.startswith("- ") for line in body_lines)
        assert "这一栏已自动整理" not in section
        assert "我的判断：它值得关注的地方" not in section

    assert "今天这几条消息，我建议你不要当新闻看" in hotspots
    assert "今天这组论文，我建议先按选题价值来读" in arxiv
    html = store.read_text(draft.html_path)
    assert "<h3>今天这几条消息，我建议你不要当新闻看</h3>" in html
    assert "<h3>今天这组论文，我建议先按选题价值来读</h3>" in html
    assert "<p>### " not in html


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
    assert "今天这组论文，我建议先按选题价值来读" in arxiv


def test_agent_laboratory_publish_package_uses_verified_sources(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, llm_provider=BadArticleLLM())
    pipeline.run_daily(date="2026-06-22")

    draft = pipeline.draft_topic("topic-agent-lab", date="2026-06-22")

    article = store.read_text(draft.markdown_path)
    html = store.read_text(draft.html_path)
    sources = store.read_text(draft.sources_path)
    evidence = store.read_text(draft.evidence_path)
    combined = "\n".join([article, html, sources, evidence])

    assert "https://arxiv.org/abs/2501.04227" in combined
    assert "https://arxiv.org/pdf/2501.04227" in combined
    assert "https://github.com/SamuelSchmidgall/AgentLaboratory" in combined
    assert "arXiv:2501.04227" in article
    assert "2025 年 1 月" in article
    assert "我今天重新翻到 Agent Laboratory" in article
    assert "不是一个灵感机器" in article
    assert "example.com" not in combined
    assert "2606.20101" not in combined
    assert "github.com/example" not in combined
    assert "Rerun note" not in combined
    assert "待 LLM" not in article
    assert "配图建议" not in article
    assert "The guidance" not in article
    assert "The paper reports" not in article


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
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")
    original_markdown = store.read_text(run.draft.markdown_path)

    titled = pipeline.regenerate_draft(run.draft.id, stage="title", reason="make it sharper")
    title_markdown = store.read_text(titled.markdown_path)

    assert titled.version == 2
    assert titled.title != run.draft.title
    assert title_markdown.splitlines()[0].startswith("# ")
    assert title_markdown != original_markdown
    assert "Rerun note" not in title_markdown

    outlined = pipeline.regenerate_draft(run.draft.id, stage="outline", reason="tighten the lead")
    outline_markdown = store.read_text(outlined.markdown_path)

    assert outlined.version == 3
    assert "## 编辑导语" in outline_markdown
    assert "tighten the lead" in outline_markdown
    assert "Rerun note" not in outline_markdown

    articled = pipeline.regenerate_draft(run.draft.id, stage="article", reason="full rewrite")
    article_markdown = store.read_text(articled.markdown_path)

    assert articled.version == 4
    assert article_markdown != original_markdown
    assert "## 主文章：长论文解读" in article_markdown
    assert "待选择" not in article_markdown
    assert "我今天重新翻到 Agent Laboratory" in article_markdown
    assert "重跑编辑札记" in article_markdown
    assert "对于正在找 AI 论文方向的同学" in article_markdown
    assert "Rerun note" not in article_markdown


def test_pipeline_style_rerun_only_rewrites_main_article(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
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


def test_pipeline_reruns_image_stage_creates_assets_when_missing(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
    run = pipeline.run_daily(date="2026-06-20")

    updated = pipeline.regenerate_draft(run.draft.id, stage="cover", reason="need visual")

    assert updated.last_rerun_stage == "cover"
    assert any(asset.kind == "cover" for asset in updated.assets)
    cover = next(asset for asset in updated.assets if asset.kind == "cover")
    assert (tmp_path / cover.path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_refresh_main_module_generates_only_main_article_content(tmp_path: Path):
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store)
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
    assert "我今天重新翻到 Agent Laboratory" in main_section
    assert "不是一个灵感机器" in main_section
    assert after_hotspots == before_hotspots
    assert after_arxiv == before_arxiv


def test_pipeline_reruns_image_stage_without_corrupting_png(tmp_path: Path):
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
