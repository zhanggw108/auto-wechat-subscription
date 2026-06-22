from pathlib import Path
from typing import Optional

import httpx
from fastapi.testclient import TestClient

from ai_radar.api import create_app


def make_client(tmp_path: Path, http_client: Optional[httpx.Client] = None) -> TestClient:
    app = create_app(storage_root=tmp_path, http_client=http_client)
    return TestClient(app)


def test_health_and_radar_today(tmp_path: Path):
    client = make_client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    radar = client.get("/api/radar/today?date=2026-06-20")
    assert radar.status_code == 200
    data = radar.json()
    assert data["date"] == "2026-06-20"
    assert data["topic_count"] >= 5
    assert data["ai_relevant_count"] >= 5
    assert len(data["top_hotspots"]) == 5
    assert data["recommended_topic"]["article_type"] == "long_paper"


def test_topics_selection_rejection_and_drafts(tmp_path: Path):
    client = make_client(tmp_path)
    client.get("/api/radar/today?date=2026-06-20")

    topics = client.get("/api/topics?date=2026-06-20")
    assert topics.status_code == 200
    items = topics.json()
    assert 5 <= len(items) <= 10

    topic_id = items[1]["id"]
    selected = client.post(f"/api/topics/{topic_id}/select")
    assert selected.status_code == 200
    assert selected.json()["status"] == "selected"

    rejected = client.post(f"/api/topics/{items[-1]['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    detail = client.get(f"/api/topics/{topic_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == topic_id

    drafts = client.get("/api/drafts?date=2026-06-20")
    assert drafts.status_code == 200
    assert len(drafts.json()) >= 1


def test_draft_detail_rerun_render_and_publish(tmp_path: Path):
    client = make_client(tmp_path)
    radar = client.get("/api/radar/today?date=2026-06-20").json()
    draft_id = radar["draft"]["id"]

    detail = client.get(f"/api/drafts/{draft_id}")
    assert detail.status_code == 200
    assert "markdown" in detail.json()
    assert "sources" in detail.json()
    assert "review_checklist" in detail.json()

    rerun = client.post(f"/api/drafts/{draft_id}/regenerate", json={"stage": "style", "reason": "humanize"})
    assert rerun.status_code == 200
    assert rerun.json()["version"] == 2
    assert rerun.json()["last_rerun_stage"] == "style"

    rendered = client.post(f"/api/drafts/{draft_id}/render-wechat")
    assert rendered.status_code == 200
    assert rendered.json()["version"] == 3

    published = client.post(f"/api/drafts/{draft_id}/mark-published")
    assert published.status_code == 200
    assert published.json()["status"] == "published"


def test_can_save_edited_draft_markdown_and_refresh_wechat_html(tmp_path: Path):
    client = make_client(tmp_path)
    radar = client.get("/api/radar/today?date=2026-06-20").json()
    draft_id = radar["draft"]["id"]
    edited_markdown = (
        "# 今日 AI 论文与热点文章包\n\n"
        "## 主文章：长论文解读\n\n"
        "人工编辑后的判断句。\n\n"
        "## 次文章 1：AI 热点\n\n"
        "保留热点模块。\n\n"
        "## 次文章 2：arXiv 高热度文章速报\n\n"
        "保留速报模块。"
    )

    saved = client.put(f"/api/drafts/{draft_id}/content", json={"markdown": edited_markdown})

    assert saved.status_code == 200
    detail = saved.json()
    assert detail["markdown"] == edited_markdown
    assert "人工编辑后的判断句。" in detail["html"]
    assert detail["draft"]["version"] == 2
    assert detail["draft"]["last_rerun_stage"] == "manual-edit"


def test_can_generate_long_article_from_user_selected_topic(tmp_path: Path):
    client = make_client(tmp_path)
    client.get("/api/radar/today?date=2026-06-20")

    generated = client.post("/api/topics/topic-long-context-rag/draft?date=2026-06-20")

    assert generated.status_code == 200
    draft = generated.json()
    assert draft["topic_id"] == "topic-long-context-rag"
    assert draft["assets"] == []

    detail = client.get(f"/api/drafts/{draft['id']}")
    assert detail.status_code == 200
    assert "长上下文模型来了，RAG 为什么还没有过时？" in detail.json()["markdown"]


def test_jobs_and_sources_endpoints(tmp_path: Path):
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2606.39999v1</id>
        <updated>2026-06-20T08:20:00Z</updated>
        <published>2026-06-20T08:20:00Z</published>
        <title>API Refresh Paper</title>
        <summary>API refresh integration proof.</summary>
        <author><name>API Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.39999" />
      </entry>
    </feed>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=arxiv_xml)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = make_client(tmp_path, http_client=http_client)
    client.get("/api/radar/today?date=2026-06-20")

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    assert any(source["type"] == "arxiv" for source in sources.json())

    refresh = client.post(f"/api/sources/{sources.json()[0]['id']}/refresh")
    assert refresh.status_code == 200
    job_id = refresh.json()["id"]

    job = client.get(f"/api/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "succeeded"

    canceled = client.post(f"/api/jobs/{job_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
