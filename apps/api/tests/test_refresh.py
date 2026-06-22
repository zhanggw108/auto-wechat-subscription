from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from ai_radar.api import create_app
from ai_radar.pipeline import DailyPipeline
from ai_radar.storage import JsonStore


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
    refreshed = client.post(f"/api/drafts/{radar['draft']['id']}/refresh-module", json={"module": "arxiv"})
    assert refreshed.status_code == 200
    assert refreshed.json()["last_rerun_stage"] == "refresh:arxiv"


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
