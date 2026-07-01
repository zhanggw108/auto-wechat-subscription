import os
from pathlib import Path

from ai_radar.storage import JsonStore


def test_json_store_save_replaces_database_atomically_without_stale_tail(tmp_path: Path, monkeypatch):
    replacements = []
    original_replace = os.replace

    def recording_replace(src, dst):
        replacements.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", recording_replace)
    store = JsonStore(tmp_path)

    store.save({"runs": {"2026-06-23": {"payload": "x" * 1000}}})
    store.save({"runs": {}})

    assert store.load() == {"runs": {}}
    assert not store.db_path.read_text(encoding="utf-8").rstrip().endswith("x" * 10)
    assert replacements
    assert replacements[-1][0].parent == tmp_path
    assert replacements[-1][1] == store.db_path
    assert not replacements[-1][0].exists()
