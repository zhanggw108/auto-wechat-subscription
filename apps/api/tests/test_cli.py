import json
import os
import subprocess
from pathlib import Path
from typing import Optional


def cli_env(extra: Optional[dict] = None) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = "apps/api"
    if extra:
        env.update(extra)
    return env


def test_daily_cli_generates_package(tmp_path: Path):
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "ai_radar.cli",
            "run-daily",
            "--date",
            "2026-06-20",
            "--storage-root",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=cli_env(),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["topic_count"] == 7
    assert payload["draft_status"] == "review"
    assert (tmp_path / payload["markdown_path"]).exists()


def test_check_sources_cli_reports_usage_without_generating_package(tmp_path: Path):
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "ai_radar.cli",
            "check-sources",
            "--date",
            "2026-06-20",
            "--storage-root",
            str(tmp_path),
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=cli_env(),
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Check strict live source health" in result.stdout
    assert not (tmp_path / "drafts").exists()


def test_run_scheduled_cli_gates_daily_generation_on_source_health(tmp_path: Path):
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "ai_radar.cli",
            "run-scheduled",
            "--date",
            "2026-06-20",
            "--storage-root",
            str(tmp_path),
            "--live-sources",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=cli_env(
            {
                "AI_RADAR_ARXIV_URL": "http://127.0.0.1:9/arxiv",
                "AI_RADAR_NEWS_RSS_URL": "http://127.0.0.1:9/news.xml",
                "AI_RADAR_GITHUB_SEARCH_URL": "http://127.0.0.1:9/github",
                "AI_RADAR_OFFICIAL_BLOGS_RSS_URL": "http://127.0.0.1:9/official.xml",
            }
        ),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["source_ok"] is False
    assert payload["failed_sources"] == 4
    assert not (tmp_path / "drafts").exists()


def test_run_scheduled_cli_generates_package_after_source_gate_when_not_live(tmp_path: Path):
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "ai_radar.cli",
            "run-scheduled",
            "--date",
            "2026-06-20",
            "--storage-root",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=cli_env(),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["source_ok"] is True
    assert payload["topic_count"] == 7
    assert payload["draft_status"] == "review"
    assert (tmp_path / payload["markdown_path"]).exists()
