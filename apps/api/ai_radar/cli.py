from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import DailyPipeline
from .storage import JsonStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    daily = subparsers.add_parser("run-daily", help="Generate the daily radar and draft package")
    daily.add_argument("--date", required=True)
    daily.add_argument("--storage-root", default="storage")
    daily.add_argument("--live-sources", action="store_true")
    args = parser.parse_args()

    if args.command == "run-daily":
        run = DailyPipeline(JsonStore(Path(args.storage_root)), live_sources=args.live_sources).run_daily(args.date)
        print(
            json.dumps(
                {
                    "date": run.date,
                    "topic_count": len(run.topics),
                    "selected_topic": run.selected_topic.title,
                    "draft_id": run.draft.id,
                    "draft_status": run.draft.status,
                    "markdown_path": run.draft.markdown_path,
                    "html_path": run.draft.html_path,
                    "sources_path": run.draft.sources_path,
                    "checklist_path": run.draft.checklist_path,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
