from __future__ import annotations

import html
import hashlib
import json
import os
import re
from difflib import SequenceMatcher
from datetime import date as date_type, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Literal
from zoneinfo import ZoneInfo

import httpx

from .connectors import parse_arxiv_feed, parse_github_search_repositories, parse_rss_feed
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
    TopicPackItem,
    TopicPackModule,
    TopicPackVersion,
    now_iso,
)
from .image_provider import Image2Provider
from .llm_provider import ResponsesLLMProvider
from .sample_data import seed_papers, seed_signals, seed_sources
from .scoring import PaperScore, build_score_report, score_papers
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
        self._last_generation_error = ""

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
            refresh_record = {
                "last_refresh_at": current.replace(microsecond=0).isoformat(),
                "draft_id": run.draft.id,
                "reason": "scheduled daily refresh",
            }
            if self.llm_provider:
                pack = self._create_topic_pack_version(
                    run=run,
                    module="all",
                    reason="scheduled daily refresh",
                    trigger="scheduled",
                )
                refresh_record["topic_pack_id"] = pack.id
                refresh_record["module"] = "all"
            self.store.set_refresh(today, refresh_record)
        return self.refresh_status(current)

    def refresh_today(self, now: datetime | None = None) -> DailyRun:
        current = beijing_now(now)
        today = current.date().isoformat()
        previous = self.store.get_run(today)
        avoid_topic_id = str(previous["selected_topic_id"]) if previous else ""
        run = self.run_daily(today, avoid_topic_id=avoid_topic_id)
        self.store.set_refresh(
            today,
            {
                "last_refresh_at": current.replace(microsecond=0).isoformat(),
                "draft_id": run.draft.id,
                "reason": "manual topic refresh",
            },
        )
        return run

    def ensure_topic_pack(self, date: str | None = None) -> TopicPackVersion:
        run_date = date or date_type.today().isoformat()
        current = self.store.current_topic_pack(run_date)
        if current:
            if current.status != "partial" and not self._topic_pack_is_complete(current):
                raise KeyError(run_date)
            return self._with_topic_pack_topic_ids(current)
        raise KeyError(run_date)

    def list_topic_packs(self, date: str | None = None) -> List[TopicPackVersion]:
        return [self._with_topic_pack_topic_ids(pack) for pack in self.store.list_topic_pack_versions(date)]

    def get_topic_pack(self, pack_id: str) -> TopicPackVersion:
        for pack in self.store.list_topic_pack_versions():
            if pack.id == pack_id:
                return self._with_topic_pack_topic_ids(pack)
        raise KeyError(pack_id)

    def refresh_topic_pack(
        self,
        date: str | None = None,
        module: TopicPackModule = "all",
        reason: str = "",
        fresh_sources: bool = False,
    ) -> TopicPackVersion:
        run_date = date or date_type.today().isoformat()
        previous = self.store.current_topic_pack(run_date)
        validate_changed = True
        if previous and not self._topic_pack_is_complete(previous):
            module = "all"
            validate_changed = False
        if not self.llm_provider:
            raise RuntimeError("LLM provider is required to refresh topic pack")
        if fresh_sources:
            previous_live_sources = self.live_sources
            self.live_sources = True
            try:
                run = self.run_daily(run_date)
            finally:
                self.live_sources = previous_live_sources
        else:
            run = self.ensure_daily_run(run_date)
        pack = self._create_topic_pack_version(
            run=run,
            module=module,
            reason=reason,
            trigger="manual",
            previous=previous,
            validate_changed=validate_changed,
        )
        self.store.set_refresh(
            run.date,
            {
                "last_refresh_at": beijing_now().isoformat(),
                "draft_id": run.draft.id,
                "reason": reason or f"manual topic pack refresh:{module}",
                "topic_pack_id": pack.id,
                "module": module,
            },
        )
        return self._with_topic_pack_topic_ids(pack)

    def _topic_pack_is_complete(self, pack: TopicPackVersion) -> bool:
        return len(pack.long_articles) == 5 and 5 <= len(pack.ai_hotspots) <= 10 and 5 <= len(pack.arxiv_papers) <= 10

    def _with_topic_pack_topic_ids(self, pack: TopicPackVersion) -> TopicPackVersion:
        topics = self.store.list_topics()
        papers = {paper.id: paper for paper in self.store.list_papers()}
        mapped = [self._with_topic_id(item, topics, papers) for item in pack.long_articles]
        return pack.model_copy(update={"long_articles": mapped})

    def _with_topic_id(self, item: TopicPackItem, topics: List[Topic], papers: Dict[str, Paper]) -> TopicPackItem:
        if item.topic_id:
            return item
        matched = self._match_topic_pack_item_to_topic(item, topics, papers)
        if not matched:
            matched = self._create_topic_from_topic_pack_item(item)
            topics.append(matched)
        return item.model_copy(update={"topic_id": matched.id})

    def _match_topic_pack_item_to_topic(self, item: TopicPackItem, topics: List[Topic], papers: Dict[str, Paper]) -> Topic | None:
        source_urls = {url.rstrip("/") for url in item.source_urls}
        normalized_title = normalize_dedupe(item.title)
        for topic in topics:
            paper = papers.get(topic.paper_id or "")
            paper_urls = set()
            if paper:
                paper_urls.add(f"https://arxiv.org/abs/{paper.arxiv_id}".rstrip("/"))
                paper_urls.add(paper.pdf_url.rstrip("/"))
                if paper.code_url:
                    paper_urls.add(paper.code_url.rstrip("/"))
            if item.arxiv_id and paper and normalize_arxiv_version(item.arxiv_id) == normalize_arxiv_version(paper.arxiv_id):
                return topic
            if source_urls and paper_urls.intersection(source_urls):
                return topic
            topic_terms = set(normalize_dedupe(topic.title).split())
            item_terms = set(normalized_title.split())
            if topic_terms and len(topic_terms.intersection(item_terms)) >= 3:
                return topic
        return None

    def _create_topic_from_topic_pack_item(self, item: TopicPackItem) -> Topic:
        topic_id = f"topic-{slugify(item.id)}"
        existing = next((topic for topic in self.store.list_topics() if topic.id == topic_id), None)
        if existing:
            return existing
        source_urls = {url.rstrip("/") for url in item.source_urls}
        signal_ids = [signal.id for signal in self.store.list_signals() if signal.url.rstrip("/") in source_urls]
        paper = next(
            (
                paper
                for paper in self.store.list_papers()
                if item.arxiv_id and normalize_arxiv_version(item.arxiv_id) == normalize_arxiv_version(paper.arxiv_id)
            ),
            None,
        )
        topic = Topic(
            id=topic_id,
            slug=slugify(item.title),
            cluster_id=f"topic-pack-{item.id}",
            paper_id=paper.id if paper else None,
            title=item.title,
            angle=item.angle,
            article_type="long_paper",
            status="candidate",
            score_total=80,
            score_detail={
                "heat": ScoreItem(value=70, reason="来自 LLM topic pack 长文章候选。"),
                "relevance": ScoreItem(value=85, reason="适合展开为 AI 论文深度解读主文章。"),
                "writeability": ScoreItem(value=82, reason="已有标题、摘要、角度和来源 URL 可作为写作入口。"),
                "conversion": ScoreItem(value=80, reason="具备学术价值、解释空间和后续追踪价值。"),
            },
            business_hook=item.angle,
            source_count=max(1, len(item.source_urls)),
            evidence_risk="medium" if signal_ids or paper else "high",
            recommendation=item.summary,
            signal_ids=signal_ids,
            created_at=now_iso(),
        )
        self.store.update_topic(topic)
        return topic

    def _previous_topic_pack_items(self, run_date: str) -> List[Dict[str, object]]:
        return [
            item.model_dump(mode="json")
            for pack in self.store.list_topic_pack_versions()
            for item in [*pack.long_articles, *pack.ai_hotspots, *pack.arxiv_papers]
        ]

    def _score_long_article_papers(self, run: DailyRun) -> List[PaperScore]:
        scores = score_papers(
            run.papers,
            run.signals,
            self._previous_topic_pack_items(run.date),
            run_date=run.date,
        )
        if len(scores) < 5:
            raise RuntimeError(f"可评分论文不足 5 篇，当前 {len(scores)} 篇")
        return scores

    def _locked_long_article_items(
        self,
        run_date: str,
        version: int,
        scores: List[PaperScore],
        llm_items: List[TopicPackItem],
        llm_response_id: str,
    ) -> List[TopicPackItem]:
        text_by_arxiv_id = {
            normalize_arxiv_version(arxiv_id): item
            for item in llm_items
            for arxiv_id in [item.arxiv_id, *(extract_arxiv_id(url) for url in item.source_urls)]
            if arxiv_id
        }
        locked: List[TopicPackItem] = []
        for index, score in enumerate(scores[:5], start=1):
            paper = score.paper
            text_item = text_by_arxiv_id.get(normalize_arxiv_version(paper.arxiv_id))
            if text_item and not _llm_item_matches_paper(text_item, paper):
                text_item = None
            title = text_item.title if text_item else fallback_topic_pack_title(paper)
            summary = text_item.summary if text_item else fallback_topic_pack_summary(paper, score)
            angle = text_item.angle if text_item else fallback_topic_pack_angle(paper)
            locked.append(
                self._make_topic_pack_item(
                    run_date=run_date,
                    version=version,
                    module="long_articles",
                    rank=index,
                    title=title,
                    summary=summary,
                    angle=angle,
                    source_urls=list(dict.fromkeys(url for url in [f"https://arxiv.org/abs/{paper.arxiv_id}", paper.pdf_url] if url)),
                    arxiv_id=paper.arxiv_id,
                    llm_response_id=llm_response_id,
                    score_detail=_score_detail_for_topic_pack(score),
                )
            )
        return locked

    def _create_topic_pack_version(
        self,
        run: DailyRun,
        module: TopicPackModule,
        reason: str,
        trigger: Literal["scheduled", "manual"],
        previous: TopicPackVersion | None = None,
        validate_changed: bool = True,
    ) -> TopicPackVersion:
        if previous is None:
            previous = self.store.current_topic_pack(run.date)
        next_version = (previous.version + 1) if previous else 1
        if not self.llm_provider:
            raise RuntimeError("LLM provider is required to refresh topic pack")
        generation_module: TopicPackModule = module if previous else "all"
        lock_long_articles = generation_module in {"long_articles", "all"} and module in {"long_articles", "all"}
        generated = self._generate_topic_pack_candidate(run.date, generation_module, reason, previous, run.topics, run.signals, run.papers)
        response_id = generated.get("_response_id", "")
        prompt_summary = generated.get("_prompt_summary", "")
        long_article_scores: List[PaperScore] = []
        missing_modules: List[Literal["long_articles", "ai_hotspots", "arxiv_papers"]] = []
        if lock_long_articles:
            long_article_scores = self._score_long_article_papers(run)
            llm_long_articles = self._items_from_payload_or_empty(
                run.date,
                next_version,
                "long_articles",
                generated.get("long_articles"),
                response_id,
                missing_modules,
            )
            long_articles = self._locked_long_article_items(run.date, next_version, long_article_scores, llm_long_articles, response_id)
        elif generation_module in {"long_articles", "all"}:
            long_articles = self._items_from_payload_or_empty(
                run.date,
                next_version,
                "long_articles",
                generated.get("long_articles"),
                response_id,
                missing_modules,
            )
        else:
            long_articles = previous.long_articles if previous else []
        if generation_module not in {"ai_hotspots", "all"}:
            ai_hotspots = previous.ai_hotspots if previous else []
        else:
            ai_hotspots = self._items_from_payload_or_previous(
                run.date,
                next_version,
                "ai_hotspots",
                generated.get("ai_hotspots"),
                response_id,
                previous.ai_hotspots if previous else [],
                missing_modules,
            )
        if generation_module not in {"arxiv_papers", "all"}:
            arxiv_papers = previous.arxiv_papers if previous else []
        else:
            arxiv_papers = self._items_from_payload_or_previous(
                run.date,
                next_version,
                "arxiv_papers",
                generated.get("arxiv_papers"),
                response_id,
                previous.arxiv_papers if previous else [],
                missing_modules,
            )
        pack = TopicPackVersion(
            id=f"topic-pack-{run.date}-v{next_version:02d}",
            date=run.date,
            version=next_version,
            trigger=trigger,
            refreshed_module=module,
            status="partial" if missing_modules else "ready",
            long_articles=self._rank_items(long_articles, "long_articles"),
            ai_hotspots=self._rank_items(ai_hotspots, "ai_hotspots"),
            arxiv_papers=self._rank_items(arxiv_papers, "arxiv_papers"),
            llm_prompt_summary=prompt_summary,
            llm_response_id=response_id,
            previous_version_id=previous.id if previous else None,
            created_at=now_iso(),
        )
        self._validate_topic_pack(pack)
        if previous and validate_changed:
            self._validate_refreshed_module_changed(previous, pack, module)
        self.store.add_topic_pack_version(pack)
        if lock_long_articles:
            report_path = self.store.topic_pack_dir(run.date, next_version) / "long-article-scores.json"
            report_path.write_text(
                json.dumps(build_score_report(pack.id, long_article_scores), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return pack

    def ensure_daily_run(self, date: str | None = None) -> DailyRun:
        run_date = date or date_type.today().isoformat()
        existing = self.store.get_run(run_date)
        if existing:
            return self._hydrate_run(existing)
        return self.run_daily(run_date)

    def run_daily(self, date: str | None = None, avoid_topic_id: str = "") -> DailyRun:
        run_date = date or date_type.today().isoformat()
        sources = seed_sources(run_date)
        if self.live_sources:
            papers, signals = self._fetch_live_sources(sources)
        else:
            signals = seed_signals(run_date)
            papers = seed_papers(run_date)
        topics = self._build_topics(run_date, signals, papers)
        selected_topic = self._select_front_page(topics, avoid_topic_id=avoid_topic_id)
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

    def check_sources(self, date: str | None = None) -> Dict[str, object]:
        run_date = date or date_type.today().isoformat()
        sources = seed_sources(run_date)
        total_papers = 0
        total_signals = 0
        results: List[Dict[str, object]] = []
        for source in sources:
            if not source.enabled or source.type not in {"arxiv", "rss", "github"}:
                continue
            fetched_papers = 0
            fetched_signals = 0
            try:
                papers, signals = self._fetch_one_source(source)
                fetched_papers = len(papers)
                fetched_signals = len(signals)
                total_papers += fetched_papers
                total_signals += fetched_signals
                source.status = "healthy"
                source.last_success_at = now_iso()
                source.last_error = None
            except Exception as exc:
                source.status = "failed"
                source.last_error = str(exc)
            self.store.upsert_many("sources", [source])
            results.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "type": source.type,
                    "url": source.url,
                    "status": source.status,
                    "last_error": source.last_error,
                    "fetched_papers": fetched_papers,
                    "fetched_signals": fetched_signals,
                }
            )
        failed = sum(1 for item in results if item["status"] == "failed")
        healthy = sum(1 for item in results if item["status"] == "healthy")
        return {
            "date": run_date,
            "ok": failed == 0,
            "total_sources": len(results),
            "healthy_sources": healthy,
            "failed_sources": failed,
            "fetched_papers": total_papers,
            "fetched_signals": total_signals,
            "sources": results,
        }

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
            include_long_article=False,
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
        generation_error = ""
        if include_long_article and self.llm_provider and module == "main":
            generated_markdown = self._generate_article_markdown(
                topic,
                paper,
                evidence_items,
                ai_hotspots,
                arxiv_hot_papers,
                include_long_article=True,
            )
            generation_error = self._last_generation_error
        elif self.llm_provider and module in {"hotspots", "arxiv"}:
            previous_generation_error = draft.generation_error
            generated_markdown = self._generate_secondary_module_markdown(
                module,
                topic,
                ai_hotspots,
                arxiv_hot_papers,
                fallback=generated_markdown,
            )
            generation_error = self._last_generation_error or previous_generation_error
        markdown = replace_article_module(existing_markdown, generated_markdown, module)
        markdown = ensure_module_refresh_changes(existing_markdown, markdown, module, topic, reason)
        self.store.write_text(draft.markdown_path, markdown)
        self.store.write_text(draft.html_path, markdown_to_wechat_html(markdown))
        if module == "main":
            visual_errors: List[str] = []
            for stage, default_reason in (
                ("cover", "generate deep paper analysis cover"),
                ("mechanism", "generate deep paper analysis mechanism"),
            ):
                try:
                    self._regenerate_visual_asset(draft, topic, stage, reason or default_reason)
                except RuntimeError as error:
                    visual_errors.append(f"{stage}: {error}")
            if visual_errors:
                generation_error = join_generation_errors(generation_error, *visual_errors)
        draft.generation_error = generation_error
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

    def _generate_topic_pack_candidate(
        self,
        run_date: str,
        module: TopicPackModule,
        reason: str,
        previous: TopicPackVersion | None,
        topics: List[Topic],
        signals: List[Signal],
        papers: List[Paper],
    ) -> Dict[str, object]:
        prompt_summary = f"刷新模块：{module}；日期：{run_date}；原因：{reason or 'manual refresh'}"
        if not self.llm_provider:
            raise RuntimeError("LLM provider is required to refresh topic pack")
        instructions = (
            "你是中文 AI 论文公众号选题策划。必须返回 JSON，不要 Markdown。"
            "字段为 long_articles、ai_hotspots、arxiv_papers。"
            "长文章 5 条，AI 热点 5-10 条，arXiv 论文 5-10 条。"
            "整体标准是学术价值优先：优先问题重要、方法有贡献、实验扎实、近期仍值得读的 AI 论文，"
            "不局限 Agent/RAG，覆盖 LLM、多模态、生成模型、AI safety、推理效率、训练方法、评测、AI coding、AI4Science、机器人等方向。"
            "long_articles 必须是近期重要 AI 论文深度解读候选，每条必须包含 arxiv_id 或 arXiv/PDF 论文 URL；"
            "不得把 GitHub 项目、产品新闻、公司动态或泛话题单独放进 long_articles。"
            "ai_hotspots 承接 AI 热点、官方博客、产品动态、GitHub 开源项目和社区讨论；GitHub 主要进入 ai_hotspots。"
            "arxiv_papers 是 5-10 篇值得关注的论文速报，按学术价值排序，不按传播热度单独决定。"
            "每条包含 title、summary、angle、source_urls，可选 arxiv_id。"
            "手动刷新时必须生成新角度，并避开历史里已经出现的标题、URL、arXiv ID 和同质角度。"
        )
        history_titles = [
            item.title
            for pack in self.store.list_topic_pack_versions(run_date)
            for item in [*pack.long_articles, *pack.ai_hotspots, *pack.arxiv_papers]
        ]
        input_text = json.dumps(
            {
                "date": run_date,
                "refresh_module": module,
                "reason": reason,
                "历史": {
                    "current_version": previous.version if previous else 0,
                    "titles_to_avoid": history_titles,
                    "current_pack": previous.model_dump(mode="json") if previous else None,
                },
                "signals": compact_signals(signals),
                "papers": compact_papers(papers),
                "topics": compact_topics(topics),
            },
            ensure_ascii=False,
        )
        try:
            result = self.llm_provider.complete(instructions, input_text)
            payload = extract_json_object(result.text)
            payload["_response_id"] = getattr(result, "response_id", "")
            payload["_prompt_summary"] = prompt_summary
            return payload
        except Exception as error:
            raise RuntimeError(f"LLM topic pack generation failed: {error}") from error

    def _items_from_payload(
        self,
        run_date: str,
        version: int,
        module: Literal["long_articles", "ai_hotspots", "arxiv_papers"],
        payload: object,
        llm_response_id: str,
    ) -> List[TopicPackItem]:
        if not isinstance(payload, list):
            raise RuntimeError(f"LLM response missing {module}")
        items: List[TopicPackItem] = []
        for index, raw in enumerate(payload, start=1):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            summary = str(raw.get("summary") or raw.get("description") or "").strip()
            angle = str(raw.get("angle") or raw.get("recommendation") or summary).strip()
            source_urls = topic_pack_source_urls(raw)
            arxiv_id = raw.get("arxiv_id") or next((extract_arxiv_id(url) for url in source_urls if extract_arxiv_id(url)), None)
            has_paper_source = bool(arxiv_id) or any(is_paper_url(url) for url in source_urls)
            if module in {"long_articles", "arxiv_papers"} and not has_paper_source:
                continue
            if module == "long_articles" and any(is_github_url(url) for url in source_urls) and not has_paper_source:
                continue
            items.append(
                self._make_topic_pack_item(
                    run_date=run_date,
                    version=version,
                    module=module,
                    rank=index,
                    title=title,
                    summary=summary or angle or title,
                    angle=angle or summary or title,
                    source_urls=source_urls,
                    arxiv_id=str(arxiv_id) if arxiv_id else None,
                    llm_response_id=llm_response_id,
                )
            )
        min_count = 5
        max_count = 5 if module == "long_articles" else 10
        if len(items) < min_count:
            raise RuntimeError(f"LLM response {module} must contain at least {min_count} valid items")
        return items[:max_count]

    def _items_from_payload_or_empty(
        self,
        run_date: str,
        version: int,
        module: Literal["long_articles", "ai_hotspots", "arxiv_papers"],
        payload: object,
        llm_response_id: str,
        missing_modules: List[Literal["long_articles", "ai_hotspots", "arxiv_papers"]],
    ) -> List[TopicPackItem]:
        try:
            return self._items_from_payload(run_date, version, module, payload, llm_response_id)
        except RuntimeError:
            missing_modules.append(module)
            return []

    def _items_from_payload_or_previous(
        self,
        run_date: str,
        version: int,
        module: Literal["ai_hotspots", "arxiv_papers"],
        payload: object,
        llm_response_id: str,
        previous_items: List[TopicPackItem],
        missing_modules: List[Literal["long_articles", "ai_hotspots", "arxiv_papers"]],
    ) -> List[TopicPackItem]:
        try:
            return self._items_from_payload(run_date, version, module, payload, llm_response_id)
        except RuntimeError:
            missing_modules.append(module)
            return previous_items

    def _make_topic_pack_item(
        self,
        run_date: str,
        version: int,
        module: Literal["long_articles", "ai_hotspots", "arxiv_papers"],
        rank: int,
        title: str,
        summary: str,
        angle: str,
        source_urls: List[str],
        arxiv_id: str | None,
        llm_response_id: str,
        topic_id: str | None = None,
        score_detail: Dict[str, object] | None = None,
    ) -> TopicPackItem:
        dedupe_key = normalize_dedupe("|".join([title, arxiv_id or "", *source_urls]))
        angle_hash = short_hash(normalize_dedupe(angle))
        return TopicPackItem(
            id=f"topic-pack-item-{run_date}-v{version:02d}-{module}-{rank}",
            module=module,
            title=title,
            summary=summary,
            angle=angle,
            source_urls=source_urls,
            arxiv_id=arxiv_id,
            topic_id=topic_id,
            rank=rank,
            llm_response_id=llm_response_id,
            dedupe_key=dedupe_key,
            angle_hash=angle_hash,
            score_detail=score_detail or {},
        )

    def _rank_items(self, items: List[TopicPackItem], module: Literal["long_articles", "ai_hotspots", "arxiv_papers"]) -> List[TopicPackItem]:
        return [item.model_copy(update={"rank": index, "module": module}) for index, item in enumerate(items, start=1)]

    def _validate_topic_pack(self, pack: TopicPackVersion) -> None:
        if len(pack.long_articles) != 5:
            raise RuntimeError("Topic pack long_articles must contain 5 items")
        if pack.ai_hotspots and not 5 <= len(pack.ai_hotspots) <= 10:
            raise RuntimeError("Topic pack ai_hotspots must contain 5-10 items")
        if pack.arxiv_papers and not 5 <= len(pack.arxiv_papers) <= 10:
            raise RuntimeError("Topic pack arxiv_papers must contain 5-10 items")

    def _validate_refreshed_module_changed(self, previous: TopicPackVersion, pack: TopicPackVersion, module: TopicPackModule) -> None:
        modules: List[Literal["long_articles", "ai_hotspots", "arxiv_papers"]]
        if module == "all":
            modules = ["long_articles", "ai_hotspots", "arxiv_papers"]
        else:
            modules = [module]
        for name in modules:
            old_items = getattr(previous, name)
            new_items = getattr(pack, name)
            old_fingerprint = {(item.dedupe_key, item.angle_hash) for item in old_items}
            new_fingerprint = {(item.dedupe_key, item.angle_hash) for item in new_items}
            if old_fingerprint == new_fingerprint:
                raise RuntimeError(f"LLM response did not produce new {name} angles")

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
                title = build_rerun_title(topic, reason, version=draft.version)
                draft.title = title
                markdown = replace_first_heading(markdown, f"今日 AI 论文与热点文章包：{title}")
                markdown = replace_visible_article_title(markdown, title)
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
                "Agent Laboratory 这篇科研 Agent 论文真正贡献是什么？",
                "从论文问题、方法流程、实验可信度和局限切入，做一篇专业但好读的论文解读。",
                "long_paper",
                "paper-agent-lab",
                ["signal-agent-lab-paper", "signal-agent-lab-code", "signal-post-paper-topics"],
            ),
            (
                "topic-long-context-rag",
                "长上下文与 RAG 的论文争论，核心其实是成本和路由",
                "围绕长上下文与检索增强的对比论文，解释方法贡献、实验设置和结论边界。",
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
                "解释为什么记忆、检索、工具和 trace 正在变成 AI 应用系统的关键工程问题。",
                "topic_inspiration",
                None,
                ["signal-anthropic-context", "signal-long-context-rag"],
            ),
            (
                "topic-evalkit",
                "EvalKit 这类评测工具为什么值得关注？",
                "从工具生态角度判断它对 LLM 应用评测和回归测试的价值。",
                "short_hotspot",
                None,
                ["signal-github-evalkit"],
            ),
            (
                "topic-agent-builder",
                "可视化 Agent Builder 的真正价值是实验回放",
                "把产品更新转成 AI 应用工程和可观测性的热点判断。",
                "short_hotspot",
                None,
                ["signal-product-agent-builder"],
            ),
            (
                "topic-thesis-agent-eval",
                "Agent 评测论文为什么还值得继续看？",
                "整理 Agent 评测在交互任务、轨迹和失败恢复上的研究价值。",
                "topic_inspiration",
                None,
                ["signal-post-paper-topics", "signal-openai-evals"],
            ),
        ]
        topics: List[Topic] = []
        paper_ids = {paper.id for paper in papers}
        for index, (topic_id, title, angle, article_type, paper_id, signal_ids) in enumerate(definitions):
            if any(signal_id not in signal_map for signal_id in signal_ids):
                continue
            if paper_id and paper_id not in paper_ids:
                continue
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
                        "relevance": ScoreItem(value=relevance, reason="与 AI 研究问题、方法贡献、实验可信度或行业变化直接相关。"),
                        "writeability": ScoreItem(value=writeability, reason="能拆成问题、方法、实验、局限和判断，适合公众号深度解读。"),
                        "conversion": ScoreItem(value=conversion, reason="具备学术价值、可读性和后续展开空间。"),
                    },
                    business_hook="适合从研究问题、方法贡献、实验可信度和局限四个角度做专业解读。",
                    source_count=len(linked),
                    evidence_risk="low" if len(linked) >= 2 else "medium",
                    recommendation=angle,
                    signal_ids=signal_ids,
                    created_at=now,
                )
            )
        known_signal_ids = {signal_id for topic in topics for signal_id in topic.signal_ids}
        dynamic_signals = [signal for signal in signals if signal.id not in known_signal_ids]
        for signal in sorted(dynamic_signals, key=live_signal_sort_key)[: max(0, 10 - len(topics))]:
            article_type = "long_paper" if signal.kind == "paper" else "short_hotspot"
            heat = live_signal_heat(signal)
            relevance = live_signal_relevance(signal)
            writeability = 86 if signal.kind == "paper" and signal.summary else 78 if signal.summary else 62
            conversion = 86 if signal.kind == "paper" else 72 if signal.kind == "repo" else 60
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
                        "heat": ScoreItem(value=heat, reason="来自严格实时信源的新信号，并按论文、代码、新闻类型校准。"),
                        "relevance": ScoreItem(value=relevance, reason="按信号类型、AI 标签和研究价值关键词估算相关性。"),
                        "writeability": ScoreItem(value=writeability, reason="有标题和摘要，可形成短评或论文解析入口。"),
                        "conversion": ScoreItem(value=conversion, reason="具备学术价值、行业判断或工具生态观察价值。"),
                    },
                    business_hook="需要人工审核后判断是否适合展开成论文深度解读或热点短评。",
                    source_count=1,
                    evidence_risk="medium",
                    recommendation=signal.summary,
                    signal_ids=[signal.id],
                    created_at=now,
                )
            )
        return sorted(topics, key=lambda item: item.score_total, reverse=True)[:10]

    def _fetch_live_sources(self, sources) -> tuple[List[Paper], List[Signal]]:
        live_papers: List[Paper] = []
        live_signals: List[Signal] = []
        failures: List[str] = []
        for source in sources:
            if not source.enabled or source.type not in {"arxiv", "rss", "github"}:
                continue
            try:
                papers, signals = self._fetch_one_source(source)
                live_papers.extend(papers)
                live_signals.extend(signals)
                source.status = "healthy"
                source.last_success_at = now_iso()
                source.last_error = None
            except Exception as exc:
                source.status = "failed"
                source.last_error = str(exc)
                failures.append(f"{source.id}: {exc}")
            finally:
                self.store.upsert_many("sources", [source])
        if failures:
            raise RuntimeError("Live source refresh failed: " + "; ".join(failures))
        if not live_signals:
            raise RuntimeError("Live source refresh failed: no signals returned from enabled sources")
        return live_papers, live_signals

    def _fetch_one_source(self, source) -> tuple[List[Paper], List[Signal]]:
        headers = {}
        if source.type in {"arxiv", "rss"}:
            headers["Cache-Control"] = "no-cache"
            headers["Pragma"] = "no-cache"
        if source.type == "github":
            headers["Accept"] = "application/vnd.github+json"
            token = os.getenv("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        response = self.http_client.get(source.url, headers=headers or None)
        response.raise_for_status()
        if source.type == "arxiv":
            return parse_arxiv_feed(response.text, source.id)
        if source.type == "rss":
            return [], parse_rss_feed(response.text, source.id)
        if source.type == "github":
            return [], parse_github_search_repositories(response.json(), source.id)
        return [], []

    def _select_front_page(self, topics: List[Topic], avoid_topic_id: str = "") -> Topic:
        long_papers = [topic for topic in topics if topic.article_type == "long_paper"]
        ranked = sorted(long_papers, key=lambda item: item.score_total, reverse=True)
        if avoid_topic_id and len(ranked) > 1:
            alternative = next((topic for topic in ranked if topic.id != avoid_topic_id), None)
            if alternative:
                return alternative
        return ranked[0]

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
        self._last_generation_error = ""
        if not include_long_article:
            return build_article_markdown(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers, include_long_article=False)
        fallback = rewrite_khazix_style(build_article_markdown(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers))
        if not self.llm_provider:
            self._last_generation_error = "LLM provider is not configured; used fallback article."
            return fallback
        instructions = (
            "你是一个谨慎、有判断力的中文 AI 论文公众号作者。只能基于证据包写作，"
            "必须使用中文输出 Markdown，重点输出“主文章：长论文解读”模块。"
            "主文章必须是专业但好读的论文深度解读，"
            "围绕论文问题、方法贡献、实验可信度、局限和为什么近期值得读展开。"
            "可以参考次文章素材理解上下文，但不要因为次文章格式影响主文章。"
            "避免报告腔、营销腔和夸大事实。"
        )
        input_text = build_llm_article_input(topic, paper, evidence_items, ai_hotspots, arxiv_hot_papers, fallback)
        try:
            result = self.llm_provider.complete(instructions, input_text)
        except Exception as error:
            self._last_generation_error = f"LLM article generation failed; used fallback article. {type(error).__name__}: {error}"
            return fallback
        text = result.text.strip()
        main_marker = "## 主文章：长论文解读"
        main_section = extract_markdown_section(text, main_marker) if main_marker in text else ""
        fallback_main_section = extract_markdown_section(fallback, main_marker)
        if not main_section:
            self._last_generation_error = "LLM article response missing main article marker; used fallback article."
            return fallback
        if article_copies_fallback(main_section, fallback_main_section):
            self._last_generation_error = "LLM article response copied local fallback template; used fallback article."
            return fallback
        if not main_article_is_publish_ready(main_section):
            self._last_generation_error = "LLM article response failed main-article publishability validation; used fallback article."
            return fallback
        return main_section

    def _generate_secondary_module_markdown(
        self,
        module: Literal["hotspots", "arxiv"],
        topic: Topic,
        ai_hotspots: List[Signal],
        arxiv_hot_papers: List[Paper],
        fallback: str,
    ) -> str:
        self._last_generation_error = ""
        marker = "## 次文章 1：AI 热点" if module == "hotspots" else "## 次文章 2：arXiv 高热度文章速报"
        module_name = "AI 热点" if module == "hotspots" else "arXiv 速报"
        instructions = (
            f"你是一个谨慎、有判断力的中文 AI 论文公众号编辑。请只改写 {module_name}模块。"
            f"必须只输出以“{marker}”开头的 Markdown 模块，不要输出主文章、另一个次文章或来源清单。"
            "必须使用中文，写成可直接发布的短文章，不要写成 bullet 素材清单。"
            "必须包含一个 ### 小标题，每条信息都要有判断，不能夸大事实，不能新增素材外事实。"
        )
        input_text = build_llm_secondary_module_input(module, topic, ai_hotspots, arxiv_hot_papers, fallback)
        try:
            result = self.llm_provider.complete(instructions, input_text)
        except Exception as error:
            self._last_generation_error = f"LLM {module} generation failed; used fallback module. {type(error).__name__}: {error}"
            return fallback
        text = result.text.strip()
        section = extract_markdown_section(text, marker) if marker in text else text
        if not section or marker not in section:
            self._last_generation_error = f"LLM {module} response missing required module marker; used fallback module."
            return fallback
        if not secondary_module_is_publish_ready(section):
            self._last_generation_error = f"LLM {module} response failed publishability validation; used fallback module."
            return fallback
        return section

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
            return ensure_style_rerun_changes(markdown, fallback, topic, reason)
        text = result.text.strip()
        replacement = extract_markdown_section(text, main_marker) if main_marker in text else text
        if not replacement or main_marker not in replacement:
            return ensure_style_rerun_changes(markdown, fallback, topic, reason)
        rewritten = replace_article_module(markdown, replacement, "main")
        return ensure_style_rerun_changes(markdown, rewritten, topic, reason)


UNPUBLISHABLE_MARKERS = ("待 LLM", "人工解析", "MVP connector")


def text_is_mostly_chinese(value: str) -> bool:
    chinese_count = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
    latin_count = sum(1 for char in value if ("a" <= char.lower() <= "z"))
    return chinese_count >= 8 and chinese_count >= latin_count


def is_publishable_chinese_text(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if any(marker in stripped for marker in UNPUBLISHABLE_MARKERS):
        return False
    return text_is_mostly_chinese(stripped)


def compact_english_concepts(value: str, max_items: int = 4) -> str:
    candidates = re.findall(r"[A-Z][A-Za-z0-9-]*(?:[- ][A-Za-z0-9][A-Za-z0-9-]*){0,5}", value)
    cleaned: List[str] = []
    stop_words = {
        "We",
        "This",
        "Mainstream",
        "The",
        "A",
        "An",
        "In",
        "For",
        "Under",
        "Execution-State Capsules",
    }
    for candidate in candidates:
        candidate = candidate.strip(" .,:;()[]")
        if len(candidate) < 3 or candidate in stop_words:
            continue
        if candidate not in cleaned:
            cleaned.append(candidate)
        if len(cleaned) >= max_items:
            break
    return "、".join(cleaned)


def zh_topic_focus(topic: Topic, paper: Paper | None) -> str:
    material = " ".join([topic.title, topic.angle, paper.abstract if paper else ""])
    return zh_focus_from_material(material)


def zh_paper_focus(paper: Paper) -> str:
    return zh_focus_from_material(" ".join([paper.title, paper.abstract]))


def zh_focus_from_material(material: str) -> str:
    lower = material.lower()
    if any(keyword in lower for keyword in ("sparse autoencoder", "sparse autoencoders", "feature splitting", "feature absorption")):
        return "可解释性、稀疏自编码器和特征表示可靠性"
    if any(keyword in lower for keyword in ("asynchronous pipeline", "pipeline parallel", "gradient delay", "pretraining")):
        return "大模型训练效率、异步流水线并行和优化稳定性"
    if any(keyword in lower for keyword in ("song generation", "music", "melodious", "vocal", "accompaniment")):
        return "音乐生成、层次化表示建模和后训练对齐"
    if any(keyword in lower for keyword in ("multi-agent", "multi agent", "communication channel", "vulnerable communication")):
        return "多智能体安全、通信通道风险和系统防护优先级"
    if any(keyword in lower for keyword in ("contrastive", "embedding norm", "embeddings", "concept specificity")):
        return "表征学习、嵌入范数和语义特异性"
    if any(keyword in lower for keyword in ("on-device", "low-latency", "small-batch", "serving", "kv cache", "checkpoint")):
        return "端侧低延迟模型服务、执行状态复用和小 batch 推理"
    if any(keyword in lower for keyword in ("rag", "retrieval", "long-context", "long context")):
        return "长上下文、检索增强和真实任务里的上下文管理"
    if any(keyword in lower for keyword in ("agent", "agents", "workflow", "tool")):
        return "Agent 工作流、工具调用和可验证评测"
    if any(keyword in lower for keyword in ("robot", "robotics", "physical-ai", "physical ai")):
        return "物理 AI、机器人策略和交互式推理"
    concepts = compact_english_concepts(material)
    if concepts:
        return f"{concepts} 相关系统问题"
    return "AI 系统设计、评测和学术解释价值"


def publishable_topic_angle(topic: Topic, paper: Paper | None) -> str:
    for candidate in (topic.recommendation, topic.angle, paper.abstract if paper else ""):
        if is_publishable_chinese_text(candidate):
            return candidate.strip()
    focus = zh_topic_focus(topic, paper)
    return f"这篇论文适合先按“{focus}”来读：不要急着复述英文摘要，而要看它提出了什么系统矛盾、如何设计机制，以及实验能不能支撑这个判断。"


def publishable_method_summary(topic: Topic, paper: Paper | None) -> str:
    if paper and is_publishable_chinese_text(paper.method_summary):
        return paper.method_summary.strip()
    focus = zh_topic_focus(topic, paper)
    return (
        f"从题目和摘要能看出，作者想围绕{focus}提出一个更细的机制设计。"
        "发布前还需要补读 PDF 的方法章节，确认它的核心对象、状态边界、复用策略和系统开销。"
        "在正文里可以先把它写成一个待验证的工程假设，而不是已经被完全证明的结论。"
    )


def publishable_method_summary_for_paper(paper: Paper) -> str:
    if is_publishable_chinese_text(paper.method_summary):
        return paper.method_summary.strip()
    focus = zh_paper_focus(paper)
    return f"从摘要看，它适合按{focus}来读；发布前需要补读 PDF，确认方法结构、实验设置和指标口径。"


def publishable_experiment_summary(topic: Topic, paper: Paper | None) -> str:
    if paper and is_publishable_chinese_text(paper.experiment_summary):
        return paper.experiment_summary.strip()
    return (
        "目前数据接入器只保留了摘要、编号和 PDF 链接，还没有结构化抽取实验表格。"
        "因此这篇稿子必须把实验结论写得克制：重点提醒读者发布前要核对任务设置、对照方法、指标口径、样本规模和失败案例。"
    )


def publishable_limitations(topic: Topic, paper: Paper | None) -> str:
    if paper and is_publishable_chinese_text(paper.limitations):
        return paper.limitations.strip()
    focus = zh_topic_focus(topic, paper)
    return (
        f"这篇论文当前最需要人工复核的是实验细节，尤其是{focus}在真实设备、真实负载或真实交互任务里的约束。"
        "如果 PDF 里没有清楚说明对照方法、硬件环境、延迟统计方式和失败案例，公众号里就不能把摘要里的说法放大成确定结论。"
    )


def build_article_markdown(
    topic: Topic,
    paper: Paper | None,
    evidence_items: List[EvidenceItem],
    ai_hotspots: List[Signal],
    arxiv_hot_papers: List[Paper],
    include_long_article: bool = True,
) -> str:
    paper_title = paper.title if paper else topic.title
    research_threads = "\n".join(f"- {item}" for item in (paper.extension_topics if paper else [topic.business_hook]))
    paper_date = human_date_zh(paper.published_at) if paper else ""
    paper_time_note = f"这篇论文发布于 {paper_date}。" if paper_date else "这篇论文还需要人工核对发布时间。"
    hotspot_article = build_hotspot_publish_article(ai_hotspots)
    arxiv_article = build_arxiv_publish_article(arxiv_hot_papers)
    source_lines = "\n".join(f"- [{item.source_title}]({item.source_url})" for item in evidence_items)
    angle = publishable_topic_angle(topic, paper)
    method = publishable_method_summary(topic, paper)
    experiment = publishable_experiment_summary(topic, paper)
    limitations = publishable_limitations(topic, paper)
    code_value = paper.code_url if paper and paper.code_url else "暂未发现稳定代码仓库，建议发布前再次检索。"
    if not include_long_article:
        return f"""# 今日 AI 论文与热点文章包

## 主文章：长论文解读

### 待生成

当前已选择：**{topic.title}**。

点击“生成长文”后，系统会围绕这篇论文生成中文深度解读，并调用 image2 生成封面图和机制图。

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

> {angle}

这篇文章不把论文包装成万能突破，而是先问三个问题：它解决的问题是否重要，方法贡献是否站得住，实验能不能支撑作者的判断。

{paper_time_note}现在把它拿出来写，是因为它代表了近期 AI 研究里一个值得认真看的问题：模型、数据、推理或系统能力的瓶颈，正在从抽象概念落到更具体的机制和实验上。

### 1. 这篇论文到底想解决什么问题

{paper_title}，arXiv:{paper.arxiv_id if paper else "待核对"}，真正值得看的不是标题里的关键词，而是它把哪个研究矛盾摆到了台面上。好的论文通常不是把概念喊大，而是把一个长期模糊的问题变成可以定义、可以比较、可以被实验反驳的对象。

### 2. 它的方法贡献在哪里

{method}

这里最需要看的，是作者有没有提出一个清楚的新机制，还是只是把已有组件重新包装。判断方法贡献时，我会优先看它改变了什么假设、减少了什么成本、提升了什么能力，以及这些提升是否来自论文声称的核心设计。

### 3. 实验结果能不能信

{experiment}

这里需要保守一点：如果只看摘要，还不能把它写成确定性的胜利。更好的写法是讲清楚它声称解决什么、需要哪些指标支撑，以及发布前还必须补读 PDF 里的实验设置。

### 4. 它和已有工作的区别是什么

这篇论文如果要写得有价值，不能只复述摘要。要把它放回同类工作里看：它是改了模型结构、训练目标、推理过程、评测方式，还是系统调度策略？它相对已有方法的区别越清楚，文章的判断就越不容易变成泛泛介绍。

### 5. 局限和风险在哪里

{limitations}

### 6. 如果有代码或实验材料，应该怎么看

代码入口：{code_value}

代码不是热度本身，只是判断论文可信度的辅助信号。有代码时，优先看它是否覆盖核心实验、是否能重跑主要结果、是否说明数据和硬件环境；没有代码时，文章里就要把结论写得更克制。

### 7. 配图建议

封面图应该突出这篇论文的核心研究对象，而不是做抽象科技背景。机制图应该把“问题输入、方法核心、实验验证”画成三段，让读者一眼知道论文在解决什么、方法如何工作、证据来自哪里。

### 8. 我的判断

{paper_title} 值得读的前提，不是它标题够热，而是它是否让一个 AI 研究问题变得更可讨论。我的判断是，这篇论文适合按下面几个线索继续追：

{research_threads}

如果后续还有作者代码、相关 benchmark、独立评测或 follow-up 论文出现，这篇就值得继续展开成更完整的系列解读。

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
        f"再看 {signal.title}。{signal.summary} 这条消息适合放在一起读，因为它补的是 AI 行业变化里的另一个侧面：工具、模型、产品和开发者生态正在怎样移动。来源，{signal.url}"
        for signal in supporting
    )
    if not supporting_text:
        supporting_text = "今天可用的稳定信号不多，所以这条热点更适合当作一个小提醒，而不是硬扩成大判断。"
    return f"""### 今天这几条消息，我建议你不要当新闻看

今天这几条消息，我建议你不要当新闻看。

更准确的读法是，把它们当成 AI 行业变化的信号。

最值得放在前面的，是 {primary.title}。{primary.summary}

我觉得它值得关注，不是因为标题听起来热，而是因为它能帮助我们判断：模型能力、工具链、产品形态或开发者生态正在往哪个方向移动。

来源，{primary.url}

{supporting_text}

所以这栏真正想提醒的不是「今天 AI 圈又发生了什么」。

而是这些消息背后，哪些变化会影响接下来一段时间的 AI 研究、产品和开发实践。
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
        f"还有一篇可以顺手放进待读列表，{paper.title}，arXiv:{paper.arxiv_id}。{publishable_method_summary_for_paper(paper)} 它适合已经熟悉相关方向的读者先读，重点看它的实验设置和验证价值，当前学术价值参考分是 {paper.replication_value}/100。链接，{paper.pdf_url}"
        for paper in secondary
    )
    if not secondary_text:
        secondary_text = "如果今天只读一篇，那就先读上面这一篇。不要贪多，先把问题、方法和实验设计看明白。"
    return f"""### 今天这组论文，我建议先按学术价值来读

今天这组论文，我建议先按学术价值来读。

也就是说，先别急着问它是不是今天刚发，也别只看标题有没有大词。

先看它能不能把一个 AI 研究问题讲清楚。

第一篇是 {primary.title}，arXiv:{primary.arxiv_id}。{publishable_method_summary_for_paper(primary)}

这篇适合已经熟悉相关方向的读者先读。读的时候不要只看结论，重点看它怎么设置问题、怎么安排对照方法、实验是否能支撑核心判断。它当前的学术价值参考分是 {primary.replication_value}/100。

链接，{primary.pdf_url}

{secondary_text}

我的建议是，次文章的 arXiv 速报不要写成论文目录。

读者真正需要的，是知道哪篇值得先读，为什么值得读，以及它有没有机会继续展开成论文深度解读。
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

内容判断:
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
- 主文章必须围绕论文问题、方法贡献、实验可信度、局限和近期为什么值得读展开。
- 次文章 1 每条热点要有一句判断，GitHub 项目只能作为热点或论文辅助证据。
- 次文章 2 每篇论文要说明方向、核心贡献、实验亮点、适合谁读，是否值得后续展开成长论文解读。
- 主文章必须包含“配图建议”，说明 image2 封面图和机制图的用途。

本地 fallback 草稿，可参考结构但不要照抄:
{fallback}
"""


def build_llm_secondary_module_input(
    module: Literal["hotspots", "arxiv"],
    topic: Topic,
    ai_hotspots: List[Signal],
    arxiv_hot_papers: List[Paper],
    fallback: str,
) -> str:
    if module == "hotspots":
        material = "\n".join(
            f"- {signal.kind} | {signal.title}: {signal.summary} URL: {signal.url}"
            for signal in ai_hotspots[:8]
        )
        requirements = (
            "- 输出模块标题必须是“## 次文章 1：AI 热点”。\n"
            "- 从热点素材中挑 3-5 条写成短文章，每条都要说明为什么值得关注。\n"
            "- GitHub 项目只能作为热点或工具生态信号，不要写成论文深度解读。"
        )
    else:
        material = "\n".join(
            f"- {paper.title} | arXiv:{paper.arxiv_id} | {paper.method_summary} | "
            f"replication:{paper.replication_value} | {paper.pdf_url}"
            for paper in arxiv_hot_papers[:8]
        )
        requirements = (
            "- 输出模块标题必须是“## 次文章 2：arXiv 高热度文章速报”。\n"
            "- 从论文素材中挑 3-5 篇写成速报，说明方向、贡献、实验亮点、适合谁读。\n"
            "- 必须说明哪些论文值得后续展开成深度解读。"
        )
    return f"""当前主选题:
{topic.title}

素材:
{material}

必须满足:
{requirements}
- 必须包含一个“### ”小标题。
- 不要输出 bullet list 素材清单，要写成自然段。
- 不要输出主文章、另一个次文章或来源清单。

本地 fallback 模块，可参考结构但不要照抄:
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
        "而是把研究问题、证据、实验和复核拆成可以检查的动作。"
        "所以后面的阅读重点，仍然放在流程是否可验证、评价是否站得住，以及人类判断应该放在哪些节点。\n"
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


def ensure_module_refresh_changes(
    original_markdown: str,
    refreshed_markdown: str,
    module: RefreshModule,
    topic: Topic,
    reason: str = "",
) -> str:
    if refreshed_markdown.strip() != original_markdown.strip():
        return refreshed_markdown
    markers = {
        "main": "## 主文章：长论文解读",
        "hotspots": "## 次文章 1：AI 热点",
        "arxiv": "## 次文章 2：arXiv 高热度文章速报",
    }
    marker = markers[module]
    section = extract_markdown_section(original_markdown, marker)
    if not section:
        return refreshed_markdown
    note_titles = {
        "main": "### 长文刷新札记",
        "hotspots": "### AI 热点刷新札记",
        "arxiv": "### arXiv 速报刷新札记",
    }
    note = (
        f"{note_titles[module]}\n\n"
        f"这次点击重新检查了 **{topic.title}** 对应模块；"
        "当前素材生成出的判断与上一版一致，所以保留原有观点，并在这里记录一次可见刷新。"
        f"触发原因：{reason or 'manual module refresh'}。\n"
    )
    replacement = f"{section.rstrip()}\n\n{note.strip()}"
    return replace_article_module(original_markdown, replacement, module)


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
        if not secondary_module_is_publish_ready(section):
            return False
    return True


def secondary_module_is_publish_ready(section: str) -> bool:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if len(lines) < 8:
        return False
    if not any(line.startswith("### ") for line in lines):
        return False
    if any(line.startswith("- ") for line in lines):
        return False
    return True


def article_main_is_chinese(markdown: str) -> bool:
    main = extract_markdown_section(markdown, "## 主文章：长论文解读")
    if not main and markdown.strip().startswith("## 主文章：长论文解读"):
        main = markdown
    chinese_count = sum(1 for char in main if "\u4e00" <= char <= "\u9fff")
    latin_count = sum(1 for char in main if ("a" <= char.lower() <= "z"))
    return chinese_count >= 20 and chinese_count >= latin_count


def main_article_is_publish_ready(markdown: str) -> bool:
    if not article_main_is_chinese(markdown):
        return False
    return all(keyword in markdown for keyword in ("方法", "实验", "局限"))


def article_copies_fallback(markdown: str, fallback: str) -> bool:
    candidate = strip_refresh_notes(markdown)
    reference = strip_refresh_notes(fallback)
    if not candidate or not reference:
        return False
    if candidate == reference or candidate.startswith(reference):
        return True
    return SequenceMatcher(None, candidate, reference).ratio() >= 0.92


def strip_refresh_notes(markdown: str) -> str:
    return re.sub(r"\n### (长文刷新札记|重跑编辑札记|风格重跑札记)\n.*", "", markdown.strip(), flags=re.S)


def join_generation_errors(*errors: str) -> str:
    return "\n".join(error.strip() for error in errors if error and error.strip())


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
- [ ] 学术价值和解读价值是否讲清楚
- [ ] 图片是否贴合内容
- [ ] HTML 复制到公众号后台是否正常
{rerun_lines}"""


def build_rerun_title(topic: Topic, reason: str = "", version: int | None = None) -> str:
    reason_hint = reason.strip()
    suffix = "重写版"
    if reason_hint:
        suffix = "判断版" if "sharp" in reason_hint.lower() or "标题" in reason_hint else "重写版"
    if version is not None:
        suffix = f"{suffix} v{version}"
    return f"{topic.title}｜{suffix}"


def replace_first_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            lines[index] = f"# {title}"
            return "\n".join(lines).rstrip() + "\n"
    return f"# {title}\n\n{markdown.lstrip()}".rstrip() + "\n"


def replace_visible_article_title(markdown: str, title: str) -> str:
    main_marker = "## 主文章：长论文解读"
    main_section = extract_markdown_section(markdown, main_marker)
    if not main_section:
        return markdown
    lines = main_section.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("### "):
            lines[index] = f"### {title}"
            replacement = "\n".join(lines).rstrip()
            return replace_article_module(markdown, replacement, "main")
    replacement = f"{main_section.rstrip()}\n\n### {title}"
    return replace_article_module(markdown, replacement, "main")


def upsert_intro_section(markdown: str, topic: Topic, reason: str = "") -> str:
    marker = "### 编辑导语"
    lead = (
        f"{marker}\n\n"
        f"这次重跑导语，把选题先压到一个明确判断：**{topic.title}** 的价值不在热度，"
        f"而在它能不能把研究问题、实验路径和证据边界拆清楚。\n\n"
        f"重跑原因：{reason or '人工请求重新整理导语'}\n"
    )
    main_marker = "## 主文章：长论文解读"
    main_section = extract_markdown_section(markdown, main_marker)
    if main_section:
        if marker in main_section:
            start = main_section.find(marker)
            end = main_section.find("\n### ", start + len(marker))
            if end < 0:
                end = len(main_section)
            replacement = f"{main_section[:start].rstrip()}\n\n{lead.strip()}\n\n{main_section[end:].lstrip()}".rstrip()
        else:
            lines = main_section.splitlines()
            insert_at = 1
            for index, line in enumerate(lines):
                if index > 0 and line.startswith("### "):
                    insert_at = index + 1
                    break
            lines.insert(insert_at, "")
            lines.insert(insert_at + 1, lead.strip())
            replacement = "\n".join(lines).rstrip()
        return replace_article_module(markdown, replacement, "main")
    legacy_marker = "## 编辑导语"
    if legacy_marker in markdown:
        start = markdown.find(legacy_marker)
        end = markdown.find("\n## ", start + len(legacy_marker))
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

## 解读价值

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


AI_RESEARCH_KEYWORDS = (
    "agent",
    "agents",
    "llm",
    "language model",
    "rag",
    "retrieval",
    "eval",
    "evaluation",
    "benchmark",
    "baseline",
    "multimodal",
    "diffusion",
    "reasoning",
    "in-context",
    "mixture-of-experts",
    "moe",
    "coding",
    "safety",
    "inference",
    "training",
    "calibration",
    "reproducible",
    "experiment",
    "实验",
    "评测",
    "复现",
    "论文",
    "模型",
    "智能体",
)


def live_signal_sort_key(signal: Signal) -> tuple[int, int, int, str]:
    kind_priority = {"paper": 0, "repo": 1, "news": 2, "product": 3, "post": 4}.get(signal.kind, 5)
    return (kind_priority, -live_signal_relevance(signal), -live_signal_heat(signal), signal.title.lower())


def live_signal_heat(signal: Signal) -> int:
    if signal.kind == "paper":
        return min(100, signal.heat + 14)
    if signal.kind == "repo":
        return min(88, max(68, signal.heat - 8))
    return min(82, signal.heat + 2)


def live_signal_relevance(signal: Signal) -> int:
    text = f"{signal.title} {signal.summary} {' '.join(signal.tags)}".lower()
    keyword_hits = sum(1 for keyword in AI_RESEARCH_KEYWORDS if keyword in text)
    if signal.kind == "paper":
        return min(98, 88 + keyword_hits * 2)
    if signal.kind == "repo":
        return min(90, 76 + keyword_hits * 2)
    return min(84, 66 + keyword_hits * 2)


def compact_signals(signals: List[Signal], limit: int = 30) -> List[Dict[str, object]]:
    ranked = sorted(signals, key=live_signal_sort_key)[:limit]
    return [
        {
            "kind": signal.kind,
            "title": signal.title,
            "summary": signal.summary[:600],
            "url": signal.url,
            "heat": signal.heat,
            "tags": signal.tags[:8],
        }
        for signal in ranked
    ]


def compact_papers(papers: List[Paper], limit: int = 10) -> List[Dict[str, object]]:
    ranked = sorted(papers, key=lambda paper: paper.replication_value, reverse=True)[:limit]
    return [
        {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "abstract": paper.abstract[:800],
            "pdf_url": paper.pdf_url,
            "code_url": paper.code_url,
            "categories": paper.categories[:6],
            "replication_value": paper.replication_value,
        }
        for paper in ranked
    ]


def compact_topics(topics: List[Topic], limit: int = 10) -> List[Dict[str, object]]:
    ranked = sorted(topics, key=lambda topic: topic.score_total, reverse=True)[:limit]
    return [
        {
            "title": topic.title,
            "angle": topic.angle,
            "article_type": topic.article_type,
            "score_total": topic.score_total,
            "business_hook": topic.business_hook,
            "evidence_risk": topic.evidence_risk,
            "recommendation": topic.recommendation,
        }
        for topic in ranked
    ]


def extract_json_object(value: str) -> Dict[str, object]:
    text = value.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not include a JSON object")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON must be an object")
    return payload


def normalize_dedupe(value: str) -> str:
    return " ".join(value.lower().strip().split())


def is_github_url(value: str) -> bool:
    return "github.com/" in value.lower()


def is_paper_url(value: str) -> bool:
    lowered = value.lower()
    return "arxiv.org/abs/" in lowered or "arxiv.org/pdf/" in lowered or "doi.org/" in lowered


def topic_pack_source_urls(raw: Dict[str, object]) -> List[str]:
    urls: List[str] = []
    for key in ("source_urls", "sources"):
        value = raw.get(key) or []
        if not isinstance(value, list):
            value = [value]
        urls.extend(str(url).strip() for url in value if str(url).strip())
    for key in ("url", "link", "pdf_url", "source_url"):
        value = str(raw.get(key) or "").strip()
        if value:
            urls.append(value)
    return list(dict.fromkeys(urls))


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


def fallback_topic_pack_title(paper: Paper) -> str:
    return f"为什么值得读：{zh_paper_focus(paper)}"


def fallback_topic_pack_summary(paper: Paper, score: PaperScore) -> str:
    reasons = "；".join(score.selection_reasons[:2]) if score.selection_reasons else "量化评分进入前五"
    return f"这篇论文入选长文候选，核心看点是{zh_paper_focus(paper)}。入选依据：{reasons}。"


def fallback_topic_pack_angle(paper: Paper) -> str:
    focus = zh_paper_focus(paper)
    return f"这篇论文适合先按“{focus}”来读：重点看它试图解决的研究矛盾、机制设计是否清楚，以及实验是否足以支撑结论。"


def _llm_item_matches_paper(item: TopicPackItem, paper: Paper) -> bool:
    paper_arxiv_id = normalize_arxiv_version(paper.arxiv_id)
    item_arxiv_ids = {
        normalize_arxiv_version(arxiv_id)
        for arxiv_id in [item.arxiv_id, *(extract_arxiv_id(url) for url in item.source_urls)]
        if arxiv_id
    }
    if paper_arxiv_id not in item_arxiv_ids:
        return False
    return _title_matches_paper(item.title, paper.title)


def _title_matches_paper(llm_title: str, paper_title: str) -> bool:
    llm_normalized = normalize_dedupe(llm_title)
    paper_normalized = normalize_dedupe(paper_title)
    if not llm_normalized or not paper_normalized:
        return False
    if llm_normalized in paper_normalized or paper_normalized in llm_normalized:
        return True
    llm_tokens = set(re.findall(r"[a-z0-9]{3,}", llm_normalized))
    paper_tokens = set(re.findall(r"[a-z0-9]{3,}", paper_normalized))
    if llm_tokens.intersection(paper_tokens):
        return True
    return SequenceMatcher(None, llm_normalized, paper_normalized).ratio() >= 0.35


def normalize_arxiv_version(value: str) -> str:
    return value.strip().removeprefix("arXiv:").split("v", 1)[0]


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def extract_arxiv_id(url: str) -> str | None:
    if "arxiv.org/" not in url:
        return None
    token = url.rstrip("/").split("/")[-1]
    return token or None


def generate_image_asset(path: Path, prompt: str, rgb: tuple[int, int, int], storage_root: Path | None = None):
    provider = Image2Provider.from_env(storage_root)
    if provider:
        try:
            return provider.generate(prompt, path)
        except Exception as error:
            raise RuntimeError(f"Image2 generation failed: {error}") from error
    raise RuntimeError("Image2 provider is not configured")
