import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { generateTopicDraft, refreshDraftModule, refreshToday, refreshTopicPackModule, rerunDraft, saveDraftContent } from "./api";
import type { DraftDetail, ProvidersSettings, RadarToday, RefreshStatus, Source, Topic, TopicPackVersion } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    generateTopicDraft: vi.fn(),
    refreshDraftModule: vi.fn(),
    refreshToday: vi.fn(),
    refreshTopicPackModule: vi.fn(),
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
    conversion: { value: 92, reason: "可展开解读" }
  },
  business_hook: "适合从研究问题、方法贡献和实验可信度展开解读。",
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
    generation_error: "",
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
    "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n适合从研究问题、方法贡献和实验可信度三个层面重点阅读。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。",
  html: "<article class=\"wechat-draft\"><h1>Agent Laboratory</h1></article>",
  sources: "# 来源清单\n\n1. Agent Laboratory",
  review_checklist: "# 审核清单\n\n- [ ] 标题是否准确，不夸大"
};

const providerSettings: ProvidersSettings = {
  llm: {
    provider: "relay",
    base_url: "https://relay.example.com/v1",
    model: "relay-text-model",
    configured: true,
    api_key_masked: "sk-...cret",
    size: "1536x1024",
    quality: "high",
    output_format: "png"
  },
  image2: {
    provider: "relay",
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

const failedSources: Source[] = [
  {
    id: "source-arxiv-cs-ai",
    name: "arXiv cs.AI / cs.LG",
    type: "arxiv",
    url: "https://export.arxiv.org/api/query?search_query=cat:cs.AI",
    enabled: true,
    fetch_interval_minutes: 1440,
    last_success_at: null,
    last_error: "503 Service Unavailable",
    status: "failed",
    created_at: "2026-06-20T07:30:00Z"
  },
  {
    id: "source-github-trending",
    name: "GitHub AI Repository Search",
    type: "github",
    url: "https://api.github.com/search/repositories?q=topic:artificial-intelligence",
    enabled: true,
    fetch_interval_minutes: 1440,
    last_success_at: "2026-06-20T07:30:00Z",
    last_error: null,
    status: "healthy",
    created_at: "2026-06-20T07:30:00Z"
  }
];

const topicPack: TopicPackVersion = {
  id: "topic-pack-2026-06-20-v01",
  date: "2026-06-20",
  version: 1,
  trigger: "scheduled",
  refreshed_module: "all",
  status: "ready",
  llm_prompt_summary: "scheduled",
  llm_response_id: "resp-1",
  previous_version_id: null,
  created_at: "2026-06-20T11:00:00Z",
  long_articles: [
    {
      id: "pack-item-long-1",
      module: "long_articles",
      title: "Agent Laboratory 会不会改变 AI 论文实验设计？",
      summary: "论文解读候选一",
      angle: "从实验规划切入",
      source_urls: ["https://arxiv.org/abs/2501.04227"],
      arxiv_id: "2501.04227",
      topic_id: "topic-agent-lab",
      rank: 1,
      status: "candidate",
      llm_response_id: "resp-1",
      dedupe_key: "agent-lab",
      angle_hash: "hash-long-1",
      score_detail: {
        total_score: { value: 87, reason: "综合得分高" },
        influence_score: { value: 25, reason: "高影响力来源" },
        method_substance: { value: 18, reason: "方法完整" },
        experiment_strength: { value: 12, reason: "实验可信" },
        selection_reasons: ["总分进入前 5", "命中高影响力机构"],
        recommended_narrative: {
          type: "evaluation_review",
          label: "评测复盘型",
          reason: "标题和摘要命中 benchmark、evaluation、SWE-bench，核心价值是重新定义评测口径。",
          alternatives: ["application_translation"]
        }
      }
    },
    {
      id: "pack-item-long-2",
      module: "long_articles",
      title: "长上下文模型来了，RAG 为什么还没有过时？",
      summary: "论文解读候选二",
      angle: "从路由实验切入",
      source_urls: ["https://arxiv.org/abs/2407.16833"],
      arxiv_id: "2407.16833",
      topic_id: "topic-long-context-rag",
      rank: 2,
      status: "candidate",
      llm_response_id: "resp-1",
      dedupe_key: "rag",
      angle_hash: "hash-long-2"
    },
    ...Array.from({ length: 3 }, (_, index) => ({
      id: `pack-item-long-${index + 3}`,
      module: "long_articles" as const,
      title: `论文解读候选 ${index + 3}`,
      summary: `论文候选概述 ${index + 3}`,
      angle: `论文候选角度 ${index + 3}`,
      source_urls: [`https://arxiv.org/abs/2606.0000${index + 3}`],
      arxiv_id: `2606.0000${index + 3}`,
      topic_id: `topic-long-${index + 3}`,
      rank: index + 3,
      status: "candidate" as const,
      llm_response_id: "resp-1",
      dedupe_key: `long-${index + 3}`,
      angle_hash: `hash-long-${index + 3}`
    }))
  ],
  ai_hotspots: Array.from({ length: 5 }, (_, index) => ({
    id: `pack-item-hotspot-${index + 1}`,
    module: "ai_hotspots" as const,
    title: `热点话题 ${index + 1}`,
    summary: `热点概述 ${index + 1}`,
    angle: `热点判断 ${index + 1}`,
    source_urls: [`https://example.com/hotspot-${index + 1}`],
    arxiv_id: null,
    topic_id: null,
    rank: index + 1,
    status: "candidate" as const,
    llm_response_id: "resp-1",
    dedupe_key: `hotspot-${index + 1}`,
    angle_hash: `hash-hotspot-${index + 1}`
  })),
  arxiv_papers: Array.from({ length: 5 }, (_, index) => ({
    id: `pack-item-arxiv-${index + 1}`,
    module: "arxiv_papers" as const,
    title: `arXiv 论文 ${index + 1}`,
    summary: `论文概述 ${index + 1}`,
    angle: `论文判断 ${index + 1}`,
    source_urls: [`https://arxiv.org/abs/2606.0000${index + 1}`],
    arxiv_id: `2606.0000${index + 1}`,
    topic_id: null,
    rank: index + 1,
    status: "candidate" as const,
    llm_response_id: "resp-1",
    dedupe_key: `arxiv-${index + 1}`,
    angle_hash: `hash-arxiv-${index + 1}`
  }))
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
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
  expect(screen.getByRole("button", { name: "刷新全部选题" })).toBeInTheDocument();
});

it("explains tomorrow refresh time after today's refresh has already run", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={{
        ...refreshStatus,
        today_refreshed: true,
        last_refresh_at: "2026-06-20T00:02:35",
        next_refresh_at: "2026-06-21T11:00:00",
        seconds_until_next_refresh: 87825
      }}
    />
  );

  expect(screen.getByText("今日已刷新，下次自动刷新为明天 11:00（北京时间）")).toBeInTheDocument();
  expect(screen.getByText("还有 24:23:45")).toBeInTheDocument();
});

it("manually refreshes today's topic pool and reloads the package", async () => {
  let resolveRefreshTopicPack: (pack: TopicPackVersion) => void = () => {};
  const refreshedTopic = {
    ...topic,
    id: "topic-long-context-rag",
    slug: "long-context-rag",
    title: "长上下文模型来了，RAG 为什么还没有过时？"
  };
  const refreshedRadar = {
    ...radar,
    recommended_topic: refreshedTopic,
    draft: {
      ...radar.draft,
      id: "draft-2026-06-20-topic-long-context-rag",
      topic_id: refreshedTopic.id,
      title: refreshedTopic.title
    }
  };
  vi.mocked(refreshTopicPackModule).mockReturnValue(
    new Promise((resolve) => {
      resolveRefreshTopicPack = resolve;
    })
  );
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/radar/today")) {
        return Promise.resolve({ ok: true, json: async () => refreshedRadar });
      }
      if (path.includes("/api/refresh/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...refreshStatus,
            today_refreshed: true,
            last_refresh_at: "2026-06-20T14:30:00",
            seconds_until_next_refresh: 73800
          })
        });
      }
      if (path.includes("/api/topics")) {
        return Promise.resolve({ ok: true, json: async () => [refreshedTopic] });
      }
      if (path.includes("/api/drafts/")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...draftDetail,
            draft: refreshedRadar.draft,
            topic: refreshedTopic,
            markdown:
              "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n手动刷新后的新选题正文。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
          })
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
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

  fireEvent.click(screen.getByRole("button", { name: "刷新全部选题" }));

  expect(await screen.findByRole("button", { name: "刷新中" })).toBeDisabled();

  resolveRefreshTopicPack({ ...topicPack, version: 2, trigger: "manual", refreshed_module: "all" });

  expect(await screen.findByText("已刷新全部选题 v2")).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { name: refreshedTopic.title }).length).toBeGreaterThan(0);
  expect(within(screen.getByTestId("article-module-main")).getByText("手动刷新后的新选题正文。")).toBeInTheDocument();
  expect(refreshTopicPackModule).toHaveBeenCalledWith("all", radar.date, "manual topic module refresh");
  expect(refreshToday).not.toHaveBeenCalled();
});

it("renders topic pool scores and business hook", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialTopicPack={topicPack}
    />
  );

  expect(screen.getByRole("heading", { name: "论文深度解读" })).toBeInTheDocument();
  expect(screen.getByText("论文解读候选一")).toBeInTheDocument();
  expect(screen.getByText("总分 87 | 影响力 25 | 方法 18 | 实验 12")).toBeInTheDocument();
  expect(screen.getByText("入选原因：总分进入前 5；命中高影响力机构")).toBeInTheDocument();
  expect(screen.getByText("推荐写法：评测复盘型")).toBeInTheDocument();
  expect(screen.getByText("标题和摘要命中 benchmark、evaluation、SWE-bench，核心价值是重新定义评测口径。")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "https://arxiv.org/abs/2501.04227" })).toBeInTheDocument();
  expect(screen.queryByTestId("topic-topic-agent-lab")).not.toBeInTheDocument();
});

it("hides score summaries for legacy long articles and non-long modules", () => {
  const legacyTopicPack: TopicPackVersion = {
    ...topicPack,
    long_articles: topicPack.long_articles.map(({ score_detail: _scoreDetail, ...item }) => item),
    ai_hotspots: topicPack.ai_hotspots.map((item, index) =>
      index === 0
        ? {
            ...item,
            score_detail: {
              total_score: { value: 66, reason: "热点测试分" },
              influence_score: { value: 11, reason: "热点影响力" },
              method_substance: { value: 10, reason: "热点方法" },
              experiment_strength: { value: 9, reason: "热点实验" },
              selection_reasons: ["非长文不展示"]
            }
          }
        : item
    )
  };

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialTopicPack={legacyTopicPack}
    />
  );

  expect(screen.queryByText("总分 87 | 影响力 25 | 方法 18 | 实验 12")).not.toBeInTheDocument();
  expect(screen.queryByText("总分 66 | 影响力 11 | 方法 10 | 实验 9")).not.toBeInTheDocument();
  expect(screen.queryByText("入选原因：非长文不展示")).not.toBeInTheDocument();
});

it("shows an empty topic pack state instead of default topics before LLM generation", () => {
  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
    />
  );

  expect(screen.getByText("今日选题还没有由 LLM 生成")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新全部选题" })).toBeInTheDocument();
  expect(screen.queryByTestId("topic-topic-agent-lab")).not.toBeInTheDocument();
});

it("loads the app with an empty topic pack state when the current LLM pack is missing", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/refresh/due")) {
        return Promise.resolve({ ok: true, json: async () => refreshStatus });
      }
      if (path.includes("/api/radar/today")) {
        return Promise.resolve({ ok: true, json: async () => radar });
      }
      if (path.includes("/api/drafts?date=")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (path.includes("/api/topics")) {
        return Promise.resolve({ ok: true, json: async () => [topic] });
      }
      if (path.includes("/api/topic-packs/current")) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Topic pack not generated yet" })
        });
      }
      if (path.includes("/api/drafts?date=")) {
        return Promise.resolve({ ok: true, json: async () => [radar.draft] });
      }
      if (path.includes("/api/drafts/")) {
        return Promise.resolve({ ok: true, json: async () => draftDetail });
      }
      if (path.includes("/api/refresh/status")) {
        return Promise.resolve({ ok: true, json: async () => refreshStatus });
      }
      if (path.includes("/api/settings/providers")) {
        return Promise.resolve({ ok: true, json: async () => providerSettings });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    })
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "今日雷达" })).toBeInTheDocument();
  expect(screen.getByText("今日选题还没有由 LLM 生成")).toBeInTheDocument();
  expect(screen.queryByTestId("topic-topic-agent-lab")).not.toBeInTheDocument();
});

it("reloads the latest updated daily draft instead of the default daily draft", async () => {
  window.localStorage.setItem("ai-radar:last-draft-id", radar.draft.id);
  const recentDraftDetail: DraftDetail = {
    ...draftDetail,
    draft: { ...radar.draft, id: "draft-recent-long-article", version: 4 },
    markdown:
      "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n刷新后仍然加载最近生成的长文。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
  };
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.includes("/api/refresh/due")) {
      return Promise.resolve({ ok: true, json: async () => refreshStatus });
    }
    if (path.includes("/api/radar/today")) {
      return Promise.resolve({ ok: true, json: async () => radar });
    }
    if (path.includes("/api/topics")) {
      return Promise.resolve({ ok: true, json: async () => [topic] });
    }
    if (path.includes("/api/topic-packs/current")) {
      return Promise.resolve({ ok: true, json: async () => topicPack });
    }
    if (path.includes("/api/drafts?date=")) {
      return Promise.resolve({
        ok: true,
        json: async () => [
          { ...radar.draft, updated_at: "2026-06-20T08:40:00Z" },
          { ...recentDraftDetail.draft, updated_at: "2026-06-20T09:00:00Z" }
        ]
      });
    }
    if (path.includes("/api/drafts/draft-recent-long-article")) {
      return Promise.resolve({ ok: true, json: async () => recentDraftDetail });
    }
    if (path.includes("/api/drafts/")) {
      return Promise.resolve({ ok: true, json: async () => draftDetail });
    }
    if (path.includes("/api/settings/providers")) {
      return Promise.resolve({ ok: true, json: async () => providerSettings });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  const mainPanel = await screen.findByTestId("article-module-main");
  expect(await within(mainPanel).findByText("刷新后仍然加载最近生成的长文。")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/api/drafts/draft-recent-long-article");
  expect(window.localStorage.getItem("ai-radar:last-draft-id")).toBe("draft-recent-long-article");
});

it("falls back to the daily draft when the remembered draft is gone", async () => {
  window.localStorage.setItem("ai-radar:last-draft-id", "draft-missing");
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path.includes("/api/refresh/due")) {
      return Promise.resolve({ ok: true, json: async () => refreshStatus });
    }
    if (path.includes("/api/radar/today")) {
      return Promise.resolve({ ok: true, json: async () => radar });
    }
    if (path.includes("/api/drafts?date=")) {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    if (path.includes("/api/topics")) {
      return Promise.resolve({ ok: true, json: async () => [topic] });
    }
    if (path.includes("/api/topic-packs/current")) {
      return Promise.resolve({ ok: true, json: async () => topicPack });
    }
    if (path.includes("/api/drafts/draft-missing")) {
      return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: "Not found" }) });
    }
    if (path.includes(`/api/drafts/${radar.draft.id}`)) {
      return Promise.resolve({ ok: true, json: async () => draftDetail });
    }
    if (path.includes("/api/settings/providers")) {
      return Promise.resolve({ ok: true, json: async () => providerSettings });
    }
    if (path.includes("/api/sources")) {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal(
    "fetch",
    fetchMock
  );

  render(<App />);

  await screen.findByRole("heading", { name: "今日雷达" });
  expect(fetchMock).toHaveBeenCalledWith("/api/drafts/draft-missing");
  expect(fetchMock).toHaveBeenCalledWith(`/api/drafts/${radar.draft.id}`);
  expect(window.localStorage.getItem("ai-radar:last-draft-id")).toBe(radar.draft.id);
});

it("shows strict live source failures with source-level diagnostics during startup", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/refresh/due")) {
        return Promise.resolve({
          ok: false,
          status: 502,
          json: async () => ({
            detail: "Live source refresh failed: source-arxiv-cs-ai: 503 Service Unavailable"
          })
        });
      }
      if (path.includes("/api/sources")) {
        return Promise.resolve({ ok: true, json: async () => failedSources });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    })
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "实时信源刷新失败" })).toBeInTheDocument();
  expect(screen.getByText(/Live source refresh failed/)).toBeInTheDocument();
  expect(screen.getByText("arXiv cs.AI / cs.LG")).toBeInTheDocument();
  expect(screen.getByText("503 Service Unavailable")).toBeInTheDocument();
  expect(screen.getByText("GitHub AI Repository Search")).toBeInTheDocument();
  expect(screen.getByText(/上一轮成功数据没有被覆盖/)).toBeInTheDocument();
});

it("shows topic pack modules and refreshes only the selected topic module", async () => {
  const refreshedPack: TopicPackVersion = {
    ...topicPack,
    id: "topic-pack-2026-06-20-v02",
    version: 2,
    trigger: "manual",
    refreshed_module: "ai_hotspots",
    previous_version_id: topicPack.id,
    ai_hotspots: topicPack.ai_hotspots.map((item, index) => ({
      ...item,
      id: `pack-item-refreshed-hotspot-${index + 1}`,
      title: `刷新后的热点 ${index + 1}`,
      angle: `LLM 新角度 ${index + 1}`
    }))
  };
  vi.mocked(refreshTopicPackModule).mockResolvedValue(refreshedPack);

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialRefreshStatus={refreshStatus}
      initialTopicPack={topicPack}
    />
  );

  expect(screen.getByRole("heading", { name: "论文深度解读" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "AI 热点话题" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "高热 arXiv 论文" })).toBeInTheDocument();
  expect(screen.getByText("热点话题 1")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "刷新 AI 热点话题" }));

  expect(await screen.findByText("已刷新 AI 热点话题 v2")).toBeInTheDocument();
  expect(screen.getByText("刷新后的热点 1")).toBeInTheDocument();
  expect(screen.getAllByText("Agent Laboratory 会不会改变 AI 论文实验设计？").length).toBeGreaterThan(0);
  expect(refreshTopicPackModule).toHaveBeenCalledWith("ai_hotspots", radar.date, "manual topic module refresh");
  expect(refreshToday).not.toHaveBeenCalled();
  expect(refreshDraftModule).not.toHaveBeenCalled();
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
  expect(screen.getByRole("button", { name: "重跑封面素材" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重跑正文配图" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新 HTML" })).toBeInTheDocument();
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
      "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n人工编辑后的判断句。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。",
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
        "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n人工编辑后的判断句。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
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

  expect(within(mainPanel).getByText("适合从研究问题、方法贡献和实验可信度三个层面重点阅读。")).toBeInTheDocument();
  expect(screen.queryByTestId("article-module-hotspots")).not.toBeInTheDocument();
  expect(screen.queryByTestId("article-module-arxiv")).not.toBeInTheDocument();
  expect(screen.queryByText("# 今日 AI 论文与热点文章包")).not.toBeInTheDocument();
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
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n### Agent Laboratory 会不会改变 AI 论文实验设计？\n\n适合从研究问题、方法贡献和实验可信度三个层面重点阅读。\n\n## 次文章 1：AI 热点\n\n### 今天这几条消息，我建议你不要当新闻看\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n### 今天这组论文，我建议先按学术价值来读\n\n论文速读清单。"
      }}
    />
  );

  fireEvent.click(screen.getByRole("tab", { name: /次文章 1/ }));

  const preview = screen.getByTestId("wechat-live-preview");
  expect(within(preview).getByRole("heading", { name: "今天这几条消息，我建议你不要当新闻看" })).toBeInTheDocument();
  expect(within(preview).queryByRole("heading", { name: "AI 热点" })).not.toBeInTheDocument();
  expect(preview).toHaveTextContent("模型和工具动态。");
  expect(preview).not.toHaveTextContent("适合从研究问题、方法贡献和实验可信度三个层面重点阅读。");
  expect(preview).not.toHaveTextContent("论文速读清单。");
});

it("does not expose default topic cards before LLM topic generation", () => {
  render(<App initialRadar={radar} initialTopics={[topic]} initialDraftDetail={draftDetail} />);

  expect(screen.queryByTestId("topic-topic-agent-lab")).not.toBeInTheDocument();
  expect(screen.getByText("今日选题还没有由 LLM 生成")).toBeInTheDocument();
});

it("selecting a long-article topic pack item loads a pending workshop draft without generating the long article", async () => {
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
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n### 待生成\n\n当前已选择：Agent Laboratory 会不会改变 AI 论文实验设计？\n\n点击“生成长文”后，系统会围绕这篇论文生成中文深度解读，并另行准备发布素材。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
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
      initialTopicPack={topicPack}
    />
  );

  fireEvent.click(screen.getAllByRole("button", { name: "选择选题" })[0]);

  expect(await screen.findByRole("button", { name: "选择中" })).toBeDisabled();

  resolveGenerate({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "draft"
  });

  const mainPanel = screen.getByTestId("article-module-main");
  await within(mainPanel).findByText(/待生成/);
  expect(mainPanel).toHaveTextContent("点击“生成长文”后");
  expect(within(mainPanel).queryByText("新选题生成后的完整正文。")).not.toBeInTheDocument();
  expect(generateTopicDraft).toHaveBeenCalledWith(topic.id, radar.date);
  expect(refreshDraftModule).not.toHaveBeenCalled();
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
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n适合从研究问题和证据边界展开阅读。\n\n## 次文章 1：AI 热点\n\n刷新后的热点。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
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
  expect(refreshDraftModule).toHaveBeenCalledWith(radar.draft.id, "hotspots", undefined);
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
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n只生成主文章模块。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
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
  expect(refreshDraftModule).toHaveBeenCalledWith(radar.draft.id, "main", "trend_slice");
  expect(generateTopicDraft).not.toHaveBeenCalled();
});

it("sends selected narrative type when generating the main article", async () => {
  vi.mocked(refreshDraftModule).mockResolvedValue({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "refresh:main"
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/api/drafts/")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...draftDetail,
            draft: { ...radar.draft, version: 2, last_rerun_stage: "refresh:main" }
          })
        });
      }
      if (path.includes("/api/radar/today")) {
        return Promise.resolve({ ok: true, json: async () => radar });
      }
      if (path.includes("/api/topics")) {
        return Promise.resolve({ ok: true, json: async () => [topic] });
      }
      if (path.includes("/api/topic-packs/current")) {
        return Promise.resolve({ ok: true, json: async () => topicPack });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    })
  );

  render(
    <App
      initialRadar={radar}
      initialTopics={[topic]}
      initialDraftDetail={draftDetail}
      initialProviderSettings={providerSettings}
      initialTopicPack={topicPack}
    />
  );

  fireEvent.change(screen.getByLabelText("长文写法"), { target: { value: "application_translation" } });
  fireEvent.click(screen.getByRole("button", { name: "生成长文" }));

  expect(await screen.findByText("已生成长文 v2")).toBeInTheDocument();
  expect(refreshDraftModule).toHaveBeenCalledWith(radar.draft.id, "main", "application_translation");
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
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n只生成主文章模块。\n\n## 次文章 1：AI 热点\n\n模型和工具动态。\n\n## 次文章 2：arXiv 高热度文章速报\n\n论文速读清单。"
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
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n重跑标题后的可见稿件。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
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

it("reruns the outline into the visible main article module", async () => {
  vi.mocked(rerunDraft).mockResolvedValue({
    ...radar.draft,
    version: 2,
    last_rerun_stage: "outline"
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...draftDetail,
        draft: { ...radar.draft, version: 2, last_rerun_stage: "outline" },
        markdown:
          "# 今日 AI 论文与热点文章包\n\n## 主文章：长论文解读\n\n### 长论文解读\n\n### 编辑导语\n\n这段导语现在出现在主文章可见区域。\n\n正文继续。\n\n## 次文章 1：AI 热点\n\n热点\n\n## 次文章 2：arXiv 高热度文章速报\n\n速报"
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

  fireEvent.click(screen.getByRole("button", { name: "重跑导语" }));

  const mainPanel = await screen.findByTestId("article-module-main");
  expect(mainPanel).toHaveTextContent("编辑导语");
  expect(mainPanel).toHaveTextContent("这段导语现在出现在主文章可见区域。");
  expect(await screen.findByText("已重跑导语 v2")).toBeInTheDocument();
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
        insert_after: "# 今日 AI 论文与热点文章包",
        width: 1536,
        height: 1024,
        provider: "image2",
        provider_request_id: "resp-cover",
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
              insert_after: "# 今日 AI 论文与热点文章包",
              width: 1536,
              height: 1024,
              provider: "image2",
              provider_request_id: "resp-cover",
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

  fireEvent.click(screen.getByRole("button", { name: "重跑封面素材" }));

  const assetsPanel = await screen.findByTestId("draft-assets-panel");
  expect(within(assetsPanel).getByText("封面")).toBeInTheDocument();
  expect(within(assetsPanel).getByText("建议插入位置：# 今日 AI 论文与热点文章包")).toBeInTheDocument();
  expect(within(assetsPanel).getByText("drafts/2026-06-20/agent-lab/cover.png")).toBeInTheDocument();
  expect(within(assetsPanel).getByText("image2")).toBeInTheDocument();
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
  expect(screen.getByLabelText("LLM 服务商")).toHaveValue("relay");
  expect(screen.getByRole("option", { name: "第三方中转" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "DeepSeek" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Doubao" })).toBeInTheDocument();
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
