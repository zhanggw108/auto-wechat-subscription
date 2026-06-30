from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import DraftContentUpdate, RefreshModuleRequest, RegenerateRequest, TopicPackRefreshRequest
from .pipeline import DailyPipeline
from .settings import ProvidersSettingsInput, SettingsStore
from .storage import JsonStore


def create_app(
    storage_root: Optional[Path] = None,
    auto_refresh_on_startup: bool = False,
    startup_now: Optional[datetime] = None,
    http_client: Optional[httpx.Client] = None,
) -> FastAPI:
    root = storage_root or Path(__file__).resolve().parents[3] / "storage"
    store = JsonStore(root)
    pipeline = DailyPipeline(store, http_client=http_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if auto_refresh_on_startup:
            pipeline.refresh_if_due(startup_now)
        yield

    app = FastAPI(title="AI Paper Content Radar", version="0.1.0", lifespan=lifespan)
    app.state.pipeline = pipeline
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "storage_root": str(root)}

    @app.get("/api/radar/today")
    def radar_today(date: Optional[str] = None):
        try:
            return pipeline.radar_today(date)
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    def parse_now(value: Optional[str]) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid now timestamp")

    @app.get("/api/refresh/status")
    def refresh_status(now: Optional[str] = None):
        return pipeline.refresh_status(parse_now(now))

    @app.post("/api/refresh/due")
    def refresh_due(now: Optional[str] = None):
        try:
            return pipeline.refresh_if_due(parse_now(now))
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    @app.post("/api/refresh/today")
    def refresh_today(now: Optional[str] = None):
        try:
            return pipeline.refresh_today(parse_now(now))
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    @app.get("/api/sources")
    def sources(date: Optional[str] = None):
        existing_sources = store.list_sources()
        if existing_sources:
            return existing_sources
        try:
            pipeline.ensure_daily_run(date)
        except RuntimeError as error:
            recorded_sources = store.list_sources()
            if recorded_sources:
                return recorded_sources
            raise HTTPException(status_code=502, detail=str(error))
        return store.list_sources()

    @app.get("/api/settings/providers")
    def get_provider_settings():
        return SettingsStore(root).public()

    @app.put("/api/settings/providers")
    def update_provider_settings(settings: ProvidersSettingsInput):
        return SettingsStore(root).update(settings)

    @app.post("/api/sources/{source_id}/refresh")
    def refresh_source(source_id: str):
        return pipeline.create_refresh_job(source_id)

    @app.get("/api/topics")
    def topics(date: Optional[str] = None):
        return pipeline.list_topics(date)

    @app.get("/api/topic-packs")
    def topic_packs(date: Optional[str] = None):
        return pipeline.list_topic_packs(date)

    @app.get("/api/topic-packs/current")
    def current_topic_pack(date: Optional[str] = None):
        try:
            return pipeline.ensure_topic_pack(date)
        except KeyError:
            raise HTTPException(status_code=404, detail="Topic pack not generated yet")

    @app.get("/api/topic-packs/{pack_id}")
    def topic_pack(pack_id: str):
        try:
            return pipeline.get_topic_pack(pack_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Topic pack not found")

    @app.post("/api/topic-packs/refresh")
    def refresh_topic_pack(request: TopicPackRefreshRequest):
        try:
            return pipeline.refresh_topic_pack(request.date, request.module, request.reason, fresh_sources=True)
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    @app.get("/api/topics/{topic_id}")
    def topic(topic_id: str):
        try:
            return pipeline.get_topic(topic_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Topic not found")

    @app.post("/api/topics/{topic_id}/select")
    def select_topic(topic_id: str):
        try:
            return pipeline.set_topic_status(topic_id, "selected")
        except KeyError:
            raise HTTPException(status_code=404, detail="Topic not found")

    @app.post("/api/topics/{topic_id}/reject")
    def reject_topic(topic_id: str):
        try:
            return pipeline.set_topic_status(topic_id, "rejected")
        except KeyError:
            raise HTTPException(status_code=404, detail="Topic not found")

    @app.post("/api/topics/{topic_id}/draft")
    def draft_topic(topic_id: str, date: Optional[str] = None):
        try:
            return pipeline.draft_topic(topic_id, date)
        except KeyError:
            raise HTTPException(status_code=404, detail="Topic not found")

    @app.get("/api/papers/{paper_id}")
    def paper(paper_id: str, date: Optional[str] = None):
        pipeline.ensure_daily_run(date)
        for item in store.list_papers():
            if item.id == paper_id:
                return item
        raise HTTPException(status_code=404, detail="Paper not found")

    @app.post("/api/papers/analyze")
    def analyze_paper():
        run = pipeline.ensure_daily_run()
        return run.papers[0]

    @app.get("/api/drafts")
    def drafts(date: Optional[str] = None):
        return pipeline.list_drafts(date)

    @app.get("/api/drafts/{draft_id}")
    def draft_detail(draft_id: str):
        try:
            return pipeline.draft_detail(draft_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Draft not found")

    @app.put("/api/drafts/{draft_id}/content")
    def update_draft_content(draft_id: str, request: DraftContentUpdate):
        try:
            return pipeline.update_draft_content(draft_id, request.markdown, request.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Draft not found")

    @app.post("/api/drafts/{draft_id}/regenerate")
    def regenerate_draft(draft_id: str, request: RegenerateRequest):
        try:
            return pipeline.regenerate_draft(draft_id, request.stage, request.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Draft not found")
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    @app.post("/api/drafts/{draft_id}/refresh-module")
    def refresh_module(draft_id: str, request: RefreshModuleRequest):
        try:
            return pipeline.refresh_module(draft_id, request.module, request.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Draft not found")
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    @app.post("/api/drafts/{draft_id}/render-wechat")
    def render_wechat(draft_id: str):
        try:
            return pipeline.regenerate_draft(draft_id, "wechat", "manual render")
        except KeyError:
            raise HTTPException(status_code=404, detail="Draft not found")

    @app.post("/api/drafts/{draft_id}/mark-published")
    def mark_published(draft_id: str):
        try:
            return pipeline.mark_published(draft_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Draft not found")

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        try:
            return pipeline.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        try:
            return pipeline.cancel_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")

    return app


app = create_app()
