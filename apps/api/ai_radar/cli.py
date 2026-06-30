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
    check_sources = subparsers.add_parser(
        "check-sources",
        help="Check strict live source health",
        description="Check strict live source health",
    )
    check_sources.add_argument("--date", required=True)
    check_sources.add_argument("--storage-root", default="storage")
    scheduled = subparsers.add_parser(
        "run-scheduled",
        help="Check live sources before running the scheduled daily radar",
        description="Run the scheduled daily radar only after strict source health passes",
    )
    scheduled.add_argument("--date", required=True)
    scheduled.add_argument("--storage-root", default="storage")
    scheduled.add_argument("--live-sources", action="store_true")
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
    elif args.command == "check-sources":
        summary = DailyPipeline(JsonStore(Path(args.storage_root))).check_sources(args.date)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if not summary["ok"]:
            raise SystemExit(1)
    elif args.command == "run-scheduled":
        pipeline = DailyPipeline(JsonStore(Path(args.storage_root)), live_sources=args.live_sources)
        source_summary = pipeline.check_sources(args.date) if args.live_sources else {"ok": True, "failed_sources": 0, "sources": []}
        if not source_summary["ok"]:
            print(
                json.dumps(
                    {
                        "date": args.date,
                        "source_ok": False,
                        "failed_sources": source_summary["failed_sources"],
                        "sources": source_summary["sources"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise SystemExit(1)
        run = pipeline.run_daily(args.date)
        print(
            json.dumps(
                {
                    "date": run.date,
                    "source_ok": True,
                    "failed_sources": source_summary["failed_sources"],
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
