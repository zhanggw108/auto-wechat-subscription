import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { generateTopicDraft, refreshDraftModule, rerunDraft, saveDraftContent } from "./api";
import type { DraftDetail, ProvidersSettings, RadarToday, RefreshStatus, Topic } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    generateTopicDraft: vi.fn(),
    refreshDraftModule: vi.fn(),
    rerunDraft: vi.fn(),
    saveDraftContent: vi.fn()
  };
});

const topic: Topic = {
  id: "topic-agent-lab",
  slug: "agent-lab",
  cluster_id: "cluster-agent-lab",
  paper_id: "paper-agent-lab",
  title: "Agent Laboratory 会不会改变 AI 论文实验设计？",
  angle: "写一篇头版论文解析",
  article_type: "long_paper",
  status: "drafted",
  score_total: 91,
  score_detail: {
    heat: { value: 95, reason: "多源出现" },
    relevance: { value: 94, reason: "研究问题明确" },
    writeability: { value: 90, reason: "结构完整" },
    conversion: { value: 92, reason: "可转选题" }
  },
  business_hook: "适合引导实验复现和创新点设计。",
  source_count: 4,
  evidence_risk: "low",
  recommendation: "优先写",
  signal_ids: ["signal-agent-lab"],
  created_at: "2026-06-20T07:50:00Z"
};

const radar: RadarToday = {
  date: "2026-06-20",
  signal_count: 8,
  ai_relevant_count: 8,
  topic_count: 7,
  source_health: [
    {
      id: "source-arxiv",
      name: "arXiv cs.AI / cs.LG",
      type: "arxiv",
      url: "https://arxiv.org",
      enabled: true,
      fetch_interval_minutes: 1440,
      last_success_at: "2026-06-20T07:30:00Z",
      last_error: null,
      status: "healthy",
      created_at: "2026-06-20T07:30:00Z"
    }
  ],
  top_hotspots: [
    {
      id: "signal-agent-lab",
      source_id: "source-arxiv",
      kind: "paper",
      title: "Agent Laboratory proposes evidence-first research agents",
      summary: "A new arXiv paper frames LLM agents as research assistants.",
      url: "https://arxiv.org/abs/2606.20101",
      published_at: "2026-06-20T02:20:00Z",
      tags: ["agents"],
      heat: 94,
      entities: {}
    }
  ],
  categories: { paper: 2, news: 2, repo: 2, product: 1, post: 1 },
  recommended_topic: topic,
  draft: {
    id: "draft-2026-06-20-topic-agent-lab",
    topic_id: "topic-agent-lab",
    title: topic.title,
    subtitle: topic.angle,
    status: "review",
    markdown_path: "drafts/article.md",
    html_path: "drafts/article-wechat.html",
    sources_path: "drafts/sources.md",
    checklist_path: "drafts/review-checklist.md",
    evidence_path: "drafts/evidence.json",
    topic_path: "drafts/topic.md",
    version: 1,
    assets: [],
    last_rerun_stage: "",
    created_at: "2026-06-20T08:40:00Z",
    updated_at: "2026-06-20T08:40:00Z"
  }
};

const draftDetail: DraftDetail = {
  draft: radar.draft,
  topic,
  evidence_items: [
    {
      id: "evidence-1",
      topic_id: topic.id,
      source_url: "https://arxiv.org/abs/2606.20101",
      source_title: "Agent Laboratory",
      claim: "研究 agent 支持实验规划",
      snippet: "paper abstract",
      confidence: "high",
      risk_note: "实验指标需人工确认",
      created_at: "2026-06-20T08:05:00Z"
    }
  ],
  markdown:
    "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n适合本科生、硕士研究生重点阅读。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。",
  html: "<article class=\"wechat-draft\"><h1>Agent Laboratory</h1></article>",
  sources: "# 来源清单\n\n1. Agent Laboratory",
  review_checklist: "# 审核清单\n\n- [ ] 标题是否准确，不夸大"
};

const providerSettings: ProvidersSettings = {
  llm: {
    base_url: "https://relay.example.com/v1",
    model: "relay-text-model",
    configured: true,
    api_key_masked: "sk-...cret",
    size: "1536x1024",
    quality: "high",
    output_format: "png"
  },
  image2: {
    base_url: "https://image.example.com/v1",
    model: "relay-image-model",
    configured: true,
    api_key_masked: "sk-...cret",
    size: "1024x1024",
    quality: "medium",
    output_format: "png"
  }
};

const refreshStatus: RefreshStatus = {
  date: "2026-06-20",
  refresh_time: "11:00",
  today_refreshed: false,
  last_refresh_at: null,
  next_refresh_at: "2026-06-20T11:00:00",
  seconds_until_next_refresh: 1800
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  Element.prototype.scrollIntoView = vi.fn();
});

it("renders radar summary, source health, and top hotspot", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  expect(screen.getByRole("heading", { name: "今日雷达" })).toBeInTheDocument();
  expect(screen.getByText("8")).toBeInTheDocument();
  expect(screen.getByText("AI 强相关信号")).toBeInTheDocument();
  expect(screen.getByText("arXiv cs.AI / cs.LG")).toBeInTheDocument();
  expect(screen.getByText("Agent Laboratory proposes evidence-first research agents")).toBeInTheDocument();
});

it("renders the scheduled refresh countdown", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  expect(screen.getByText("下次刷新 11:00")).toBeInTheDocument();
  expect(screen.getByText("还有 00:30:00")).toBeInTheDocument();
});

it("renders topic pool scores and business hook", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
    />
  );

  const card = screen.getByTestId("topic-topic-agent-lab");
  expect(within(card).getByText("Heat")).toBeInTheDocument();
  expect(within(card).getByText("95")).toBeInTheDocument();
  expect(within(card).getByText("Conversion")).toBeInTheDocument();
  expect(within(card).getByText("适合引导实验复现和创新点设计。")).toBeInTheDocument();
  expect(within(card).getByRole("button", { name: "选择选题" })).toBeInTheDocument();
});

it("renders article workshop package with markdown, html, sources, and checklist", () => {
  const { container } = render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  expect(screen.getByRole("heading", { name: "文章工坊" })).toBeInTheDocument();
  expect(screen.getByText(`当前稿件：${topic.title}`)).toBeInTheDocument();
  const mainPanel = screen.getByTestId("article-module-main");
  expect(within(mainPanel).getByText("主文章")).toBeInTheDocument();
  expect(within(mainPanel).getByRole("heading", { name: "长论文解读" })).toBeInTheDocument();
  expect(container.querySelectorAll('[data-testid="article-module-main"] pre')).toHaveLength(1);
  expect(screen.queryByTestId("article-module-hotspots")).not.toBeInTheDocument();
  expect(screen.queryByTestId("article-module-arxiv")).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /次文章 1/ })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /次文章 2/ })).toBeInTheDocument();
  expect(screen.getByText("Markdown")).toBeInTheDocument();
  expect(screen.getByText("WeChat HTML")).toBeInTheDocument();
  expect(screen.getByText("# 来源清单")).toBeInTheDocument();
  expect(screen.getByText("- [ ] 标题是否准确，不夸大")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑标题" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑导语" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑整篇" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑风格" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑封面" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑机制图" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成 HTML" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成长文" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成 AI 热点" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成 arXiv 速报" })).toBeInTheDocument();
});

it("supports mature editor workflow with markdown editing, live preview, save, and copy actions", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  vi.mocked(saveDraftContent).mockResolvedValue({
    ...draftDetail,
    draft: { ...radar.draft, version: 2, last_rerun_stage: "manual-edit" },
    markdown:
      "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n人工编辑后的判断句。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。",
    html: '<article class="wechat-draft"><h2>主文章：长论文解读</h2><p>人工编辑后的判断句。</p></article>'
  });

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "编辑 Markdown" }));
  const editor = screen.getByLabelText("公众号 Markdown 编辑器");
  fireEvent.change(editor, {
    target: {
      value:
        "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n人工编辑后的判断句。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
    }
  });
  expect(screen.getByText("未保存修改")).toBeInTheDocument();
  expect(screen.getByTestId("wechat-live-preview")).toHaveTextContent("人工编辑后的判断句。");

  fireEvent.click(screen.getByRole("button", { name: "保存并生成 HTML" }));

  expect(await screen.findByText("已保存 v2")).toBeInTheDocument();
  expect(saveDraftContent).toHaveBeenCalledWith(
    radar.draft.id,
    expect.stringContaining("人工编辑后的判断句。")
  );

  fireEvent.click(screen.getByRole("button", { name: "复制 Markdown" }));
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining("人工编辑后的判断句。"));
  fireEvent.click(screen.getByRole("button", { name: "复制 HTML" }));
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining("wechat-draft"));
});

it("renders each article module in a separate panel with anchor navigation", () => {
  render(<App initialRadar={radar} initialTopics={[topic]} initialDraftDetail={draftDetail} />);

  expect(screen.getByRole("tab", { name: /主文章/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: /次文章 1/ })).toHaveAttribute("aria-selected", "false");
  expect(screen.getByRole("tab", { name: /次文章 2/ })).toHaveAttribute("aria-selected", "false");

  const mainPanel = screen.getByTestId("article-module-main");

  expect(within(mainPanel).getByText("适合本科生、硕士研究生重点阅读。")).toBeInTheDocument();
  expect(screen.queryByTestId("article-module-hotspots")).not.toBeInTheDocument();
  expect(screen.queryByTestId("article-module-arxiv")).not.toBeInTheDocument();
  expect(screen.queryByText("# 今日公众号文章包")).not.toBeInTheDocument();
});

it("switches the visible article module without showing the full package", () => {
  render(<App initialRadar={radar} initialTopics={[topic]} initialDraftDetail={draftDetail} />);

  fireEvent.click(screen.getByRole("tab", { name: /次文章 1/ }));

  expect(screen.queryByTestId("article-module-main")).not.toBeInTheDocument();
  expect(screen.getByTestId("article-module-hotspots")).toHaveTextContent("模型和工具动态。");
  expect(screen.queryByTestId("article-module-arxiv")).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /次文章 1/ })).toHaveAttribute("aria-selected", "true");

  fireEvent.click(screen.getByRole("tab", { name: /次文章 2/ }));

  expect(screen.queryByTestId("article-module-main")).not.toBeInTheDocument();
  expect(screen.queryByTestId("article-module-hotspots")).not.toBeInTheDocument();
  expect(screen.getByTestId("article-module-arxiv")).toHaveTextContent("论文速读清单。");
  expect(screen.getByRole("tab", { name: /次文章 2/ })).toHaveAttribute("aria-selected", "true");
});

it("updates the live preview to only render the selected article module", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={{
        ...draftDetail,
        markdown:
          "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n### Agent Laboratory 会不会改变 AI 论文实验设计？\n\n适合本科生、硕士研究生重点阅读。\n\n## 次文章 1：AI 热点\n\n### 今天这几条消息，我建议你不要当新闻看\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n### 今天这组论文，我建议先按选题价值来读\n\n论文速读清单。"
      }}
    />
  );

  fireEvent.click(screen.getByRole("tab", { name: /次文章 1/ }));

  const preview = screen.getByTestId("wechat-live-preview");
  expect(within(preview).getByRole("heading", { name: "今天这几条消息，我建议你不要当新闻看" })).toBeInTheDocument();
  expect(within(preview).queryByRole("heading", { name: "AI 热点" })).not.toBeInTheDocument();
  expect(preview).toHaveTextContent("模型和工具动态。");
  expect(preview).not.toHaveTextContent("适合本科生、硕士研究生重点阅读。");
  expect(preview).not.toHaveTextContent("论文速读清单。");
});

it("scrolls from topic card to workshop when selecting a topic", () => {
  render(<App initialRadar={radar} initialTopics={[topic]} initialDraftDetail={draftDetail} />);

  fireEvent.click(screen.getByTestId("topic-topic-agent-lab"));

  expect(window.location.hash).toBe("#workshop");
  expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
});

it("selecting a topic generates and loads the topic draft", async () => {
  let resolveGenerate: (draft: typeof radar.draft) => void = () => {};
  vi.mocked(generateTopicDraft).mockReturnValue(
    new Promise((resolve) => {
      resolveGenerate = resolve;
    })
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: { ...radar.draft, version: 2, last_rerun_stage: "draft" },
        markdown:
          "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n新选题生成后的完整正文。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
      })
    })
  );
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "选择选题" }));

  expect(await screen.findByRole("button", { name: "选择中" })).toBeDisabled();

  resolveGenerate({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "draft"
  });

  expect(await within(screen.getByTestId("article-module-main")).findByText("新选题生成后的完整正文。")).toBeInTheDocument();
  expect(generateTopicDraft).toHaveBeenCalledWith(topic.id, radar.date);
  expect(window.location.hash).toBe("#workshop");
});

it("refreshes an individual article module and reloads draft detail", async () => {
  vi.mocked(refreshDraftModule).mockResolvedValue({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "refresh:hotspots"
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: { ...radar.draft, version: 2, last_rerun_stage: "refresh:hotspots" },
        markdown:
          "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n适合本科生。\n\n## 次文章 1：AI 热点\n\n刷新后的热点。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
      })
    })
  );

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "生成 AI 热点" }));

  expect(await within(screen.getByTestId("article-module-hotspots")).findByText("刷新后的热点。")).toBeInTheDocument();
  expect(refreshDraftModule).toHaveBeenCalledWith(radar.draft.id, "hotspots");
});

it("generates only the selected article module from the workshop action", async () => {
  vi.mocked(refreshDraftModule).mockResolvedValue({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "refresh:main"
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: { ...radar.draft, version: 2, last_rerun_stage: "refresh:main" },
        markdown:
          "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n只生成主文章模块。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
      })
    })
  );

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "生成长文" }));

  expect(await within(screen.getByTestId("article-module-main")).findByText("只生成主文章模块。")).toBeInTheDocument();
  expect(screen.queryByTestId("article-module-hotspots")).not.toBeInTheDocument();
  expect(screen.queryByTestId("article-module-arxiv")).not.toBeInTheDocument();
  expect(refreshDraftModule).toHaveBeenCalledWith(radar.draft.id, "main");
  expect(generateTopicDraft).not.toHaveBeenCalled();
});

it("shows visible progress and success feedback when generating a long article", async () => {
  let resolveRefresh: (draft: typeof radar.draft) => void = () => {};
  vi.mocked(refreshDraftModule).mockReturnValue(
    new Promise((resolve) => {
      resolveRefresh = resolve;
    })
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: { ...radar.draft, version: 2, last_rerun_stage: "refresh:main" },
        markdown:
          "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n只生成主文章模块。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
      })
    })
  );

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "生成长文" }));

  expect(await screen.findByText("正在生成长文...")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新中" })).toBeDisabled();

  resolveRefresh({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "refresh:main"
  });

  expect(await screen.findByText("已生成长文 v2")).toBeInTheDocument();
});

it("reruns a draft stage and reloads visible draft detail", async () => {
  let resolveRerun: (draft: typeof radar.draft) => void = () => {};
  vi.mocked(rerunDraft).mockReturnValue(
    new Promise((resolve) => {
      resolveRerun = resolve;
    })
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: { ...radar.draft, version: 2, last_rerun_stage: "title" },
        markdown:
          "# 今日公众号文章包\n\n## 主文章：长论文解读\n\n重跑标题后的可见稿件。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
      })
    })
  );

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "重跑标题" }));

  expect(await screen.findByText("正在重跑标题...")).toBeInTheDocument();

  resolveRerun({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "title"
  });

  expect(await within(screen.getByTestId("article-module-main")).findByText("重跑标题后的可见稿件。")).toBeInTheDocument();
  expect(await screen.findByText("已重跑标题 v2")).toBeInTheDocument();
  expect(rerunDraft).toHaveBeenCalledWith(radar.draft.id, "title");
});

it("reruns cover and shows the generated visual asset in the workshop", async () => {
  vi.mocked(rerunDraft).mockResolvedValue({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "cover",
    assets: [
      {
        id: "asset-cover",
        draft_id: radar.draft.id,
        kind: "cover",
        prompt: "研究雷达锁定一篇高价值 AI 论文",
        revised_prompt: "revised cover prompt",
        path: "drafts/2026-06-20/agent-lab/cover.png",
        width: 1536,
        height: 1024,
        provider: "image2-placeholder",
        provider_request_id: null,
        created_at: "2026-06-20T08:45:00Z"
      }
    ]
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: {
          ...radar.draft,
          version: 2,
          last_rerun_stage: "cover",
          assets: [
            {
              id: "asset-cover",
              draft_id: radar.draft.id,
              kind: "cover",
              prompt: "研究雷达锁定一篇高价值 AI 论文",
              revised_prompt: "revised cover prompt",
              path: "drafts/2026-06-20/agent-lab/cover.png",
              width: 1536,
              height: 1024,
              provider: "image2-placeholder",
              provider_request_id: null,
              created_at: "2026-06-20T08:45:00Z"
            }
          ]
        }
      })
    })
  );

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "重跑封面" }));

  const assetsPanel = await screen.findByTestId("draft-assets-panel");
  expect(within(assetsPanel).getByText("cover")).toBeInTheDocument();
  expect(within(assetsPanel).getByText("drafts/2026-06-20/agent-lab/cover.png")).toBeInTheDocument();
  expect(within(assetsPanel).getByText("image2-placeholder")).toBeInTheDocument();
  expect(rerunDraft).toHaveBeenCalledWith(radar.draft.id, "cover");
});

it("renders provider admin settings without exposing saved API keys", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
    />
  );

  expect(screen.getByRole("link", { name: /管理端/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "管理端" })).toBeInTheDocument();
  expect(screen.getByLabelText("LLM Base URL")).toHaveValue("https://relay.example.com/v1");
  expect(screen.getByLabelText("LLM API Key")).toHaveValue("");
  expect(screen.getByLabelText("LLM Model")).toHaveValue("relay-text-model");
  expect(screen.getByLabelText("Image Base URL")).toHaveValue("https://image.example.com/v1");
  expect(screen.getByLabelText("Image API Key")).toHaveValue("");
  expect(screen.getByLabelText("Image Model")).toHaveValue("relay-image-model");
  expect(screen.getByLabelText("Image Size")).toHaveValue("1024x1024");
  expect(screen.getByLabelText("Image Quality")).toHaveValue("medium");
  expect(screen.getByLabelText("Image Format")).toHaveValue("png");
  expect(screen.getByRole("button", { name: "保存配置" })).toBeInTheDocument();
  expect(screen.getAllByText("sk-...cret")).toHaveLength(2);
  expect(screen.queryByDisplayValue("sk-...cret")).not.toBeInTheDocument();
});
