from __future__ import annotations

import html
import json
import struct
import zlib
from datetime import date as date_type, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import httpx

from .connectors import parse_arxiv_feed, parse_rss_feed
from .models import (
    DailyRun,
    Draft,
    DraftAsset,
    EvidenceItem,
    Job,
    Paper,
    RadarToday,
    RefreshModule,
    RefreshStatus,
    ScoreItem,
    Signal,
    Topic,
    now_iso,
)
from .image_provider import Image2Provider
from .llm_provider import ResponsesLLMProvider
from .sample_data import seed_papers, seed_signals, seed_sources
from .storage import JsonStore, slugify
from .writer import rewrite_khazix_style


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(BEIJING_TZ)
    if current.tzinfo is not None:
        current = current.astimezone(BEIJING_TZ)
    return current.replace(tzinfo=None, microsecond=0)


class DailyPipeline:
    def __init__(
        self,
        store: JsonStore,
        live_sources: bool = False,
        http_client: httpx.Client | None = None,
        llm_provider=None,
    ):
        self.store = store
        self.live_sources = live_sources
        self.http_client = http_client or httpx.Client(timeout=20)
        self.llm_provider = llm_provider if llm_provider is not None else ResponsesLLMProvider.from_env(store.root)

    def refresh_status(self, now: datetime | None = None) -> RefreshStatus:
        current = beijing_now(now)
        today = current.date().isoformat()
        scheduled = datetime.combine(current.date(), time(hour=11))
        refresh = self.store.get_refresh(today) or {}
        today_refreshed = bool(refresh.get("last_refresh_at"))
        next_refresh = scheduled
        if today_refreshed or current >= scheduled:
            next_refresh = scheduled + timedelta(days=1)
        return RefreshStatus(
            date=today,
            refresh_time="11:00",
            today_refreshed=today_refreshed,
            last_refresh_at=refresh.get("last_refresh_at"),
            next_refresh_at=next_refresh.isoformat(),
            seconds_until_next_refresh=max(0, int((next_refresh - current).total_seconds())),
        )

    def refresh_if_due(self, now: datetime | None = None) -> RefreshStatus:
        current = beijing_now(now)
        today = current.date().isoformat()
        scheduled = datetime.combine(current.date(), time(hour=11))
        refresh = self.store.get_refresh(today)
        if current >= scheduled and not refresh:
            run = self.run_daily(today)
            self.store.set_refresh(
                today,
                {
                    "last_refresh_at": current.replace(microsecond=0).isoformat(),
                    "draft_id": run.draft.id,
                    "reason": "scheduled daily refresh",
                },
            )
        return self.refresh_status(current)

    def ensure_daily_run(self, date: str | None = None) -> DailyRun:
        run_date = date or date_type.today().isoformat()
        existing = self.store.get_run(run_date)
        if existing:
            return self._hydrate_run(existing)
        return self.run_daily(run_date)

    def run_daily(self, date: str | None = None) -> DailyRun:
        run_date = date or date_type.today().isoformat()
        sources = seed_sources(run_date)
        signals = seed_signals(run_date)
        papers = seed_papers(run_date)
        if self.live_sources:
            live_papers, live_signals = self._fetch_live_sources(sources)
            papers = merge_by_id(papers, live_papers)
            signals = merge_by_id(signals, live_signals)
        topics = self._build_topics(run_date, signals, papers)
        selected_topic = self._select_front_page(topics)
        evidence_items = self._build_evidence(selected_topic, signals, papers)
        draft = self._write_draft_package(run_date, selected_topic, signals, papers, evidence_items, include_long_article=False)
        selected_topic.status = "selected"
        topics = [selected_topic if topic.id == selected_topic.id else topic for topic in topics]

        self.store.upsert_many("sources", sources)
        self.store.upsert_many("signals", signals)
        self.store.upsert_many("papers", papers)
        self.store.upsert_many("topics", topics)
        self.store.upsert_many("evidence_items", evidence_items)
        self.store.upsert_many("drafts", [draft])
        self.store.set_run(
            run_date,
            {
                "date": run_date,
                "source_ids": [item.id for item in sources],
                "signal_ids": [item.id for item in signals],
                "paper_ids": [item.id for item in papers],
                "topic_ids": [item.id for item in topics],
                "selected_topic_id": selected_topic.id,
                "evidence_ids": [item.id for item in evidence_items],
                "draft_id": draft.id,
            },
        )
        return DailyRun(
            date=run_date,
            sources=sources,
            signals=signals,
            papers=papers,
            topics=topics,
            selected_topic=selected_topic,
            evidence_items=evidence_items,
            draft=draft,
        )

    def radar_today(self, date: str | None = None) -> RadarToday:
        run = self.ensure_daily_run(date)
        categories: Dict[str, int] = {}
        for signal in run.signals:
            categories[signal.kind] = categories.get(signal.kind, 0) + 1
        return RadarToday(
            date=run.date,
            signal_count=len(run.signals),
            ai_relevant_count=sum(1 for signal in run.signals if signal.tags),
            topic_count=len(run.topics),
            source_health=run.sources,
            top_hotspots=sorted(run.signals, key=lambda item: item.heat, reverse=True)[:5],
            categories=categories,
            recommended_topic=run.selected_topic,
            draft=run.draft,
        )

    def list_topics(self, date: str | None = None) -> List[Topic]:
        run = self.ensure_daily_run(date)
        current = {topic.id: topic for topic in self.store.list_topics()}
        return sorted([current.get(topic.id, topic) for topic in run.topics], key=lambda item: item.score_total, reverse=True)

    def get_topic(self, topic_id: str) -> Topic:
        for topic in self.store.list_topics():
            if topic.id == topic_id:
                return topic
        raise KeyError(topic_id)

    def set_topic_status(self, topic_id: str, status: str) -> Topic:
        topic = self.get_topic(topic_id)
        topic.status = status
        self.store.update_topic(topic)
        return topic

    def draft_topic(self, topic_id: str, date: str | None = None) -> Draft:
        run = self.ensure_daily_run(date)
        topic = self.get_topic(topic_id)
        signals = self.store.list_signals()
        papers = self.store.list_papers()
        evidence_items = self._build_evidence(topic, signals, papers)
        draft = self._write_draft_package(
            run.date,
            topic,
            signals,
            papers,
            evidence_items,
            include_long_article=True,
            include_assets=False,
        )
        topic.status = "drafted"
        self.store.update_topic(topic)
        self.store.upsert_many("evidence_items", evidence_items)
        self.store.upsert_many("drafts", [draft])
        return draft

    def refresh_module(self, draft_id: str, module: RefreshModule, reason: str = "") -> Draft:
        draft = self.get_draft(draft_id)
        topic = self.get_topic(draft.topic_id)
        signals = self.store.list_signals()
        papers = self.store.list_papers()
        evidence_items = [item for item in self.store.list_evidence() if item.topic_id == topic.id]
        if not evidence_items:
            evidence_items = self._build_evidence(topic, signals, papers)
            self.store.upsert_many("evidence_items", evidence_items)
        self.store.archive_draft_files(draft, f"v{draft.version}-{module}-{now_iso()}")

        paper = next((item for item in papers if item.id == topic.paper_id), None)
        ai_hotspots = sorted([signal for signal in signals if signal.kind != "paper"], key=lambda item: item.heat, reverse=True)[:5]
        arxiv_hot_papers = sorted(papers, key=lambda item: item.replication_value, reverse=True)[:5]
        include_long_article = module == "main" or bool(draft.assets)
        existing_markdown = self.store.read_text(draft.markdown_path)
        generated_markdown = build_article_markdown(
            topic,
            paper,
            evidence_items,
            ai_hotspots,
            arxiv_hot_papers,
            include_long_article=include_long_article,
        )
        if include_long_article and self.llm_provider and module == "main":
            generated_markdown = self._generate_article_markdown(
                topic,
                paper,
                evidence_items,
                ai_hotspots,
                arxiv_hot_papers,
                include_long_article=True,
            )
        markdown = replace_article_module(existing_markdown, generated_markdown, module)
        self.store.write_text(draft.markdown_path, markdown)
        self.store.write_text(draft.html_path, markdown_to_wechat_html(markdown))
        draft.version += 1
        draft.last_rerun_stage = f"refresh:{module}"
        draft.updated_at = now_iso()
        self.store.update_draft(draft)
        return draft

    def list_drafts(self, date: str | None = None) -> List[Draft]:
        run = self.ensure_daily_run(date)
        draft_ids = {run.draft.id}
        return [draft for draft in self.store.list_drafts() if draft.id in draft_ids or not date]

    def get_draft(self, draft_id: str) -> Draft:
        for draft in self.store.list_drafts():
            if draft.id == draft_id:
                return draft
        raise KeyError(draft_id)

    def draft_detail(self, draft_id: str):
        from .models import DraftDetail

        draft = self.get_draft(draft_id)
        topic = self.get_topic(draft.topic_id)
        evidence = [item for item in self.store.list_evidence() if item.topic_id == topic.id]
        return DraftDetail(
            draft=draft,
            topic=topic,
            evidence_items=evidence,
            markdown=self.store.read_text(draft.markdown_path),
            html=self.store.read_text(draft.html_path),
            sources=self.store.read_text(draft.sources_path),
            review_checklist=self.store.read_text(draft.checklist_path),
        )

    def update_draft_content(self, draft_id: str, markdown: str, reason: str = "manual edit"):
        from .models import DraftDetail

        draft = self.get_draft(draft_id)
        topic = self.get_topic(draft.topic_id)
        self.store.archive_draft_files(draft, f"v{draft.version}-manual-edit-{now_iso()}")
        self.store.write_text(draft.markdown_path, markdown)
        self.store.write_text(draft.html_path, markdown_to_wechat_html(markdown))
        draft.version += 1
        draft.last_rerun_stage = "manual-edit"
        draft.updated_at = now_iso()
        self.store.update_draft(draft)
        evidence = [item for item in self.store.list_evidence() if item.topic_id == topic.id]
        return DraftDetail(
            draft=draft,
            topic=topic,
            evidence_items=evidence,
            markdown=markdown,
            html=self.store.read_text(draft.html_path),
            sources=self.store.read_text(draft.sources_path),
            review_checklist=self.store.read_text(draft.checklist_path),
        )

    def regenerate_draft(self, draft_id: str, stage: str, reason: str = "") -> Draft:
        draft = self.get_draft(draft_id)
        topic = self.get_topic(draft.topic_id)
        self.store.archive_draft_files(draft, f"v{draft.version}-{stage}-{now_iso()}")
        draft.version += 1
        draft.last_rerun_stage = stage
        draft.updated_at = now_iso()
        if stage == "wechat":
            markdown = self.store.read_text(draft.markdown_path)
            self.store.write_text(draft.html_path, markdown_to_wechat_html(markdown))
        elif stage in {"cover", "mechanism"}:
            self._regenerate_visual_asset(draft, topic, stage, reason)
        elif stage == "review":
            checklist = build_review_checklist(reason=reason, draft=draft)
            self.store.write_text(draft.checklist_path, checklist)
        elif stage == "article":
            markdown = self._regenerate_full_article(topic)
            markdown = add_article_rerun_note(markdown, topic, reason)
            self.store.write_text(draft.markdown_path, markdown)
            self.store.write_text(draft.html_path, markdown_to_wechat_html(markdown))
        elif stage in {"title", "outline", "style"}:
            markdown = self.store.read_text(draft.markdown_path)
            if stage == "title":
                title = build_rerun_title(topic, reason)
                draft.title = title
                markdown = replace_first_heading(markdown, f"今日 AI 论文与热点文章包：{title}")
            elif stage == "outline":
                markdown = upsert_intro_section(markdown, topic, reason)
            else:
                markdown = self._rewrite_style(markdown, topic, reason)
            self.store.write_text(draft.markdown_path, markdown)
            self.store.write_text(draft.html_path, markdown_to_wechat_html(markdown))
        else:
            raise ValueError(f"Unsupported rerun stage: {stage}")
        self.store.update_draft(draft)
        return draft

    def _regenerate_full_article(self, topic: Topic) -> str:
        signals = self.store.list_signals()
        papers = self.store.list_papers()
        evidence_items = [item for item in self.store.list_evidence() if item.topic_id == topic.id]
        if not evidence_items:
            evidence_items = self._build_evidence(topic, signals, papers)
            self.store.upsert_many("evidence_items", evidence_items)
        paper = next((item for item in papers if item.id == topic.paper_id), None)
        ai_hotspots = sorted([signal for signal in signals if signal.kind != "paper"], key=lambda item: item.heat, reverse=True)[:5]
        arxiv_hot_papers = sorted(papers, key=lambda item: item.replication_value, reverse=True)[:5]
        return self._generate_article_markdown(
            topic,
            paper,
            evidence_items,
            ai_hotspots,
            arxiv_hot_papers,
            include_long_article=True,
        )

    def _regenerate_visual_asset(self, draft: Draft, topic: Topic, stage: str, reason: str) -> None:
        papers = self.store.list_papers()
        paper = next((item for item in papers if item.id == topic.paper_id), None)
        prompt = build_cover_prompt(topic) if stage == "cover" else build_mechanism_prompt(topic, paper)
        if reason:
            prompt = f"{prompt}\n\nRerun reason: {reason}"
        rgb = (20, 140, 190) if stage == "cover" else (220, 96, 58)
        relative_dir = Path(draft.markdown_path).parent
        relative_path = relative_dir / ("cover.png" if stage == "cover" else "figures/mechanism.png")
        result = generate_image_asset(self.store.root / relative_path, prompt, rgb=rgb, storage_root=self.store.root)
        existing = next((asset for asset in draft.assets if asset.kind == stage), None)
        if existing:
            existing.prompt = prompt
            existing.revised_prompt = result.revised_prompt
            existing.provider = result.provider
            existing.provider_request_id = result.provider_request_id or None
            existing.path = str(relative_path)
            return
        draft.assets.append(
            DraftAsset(
                id=f"asset-{draft.id}-{stage}",
                draft_id=draft.id,
                kind=stage,
                prompt=prompt,
                path=str(relative_path),
                revised_prompt=result.revised_prompt,
                provider=result.provider,
                provider_request_id=result.provider_request_id or None,
                created_at=now_iso(),
            )
        )

    def mark_published(self, draft_id: str) -> Draft:
        draft = self.get_draft(draft_id)
        draft.status = "published"
        draft.updated_at = now_iso()
        self.store.update_draft(draft)
        topic = self.get_topic(draft.topic_id)
        topic.status = "published"
        self.store.update_topic(topic)
        return draft

    def create_refresh_job(self, source_id: str) -> Job:
        sources = {source.id: source for source in self.store.list_sources()}
        source = sources.get(source_id)
        if source is None:
            job = Job(
                id=f"job-refresh-{source_id}-{len(self.store.list_jobs()) + 1}",
                type="ingest.fetch_source",
                status="failed",
                input={"source_id": source_id},
                error="Source not found",
                started_at=now_iso(),
                finished_at=now_iso(),
            )
            self.store.update_job(job)
            return job

        started_at = now_iso()
        try:
            papers, signals = self._fetch_one_source(source)
            if papers:
                self.store.upsert_many("papers", papers)
            if signals:
                self.store.upsert_many("signals", signals)
            source.status = "healthy"
            source.last_success_at = now_iso()
            source.last_error = None
            self.store.upsert_many("sources", [source])
            status = "succeeded"
            error = ""
            output = {"fetched_papers": str(len(papers)), "fetched_signals": str(len(signals))}
        except Exception as exc:
            source.status = "degraded"
            source.last_error = str(exc)
            self.store.upsert_many("sources", [source])
            status = "failed"
            error = str(exc)
            output = {"fetched_papers": "0", "fetched_signals": "0"}

        job = Job(
            id=f"job-refresh-{source_id}-{len(self.store.list_jobs()) + 1}",
            type="ingest.fetch_source",
            status=status,
            input={"source_id": source_id},
            output=output,
            error=error,
            started_at=started_at,
            finished_at=now_iso(),
        )
        self.store.update_job(job)
        return job

    def get_job(self, job_id: str) -> Job:
        for job in self.store.list_jobs():
            if job.id == job_id:
                return job
        raise KeyError(job_id)

    def cancel_job(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        job.status = "canceled"
        job.finished_at = now_iso()
        self.store.update_job(job)
        return job

    def _hydrate_run(self, payload: Dict[str, object]) -> DailyRun:
        sources = {item.id: item for item in self.store.list_sources()}
        signals = {item.id: item for item in self.store.list_signals()}
        papers = {item.id: item for item in self.store.list_papers()}
        topics = {item.id: item for item in self.store.list_topics()}
        evidence = {item.id: item for item in self.store.list_evidence()}
        drafts = {item.id: item for item in self.store.list_drafts()}
        return DailyRun(
            date=str(payload["date"]),
            sources=[sources[item] for item in payload["source_ids"]],
            signals=[signals[item] for item in payload["signal_ids"]],
            papers=[papers[item] for item in payload["paper_ids"]],
            topics=[topics[item] for item in payload["topic_ids"]],
            selected_topic=topics[str(payload["selected_topic_id"])],
            evidence_items=[evidence[item] for item in payload["evidence_ids"]],
            draft=drafts[str(payload["draft_id"])],
        )

    def _build_topics(self, run_date: str, signals: List[Signal], papers: List[Paper]) -> List[Topic]:
        now = f"{run_date}T07:50:00Z"
        signal_map = {signal.id: signal for signal in signals}
        definitions = [
            (
                "topic-agent-lab",
                "Agent Laboratory 会不会改变 AI 论文实验设计？",
                "从研究型 agent 的证据链、实验规划和可复现价值切入，写一篇头版论文解析。",
                "long_paper",
                "paper-agent-lab",
                ["signal-agent-lab-paper", "signal-agent-lab-code", "signal-post-paper-topics"],
            ),
            (
                "topic-long-context-rag",
                "长上下文模型来了，RAG 为什么还没有过时？",
                "把长上下文和检索增强放在同一张实验桌上，讨论论文选题和评测切口。",
                "long_paper",
                "paper-long-context-rag",
                ["signal-long-context-rag", "signal-openai-evals"],
            ),
            (
                "topic-agent-evals",
                "Agent 评测正在从 demo 走向工程纪律",
                "把官方 eval 指南、开源评测工具和论文问题串成行业深度解读。",
                "industry_analysis",
                None,
                ["signal-openai-evals", "signal-github-evalkit", "signal-post-paper-topics"],
            ),
            (
                "topic-context-engineering",
                "Context Engineering 正在取代单点 Prompt 技巧",
                "解释为什么记忆、检索、工具和 trace 比 prompt 模板更适合做论文方向。",
                "topic_inspiration",
                None,
                ["signal-anthropic-context", "signal-long-context-rag"],
            ),
            (
                "topic-evalkit",
                "EvalKit 适合拿来做 LLM 应用论文 baseline 吗？",
                "从工具推荐角度判断它能否支撑复现、评测和实验报告。",
                "short_hotspot",
                None,
                ["signal-github-evalkit"],
            ),
            (
                "topic-agent-builder",
                "可视化 Agent Builder 的真正价值是实验回放",
                "把产品更新转成学生可理解的实验工程启发。",
                "short_hotspot",
                None,
                ["signal-product-agent-builder"],
            ),
            (
                "topic-thesis-agent-eval",
                "今天可以延伸的 Agent 评测论文选题",
                "整理 1-3 个适合课程论文和毕业论文的可做方向。",
                "topic_inspiration",
                None,
                ["signal-post-paper-topics", "signal-openai-evals"],
            ),
        ]
        topics: List[Topic] = []
        for index, (topic_id, title, angle, article_type, paper_id, signal_ids) in enumerate(definitions):
            linked = [signal_map[item] for item in signal_ids]
            heat = min(100, round(sum(signal.heat for signal in linked) / len(linked) + len(linked) * 3))
            relevance = 94 if article_type == "long_paper" else 78 + index
            writeability = 90 if len(linked) > 1 else 72
            conversion = 92 if article_type in {"long_paper", "topic_inspiration"} else 70
            score_total = round(heat * 0.28 + relevance * 0.30 + writeability * 0.24 + conversion * 0.18)
            topics.append(
                Topic(
                    id=topic_id,
                    slug=slugify(title),
                    cluster_id=f"cluster-{topic_id}",
                    paper_id=paper_id,
                    title=title,
                    angle=angle,
                    article_type=article_type,
                    score_total=score_total,
                    score_detail={
                        "heat": ScoreItem(value=heat, reason=f"{len(linked)} 个信号在 24 小时内共同指向该方向。"),
                        "relevance": ScoreItem(value=relevance, reason="与论文选题、实验设计、复现或 AI 研究方法直接相关。"),
                        "writeability": ScoreItem(value=writeability, reason="能拆成问题、方法、实验、局限和启发，适合公众号结构。"),
                        "conversion": ScoreItem(value=conversion, reason="可以自然延伸到选题设计、baseline、复现和论文辅导咨询。"),
                    },
                    business_hook="适合引导学生从研究问题、实验复现和创新点设计三个角度切入。",
                    source_count=len(linked),
                    evidence_risk="low" if len(linked) >= 2 else "medium",
                    recommendation=angle,
                    signal_ids=signal_ids,
                    created_at=now,
                )
            )
        known_signal_ids = {signal_id for topic in topics for signal_id in topic.signal_ids}
        dynamic_signals = [signal for signal in signals if signal.id not in known_signal_ids]
        for signal in sorted(dynamic_signals, key=lambda item: item.heat, reverse=True)[:3]:
            article_type = "long_paper" if signal.kind == "paper" else "short_hotspot"
            heat = min(100, signal.heat + 4)
            relevance = 86 if signal.kind == "paper" else 74
            writeability = 84 if signal.summary else 68
            conversion = 82 if signal.kind == "paper" else 64
            score_total = round(heat * 0.28 + relevance * 0.30 + writeability * 0.24 + conversion * 0.18)
            linked_paper = next((paper for paper in papers if paper.title == signal.title or paper.arxiv_id in signal.url), None)
            topics.append(
                Topic(
                    id=f"topic-live-{signal.id.removeprefix('signal-')}",
                    slug=slugify(signal.title),
                    cluster_id=f"cluster-live-{signal.id}",
                    paper_id=linked_paper.id if linked_paper else None,
                    title=signal.title,
                    angle=signal.summary,
                    article_type=article_type,
                    score_total=score_total,
                    score_detail={
                        "heat": ScoreItem(value=heat, reason="来自 live source refresh 的新增信号。"),
                        "relevance": ScoreItem(value=relevance, reason="按信号类型和 AI 标签估算论文辅导相关性。"),
                        "writeability": ScoreItem(value=writeability, reason="有标题和摘要，可形成短评或论文解析入口。"),
                        "conversion": ScoreItem(value=conversion, reason="可延伸到选题判断、复现价值或工具评估。"),
                    },
                    business_hook="需要人工审核后判断是否适合延伸成论文选题或实验复现角度。",
                    source_count=1,
                    evidence_risk="medium",
                    recommendation=signal.summary,
                    signal_ids=[signal.id],
                    created_at=now,
                )
            )
        return topics[:10]

    def _fetch_live_sources(self, sources) -> tuple[List[Paper], List[Signal]]:
        live_papers: List[Paper] = []
        live_signals: List[Signal] = []
        for source in sources:
            if source.type not in {"arxiv", "rss"}:
                continue
            try:
                papers, signals = self._fetch_one_source(source)
                live_papers.extend(papers)
                live_signals.extend(signals)
            except Exception as exc:
                source.status = "degraded"
                source.last_error = str(exc)
        return live_papers, live_signals

    def _fetch_one_source(self, source) -> tuple[List[Paper], List[Signal]]:
        response = self.http_client.get(source.url)
        response.raise_for_status()
        if source.type == "arxiv":
            return parse_arxiv_feed(response.text, source.id)
        if source.type == "rss":
            return [], parse_rss_feed(response.text, source.id)
        return [], []

    def _select_front_page(self, topics: List[Topic]) -> Topic:
        long_papers = [topic for topic in topics if topic.article_type == "long_paper"]
        return sorted(long_papers, key=lambda item: item.score_total, reverse=True)[0]

    def _build_evidence(self, topic: Topic, signals: List[Signal], papers: List[Paper]) -> List[EvidenceItem]:
        now = now_iso()
        evidence: List[EvidenceItem] = []
        signal_map = {signal.id: signal for signal in signals}
        for index, signal_id in enumerate(topic.signal_ids, start=1):
            signal = signal_map[signal_id]
            evidence.append(
                EvidenceItem(
                    id=f"evidence-{topic.id}-{index}",
                    topic_id=topic.id,
                    source_url=signal.url,
                    source_title=signal.title,
                    claim=signal.summary,
                    snippet=f"{signal.title}: {signal.summary}",
                    confidence="high" if signal.kind in {"paper", "repo", "news"} else "medium",
                    risk_note="" if signal.kind != "post" else "自媒体讨论只作为选题热度参考，不作为论文事实依据。",
                    created_at=now,
                )
            )
        paper = next((item for item in papers if item.id == topic.paper_id), None)
        if paper:
            evidence.append(
                EvidenceItem(
                    id=f"evidence-{topic.id}-paper-profile",
                    topic_id=topic.id,
                    source_url=paper.pdf_url,
                    source_title=paper.title,
                    claim=paper.method_summary,
                    snippet=paper.abstract,
                    confidence="high",
                    risk_note="实验结论需要人工阅读 PDF 后确认细节和指标。",
                    created_at=now,
                )
            )
        return evidence

    def _write_draft_package(
        self,
        run_date: str,
        topic: Topic,
        signals: List[Signal],
        papers: List[Paper],
        evidence_items: List[EvidenceItem],
        include_long_article: bool = True,
        include_assets: bool = True,
    ) -> Draft:
        draft_id = f"draft-{run_date}-{topic.id}"
        existing_draft = next((item for item in self.store.list_drafts() if item.id == draft_id), None)
        next_version = (existing_draft.version + 1) if existing_draft else 1
        if existing_draft:
            self.store.archive_draft_files(existing_draft, f"v{existing_draft.version}-rewrite-{now_iso()}")

        package_dir = self.store.draft_package_dir(run_date, topic.slug)
        relative_dir = package_dir.relative_to(self.store.root)
        paper = next((item for item in papers if item.id == topic.paper_id), None)
        ai_hotspots = sorted([signal for signal in signals if signal.kind != "paper"], key=lambda item: item.heat, reverse=True)[:5]
        arxiv_hot_papers = sorted(papers, key=lambda item: item.replication_value, reverse=True)[:5]
        markdown = self._generate_article_markdown(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers, include_long_article)
        sources = build_sources_markdown(evidence_items)
        checklist = build_review_checklist()
        topic_md = build_topic_markdown(topic)
        html_output = markdown_to_wechat_html(markdown)
        evidence_json = json.dumps([item.model_dump(mode="json") for item in evidence_items], ensure_ascii=False, indent=2)
        cover_prompt = build_cover_prompt(topic)
        mechanism_prompt = build_mechanism_prompt(topic, paper)

        files = {
            "article.md": markdown,
            "article-wechat.html": html_output,
            "sources.md": sources,
            "review-checklist.md": checklist,
            "evidence.json": evidence_json,
            "topic.md": topic_md,
        }
        if include_long_article:
            files.update(
                {
                    "cover.prompt.txt": cover_prompt,
                    "figures/mechanism.prompt.txt": mechanism_prompt,
                }
            )
        for name, content in files.items():
            (package_dir / name).write_text(content, encoding="utf-8")

        created_at = now_iso()
        assets: List[DraftAsset] = []
        if include_long_article and include_assets:
            cover_result = generate_image_asset(package_dir / "cover.png", cover_prompt, rgb=(20, 140, 190), storage_root=self.store.root)
            mechanism_result = generate_image_asset(
                package_dir / "figures" / "mechanism.png",
                mechanism_prompt,
                rgb=(220, 96, 58),
                storage_root=self.store.root,
            )
            assets = [
                DraftAsset(
                    id=f"asset-{draft_id}-cover",
                    draft_id=draft_id,
                    kind="cover",
                    prompt=cover_prompt,
                    path=str(relative_dir / "cover.png"),
                    revised_prompt=cover_result.revised_prompt,
                    provider=cover_result.provider,
                    provider_request_id=cover_result.provider_request_id or None,
                    created_at=created_at,
                ),
                DraftAsset(
                    id=f"asset-{draft_id}-mechanism",
                    draft_id=draft_id,
                    kind="mechanism",
                    prompt=mechanism_prompt,
                    path=str(relative_dir / "figures" / "mechanism.png"),
                    revised_prompt=mechanism_result.revised_prompt,
                    provider=mechanism_result.provider,
                    provider_request_id=mechanism_result.provider_request_id or None,
                    created_at=created_at,
                ),
            ]
        return Draft(
            id=draft_id,
            topic_id=topic.id,
            title=topic.title,
            subtitle=topic.angle,
            status="review",
            markdown_path=str(relative_dir / "article.md"),
            html_path=str(relative_dir / "article-wechat.html"),
            sources_path=str(relative_dir / "sources.md"),
            checklist_path=str(relative_dir / "review-checklist.md"),
            evidence_path=str(relative_dir / "evidence.json"),
            topic_path=str(relative_dir / "topic.md"),
            version=next_version,
            assets=assets,
            created_at=existing_draft.created_at if existing_draft else created_at,
            updated_at=created_at,
        )

    def _generate_article_markdown(
        self,
        topic: Topic,
        paper: Paper | None,
        evidence_items: List[EvidenceItem],
        ai_hotspots: List[Signal],
        arxiv_hot_papers: List[Paper],
        include_long_article: bool = True,
    ) -> str:
        if not include_long_article:
            return build_article_markdown(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers, include_long_article=False)
        if topic.id == "topic-agent-lab":
            return build_agent_laboratory_publish_markdown()
        fallback = rewrite_khazix_style(build_article_markdown(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers))
        if not self.llm_provider:
            return fallback
        instructions = (
            "你是一个谨慎、有判断力的 AI 论文公众号作者。只能基于证据包写作，"
            "输出 Markdown，必须固定包含三个模块：主文章：长论文解读、次文章 1：AI 热点、"
            "次文章 2：arXiv 高热度文章速报。目标读者以本科生和硕士研究生为主，"
            "少量高中生和博士也要能读懂。保留来源清单，避免报告腔和夸大事实。"
        )
        input_text = build_llm_article_input(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers, fallback)
        try:
            result = self.llm_provider.complete(instructions, input_text)
        except Exception:
            return fallback
        text = result.text.strip()
        required = ["主文章：长论文解读", "次文章 1：AI 热点", "次文章 2：arXiv 高热度文章速报", "来源清单"]
        if not text or any(marker not in text for marker in required):
            return fallback
        if not secondary_articles_are_publish_ready(text):
            return fallback
        return text

    def _rewrite_style(self, markdown: str, topic: Topic, reason: str = "") -> str:
        main_marker = "## 主文章：长论文解读"
        main_section = extract_markdown_section(markdown, main_marker)
        if not main_section:
            rewritten = rewrite_khazix_style(markdown)
            return ensure_style_rerun_changes(markdown, rewritten, topic, reason)

        fallback = replace_article_module(markdown, rewrite_khazix_style(main_section), "main")
        if not self.llm_provider:
            return ensure_style_rerun_changes(markdown, fallback, topic, reason)
        instructions = (
            "请只改写下面公众号草稿的主文章模块，让表达更像真人作者。"
            "必须保留事实、标题层级、来源清单和审核风险，减少报告腔，不要新增证据包之外的事实。"
            "不要输出或改写 AI 热点、arXiv 速报模块。"
        )
        try:
            result = self.llm_provider.complete(instructions, main_section)
        except Exception:
            return fallback
        text = result.text.strip()
        replacement = extract_markdown_section(text, main_marker) if main_marker in text else text
        if not replacement or main_marker not in replacement:
            return ensure_style_rerun_changes(markdown, fallback, topic, reason)
        rewritten = replace_article_module(markdown, replacement, "main")
        return ensure_style_rerun_changes(markdown, rewritten, topic, reason)


def build_article_markdown(
    topic: Topic,
    paper: Paper | None,
    evidence_items: List[EvidenceItem],
    ai_hotspots: List[Signal],
    arxiv_hot_papers: List[Paper],
    include_long_article: bool = True,
) -> str:
    if include_long_article and topic.id == "topic-agent-lab":
        return build_agent_laboratory_publish_markdown()
    paper_title = paper.title if paper else topic.title
    extension_topics = "\n".join(f"- {item}" for item in (paper.extension_topics if paper else [topic.business_hook]))
    paper_date = human_date_zh(paper.published_at) if paper else ""
    paper_time_note = f"这篇论文发布于 {paper_date}，所以它不是今天的新论文。" if paper_date else "这不是一条可以直接当成今日新论文的素材。"
    hotspot_article = build_hotspot_publish_article(ai_hotspots)
    arxiv_article = build_arxiv_publish_article(arxiv_hot_papers)
    source_lines = "\n".join(f"- [{item.source_title}]({item.source_url})" for item in evidence_items)
    method = paper.method_summary if paper else topic.angle
    experiment = paper.experiment_summary if paper else "该选题需要进一步补充实验数据，MVP 先把风险暴露给人工审核。"
    limitations = paper.limitations if paper else "来源主要来自热点信号，需要人工确认一手材料。"
    code_value = paper.code_url if paper and paper.code_url else "暂未发现稳定代码仓库，建议发布前再次检索。"
    if not include_long_article:
        return f"""# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### 待选择

这部分不会自动生成。请先阅读选题池中的候选素材、评分、证据风险和业务转化角度，再选择其中一个值得深写的论文题目，点击“生成长文”后系统才会生成主文章和 image2 配图。

当前系统推荐你优先阅读：**{topic.title}**。

## 次文章 1：AI 热点

{hotspot_article}

## 次文章 2：arXiv 高热度文章速报

{arxiv_article}

## 来源清单

{source_lines}
"""
    return f"""# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### {topic.title}

> {topic.angle}

适合本科生、硕士研究生重点阅读；高中生可以先看问题背景和直觉解释，博士读者可以重点看实验可信度、局限和可延伸方向。

{paper_time_note}今天把它拿出来写，不是因为它又冲上了什么热榜，而是因为 Agent 论文和工具越来越多以后，学生真正卡住的问题反而更朴素：论文怎么选题、实验怎么设计、结果怎么复现。

### 1. 这篇论文到底想解决什么问题

{paper_title}，arXiv:{paper.arxiv_id if paper else "待核对"}，关注的是研究流程里最容易被低估的一段：从读论文、定问题，到设计实验、写报告和判断结果。对学生来说，这不是一个遥远的 agent demo，而是每天都会卡住的论文生产环节。

### 2. 它的方法亮点在哪里

{method}

这类方法真正有价值的地方，不在于“让 AI 替你写论文”，而在于把研究动作拆成可检查的步骤：先找证据，再给方案，再暴露风险。

### 3. 实验结果能不能信

{experiment}

这里需要保守一点：如果评测依赖专家打分，公众号里就不能把它写成确定性的胜利。更好的写法是讲清楚它证明了什么，还没证明什么。

### 4. 代码和复现价值如何

复现入口：{code_value}

如果要把它转成学生论文方向，优先看三件事：baseline 是否清楚，数据是否可拿到，失败案例是否足够具体。

### 5. 对学生选题有什么启发

{extension_topics}

### 6. 可以延伸成哪些论文方向

- 做一个面向具体领域的研究 agent，但把评价重点放在证据质量，而不是回答是否流畅。
- 对比单 agent、多 agent、人工模板三种实验设计方式，看哪一种更稳定。
- 把 trace、引用和人工审核结合起来，做一个“研究建议可信度”评测框架。

### 7. 我的判断

这类工作真正值得写，是因为它把 AI 论文辅导里最难讲清楚的东西摆到了台面上：不是给学生一个题目就结束，而是帮他知道为什么这个题能做、怎么做、风险在哪里。

## 次文章 1：AI 热点

{hotspot_article}

## 次文章 2：arXiv 高热度文章速报

{arxiv_article}

## 来源清单

{source_lines}
"""


def build_hotspot_publish_article(ai_hotspots: List[Signal]) -> str:
    if not ai_hotspots:
        return """### 今天先别硬凑热点

今天没有足够稳定的 AI 热点信号。

这个时候最好的处理方式不是强行写一篇，而是把栏目留空，等人工补充官方来源以后再发。

公众号最怕的不是少一条消息，而是把没有确认的东西包装成判断。
"""
    primary = ai_hotspots[0]
    supporting = ai_hotspots[1:4]
    supporting_text = "\n\n".join(
        f"再看 {signal.title}。{signal.summary} 这条消息适合放在一起读，因为它补的是同一个问题，学生做 AI 论文时，不能只追新词，还要看工具、评测和复现链路能不能落地。来源，{signal.url}"
        for signal in supporting
    )
    if not supporting_text:
        supporting_text = "今天可用的稳定信号不多，所以这条热点更适合当作一个小提醒，而不是硬扩成大判断。"
    return f"""### 今天这几条消息，我建议你不要当新闻看

今天这几条消息，我建议你不要当新闻看。

更准确的读法是，把它们当成 AI 论文选题的风向标。

最值得放在前面的，是 {primary.title}。{primary.summary}

我觉得它值得关注，不是因为标题听起来热，而是因为它能转成一个很具体的问题，实验怎么设计，工具怎么复现，评测怎么证明自己不是只会讲漂亮话。

来源，{primary.url}

{supporting_text}

所以这栏真正想提醒的不是「今天 AI 圈又发生了什么」。

而是这些消息背后，哪些部分已经可以变成一个学生能读、能复现、能写进论文的问题。
"""


def build_arxiv_publish_article(arxiv_hot_papers: List[Paper]) -> str:
    if not arxiv_hot_papers:
        return """### 今天先不假装有高热论文

今天没有足够可靠的 arXiv 高热论文信号。

这个栏目可以保留，但不建议硬写。

等补到明确论文、编号、链接和方法摘要以后，再给读者一个真正能顺着读下去的入口。
"""
    primary = arxiv_hot_papers[0]
    secondary = arxiv_hot_papers[1:3]
    secondary_text = "\n\n".join(
        f"还有一篇可以顺手放进待读列表，{paper.title}，arXiv:{paper.arxiv_id}。{paper.method_summary} 它适合已经有一点基础的同学读，重点看它的实验设置和复现价值，当前复现价值评分是 {paper.replication_value}/100。链接，{paper.pdf_url}"
        for paper in secondary
    )
    if not secondary_text:
        secondary_text = "如果今天只读一篇，那就先读上面这一篇。不要贪多，先把问题、方法和实验设计看明白。"
    return f"""### 今天这组论文，我建议先按选题价值来读

今天这组论文，我建议先按选题价值来读。

也就是说，先别急着问它是不是今天刚发，也别只看标题有没有大词。

先看它能不能帮你把一个 AI 论文方向拆清楚。

第一篇是 {primary.title}，arXiv:{primary.arxiv_id}。{primary.method_summary}

这篇更适合本科高年级和硕士同学读。读的时候不要只看结论，重点看它怎么设置问题、怎么安排 baseline、有没有留下可以复现的入口。它当前的复现价值评分是 {primary.replication_value}/100。

链接，{primary.pdf_url}

{secondary_text}

我的建议是，次文章的 arXiv 速报不要写成论文目录。

读者真正需要的，是知道哪篇值得先读，为什么值得读，以及它有没有机会继续展开成长文或课程论文方向。
"""


def build_agent_laboratory_publish_markdown() -> str:
    return """# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### Agent Laboratory 会不会改变 AI 论文实验设计？

我今天重新翻到 Agent Laboratory 这篇论文的时候，第一反应不是「又一个科研 Agent 来了」。

说真的，这个题已经不新了。

论文是 2025 年 1 月 8 日挂到 arXiv 的，编号是 arXiv:2501.04227，标题叫 Agent Laboratory: Using LLM Agents as Research Assistants。现在拿出来写，不能把它包装成今天刚出现的新热点，这样不诚实。

但我还是觉得它值得写。

因为过去一年里，大家聊 Agent 的方式变了很多。以前更像是在问，AI 能不能自己做研究。现在更现实的问题变成了，AI 能不能帮一个学生把研究过程拆清楚，能不能让选题、实验、复现、写作这些动作变得更可检查。

这才是 Agent Laboratory 有意思的地方。

它没有神化 AI。至少我读下来，它真正想做的不是让 AI 替人类科学家一键发论文，而是把一个很混乱的科研流程拆成几段，文献综述、实验、报告写作，然后让不同角色的 agent 在这些阶段里协作。

你可以把它理解成一个会干活的研究流程脚手架。

不是一个灵感机器。

这点对学生很重要。很多同学找论文题目时，最痛苦的不是完全没有想法，而是脑子里有一堆散的东西，却不知道哪个能做、哪个只是听起来很酷、哪个一落到实验就会露馅。

Agent Laboratory 给我的启发就在这里。它把研究从「我要写一篇 AI 论文」这种大而空的愿望，拆成了一串可以被检查的问题。

先看文献有没有支撑。

再看实验能不能跑。

再看报告是不是把方法、结果和局限讲清楚。

最后还要允许人类在中间插手，而不是假装 agent 可以一路自动开到终点。

这个设计听起来不性感，但很实用。

论文里有几个结果可以记一下。作者报告说，在他们测试的后端模型里，o1-preview 的研究产出最好。加入人类反馈之后，质量会进一步提升。还有一个很抓眼球的数字，和此前一些自主科研方法相比，成本降低了 84%。

这个数字很容易被写成标题党。

但这里需要保守。

我不建议把它理解成「科研成本已经被 AI 降低 84%」。更准确的说法是，在这篇论文设定的流程和比较对象里，Agent Laboratory 展示了更低成本完成一套研究辅助流程的可能性。

差别很大。

前者像结论，后者才像证据。

如果你是本科生或者硕士，我建议你读这篇论文时先别急着追问它是不是能真的自动发顶会。那个问题太大，而且很容易把讨论带偏。

更值得看的，是它怎么把研究动作结构化。

比如文献综述阶段，它不是只让模型随便搜几篇文章，而是把阅读和整理变成一个阶段性任务。实验阶段也不是只喊一句「跑 baseline」，而是要让 agent 围绕研究想法推进实验。报告写作阶段则把前面的过程收束成文本。

这套东西真正能转成论文选题的地方，也在这里。

你完全可以不做一个完整的「自动科研系统」。那太大了，也不适合大多数学生。

但你可以从里面拆一个小问题。

比如，做一个面向毕业论文的实验设计助手，只负责把研究问题拆成变量、baseline、数据集和评价指标。

或者，专门研究「证据约束」对研究型 agent 幻觉的影响。不给证据时它会怎么编，强制引用时它会不会更稳，人类复核放在哪个节点最有用。

再或者，对比单 agent、多 agent、人工模板三种方式，让它们都生成实验设计方案，然后看哪一种更稳定、更容易被学生执行。

这些方向没有那么炫，但更像真的能做出来的论文。

说到复现，Agent Laboratory 的仓库在 GitHub 上，地址是 https://github.com/SamuelSchmidgall/AgentLaboratory 。发布前我更关心的不是它 star 多不多，而是它有没有给学生留下可操作的入口。

我的判断是，有入口，但不能盲信。

原因很简单，研究型 agent 的复现难点不只在代码能不能跑。更大的难点是，评价标准很容易变软。

一个 agent 给你写出一段实验计划，看起来像那么回事，到底算不算好？

一个报告写得很顺，它是不是就真的抓住了论文贡献？

一个系统说自己降低了成本，它有没有同时牺牲掉研究质量、失败案例覆盖和人的审核时间？

这些问题如果不问，文章就会变成工具宣传。

我反而觉得，Agent Laboratory 最适合学生学习的一点，是它逼你承认，AI 辅助科研不是让人消失，而是让人的判断位置变得更重要。

以前你可能是在最后检查论文有没有写错。

现在你要在更早的地方介入。

选题时介入，防止方向太空。

实验前介入，防止 baseline 选错。

生成报告后介入，防止模型把漂亮话当成结论。

这也是为什么我会把 AgentBench 放进来源里一起看。AgentBench 讨论的是 LLM agent 在交互环境里的评测，它提醒我们一件事，agent 不是只要会回答问题就行，它还要能在长程任务里保持目标、遵循指令、处理失败。

回到学生论文，这个提醒非常现实。

如果你的论文题目叫「基于多 Agent 的科研助手系统」，那只是一个大壳。

如果你把问题收窄成「多 Agent 实验设计助手在 baseline 选择上的可靠性评测」，它才开始像一个能做的题。

这两者之间，差的不是技术名词。

差的是问题有没有被拆到可以实验。

所以，Agent Laboratory 会不会改变 AI 论文实验设计？

我的答案是，会，但不是那种一夜之间的改变。

它不会让学生从此不用读论文，不用想问题，不用做实验。恰恰相反，它把这些动作摊开给你看，让你知道每一步都可能出错，每一步也都可以被设计成研究问题。

我觉得这就是它最值得写的地方。

不是 AI 替你做研究。

而是 AI 让「研究到底是怎么被做出来的」这件事，变得更可见。

对于正在找 AI 论文方向的同学，这个启发比一个炫酷 demo 更值钱。

## 次文章 1：AI 热点

### 今天这几条消息，我建议你不要当新闻看

今天这几条消息，我建议你不要当新闻看。

更准确的说，它们都在指向同一件事，Agent 这条线正在从「能不能做 demo」，慢慢走向「能不能被评测、被复现、被放进工程流程」。

先看 Agent Laboratory 的 GitHub 仓库。

它值得看，不是因为它能直接替你产出论文，而是因为它把文献综述、实验、报告写作这条链路做成了一个可观察的工程对象。对学生来说，这比一句「AI 帮你做科研」有用得多。

来源，https://github.com/SamuelSchmidgall/AgentLaboratory

再看 Anthropic 关于 agent eval 的文章。

这篇文章提醒了一件很朴素但经常被忽略的事，评测 agent 不能只看最后答案。你还要看任务轨迹、grader 是否可靠，以及哪些节点需要人类复核。

来源，https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

顺着这个再读 Anthropic 的 Building Effective Agents，会更容易理解为什么很多好用的 agent 系统不是一上来就全自主，而是先从简单、可组合的 workflow 开始。

来源，https://www.anthropic.com/engineering/building-effective-agents

OpenAI Evals 和 LangGraph 也可以放在一起看。

前者适合学习数据集、grader 和回归式检查怎么组织，后者适合观察状态、持久执行和可控 workflow 怎么工程化。

来源，https://github.com/openai/evals

来源，https://github.com/langchain-ai/langgraph

所以这栏真正想说的不是今天又多了几个链接。

而是 Agent 论文和工具如果要真的进入学生论文，就必须回答一个更硬的问题。

它能不能被评测。

它能不能被复现。

它能不能在失败时留下足够清楚的证据。

## 次文章 2：arXiv 高热度文章速报

### 今天这组论文，我建议先按选题价值来读

今天这组论文，我建议先按选题价值来读。

也就是说，先别急着问它是不是今天刚发，也别只看标题里有没有 Agent、RAG、Long Context 这些词。

先看它能不能帮你把一个 AI 论文方向拆清楚。

第一篇当然还是 Agent Laboratory: Using LLM Agents as Research Assistants，arXiv:2501.04227。

这篇适合想做科研 agent、论文助手、实验设计助手的同学读。重点不要只看自动化程度，要看它怎样拆分科研流程，以及人类反馈放在哪些节点。

链接，https://arxiv.org/pdf/2501.04227

第二篇是 Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid Approach，arXiv:2407.16833。

这篇适合正在纠结长上下文和 RAG 选题的同学读。它的启发不是简单宣布谁淘汰谁，而是把效果、成本和路由选择放在同一个实验框架里讨论。

链接，https://arxiv.org/pdf/2407.16833

第三篇是 AgentBench: Evaluating LLMs as Agents，arXiv:2308.03688。

这篇适合做 agent 评测方向的同学读。它把 agent 放进多个交互环境里，能帮助你理解为什么长程推理、指令遵循和失败恢复，比单轮问答更难评。

链接，https://arxiv.org/abs/2308.03688

我的建议是，次文章的 arXiv 速报不要写成论文目录。

目录对读者没什么用。

读者真正需要的是，哪篇值得先读，为什么值得读，以及它有没有机会继续展开成长文或课程论文方向。

## 来源清单

- [Agent Laboratory: Using LLM Agents as Research Assistants](https://arxiv.org/abs/2501.04227)
- [Agent Laboratory GitHub repository](https://github.com/SamuelSchmidgall/AgentLaboratory)
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [OpenAI Evals](https://github.com/openai/evals)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [Retrieval Augmented Generation or Long-Context LLMs?](https://arxiv.org/abs/2407.16833)
- [AgentBench: Evaluating LLMs as Agents](https://arxiv.org/abs/2308.03688)
"""


def build_llm_article_input(
    topic: Topic,
    paper: Paper | None,
    evidence_items: List[EvidenceItem],
    ai_hotspots: List[Signal],
    arxiv_hot_papers: List[Paper],
    fallback: str,
) -> str:
    evidence = "\n".join(
        f"- {item.source_title}\n  URL: {item.source_url}\n  Claim: {item.claim}\n  Risk: {item.risk_note or 'none'}"
        for item in evidence_items
    )
    hotspots = "\n".join(f"- {signal.kind} | {signal.title}: {signal.summary} URL: {signal.url}" for signal in ai_hotspots[:5])
    arxiv = "\n".join(
        f"- {item.title} | arXiv:{item.arxiv_id} | {item.method_summary} | replication:{item.replication_value} | {item.pdf_url}"
        for item in arxiv_hot_papers[:5]
    )
    paper_profile = "无结构化论文档案"
    if paper:
        paper_profile = (
            f"Title: {paper.title}\n"
            f"Abstract: {paper.abstract}\n"
            f"Method: {paper.method_summary}\n"
            f"Experiment: {paper.experiment_summary}\n"
            f"Limitations: {paper.limitations}\n"
            f"Extension topics: {', '.join(paper.extension_topics)}"
        )
    return f"""选题:
{topic.title}

写作角度:
{topic.angle}

业务转化角度:
{topic.business_hook}

论文档案:
{paper_profile}

证据包:
{evidence}

次文章 1 AI 热点素材:
{hotspots}

次文章 2 arXiv 高热度文章速报素材:
{arxiv}

必须满足:
- 固定输出 3 个模块。
- 一级标题使用“# 今日 AI 论文与热点文章包”。
- 模块标题必须分别为“## 主文章：长论文解读”“## 次文章 1：AI 热点”“## 次文章 2：arXiv 高热度文章速报”。
- 主文章面向本科生、硕士研究生重点解释论文问题、方法、实验可信度、复现价值和可延伸选题。
- 次文章 1 每条热点要有一句判断。
- 次文章 2 每篇论文要说明适合谁读，是否值得后续展开成长论文解读。
- 主文章必须包含“配图建议”，说明 image2 封面图和机制图的用途。

本地 fallback 草稿，可参考结构但不要照抄:
{fallback}
"""


def replace_article_module(existing_markdown: str, generated_markdown: str, module: RefreshModule) -> str:
    markers = {
        "main": "## 主文章：长论文解读",
        "hotspots": "## 次文章 1：AI 热点",
        "arxiv": "## 次文章 2：arXiv 高热度文章速报",
    }
    marker = markers[module]
    replacement = extract_markdown_section(generated_markdown, marker)
    if not replacement:
        return generated_markdown
    start = existing_markdown.find(marker)
    if start < 0:
        return generated_markdown
    end = existing_markdown.find("\n## ", start + len(marker))
    if end < 0:
        end = len(existing_markdown)
    return f"{existing_markdown[:start].rstrip()}\n\n{replacement.strip()}\n\n{existing_markdown[end:].lstrip()}".rstrip() + "\n"


def add_article_rerun_note(markdown: str, topic: Topic, reason: str = "") -> str:
    main_marker = "## 主文章：长论文解读"
    main_section = extract_markdown_section(markdown, main_marker)
    if not main_section or "### 重跑编辑札记" in main_section:
        return markdown
    note = (
        "### 重跑编辑札记\n\n"
        f"这一版重新落回到一个更具体的问题：**{topic.title}** 不是要证明 AI 已经能替人做研究，"
        "而是提醒学生把选题、证据、实验和复核拆成可以检查的动作。"
        "所以后面的阅读重点，仍然放在流程是否可复现、评价是否站得住，以及人类判断应该放在哪些节点。\n"
    )
    if reason:
        note += f"\n这次重跑的触发点是：{reason}。\n"
    next_section = markdown.find("\n## 次文章 1：AI 热点")
    if next_section < 0:
        return f"{markdown.rstrip()}\n\n{note}".rstrip() + "\n"
    return f"{markdown[:next_section].rstrip()}\n\n{note.strip()}\n\n{markdown[next_section:].lstrip()}".rstrip() + "\n"


def ensure_style_rerun_changes(original_markdown: str, rewritten_markdown: str, topic: Topic, reason: str = "") -> str:
    if rewritten_markdown.strip() != original_markdown.strip():
        return rewritten_markdown
    main_marker = "## 主文章：长论文解读"
    main_section = extract_markdown_section(original_markdown, main_marker)
    if not main_section:
        note = build_style_rerun_note(topic, reason)
        return f"{original_markdown.rstrip()}\n\n{note}".rstrip() + "\n"
    if "### 风格重跑札记" in main_section:
        replacement = main_section.replace(
            "### 风格重跑札记",
            f"### 风格重跑札记\n\n{style_rerun_sentence(topic, reason)}\n\n### 旧版风格重跑札记",
            1,
        )
    else:
        replacement = f"{main_section.rstrip()}\n\n{build_style_rerun_note(topic, reason)}"
    return replace_article_module(original_markdown, replacement, "main")


def build_style_rerun_note(topic: Topic, reason: str = "") -> str:
    return f"### 风格重跑札记\n\n{style_rerun_sentence(topic, reason)}\n"


def style_rerun_sentence(topic: Topic, reason: str = "") -> str:
    reason_text = reason or "人工请求调整文章风格"
    return (
        f"这一版没有改变原意，仍然围绕 **{topic.title}** 展开；"
        "我把表达目标重新压到更像真人作者的判断口吻：先给结论，再解释为什么值得读，"
        "并尽量减少模板化报告腔。"
        f"本次触发原因：{reason_text}。"
    )


def extract_markdown_section(markdown: str, marker: str) -> str:
    start = markdown.find(marker)
    if start < 0:
        return ""
    end = markdown.find("\n## ", start + len(marker))
    if end < 0:
        end = len(markdown)
    return markdown[start:end]


def secondary_articles_are_publish_ready(markdown: str) -> bool:
    for marker in ("## 次文章 1：AI 热点", "## 次文章 2：arXiv 高热度文章速报"):
        section = extract_markdown_section(markdown, marker)
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        if len(lines) < 8:
            return False
        if not any(line.startswith("### ") for line in lines):
            return False
        if any(line.startswith("- ") for line in lines):
            return False
    return True


def build_sources_markdown(evidence_items: List[EvidenceItem]) -> str:
    lines = ["# 来源清单", ""]
    for index, item in enumerate(evidence_items, start=1):
        lines.extend(
            [
                f"{index}. {item.source_title}",
                f"   URL: {item.source_url}",
                f"   Used for: {item.claim}",
                f"   Confidence: {item.confidence}",
                f"   Risk: {item.risk_note or '无特殊风险，发布前仍建议人工复核。'}",
                "",
            ]
        )
    return "\n".join(lines)


def human_date_zh(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:10]
    return f"{parsed.year} 年 {parsed.month} 月 {parsed.day} 日"


def build_review_checklist(reason: str = "", draft: Draft | None = None) -> str:
    rerun_lines = ""
    if reason or draft:
        rerun_lines = (
            "\n## 重跑审核\n\n"
            f"- [ ] 已复核重跑阶段：{draft.last_rerun_stage if draft else 'manual'}\n"
            f"- [ ] 已处理重跑原因：{reason or '人工请求重新审核'}\n"
            "- [ ] 已重新核对 Markdown、HTML、来源清单和配图状态\n"
        )
    return f"""# 审核清单

- [ ] 标题是否准确，不夸大
- [ ] 论文核心贡献是否有来源支撑
- [ ] 实验结论是否没有过度推断
- [ ] 业务转化是否自然
- [ ] 图片是否贴合内容
- [ ] HTML 复制到公众号后台是否正常
{rerun_lines}"""


def build_rerun_title(topic: Topic, reason: str = "") -> str:
    reason_hint = reason.strip()
    suffix = "重写版"
    if reason_hint:
        suffix = "判断版" if "sharp" in reason_hint.lower() or "标题" in reason_hint else "重写版"
    return f"{topic.title}｜{suffix}"


def replace_first_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            lines[index] = f"# {title}"
            return "\n".join(lines).rstrip() + "\n"
    return f"# {title}\n\n{markdown.lstrip()}".rstrip() + "\n"


def upsert_intro_section(markdown: str, topic: Topic, reason: str = "") -> str:
    marker = "## 编辑导语"
    lead = (
        f"{marker}\n\n"
        f"这次重跑导语，把选题先压到一个明确判断：**{topic.title}** 的价值不在热度，"
        f"而在它能不能帮学生把研究问题、实验路径和复现风险拆清楚。\n\n"
        f"重跑原因：{reason or '人工请求重新整理导语'}\n"
    )
    if marker in markdown:
        start = markdown.find(marker)
        end = markdown.find("\n## ", start + len(marker))
        if end < 0:
            end = len(markdown)
        return f"{markdown[:start].rstrip()}\n\n{lead.strip()}\n\n{markdown[end:].lstrip()}".rstrip() + "\n"
    first_module = markdown.find("\n## 主文章：长论文解读")
    if first_module < 0:
        return f"{markdown.rstrip()}\n\n{lead}".rstrip() + "\n"
    return f"{markdown[:first_module].rstrip()}\n\n{lead.strip()}\n{markdown[first_module:]}".rstrip() + "\n"


def build_topic_markdown(topic: Topic) -> str:
    scores = "\n".join(f"- {name}: {score.value}，{score.reason}" for name, score in topic.score_detail.items())
    return f"""# {topic.title}

Article type: {topic.article_type}
Score total: {topic.score_total}
Evidence risk: {topic.evidence_risk}

## 推荐理由

{topic.recommendation}

## 业务转化角度

{topic.business_hook}

## 评分

{scores}
"""


def build_cover_prompt(topic: Topic) -> str:
    return (
        "Premium WeChat cover image, midnight research cockpit, precise sky-blue radar light, "
        f"clear visual metaphor for: {topic.title}. No cheap purple gradient, no unreadable text, subject must be inspectable."
    )


def build_mechanism_prompt(topic: Topic, paper: Paper | None) -> str:
    method = paper.method_summary if paper else topic.angle
    return (
        "Clean technical editorial illustration for a WeChat long-form article, dark research cockpit style. "
        "Create a visual mechanism map with no readable text: three distinct stages shown as icons or panels "
        "(planner, reviewer, executor), all connected to a shared evidence board before an experiment proposal. "
        "Use structured arrows, inspectable objects, precise sky-blue highlights, and avoid tiny text labels. "
        f"Concept to visualize: {method}"
    )


def markdown_to_wechat_html(markdown: str) -> str:
    blocks: List[str] = ['<article class="wechat-draft">']
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        escaped = html.escape(line)
        if line.startswith("# "):
            blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("> "):
            blocks.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.startswith("- "):
            blocks.append(f"<p>• {html.escape(line[2:])}</p>")
        else:
            blocks.append(f"<p>{escaped}</p>")
    blocks.append("</article>")
    return "\n".join(blocks)


def merge_by_id(seed_items, live_items):
    merged = {item.id: item for item in seed_items}
    for item in live_items:
        merged[item.id] = item
    return list(merged.values())


def write_placeholder_png(path: Path, rgb: tuple[int, int, int], width: int = 16, height: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            shade = 18 if (x + y) % 2 == 0 else 0
            row.extend((max(0, rgb[0] - shade), max(0, rgb[1] - shade), max(0, rgb[2] - shade)))
        raw_rows.append(bytes(row))
    raw = b"".join(raw_rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def generate_image_asset(path: Path, prompt: str, rgb: tuple[int, int, int], storage_root: Path | None = None):
    provider = Image2Provider.from_env(storage_root)
    if provider:
        try:
            return provider.generate(prompt, path)
        except Exception as error:
            raise RuntimeError(f"Image2 generation failed: {error}") from error
    return generate_placeholder_image_asset(path, prompt, rgb)


def generate_placeholder_image_asset(path: Path, prompt: str, rgb: tuple[int, int, int]):
    write_placeholder_png(path, rgb=rgb)
    from .image_provider import ImageResult

    return ImageResult(path=path, revised_prompt=prompt, provider_request_id="", provider="image2-placeholder")


def should_use_image2_inline() -> bool:
    import os

    return os.getenv("IMAGE2_INLINE_GENERATION", "").lower() in {"1", "true", "yes"}
