import base64
import json
from pathlib import Path

import httpx

from ai_radar.connectors import parse_arxiv_feed, parse_rss_feed
from ai_radar.image_provider import Image2Provider
from ai_radar.pipeline import DailyPipeline, generate_image_asset
from ai_radar.storage import JsonStore


def test_parse_arxiv_feed_extracts_paper_signal_and_profile():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2606.20101v1</id>
        <updated>2026-06-20T02:20:00Z</updated>
        <published>2026-06-20T02:20:00Z</published>
        <title>Agent Laboratory: Using LLM Agents as Research Assistants</title>
        <summary> A paper about research agents. </summary>
        <author><name>Mira Chen</name></author>
        <author><name>Sanjay Rao</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.20101" />
      </entry>
    </feed>
    """

    papers, signals = parse_arxiv_feed(xml, source_id="source-arxiv")

    assert papers[0].arxiv_id == "2606.20101"
    assert papers[0].authors == ["Mira Chen", "Sanjay Rao"]
    assert papers[0].categories == ["cs.AI"]
    assert signals[0].kind == "paper"
    assert signals[0].url == "http://arxiv.org/abs/2606.20101v1"


def test_parse_rss_feed_extracts_ai_news_signal():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel><title>AI News Radar</title>
      <item>
        <guid>agent-evals</guid>
        <title>Agent evals move toward traces</title>
        <link>https://example.com/agent-evals</link>
        <description>Trace-based evaluation is becoming standard.</description>
        <pubDate>Sat, 20 Jun 2026 06:30:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    signals = parse_rss_feed(xml, source_id="source-ai-news-radar")

    assert signals[0].id == "signal-agent-evals"
    assert signals[0].kind == "news"
    assert "Trace-based" in signals[0].summary


def test_image2_provider_decodes_responses_image_output(tmp_path: Path):
    png = b"\x89PNG\r\n\x1a\nfake"

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        assert "/v1/responses" in str(request.url)
        assert "image_generation" in body
        return httpx.Response(
            200,
            json={
                "id": "resp-1",
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(png).decode("ascii"),
                        "revised_prompt": "revised prompt",
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Image2Provider(
        base_url="https://image2.example.com/v1",
        api_key="test-key",
        model="relay-image-model",
        client=client,
    )

    result = provider.generate("draw cover", tmp_path / "cover.png")

    assert result.path == tmp_path / "cover.png"
    assert result.revised_prompt == "revised prompt"
    assert result.provider_request_id == "resp-1"
    assert result.path.read_bytes() == png


def test_image2_provider_from_env_uses_image_generation_timeout_by_default(monkeypatch):
    monkeypatch.setenv("IMAGE2_BASE_URL", "https://image2.example.com/v1")
    monkeypatch.setenv("IMAGE2_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE2_RESPONSES_MODEL", "relay-image-model")

    provider = Image2Provider.from_env()

    assert provider is not None
    assert provider.client.timeout.read == 90


def test_image2_provider_from_env_allows_timeout_override(monkeypatch):
    monkeypatch.setenv("IMAGE2_BASE_URL", "https://image2.example.com/v1")
    monkeypatch.setenv("IMAGE2_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE2_RESPONSES_MODEL", "relay-image-model")
    monkeypatch.setenv("IMAGE2_TIMEOUT_SECONDS", "180")

    provider = Image2Provider.from_env()

    assert provider is not None
    assert provider.client.timeout.read == 180


def test_generate_image_asset_uses_configured_image2_without_inline_env(tmp_path: Path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\nfake"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp-configured",
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(png).decode("ascii"),
                        "revised_prompt": "configured revised prompt",
                    }
                ],
            },
        )

    settings = {
        "image2": {
            "base_url": "https://image2.example.com/v1",
            "api_key": "test-key",
            "model": "relay-image-model",
        }
    }
    (tmp_path / "settings.local.json").write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setenv("IMAGE2_BASE_URL", "https://image2.example.com/v1")
    monkeypatch.setenv("IMAGE2_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE2_RESPONSES_MODEL", "relay-image-model")
    monkeypatch.delenv("IMAGE2_INLINE_GENERATION", raising=False)
    real_client = httpx.Client
    monkeypatch.setattr(
        "ai_radar.image_provider.httpx.Client",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )

    result = generate_image_asset(tmp_path / "cover.png", "draw cover", rgb=(20, 140, 190), storage_root=tmp_path)

    assert result.provider == "image2"
    assert result.provider_request_id == "resp-configured"
    assert result.revised_prompt == "configured revised prompt"
    assert result.path.read_bytes() == png


def test_generate_image_asset_surfaces_configured_image2_failures(tmp_path: Path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "upstream image failure"})

    settings = {
        "image2": {
            "base_url": "https://image2.example.com/v1",
            "api_key": "test-key",
            "model": "relay-image-model",
        }
    }
    (tmp_path / "settings.local.json").write_text(json.dumps(settings), encoding="utf-8")
    real_client = httpx.Client
    monkeypatch.setattr(
        "ai_radar.image_provider.httpx.Client",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )

    try:
        generate_image_asset(tmp_path / "cover.png", "draw cover", rgb=(20, 140, 190), storage_root=tmp_path)
    except RuntimeError as error:
        assert "Image2 generation failed" in str(error)
    else:
        raise AssertionError("configured image2 failure should not silently create a placeholder")

    assert not (tmp_path / "cover.png").exists()


def test_daily_pipeline_can_merge_live_arxiv_and_rss_sources(tmp_path: Path):
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2606.29999v1</id>
        <updated>2026-06-20T08:20:00Z</updated>
        <published>2026-06-20T08:20:00Z</published>
        <title>Fresh Live Paper for Radar</title>
        <summary>Live arXiv integration proof.</summary>
        <author><name>Live Author</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.29999" />
      </entry>
    </feed>
    """
    rss_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>live-rss-item</guid>
        <title>Fresh RSS AI item</title>
        <link>https://example.com/live-rss-item</link>
        <description>Live RSS integration proof.</description>
        <pubDate>Sat, 20 Jun 2026 08:30:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "arxiv" in str(request.url):
            return httpx.Response(200, text=arxiv_xml)
        return httpx.Response(200, text=rss_xml)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=JsonStore(tmp_path), live_sources=True, http_client=client)

    run = pipeline.run_daily(date="2026-06-20")

    assert any(signal.title == "Fresh Live Paper for Radar" for signal in run.signals)
    assert any(signal.title == "Fresh RSS AI item" for signal in run.signals)
    assert any(paper.arxiv_id == "2606.29999" for paper in run.papers)
    assert any(topic.title == "Fresh Live Paper for Radar" for topic in run.topics)
    assert any(topic.title == "Fresh RSS AI item" for topic in run.topics)


def test_refresh_source_fetches_and_persists_live_items(tmp_path: Path):
    rss_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>refresh-rss-item</guid>
        <title>Refresh RSS AI item</title>
        <link>https://example.com/refresh-rss-item</link>
        <description>Refresh integration proof.</description>
        <pubDate>Sat, 20 Jun 2026 08:45:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=rss_xml)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=JsonStore(tmp_path), http_client=client)
    pipeline.run_daily(date="2026-06-20")

    job = pipeline.create_refresh_job("source-ai-news-radar")

    assert job.status == "succeeded"
    assert any(signal.title == "Refresh RSS AI item" for signal in pipeline.store.list_signals())
    assert job.output["fetched_signals"] == "1"
