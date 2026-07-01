import base64
import json
from pathlib import Path

import httpx

from ai_radar.connectors import parse_arxiv_feed, parse_github_search_repositories, parse_rss_feed
from ai_radar.image_provider import Image2Provider
from ai_radar.pipeline import DailyPipeline, generate_image_asset
from ai_radar.sample_data import seed_sources
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


def test_parse_rss_feed_limits_items_to_recent_batch():
    items = "\n".join(
        f"""
        <item>
          <guid>item-{index}</guid>
          <title>AI item {index}</title>
          <link>https://example.com/item-{index}</link>
          <description>RSS item {index}</description>
          <pubDate>Sat, 20 Jun 2026 08:{index % 60:02d}:00 GMT</pubDate>
        </item>
        """
        for index in range(80)
    )
    xml = f"<?xml version=\"1.0\"?><rss version=\"2.0\"><channel>{items}</channel></rss>"

    signals = parse_rss_feed(xml, source_id="source-rss")

    assert len(signals) == 50
    assert signals[0].title == "AI item 0"
    assert signals[-1].title == "AI item 49"


def test_parse_github_search_repositories_extracts_repo_signals():
    payload = {
        "items": [
            {
                "id": 123,
                "full_name": "openai/evals",
                "html_url": "https://github.com/openai/evals",
                "description": "Evals is a framework for evaluating LLMs.",
                "stargazers_count": 16500,
                "forks_count": 2500,
                "open_issues_count": 300,
                "updated_at": "2026-06-20T08:30:00Z",
                "topics": ["evals", "llm"],
            }
        ]
    }

    signals = parse_github_search_repositories(payload, source_id="source-github-search")

    assert signals[0].id == "signal-github-repo-123"
    assert signals[0].kind == "repo"
    assert signals[0].title == "openai/evals"
    assert signals[0].url == "https://github.com/openai/evals"
    assert signals[0].heat == 100
    assert signals[0].entities == {"repos": ["openai/evals"]}


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


def test_image2_provider_allows_per_request_size(tmp_path: Path):
    png = b"\x89PNG\r\n\x1a\nfake"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        assert body["tools"][0]["size"] == "1504x640"
        return httpx.Response(
            200,
            json={
                "id": "resp-cover",
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(png).decode("ascii"),
                    }
                ],
            },
        )

    provider = Image2Provider(
        base_url="https://image2.example.com/v1",
        api_key="test-key",
        model="relay-image-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    provider.generate("draw cover", tmp_path / "cover.png", size="1504x640")


def test_image2_provider_from_env_uses_image_generation_timeout_by_default(monkeypatch):
    monkeypatch.setenv("IMAGE2_BASE_URL", "https://image2.example.com/v1")
    monkeypatch.setenv("IMAGE2_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE2_RESPONSES_MODEL", "relay-image-model")

    provider = Image2Provider.from_env()

    assert provider is not None
    assert provider.client.timeout.read == 240


def test_image2_provider_from_env_allows_timeout_override(monkeypatch):
    monkeypatch.setenv("IMAGE2_BASE_URL", "https://image2.example.com/v1")
    monkeypatch.setenv("IMAGE2_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE2_RESPONSES_MODEL", "relay-image-model")
    monkeypatch.setenv("IMAGE2_TIMEOUT_SECONDS", "180")

    provider = Image2Provider.from_env()

    assert provider is not None
    assert provider.client.timeout.read == 180


def test_image2_provider_retries_timeout_once_before_success(tmp_path: Path):
    png = b"\x89PNG\r\n\x1a\nretried"
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow image generation", request=request)
        return httpx.Response(
            200,
            json={
                "id": "resp-after-retry",
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(png).decode("ascii"),
                        "revised_prompt": "retried prompt",
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
        max_retries=1,
    )

    result = provider.generate("draw mechanism", tmp_path / "mechanism.png")

    assert attempts == 2
    assert result.provider_request_id == "resp-after-retry"
    assert result.path.read_bytes() == png


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


def test_generate_image_asset_fails_when_image2_is_not_configured(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("IMAGE2_BASE_URL", raising=False)
    monkeypatch.delenv("IMAGE2_API_KEY", raising=False)
    monkeypatch.delenv("IMAGE2_RESPONSES_MODEL", raising=False)

    try:
        generate_image_asset(tmp_path / "cover.png", "draw cover", rgb=(20, 140, 190), storage_root=tmp_path)
    except RuntimeError as error:
        assert "Image2 provider is not configured" in str(error)
    else:
        raise AssertionError("missing image2 config should fail instead of creating a placeholder")

    assert not (tmp_path / "cover.png").exists()


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


def test_daily_pipeline_uses_only_strict_live_sources_without_sample_fallback(tmp_path: Path):
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
        url = str(request.url)
        if "arxiv" in url:
            return httpx.Response(200, text=arxiv_xml)
        if "api.github.com" in url:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 456,
                            "full_name": "example/live-ai-repo",
                            "html_url": "https://github.com/example/live-ai-repo",
                            "description": "Live GitHub integration proof.",
                            "stargazers_count": 1200,
                            "forks_count": 120,
                            "open_issues_count": 20,
                            "updated_at": "2026-06-20T08:35:00Z",
                            "topics": ["ai"],
                        }
                    ]
                },
            )
        return httpx.Response(200, text=rss_xml)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=JsonStore(tmp_path), live_sources=True, http_client=client)

    run = pipeline.run_daily(date="2026-06-20")

    assert any(signal.title == "Fresh Live Paper for Radar" for signal in run.signals)
    assert any(signal.title == "Fresh RSS AI item" for signal in run.signals)
    assert any(signal.title == "example/live-ai-repo" for signal in run.signals)
    assert any(paper.arxiv_id == "2606.29999" for paper in run.papers)
    assert any(topic.title == "Fresh Live Paper for Radar" for topic in run.topics)
    assert any(topic.title == "Fresh RSS AI item" for topic in run.topics)
    assert not any(signal.id == "signal-agent-lab-paper" for signal in run.signals)
    assert not any(paper.id == "paper-agent-lab" for paper in run.papers)


def test_strict_live_daily_run_builds_five_to_ten_topics_and_prioritizes_papers(tmp_path: Path):
    entries = "\n".join(
        f"""
      <entry>
        <id>http://arxiv.org/abs/2606.30{index:03d}v1</id>
        <updated>2026-06-20T08:2{index}:00Z</updated>
        <published>2026-06-20T08:2{index}:00Z</published>
        <title>Live Agent Evaluation Paper {index}</title>
        <summary>Paper {index} studies agent evaluation, reproducible baselines, and LLM experiment design.</summary>
        <author><name>Live Author {index}</name></author>
        <category term="cs.AI" />
        <link title="pdf" href="https://arxiv.org/pdf/2606.30{index:03d}" />
      </entry>
        """
        for index in range(6)
    )
    arxiv_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>
    """
    rss_items = "\n".join(
        f"""
      <item>
        <guid>rss-{index}</guid>
        <title>Agent tooling news {index}</title>
        <link>https://example.com/rss-{index}</link>
        <description>News {index} covers agent tooling and evaluation workflows.</description>
        <pubDate>Sat, 20 Jun 2026 08:{index:02d}:00 GMT</pubDate>
      </item>
        """
        for index in range(4)
    )
    rss_xml = f"<?xml version=\"1.0\"?><rss version=\"2.0\"><channel>{rss_items}</channel></rss>"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "arxiv" in url:
            return httpx.Response(200, text=arxiv_xml)
        if "api.github.com" in url:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 999,
                            "full_name": "example/agent-eval-toolkit",
                            "html_url": "https://github.com/example/agent-eval-toolkit",
                            "description": "Agent evaluation toolkit with reproducible baselines.",
                            "stargazers_count": 25000,
                            "forks_count": 2000,
                            "open_issues_count": 50,
                            "updated_at": "2026-06-20T08:35:00Z",
                            "topics": ["agents", "evals"],
                        }
                    ]
                },
            )
        return httpx.Response(200, text=rss_xml)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=JsonStore(tmp_path), live_sources=True, http_client=client)

    run = pipeline.run_daily(date="2026-06-20")

    assert 5 <= len(run.topics) <= 10
    assert run.selected_topic.article_type == "long_paper"
    assert run.selected_topic.title.startswith("Live Agent Evaluation Paper")
    assert any(topic.article_type == "short_hotspot" and "agent-eval-toolkit" in topic.title for topic in run.topics)


def test_strict_live_daily_run_fails_when_any_enabled_source_fails_without_persisting_run(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "arxiv" in str(request.url):
            return httpx.Response(503, text="arxiv unavailable")
        return httpx.Response(200, text="<rss version='2.0'><channel></channel></rss>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = JsonStore(tmp_path)
    pipeline = DailyPipeline(store=store, live_sources=True, http_client=client)

    try:
        pipeline.run_daily(date="2026-06-20")
    except RuntimeError as error:
        assert "Live source refresh failed" in str(error)
        assert "source-arxiv-cs-ai" in str(error)
    else:
        raise AssertionError("strict live daily run should fail when an enabled source fails")

    assert store.get_run("2026-06-20") is None
    arxiv_source = next(source for source in store.list_sources() if source.id == "source-arxiv-cs-ai")
    assert arxiv_source.status == "failed"
    assert "503" in (arxiv_source.last_error or "")


def test_github_source_uses_optional_token_header(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-test-token")
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"items": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=JsonStore(tmp_path), http_client=client)
    source = next(source for source in seed_sources("2026-06-20") if source.type == "github")

    papers, signals = pipeline._fetch_one_source(source)

    assert papers == []
    assert signals == []
    assert captured_headers["authorization"] == "Bearer ghp-test-token"


def test_live_source_requests_disable_conditional_cache_for_rss(tmp_path: Path):
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers["cache-control"] = request.headers.get("cache-control")
        captured_headers["pragma"] = request.headers.get("pragma")
        return httpx.Response(
            200,
            text="""<?xml version="1.0"?><rss version="2.0"><channel>
            <item><guid>fresh</guid><title>Fresh RSS</title><link>https://example.com/fresh</link><description>Fresh body</description></item>
            </channel></rss>""",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=JsonStore(tmp_path), http_client=client)
    source = next(source for source in seed_sources("2026-06-20") if source.type == "rss")

    _papers, signals = pipeline._fetch_one_source(source)

    assert signals[0].title == "Fresh RSS"
    assert captured_headers["cache-control"] == "no-cache"
    assert captured_headers["pragma"] == "no-cache"


def test_seed_sources_uses_real_defaults_and_allows_url_overrides(monkeypatch):
    monkeypatch.setenv("AI_RADAR_ARXIV_URL", "https://example.com/arxiv")
    monkeypatch.setenv("AI_RADAR_NEWS_RSS_URL", "https://example.com/news.xml")
    monkeypatch.setenv("AI_RADAR_GITHUB_SEARCH_URL", "https://example.com/github-search")
    monkeypatch.setenv("AI_RADAR_OFFICIAL_BLOGS_RSS_URL", "https://example.com/official.xml")

    sources = {source.id: source for source in seed_sources("2026-06-20")}

    assert sources["source-arxiv-cs-ai"].url == "https://example.com/arxiv"
    assert sources["source-ai-news-radar"].url == "https://example.com/news.xml"
    assert sources["source-github-trending"].url == "https://example.com/github-search"
    assert sources["source-official-blogs"].url == "https://example.com/official.xml"

    monkeypatch.delenv("AI_RADAR_ARXIV_URL")
    monkeypatch.delenv("AI_RADAR_NEWS_RSS_URL")
    monkeypatch.delenv("AI_RADAR_GITHUB_SEARCH_URL")
    monkeypatch.delenv("AI_RADAR_OFFICIAL_BLOGS_RSS_URL")
    default_sources = {source.id: source for source in seed_sources("2026-06-20")}

    assert default_sources["source-ai-news-radar"].url != "https://example.com/ai-news-radar.xml"
    assert default_sources["source-ai-news-radar"].url.startswith("https://")
    assert "max_results=30" in default_sources["source-arxiv-cs-ai"].url
    assert "api.github.com/search/repositories" in default_sources["source-github-trending"].url


def test_check_sources_returns_health_summary_without_creating_daily_run(tmp_path: Path):
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

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "arxiv" in url:
            return httpx.Response(200, text=arxiv_xml)
        if "api.github.com" in url:
            return httpx.Response(200, json={"items": []})
        return httpx.Response(503, text="rss down")

    store = JsonStore(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    pipeline = DailyPipeline(store=store, http_client=client)

    summary = pipeline.check_sources("2026-06-20")

    assert summary["ok"] is False
    assert summary["date"] == "2026-06-20"
    assert summary["total_sources"] == 4
    assert summary["healthy_sources"] == 2
    assert summary["failed_sources"] == 2
    assert summary["fetched_papers"] == 1
    assert any(item["status"] == "failed" and "503" in item["last_error"] for item in summary["sources"])
    assert store.get_run("2026-06-20") is None


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
