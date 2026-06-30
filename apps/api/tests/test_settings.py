from pathlib import Path

from fastapi.testclient import TestClient

from ai_radar.api import create_app
from ai_radar.settings import SettingsStore


def test_settings_api_masks_keys_and_persists_provider_config(tmp_path: Path):
    client = TestClient(create_app(storage_root=tmp_path))

    empty = client.get("/api/settings/providers")
    assert empty.status_code == 200
    assert empty.json()["llm"]["configured"] is False
    assert empty.json()["image2"]["configured"] is False

    saved = client.put(
        "/api/settings/providers",
        json={
            "llm": {
                "provider": "deepseek",
                "base_url": "https://relay.example.com/v1",
                "api_key": "sk-llm-secret",
                "model": "relay-text-model",
            },
            "image2": {
                "base_url": "https://image.example.com/v1",
                "api_key": "sk-image-secret",
                "model": "relay-image-model",
                "size": "1536x1024",
                "quality": "high",
                "output_format": "png",
            },
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["llm"]["configured"] is True
    assert payload["llm"]["provider"] == "deepseek"
    assert payload["llm"]["api_key_masked"] == "sk-...cret"
    assert "sk-llm-secret" not in str(payload)
    assert payload["image2"]["configured"] is True
    assert payload["image2"]["api_key_masked"] == "sk-...cret"
    assert "sk-image-secret" not in str(payload)

    raw = SettingsStore(tmp_path).load_private()
    assert raw["llm"]["provider"] == "deepseek"
    assert raw["llm"]["api_key"] == "sk-llm-secret"
    assert raw["image2"]["api_key"] == "sk-image-secret"


def test_settings_update_preserves_existing_key_when_blank(tmp_path: Path):
    store = SettingsStore(tmp_path)
    store.save_private(
        {
            "llm": {
                "provider": "relay",
                "base_url": "https://old.example.com/v1",
                "api_key": "sk-existing",
                "model": "old-model",
            },
            "image2": {},
        }
    )
    client = TestClient(create_app(storage_root=tmp_path))

    saved = client.put(
        "/api/settings/providers",
        json={
            "llm": {
                "provider": "doubao",
                "base_url": "https://new.example.com/v1",
                "api_key": "",
                "model": "new-model",
            },
            "image2": {},
        },
    )

    assert saved.status_code == 200
    raw = SettingsStore(tmp_path).load_private()
    assert raw["llm"]["api_key"] == "sk-existing"
    assert raw["llm"]["provider"] == "doubao"
    assert raw["llm"]["base_url"] == "https://new.example.com/v1"
