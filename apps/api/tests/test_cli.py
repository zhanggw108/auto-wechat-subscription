import json
import subprocess
from pathlib import Path


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
        env={"PYTHONPATH": "apps/api"},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["topic_count"] == 7
    assert payload["draft_status"] == "review"
    assert (tmp_path / payload["markdown_path"]).exists()
