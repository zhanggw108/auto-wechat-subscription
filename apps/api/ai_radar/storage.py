from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel

from .models import Draft, EvidenceItem, Job, Paper, Signal, Source, Topic


class JsonStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "radar-db.json"

    def load(self) -> Dict[str, object]:
        if not self.db_path.exists():
            return {
                "runs": {},
                "sources": [],
                "signals": [],
                "papers": [],
                "topics": [],
                "evidence_items": [],
                "drafts": [],
                "jobs": [],
                "refreshes": {},
            }
        return json.loads(self.db_path.read_text(encoding="utf-8"))

    def save(self, data: Dict[str, object]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_many(self, key: str, items: Iterable[BaseModel]) -> None:
        data = self.load()
        existing = {item["id"]: item for item in data.get(key, [])}
        for item in items:
            existing[item.id] = item.model_dump(mode="json")
        data[key] = list(existing.values())
        self.save(data)

    def set_run(self, date: str, payload: Dict[str, object]) -> None:
        data = self.load()
        runs = data.setdefault("runs", {})
        runs[date] = payload
        self.save(data)

    def get_run(self, date: str) -> Optional[Dict[str, object]]:
        return self.load().get("runs", {}).get(date)

    def get_refresh(self, date: str) -> Optional[Dict[str, object]]:
        return self.load().get("refreshes", {}).get(date)

    def set_refresh(self, date: str, payload: Dict[str, object]) -> None:
        data = self.load()
        refreshes = data.setdefault("refreshes", {})
        refreshes[date] = payload
        self.save(data)

    def list_sources(self) -> List[Source]:
        return [Source(**item) for item in self.load().get("sources", [])]

    def list_signals(self) -> List[Signal]:
        return [Signal(**item) for item in self.load().get("signals", [])]

    def list_papers(self) -> List[Paper]:
        return [Paper(**item) for item in self.load().get("papers", [])]

    def list_topics(self) -> List[Topic]:
        return [Topic(**item) for item in self.load().get("topics", [])]

    def list_evidence(self) -> List[EvidenceItem]:
        return [EvidenceItem(**item) for item in self.load().get("evidence_items", [])]

    def list_drafts(self) -> List[Draft]:
        return [Draft(**item) for item in self.load().get("drafts", [])]

    def list_jobs(self) -> List[Job]:
        return [Job(**item) for item in self.load().get("jobs", [])]

    def update_topic(self, topic: Topic) -> None:
        self.upsert_many("topics", [topic])

    def update_draft(self, draft: Draft) -> None:
        self.upsert_many("drafts", [draft])

    def update_job(self, job: Job) -> None:
        self.upsert_many("jobs", [job])

    def draft_package_dir(self, date: str, slug: str) -> Path:
        directory = self.root / "drafts" / date / slug
        (directory / "figures").mkdir(parents=True, exist_ok=True)
        return directory

    def write_text(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_text(self, relative_path: str) -> str:
        return (self.root / relative_path).read_text(encoding="utf-8")

    def archive_draft_files(self, draft: Draft, label: str) -> Dict[str, str]:
        files = [
            draft.markdown_path,
            draft.html_path,
            draft.sources_path,
            draft.checklist_path,
            draft.evidence_path,
            draft.topic_path,
        ]
        archive_root = self.root / Path(draft.markdown_path).parent / "history" / slugify(label)
        archive_root.mkdir(parents=True, exist_ok=True)
        archived: Dict[str, str] = {}
        for relative in files:
            source = self.root / relative
            if source.exists():
                destination = archive_root / source.name
                shutil.copy2(source, destination)
                archived[relative] = str(destination.relative_to(self.root))
        return archived


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.lower()).strip("-")
    return slug[:72] or "draft"
