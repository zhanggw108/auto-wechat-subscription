from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SourceType = Literal["rss", "api", "github", "arxiv", "manual"]
SourceStatus = Literal["healthy", "degraded", "failed"]
SignalKind = Literal["news", "paper", "repo", "product", "post"]
ArticleType = Literal["long_paper", "industry_analysis", "topic_inspiration", "short_hotspot"]
TopicStatus = Literal["candidate", "selected", "drafted", "published", "rejected"]
DraftStatus = Literal["generating", "review", "ready", "published", "rejected"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
RefreshModule = Literal["main", "hotspots", "arxiv"]
TopicPackModule = Literal["long_articles", "ai_hotspots", "arxiv_papers", "all"]
NarrativeType = Literal[
    "evaluation_review",
    "mechanism_explainer",
    "controversy_judgement",
    "trend_slice",
    "application_translation",
]


class ScoreItem(BaseModel):
    value: int = Field(ge=0, le=100)
    reason: str


class Source(BaseModel):
    id: str
    name: str
    type: SourceType
    url: str
    enabled: bool = True
    fetch_interval_minutes: int = 1440
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    status: SourceStatus = "healthy"
    created_at: str


class Signal(BaseModel):
    id: str
    source_id: str
    kind: SignalKind
    title: str
    summary: str
    url: str
    published_at: str
    tags: List[str] = Field(default_factory=list)
    heat: int = Field(ge=0, le=100)
    entities: Dict[str, List[str]] = Field(default_factory=dict)


class Paper(BaseModel):
    id: str
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    pdf_url: str
    code_url: Optional[str] = None
    published_at: str
    categories: List[str]
    method_summary: str
    experiment_summary: str
    limitations: str
    replication_value: int = Field(ge=0, le=100)
    extension_topics: List[str]


class Topic(BaseModel):
    id: str
    slug: str
    cluster_id: str
    paper_id: Optional[str] = None
    title: str
    angle: str
    article_type: ArticleType
    status: TopicStatus = "candidate"
    score_total: int = Field(ge=0, le=100)
    score_detail: Dict[str, ScoreItem]
    business_hook: str
    source_count: int
    evidence_risk: Literal["low", "medium", "high"]
    recommendation: str
    signal_ids: List[str]
    created_at: str


class TopicPackItem(BaseModel):
    id: str
    module: Literal["long_articles", "ai_hotspots", "arxiv_papers"]
    title: str
    summary: str
    angle: str
    source_urls: List[str] = Field(default_factory=list)
    arxiv_id: Optional[str] = None
    topic_id: Optional[str] = None
    rank: int = Field(ge=1)
    status: TopicStatus = "candidate"
    llm_response_id: str = ""
    dedupe_key: str
    angle_hash: str
    score_detail: Dict[str, object] = Field(default_factory=dict)


class TopicPackVersion(BaseModel):
    id: str
    date: str
    version: int = Field(ge=1)
    trigger: Literal["scheduled", "manual"]
    refreshed_module: TopicPackModule
    status: Literal["generating", "ready", "partial", "failed"] = "ready"
    long_articles: List[TopicPackItem]
    ai_hotspots: List[TopicPackItem]
    arxiv_papers: List[TopicPackItem]
    llm_prompt_summary: str = ""
    llm_response_id: str = ""
    previous_version_id: Optional[str] = None
    created_at: str


class EvidenceItem(BaseModel):
    id: str
    topic_id: str
    source_url: str
    source_title: str
    claim: str
    snippet: str
    confidence: Literal["high", "medium", "low"]
    risk_note: str = ""
    created_at: str


class DraftAsset(BaseModel):
    id: str
    draft_id: str
    kind: Literal["cover", "mechanism", "inline_illustration", "quote", "source_file"]
    prompt: str
    revised_prompt: Optional[str] = None
    path: str
    insert_after: str = ""
    width: int = 1536
    height: int = 1024
    provider: str = "image2"
    provider_request_id: Optional[str] = None
    created_at: str


class Draft(BaseModel):
    id: str
    topic_id: str
    title: str
    subtitle: str
    status: DraftStatus
    markdown_path: str
    html_path: str
    sources_path: str
    checklist_path: str
    evidence_path: str
    topic_path: str
    version: int
    assets: List[DraftAsset] = Field(default_factory=list)
    last_rerun_stage: str = ""
    generation_error: str = ""
    created_at: str
    updated_at: str


class Job(BaseModel):
    id: str
    type: str
    status: JobStatus
    input: Dict[str, str] = Field(default_factory=dict)
    output: Dict[str, str] = Field(default_factory=dict)
    error: str = ""
    retry_count: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class RadarToday(BaseModel):
    date: str
    signal_count: int
    ai_relevant_count: int
    topic_count: int
    source_health: List[Source]
    top_hotspots: List[Signal]
    categories: Dict[str, int]
    recommended_topic: Topic
    draft: Draft


class DailyRun(BaseModel):
    date: str
    sources: List[Source]
    signals: List[Signal]
    papers: List[Paper]
    topics: List[Topic]
    selected_topic: Topic
    evidence_items: List[EvidenceItem]
    draft: Draft


class DraftDetail(BaseModel):
    draft: Draft
    topic: Topic
    evidence_items: List[EvidenceItem]
    markdown: str
    html: str
    sources: str
    review_checklist: str


class RegenerateRequest(BaseModel):
    stage: Literal["title", "outline", "article", "style", "review", "cover", "mechanism", "visuals", "wechat"]
    reason: str = ""


class RefreshModuleRequest(BaseModel):
    module: RefreshModule
    reason: str = "manual refresh"
    narrative_type: Optional[NarrativeType] = None


class TopicPackRefreshRequest(BaseModel):
    date: Optional[str] = None
    module: TopicPackModule
    reason: str = "manual refresh"


class DraftContentUpdate(BaseModel):
    markdown: str = Field(min_length=1)
    reason: str = "manual edit"


class RefreshStatus(BaseModel):
    date: str
    refresh_time: str
    today_refreshed: bool
    last_refresh_at: Optional[str] = None
    next_refresh_at: str
    seconds_until_next_refresh: int


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
