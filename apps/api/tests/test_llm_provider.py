import httpx

from ai_radar.llm_provider import ResponsesLLMProvider
from ai_radar.pipeline import DailyPipeline
from ai_radar.storage import JsonStore


PUBLISH_READY_SECONDARY_SECTIONS = (
    "## 次文章 1：AI 热点\n\n"
    "### 今天这几条消息，我建议你不要当新闻看\n\n"
    "今天这几条消息，我建议你不要当新闻看。\n\n"
    "更准确的读法是，把它们当成 AI 论文选题的风向标。\n\n"
    "最值得放在前面的，是测试热点。它能转成实验设计、工具复现和评测问题。\n\n"
    "来源，https://example.com/hotspot\n\n"
    "所以这栏真正想提醒的不是今天 AI 圈又发生了什么。\n\n"
    "而是这些消息背后，哪些部分已经可以变成一个学生能读、能复现、能写进论文的问题。\n\n"
    "## 次文章 2：arXiv 高热度文章速报\n\n"
    "### 今天这组论文，我建议先按选题价值来读\n\n"
    "今天这组论文，我建议先按选题价值来读。\n\n"
    "也就是说，先别急着问它是不是今天刚发，也别只看标题有没有大词。\n\n"
    "先看它能不能帮你把一个 AI 论文方向拆清楚。\n\n"
    "第一篇是 Test Paper，arXiv:2606.00001。它展示了一个可复现的测试方法。\n\n"
    "这篇更适合本科高年级和硕士同学读，重点看 baseline 和复现入口。\n\n"
    "链接，https://arxiv.org/pdf/2606.00001\n\n"
    "读者真正需要的，是知道哪篇值得先读，为什么值得读，以及它有没有机会继续展开成长文或课程论文方向。\n\n"
)


def llm_article(main_body: str) -> str:
    return (
        "# 今日 AI 论文与热点文章包\n\n"
        f"## 主文章：长论文解读\n\n{main_body}\n\n"
        f"{PUBLISH_READY_SECONDARY_SECTIONS}"
        "## 来源清单\n\n- source"
    )


def test_responses_llm_provider_posts_compatible_request_and_reads_output_text():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode("utf-8")
        assert str(request.url) == "https://relay.example.com/v1/responses"
        assert request.headers["authorization"] == "Bearer test-key"
        assert '"model":"relay-model"' in payload
        assert '"instructions":"Write like a careful editor."' in payload
        assert '"input":"Draft evidence pack"' in payload
        return httpx.Response(200, json={"id": "resp-1", "output_text": "LLM article body"})

    provider = ResponsesLLMProvider(
        base_url="https://relay.example.com/v1",
        api_key="test-key",
        model="relay-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.complete("Write like a careful editor.", "Draft evidence pack")

    assert result.text == "LLM article body"
    assert result.response_id == "resp-1"


def test_responses_llm_provider_from_env_uses_interactive_timeout(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://relay.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_RESPONSES_MODEL", "relay-model")

    provider = ResponsesLLMProvider.from_env()

    assert provider is not None
    assert provider.client.timeout.read == 8


def test_responses_llm_provider_from_env_allows_timeout_override(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://relay.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_RESPONSES_MODEL", "relay-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "90")

    provider = ResponsesLLMProvider.from_env()

    assert provider is not None
    assert provider.client.timeout.read == 90


def test_pipeline_uses_injected_llm_for_article_generation(tmp_path):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        def complete(self, instructions, input_text):
            self.calls.append((instructions, input_text))
            return type(
                "Result",
                (),
                    {
                        "text": llm_article("LLM 正文"),
                        "response_id": "fake-1",
                    },
                )()

    llm = FakeLLM()
    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")

    article = (tmp_path / draft.markdown_path).read_text(encoding="utf-8")
    assert "LLM 正文" in article
    assert llm.calls
    assert "证据包" in llm.calls[0][1]


def test_pipeline_uses_injected_llm_for_style_rerun(tmp_path):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        def complete(self, instructions, input_text):
            self.calls.append((instructions, input_text))
            if len(self.calls) == 1:
                return type(
                    "Result",
                    (),
                    {
                        "text": llm_article("正文"),
                        "response_id": "draft",
                    },
                )()
            return type(
                "Result",
                (),
                {
                    "text": llm_article("更像真人的表达"),
                    "response_id": "style",
                },
            )()

    llm = FakeLLM()
    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=llm)
    pipeline.run_daily("2026-06-20")
    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")

    pipeline.regenerate_draft(draft.id, "style", "make it human")

    article = (tmp_path / draft.markdown_path).read_text(encoding="utf-8")
    assert "更像真人的表达" in article
    assert len(llm.calls) == 2
    assert "改写" in llm.calls[1][0]


def test_pipeline_rejects_style_rerun_that_drops_three_module_structure(tmp_path):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        def complete(self, instructions, input_text):
            self.calls.append((instructions, input_text))
            if len(self.calls) == 1:
                return type(
                    "Result",
                    (),
                    {
                        "text": llm_article("初稿"),
                        "response_id": "draft",
                    },
                )()
            return type("Result", (), {"text": "# 旧结构\n\n丢失模块\n\n## 来源清单\n\n- source", "response_id": "style"})()

    pipeline = DailyPipeline(JsonStore(tmp_path), llm_provider=FakeLLM())
    pipeline.run_daily("2026-06-20")
    draft = pipeline.draft_topic("topic-long-context-rag", date="2026-06-20")

    pipeline.regenerate_draft(draft.id, "style", "make it human")

    article = (tmp_path / draft.markdown_path).read_text(encoding="utf-8")
    assert "主文章：长论文解读" in article
    assert "次文章 1：AI 热点" in article
    assert "次文章 2：arXiv 高热度文章速报" in article
