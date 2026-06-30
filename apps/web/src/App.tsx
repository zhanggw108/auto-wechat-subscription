import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Article,
  Broadcast,
  CheckCircle,
  Clock,
  ClipboardText,
  GearSix,
  Image,
  FileHtml,
  FloppyDisk,
  NotePencil,
  Pulse,
  Repeat,
  Sparkle,
  Stack,
  TrendUp
} from "@phosphor-icons/react";

import {
  DraftDetail,
  ProvidersSettings,
  ProvidersSettingsUpdate,
  RadarToday,
  RefreshModule,
  RefreshStatus,
  Topic,
  TopicPackItem,
  TopicPackModule,
  TopicPackVersion,
  fetchCurrentTopicPack,
  fetchDraftDetail,
  fetchProviderSettings,
  fetchRadar,
  fetchRefreshStatus,
  fetchSources,
  fetchTopics,
  generateTopicDraft,
  refreshDraftModule,
  refreshIfDue,
  refreshTopicPackModule,
  rerunDraft,
  saveDraftContent,
  saveProviderSettings
} from "./api";
import "./styles.css";

type AppProps = {
  initialRadar?: RadarToday;
  initialTopics?: Topic[];
  initialDraftDetail?: DraftDetail;
  initialProviderSettings?: ProvidersSettings;
  initialRefreshStatus?: RefreshStatus;
  initialTopicPack?: TopicPackVersion;
};

type SettingsForm = {
  llm: {
    provider: string;
    base_url: string;
    api_key: string;
    model: string;
  };
  image2: {
    base_url: string;
    api_key: string;
    model: string;
    size: string;
    quality: string;
    output_format: string;
  };
};

const llmProviderDefaults: Record<string, string> = {
  relay: "",
  deepseek: "https://api.deepseek.com",
  doubao: "https://ark.cn-beijing.volces.com/api/v3"
};

const rerunActions = [
  { label: "重跑标题", stage: "title", icon: NotePencil },
  { label: "重跑导语", stage: "outline", icon: Repeat },
  { label: "重跑整篇", stage: "article", icon: Article },
  { label: "重跑风格", stage: "style", icon: Repeat },
  { label: "重跑封面素材", stage: "cover", icon: Image },
  { label: "重跑机制图素材", stage: "mechanism", icon: Image },
  { label: "刷新 HTML", stage: "wechat", icon: FileHtml }
];

const moduleRefreshActions: Array<{ label: string; module: RefreshModule; title: string }> = [
  { label: "生成长文", module: "main", title: "长论文解读" },
  { label: "生成 AI 热点", module: "hotspots", title: "次文章 1" },
  { label: "生成 arXiv 速报", module: "arxiv", title: "次文章 2" }
];

const moduleFeedbackLabels: Record<RefreshModule, string> = {
  main: "长文",
  hotspots: "AI 热点",
  arxiv: "arXiv 速报"
};

const topicPackModuleLabels: Record<TopicPackModule, string> = {
  long_articles: "论文解读候选",
  ai_hotspots: "AI 热点话题",
  arxiv_papers: "高热 arXiv 论文",
  all: "全部选题"
};

const rerunFeedbackLabels: Record<string, string> = {
  title: "标题",
  outline: "导语",
  article: "整篇",
  style: "风格",
  cover: "封面",
  mechanism: "机制图",
  wechat: "HTML"
};

const emptyProviderSettings: ProvidersSettings = {
  llm: {
    provider: "relay",
    base_url: "",
    model: "",
    configured: false,
    api_key_masked: "",
    size: "1536x1024",
    quality: "high",
    output_format: "png"
  },
  image2: {
    provider: "relay",
    base_url: "",
    model: "",
    configured: false,
    api_key_masked: "",
    size: "1536x1024",
    quality: "high",
    output_format: "png"
  }
};

function settingsToForm(settings: ProvidersSettings): SettingsForm {
  return {
    llm: {
      provider: settings.llm.provider || "relay",
      base_url: settings.llm.base_url,
      api_key: "",
      model: settings.llm.model
    },
    image2: {
      base_url: settings.image2.base_url,
      api_key: "",
      model: settings.image2.model,
      size: settings.image2.size || "1536x1024",
      quality: settings.image2.quality || "high",
      output_format: settings.image2.output_format || "png"
    }
  };
}

function App({ initialRadar, initialTopics, initialDraftDetail, initialProviderSettings, initialRefreshStatus, initialTopicPack }: AppProps) {
  const [radar, setRadar] = useState<RadarToday | null>(initialRadar ?? null);
  const [topics, setTopics] = useState<Topic[]>(initialTopics ?? []);
  const [topicPack, setTopicPack] = useState<TopicPackVersion | null>(initialTopicPack ?? null);
  const [draftDetail, setDraftDetail] = useState<DraftDetail | null>(initialDraftDetail ?? null);
  const [providerSettings, setProviderSettings] = useState<ProvidersSettings>(initialProviderSettings ?? emptyProviderSettings);
  const [refreshStatus, setRefreshStatus] = useState<RefreshStatus | null>(initialRefreshStatus ?? null);
  const [sourceDiagnostics, setSourceDiagnostics] = useState<RadarToday["source_health"]>(initialRadar?.source_health ?? []);
  const [countdownSeconds, setCountdownSeconds] = useState(initialRefreshStatus?.seconds_until_next_refresh ?? 0);
  const [settingsForm, setSettingsForm] = useState<SettingsForm>(() =>
    settingsToForm(initialProviderSettings ?? emptyProviderSettings)
  );
  const [status, setStatus] = useState(initialRadar ? "ready" : "loading");
  const [settingsStatus, setSettingsStatus] = useState(initialProviderSettings ? "ready" : "loading");
  const [settingsMessage, setSettingsMessage] = useState("");
  const [refreshingModule, setRefreshingModule] = useState<RefreshModule | "">("");
  const [rerunningStage, setRerunningStage] = useState("");
  const [generatingTopicId, setGeneratingTopicId] = useState("");
  const [dueRefreshing, setDueRefreshing] = useState(false);
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [refreshingTopicModule, setRefreshingTopicModule] = useState<TopicPackModule | "">("");
  const [refreshMessage, setRefreshMessage] = useState("");
  const [editorMode, setEditorMode] = useState<"review" | "edit">("review");
  const [editorMarkdown, setEditorMarkdown] = useState(initialDraftDetail?.markdown ?? "");
  const [editorStatus, setEditorStatus] = useState("");
  const [savingDraft, setSavingDraft] = useState(false);
  const [activeModuleId, setActiveModuleId] = useState("article-module-main");

  useEffect(() => {
    if (initialRadar) {
      return;
    }

    let cancelled = false;
    async function load() {
      try {
        setStatus("loading");
        const nextRefresh = await refreshIfDue();
        if (!cancelled) {
          setRefreshStatus(nextRefresh);
          setCountdownSeconds(nextRefresh.seconds_until_next_refresh);
        }
        const nextRadar = await fetchRadar();
        const nextTopics = await fetchTopics();
        const nextTopicPack = await fetchCurrentTopicPack(nextRadar.date);
        const nextDetail = await fetchDraftDetail(nextRadar.draft.id);
        if (!cancelled) {
          setRadar(nextRadar);
          setTopics(nextTopics);
          setTopicPack(nextTopicPack);
          setDraftDetail(nextDetail);
          setStatus("ready");
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Load failed";
          setStatus(message);
          try {
            const sources = await fetchSources();
            if (!cancelled) {
              setSourceDiagnostics(sources);
            }
          } catch {
            if (!cancelled) {
              setSourceDiagnostics([]);
            }
          }
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [initialRadar]);

  useEffect(() => {
    if (initialRefreshStatus) {
      return;
    }

    let cancelled = false;
    async function loadRefreshStatus() {
      try {
        const nextRefresh = initialRadar ? await fetchRefreshStatus() : null;
        if (nextRefresh && !cancelled) {
          setRefreshStatus(nextRefresh);
          setCountdownSeconds(nextRefresh.seconds_until_next_refresh);
        }
      } catch {
        if (!cancelled) {
          setRefreshStatus(null);
        }
      }
    }
    loadRefreshStatus();
    return () => {
      cancelled = true;
    };
  }, [initialRadar, initialRefreshStatus]);

  useEffect(() => {
    if (!refreshStatus) {
      return;
    }
    const timer = window.setInterval(() => {
      setCountdownSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [refreshStatus?.next_refresh_at]);

  useEffect(() => {
    if (!refreshStatus || countdownSeconds > 0 || dueRefreshing || initialRefreshStatus) {
      return;
    }
    void handleDueRefresh();
  }, [countdownSeconds, dueRefreshing, initialRefreshStatus, refreshStatus]);

  useEffect(() => {
    if (initialProviderSettings) {
      return;
    }

    let cancelled = false;
    async function loadSettings() {
      try {
        setSettingsStatus("loading");
        const nextSettings = await fetchProviderSettings();
        if (!cancelled) {
          setProviderSettings(nextSettings);
          setSettingsForm(settingsToForm(nextSettings));
          setSettingsStatus("ready");
        }
      } catch (error) {
        if (!cancelled) {
          setSettingsStatus(error instanceof Error ? error.message : "Settings load failed");
        }
      }
    }
    loadSettings();
    return () => {
      cancelled = true;
    };
  }, [initialProviderSettings]);

  useEffect(() => {
    setEditorMarkdown(draftDetail?.markdown ?? "");
  }, [draftDetail?.draft.id, draftDetail?.draft.version, draftDetail?.markdown]);

  useEffect(() => {
    setEditorStatus("");
  }, [draftDetail?.draft.id]);

  const editorDirty = Boolean(draftDetail && editorMarkdown !== draftDetail.markdown);
  const articleModules = useMemo(() => parseArticleModules(editorMarkdown), [editorMarkdown]);
  const activeArticleModule = articleModules.find((item) => item.id === activeModuleId) ?? articleModules[0];
  const previewHtml = useMemo(() => markdownToPreviewHtml(articleModuleToPreviewMarkdown(activeArticleModule)), [activeArticleModule]);

  async function handleRerun(stage: string) {
    if (!draftDetail) {
      return;
    }
    setRerunningStage(stage);
    setEditorStatus(`正在重跑${rerunFeedbackLabels[stage] ?? stage}...`);
    try {
      const nextDraft = await rerunDraft(draftDetail.draft.id, stage);
      const nextDetail = await fetchDraftDetail(nextDraft.id);
      setDraftDetail(nextDetail);
      setEditorMarkdown(nextDetail.markdown);
      setEditorStatus(`已重跑${rerunFeedbackLabels[stage] ?? stage} v${nextDetail.draft.version}`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? `重跑失败：${error.message}` : "重跑失败");
    } finally {
      setRerunningStage("");
    }
  }

  function scrollToWorkshop() {
    window.history.replaceState(null, "", "#workshop");
    document.getElementById("workshop")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleSelectTopicDraft(topicId: string) {
    if (!radar) {
      return;
    }
    scrollToWorkshop();
    setGeneratingTopicId(topicId);
    setEditorStatus("正在选择选题...");
    try {
      const nextDraft = await generateTopicDraft(topicId, radar.date);
      const nextDetail = await fetchDraftDetail(nextDraft.id);
      setDraftDetail(nextDetail);
      setEditorMarkdown(nextDetail.markdown);
      setActiveModuleId("article-module-main");
      setEditorStatus(`已选择选题 v${nextDetail.draft.version}，点击“生成长文”继续`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? `选择选题失败：${error.message}` : "选择选题失败");
    } finally {
      setGeneratingTopicId("");
    }
  }

  async function handleDueRefresh() {
    setDueRefreshing(true);
    try {
      const nextRefresh = await refreshIfDue();
      const nextRadar = await fetchRadar();
      const nextTopics = await fetchTopics();
      const nextTopicPack = await fetchCurrentTopicPack(nextRadar.date);
      const nextDetail = await fetchDraftDetail(nextRadar.draft.id);
      setRefreshStatus(nextRefresh);
      setCountdownSeconds(nextRefresh.seconds_until_next_refresh);
      setRadar(nextRadar);
      setSourceDiagnostics(nextRadar.source_health);
      setTopics(nextTopics);
      setTopicPack(nextTopicPack);
      setDraftDetail(nextDetail);
      setEditorMarkdown(nextDetail.markdown);
      setRefreshMessage("已完成自动刷新");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Scheduled refresh failed";
      setStatus(message);
      try {
        setSourceDiagnostics(await fetchSources());
      } catch {
        setSourceDiagnostics(radar?.source_health ?? []);
      }
    } finally {
      setDueRefreshing(false);
    }
  }

  async function handleManualRefreshToday() {
    setManualRefreshing(true);
    setRefreshMessage("正在刷新全部选题...");
    try {
      const nextTopicPack = await refreshTopicPackModule("all", radar?.date, "manual topic module refresh");
      const nextRefresh = await fetchRefreshStatus();
      const nextRadar = await fetchRadar();
      const nextTopics = await fetchTopics();
      const nextDetail = await fetchDraftDetail(nextRadar.draft.id);
      setRefreshStatus(nextRefresh);
      setCountdownSeconds(nextRefresh.seconds_until_next_refresh);
      setRadar(nextRadar);
      setTopics(nextTopics);
      setTopicPack(nextTopicPack);
      setDraftDetail(nextDetail);
      setEditorMarkdown(nextDetail.markdown);
      setActiveModuleId("article-module-main");
      setRefreshMessage(`已刷新全部选题 v${nextTopicPack.version}`);
      setEditorStatus(`已载入新选题：${nextRadar.recommended_topic.title}`);
    } catch (error) {
      setRefreshMessage(error instanceof Error ? `刷新失败：${error.message}` : "刷新失败");
    } finally {
      setManualRefreshing(false);
    }
  }

  async function handleRefreshTopicModule(module: TopicPackModule) {
    if (!radar) {
      return;
    }
    setRefreshingTopicModule(module);
    setRefreshMessage(`正在刷新${topicPackModuleLabels[module]}...`);
    try {
      const nextPack = await refreshTopicPackModule(module, radar.date, "manual topic module refresh");
      setTopicPack(nextPack);
      try {
        const nextTopics = await fetchTopics();
        setTopics(nextTopics);
      } catch {
        // The versioned topic pack is the source of truth for module refreshes.
      }
      setRefreshMessage(`已刷新 ${topicPackModuleLabels[module]} v${nextPack.version}`);
    } catch (error) {
      setRefreshMessage(error instanceof Error ? `刷新失败：${error.message}` : "刷新失败");
    } finally {
      setRefreshingTopicModule("");
    }
  }

  async function handleRefreshModule(module: RefreshModule) {
    if (!draftDetail) {
      return;
    }
    setActiveModuleId(moduleToArticleModuleId(module));
    setRefreshingModule(module);
    setEditorStatus(`正在生成${moduleFeedbackLabels[module]}...`);
    try {
      const nextDraft = await refreshDraftModule(draftDetail.draft.id, module);
      const nextDetail = await fetchDraftDetail(nextDraft.id);
      setDraftDetail(nextDetail);
      setEditorMarkdown(nextDetail.markdown);
      setEditorStatus(`已生成${moduleFeedbackLabels[module]} v${nextDetail.draft.version}`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? `生成失败：${error.message}` : "生成失败");
    } finally {
      setRefreshingModule("");
    }
  }

  async function handleSaveDraftContent() {
    if (!draftDetail) {
      return;
    }
    setSavingDraft(true);
    setEditorStatus("");
    try {
      const nextDetail = await saveDraftContent(draftDetail.draft.id, editorMarkdown);
      setDraftDetail(nextDetail);
      setEditorMarkdown(nextDetail.markdown);
      setEditorStatus(`已保存 v${nextDetail.draft.version}`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSavingDraft(false);
    }
  }

  async function handleCopy(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setEditorStatus(`已复制 ${label}`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? error.message : "复制失败");
    }
  }

  function updateSettingsForm(provider: "llm", field: keyof SettingsForm["llm"], value: string): void;
  function updateSettingsForm(provider: "image2", field: keyof SettingsForm["image2"], value: string): void;
  function updateSettingsForm(provider: "llm" | "image2", field: string, value: string) {
    setSettingsForm((current) => ({
      ...current,
      [provider]: {
        ...current[provider],
        [field]: value,
        ...(provider === "llm" && field === "provider" && value !== "relay" ? { base_url: llmProviderDefaults[value] } : {})
      }
    }));
  }

  async function handleSaveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSettingsMessage("");
    setSettingsStatus("saving");
    const payload: ProvidersSettingsUpdate = {
      llm: settingsForm.llm,
      image2: settingsForm.image2
    };
    try {
      const nextSettings = await saveProviderSettings(payload);
      setProviderSettings(nextSettings);
      setSettingsForm(settingsToForm(nextSettings));
      setSettingsStatus("ready");
      setSettingsMessage("配置已保存");
    } catch (error) {
      setSettingsStatus(error instanceof Error ? error.message : "Settings save failed");
    }
  }

  if (!radar || !draftDetail) {
    const failedSources = sourceDiagnostics.filter((source) => source.status === "failed" || source.status === "degraded");
    const diagnosticSources = [...sourceDiagnostics].sort((left, right) => {
      const weight = { failed: 0, degraded: 1, healthy: 2 } as const;
      return weight[left.status] - weight[right.status];
    });
    const isSourceFailure = status !== "loading" && (status.includes("Live source refresh failed") || failedSources.length > 0);
    return (
      <main className="app-shell app-shell--loading">
        <section className={`loading-panel ${isSourceFailure ? "loading-panel--error" : ""}`}>
          <Pulse size={30} weight="duotone" />
          <h1>{isSourceFailure ? "实时信源刷新失败" : "AI 内容雷达启动中"}</h1>
            <p>{status === "loading" ? "正在生成今日 AI 论文雷达、热点和稿件包。" : status}</p>
          {isSourceFailure ? (
            <div className="source-diagnostics">
              <p>上一轮成功数据没有被覆盖。请先修复失败信源，再重新刷新今日雷达。</p>
              <div className="source-diagnostics__list">
                {diagnosticSources.map((source) => (
                  <a className="source-diagnostic-row" href={source.url} key={source.id}>
                    <span className={`health-dot health-dot--${source.status}`} />
                    <strong>{source.name}</strong>
                    <small>{source.last_error || source.status}</small>
                  </a>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="side-rail" aria-label="Workspace navigation">
        <div className="brand-mark">
          <span className="brand-mark__dot" />
          <div>
            <strong>AI Paper Radar</strong>
            <small>{radar.date}</small>
          </div>
        </div>

        <nav className="nav-stack">
          <a href="#radar">
            <Broadcast size={18} /> 今日雷达
          </a>
          <a href="#topics">
            <Stack size={18} /> 选题池
          </a>
          <a href="#workshop">
            <Article size={18} /> 文章工坊
          </a>
          <a href="#admin">
            <GearSix size={18} /> 管理端
          </a>
        </nav>

        <section className="refresh-card" aria-label="Daily refresh countdown">
          <div>
            <Clock size={18} />
            <strong>下次刷新 {refreshStatus?.refresh_time ?? "11:00"}</strong>
          </div>
          <span>{refreshStatus?.today_refreshed ? "今日已刷新" : "今日待刷新"}</span>
          <p>还有 {formatDuration(countdownSeconds)}</p>
          <button disabled={manualRefreshing || dueRefreshing} onClick={handleManualRefreshToday} type="button">
            <Repeat size={16} /> {manualRefreshing ? "刷新中" : "刷新全部选题"}
          </button>
          {refreshMessage ? <small aria-live="polite">{refreshMessage}</small> : null}
        </section>

        <section className="source-strip">
          <h2>来源健康</h2>
          {radar.source_health.map((source) => (
            <a className="source-chip" href={source.url} key={source.id}>
              <span className={`health-dot health-dot--${source.status}`} />
              <span>{source.name}</span>
            </a>
          ))}
        </section>
      </aside>

      <div className="workspace">
        <section className="radar-section" id="radar">
          <div>
            <p className="section-kicker">Daily signal sweep</p>
            <h1>今日雷达</h1>
            <p className="section-copy">
              系统已把近期 AI 论文、行业新闻、开源项目和产品发布压缩成三组内容：论文深度解读、AI 热点和高热 arXiv 论文。优先看学术价值高、证据风险低、能讲清楚研究问题的内容。
            </p>
          </div>

          <div className="metric-grid" aria-label="Daily radar metrics">
            <Metric label="总信号" value={String(radar.signal_count)} icon={<Pulse size={20} />} />
            <Metric label="AI 强相关信号" value={`${radar.ai_relevant_count} 条`} icon={<Sparkle size={20} />} />
            <Metric label="候选选题" value={`${radar.topic_count} 个`} icon={<TrendUp size={20} />} />
          </div>

          <div className="radar-band">
            <div className="radar-orbit" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div>
              <p className="section-kicker">Recommended front page</p>
              <h2>{radar.recommended_topic.title}</h2>
              <p>{radar.recommended_topic.recommendation}</p>
            </div>
          </div>

          <div className="hotspot-list">
            {radar.top_hotspots.map((signal) => (
              <a href={signal.url} className="hotspot-row" key={signal.id}>
                <span>{signal.kind}</span>
                <strong>{signal.title}</strong>
                <em>{signal.heat}</em>
              </a>
            ))}
          </div>
        </section>

        <section className="topic-section" id="topics">
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Topic scoring</p>
              <h2>选题池</h2>
            </div>
            <span className="quiet-badge">
              {topicPack ? `topic pack v${topicPack.version}` : "5-10 candidates"}
            </span>
          </div>

          {topicPack ? (
            <div className="topic-pack-grid" aria-label="今日选题包">
              <TopicPackModulePanel
                title="论文深度解读"
                description="5 篇近期重要 AI 论文，标明来源后作为长文章主线"
                items={topicPack.long_articles}
                refreshing={refreshingTopicModule === "long_articles"}
                onRefresh={() => handleRefreshTopicModule("long_articles")}
                refreshLabel="刷新论文解读候选"
                onGenerate={(item) => {
                  if (item.topic_id) {
                    void handleSelectTopicDraft(item.topic_id);
                  }
                }}
                generatingTopicId={generatingTopicId}
              />
              <TopicPackModulePanel
                title="AI 热点话题"
                description="5-10 个当天 AI 圈热点，保持简要概述"
                items={topicPack.ai_hotspots}
                refreshing={refreshingTopicModule === "ai_hotspots"}
                onRefresh={() => handleRefreshTopicModule("ai_hotspots")}
                refreshLabel="刷新 AI 热点话题"
              />
              <TopicPackModulePanel
                title="高热 arXiv 论文"
                description="5-10 篇高热论文速报，可标记后续展开"
                items={topicPack.arxiv_papers}
                refreshing={refreshingTopicModule === "arxiv_papers"}
                onRefresh={() => handleRefreshTopicModule("arxiv_papers")}
                refreshLabel="刷新 arXiv 论文"
              />
            </div>
          ) : null}

          {!topicPack ? (
            <section className="topic-pack-empty">
              <h3>今日选题还没有由 LLM 生成</h3>
              <p>点击刷新后会调用你配置的 LLM 生成论文深度解读、AI 热点和 arXiv 三个模块。未生成前不再展示内置默认选题。</p>
            </section>
          ) : null}
        </section>

        <section className="workshop-section" id="workshop">
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Review package</p>
              <h2>文章工坊</h2>
              <p className="workshop-context">当前稿件：{draftDetail.topic.title}</p>
            </div>
            <div className="action-row">
              <button onClick={() => setEditorMode((current) => (current === "edit" ? "review" : "edit"))} type="button">
                <NotePencil size={17} /> {editorMode === "edit" ? "阅读模式" : "编辑 Markdown"}
              </button>
              <button disabled={!editorDirty || savingDraft} onClick={handleSaveDraftContent} type="button">
                <FloppyDisk size={17} /> {savingDraft ? "保存中" : "保存并生成 HTML"}
              </button>
              <button onClick={() => handleCopy(editorMarkdown, "Markdown")} type="button">
                <ClipboardText size={17} /> 复制 Markdown
              </button>
              <button onClick={() => handleCopy(draftDetail.html, "HTML")} type="button">
                <ClipboardText size={17} /> 复制 HTML
              </button>
              {rerunActions.map((action) => {
                const Icon = action.icon;
                return (
                  <button key={action.stage} onClick={() => handleRerun(action.stage)}>
                    <Icon size={17} /> {rerunningStage === action.stage ? "重跑中" : action.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="editor-state-row" aria-live="polite">
            <span>{editorDirty ? "未保存修改" : editorStatus || `已保存 v${draftDetail.draft.version}`}</span>
            <small>参考 doocs/md 的成熟编辑器体验：编辑、预览、复制和正式 HTML 生成分离，发布仍由人工确认。</small>
          </div>

          <div className="workshop-grid">
            <article className="editor-pane">
              <div className="module-strip" aria-label="公众号文章模块">
                {articleModules.map((item) => (
                  <button
                    aria-selected={item.id === activeArticleModule.id}
                    className={`module-pill ${item.id === activeArticleModule.id ? "module-pill--active" : ""}`}
                    key={item.label}
                    onClick={() => setActiveModuleId(item.id)}
                    role="tab"
                    type="button"
                  >
                    <span>{item.label}</span>
                    <strong>{item.title}</strong>
                    <small>{item.summary}</small>
                  </button>
                ))}
              </div>
              <div className="module-refresh-row" aria-label="模块刷新">
                {moduleRefreshActions.map((action) => (
                  <button
                    disabled={refreshingModule === action.module}
                    key={action.module}
                    onClick={() => handleRefreshModule(action.module)}
                    title={action.title}
                    type="button"
                  >
                    <Repeat size={16} /> {refreshingModule === action.module ? "刷新中" : action.label}
                  </button>
                ))}
              </div>
              <div className="pane-title">
                <span>{editorMode === "edit" ? "Markdown Editor" : "Markdown"}</span>
                <small>v{draftDetail.draft.version}</small>
              </div>
              {editorMode === "edit" ? (
                <textarea
                  aria-label="公众号 Markdown 编辑器"
                  className="markdown-editor"
                  onChange={(event) => setEditorMarkdown(event.target.value)}
                  spellCheck={false}
                  value={editorMarkdown}
                />
              ) : (
                <div className="article-module-stack">
                  <section className="article-module-panel" data-testid={activeArticleModule.id} id={activeArticleModule.id}>
                    <div className="article-module-panel__header">
                      <span>{activeArticleModule.label}</span>
                      <h3>{activeArticleModule.title}</h3>
                    </div>
                    <pre>{activeArticleModule.body}</pre>
                  </section>
                </div>
              )}
            </article>

            <aside className="review-pane">
              <section>
                <h3>实时预览</h3>
                <div
                  className="wechat-live-preview"
                  data-testid="wechat-live-preview"
                  dangerouslySetInnerHTML={{ __html: previewHtml }}
                />
              </section>
              <section>
                <h3>WeChat HTML</h3>
                <pre>{draftDetail.html}</pre>
              </section>
              <section>
                <h3>{firstLine(draftDetail.sources)}</h3>
                {restLines(draftDetail.sources).map((line, index) => (
                  <p key={`${line}-${index}`}>{line}</p>
                ))}
              </section>
              <section>
                <h3>{firstLine(draftDetail.review_checklist)}</h3>
                {restLines(draftDetail.review_checklist).map((line, index) => (
                  <p key={`${line}-${index}`}>{line}</p>
                ))}
              </section>
              <section>
                <h3>证据链</h3>
                {draftDetail.evidence_items.map((item) => (
                  <a href={item.source_url} className="evidence-row" key={item.id}>
                    <CheckCircle size={17} />
                    <span>{item.source_title}</span>
                    <em>{item.confidence}</em>
                  </a>
                ))}
              </section>
              <section data-testid="draft-assets-panel">
                <h3>素材</h3>
                {draftDetail.draft.assets.length ? (
                  <div className="asset-list">
                    {draftDetail.draft.assets.map((asset) => (
                      <article className="asset-row" key={asset.id}>
                        <div>
                          <strong>{asset.kind}</strong>
                          <span>{asset.provider}</span>
                        </div>
                        <code>{asset.path}</code>
                        <p>{asset.revised_prompt || asset.prompt}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p>尚未生成封面或机制图素材。</p>
                )}
              </section>
            </aside>
          </div>
        </section>

        <section className="admin-section" id="admin">
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Provider control</p>
              <h2>管理端</h2>
            </div>
            <span className={`quiet-badge ${settingsStatus === "saving" ? "quiet-badge--busy" : ""}`}>
              {settingsStatus === "saving" ? "保存中" : settingsMessage || "本地配置"}
            </span>
          </div>

          <form className="provider-form" onSubmit={handleSaveSettings}>
            <ProviderPanel
              title="LLM Responses"
              description="用于正文生成与风格重跑。Base URL 会拼接 /responses。"
              configured={providerSettings.llm.configured}
              maskedKey={providerSettings.llm.api_key_masked}
            >
              <Field label="LLM 服务商">
                <select
                  aria-label="LLM 服务商"
                  value={settingsForm.llm.provider}
                  onChange={(event) => updateSettingsForm("llm", "provider", event.target.value)}
                >
                  <option value="relay">第三方中转</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="doubao">Doubao</option>
                </select>
              </Field>
              <Field label="LLM Base URL">
                <input
                  aria-label="LLM Base URL"
                  value={settingsForm.llm.base_url}
                  onChange={(event) => updateSettingsForm("llm", "base_url", event.target.value)}
                  placeholder={llmProviderDefaults[settingsForm.llm.provider] || "https://relay.example.com/v1"}
                />
              </Field>
              <Field label="LLM API Key">
                <input
                  aria-label="LLM API Key"
                  value={settingsForm.llm.api_key}
                  onChange={(event) => updateSettingsForm("llm", "api_key", event.target.value)}
                  placeholder="留空则保留现有 key"
                  type="password"
                  autoComplete="new-password"
                />
              </Field>
              <Field label="LLM Model">
                <input
                  aria-label="LLM Model"
                  value={settingsForm.llm.model}
                  onChange={(event) => updateSettingsForm("llm", "model", event.target.value)}
                  placeholder="relay-text-model"
                />
              </Field>
            </ProviderPanel>

            <ProviderPanel
              title="Image Responses"
              description="用于封面和机制图重跑。未配置或调用失败时会直接提示失败。"
              configured={providerSettings.image2.configured}
              maskedKey={providerSettings.image2.api_key_masked}
            >
              <Field label="Image Base URL">
                <input
                  aria-label="Image Base URL"
                  value={settingsForm.image2.base_url}
                  onChange={(event) => updateSettingsForm("image2", "base_url", event.target.value)}
                  placeholder="https://image-relay.example.com/v1"
                />
              </Field>
              <Field label="Image API Key">
                <input
                  aria-label="Image API Key"
                  value={settingsForm.image2.api_key}
                  onChange={(event) => updateSettingsForm("image2", "api_key", event.target.value)}
                  placeholder="留空则保留现有 key"
                  type="password"
                  autoComplete="new-password"
                />
              </Field>
              <Field label="Image Model">
                <input
                  aria-label="Image Model"
                  value={settingsForm.image2.model}
                  onChange={(event) => updateSettingsForm("image2", "model", event.target.value)}
                  placeholder="relay-image-model"
                />
              </Field>
              <Field label="Image Size">
                <input
                  aria-label="Image Size"
                  value={settingsForm.image2.size}
                  onChange={(event) => updateSettingsForm("image2", "size", event.target.value)}
                  placeholder="1536x1024"
                />
              </Field>
              <Field label="Image Quality">
                <select
                  aria-label="Image Quality"
                  value={settingsForm.image2.quality}
                  onChange={(event) => updateSettingsForm("image2", "quality", event.target.value)}
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </Field>
              <Field label="Image Format">
                <select
                  aria-label="Image Format"
                  value={settingsForm.image2.output_format}
                  onChange={(event) => updateSettingsForm("image2", "output_format", event.target.value)}
                >
                  <option value="png">png</option>
                  <option value="jpeg">jpeg</option>
                  <option value="webp">webp</option>
                </select>
              </Field>
            </ProviderPanel>

            <div className="settings-footer">
              {settingsStatus !== "ready" && settingsStatus !== "saving" ? <p role="alert">{settingsStatus}</p> : <span />}
              <button className="primary-action" disabled={settingsStatus === "saving"} type="submit">
                <FloppyDisk size={17} /> 保存配置
              </button>
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return (
    <div className="metric-tile">
      <div>{icon}</div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function topicPackScoreSummary(item: TopicPackItem): { line: string; reasons: string } | null {
  const score = item.score_detail;
  if (!score?.total_score || typeof score.total_score.value !== "number") return null;
  const influence = typeof score.influence_score?.value === "number" ? score.influence_score.value : 0;
  const method = typeof score.method_substance?.value === "number" ? score.method_substance.value : 0;
  const experiment = typeof score.experiment_strength?.value === "number" ? score.experiment_strength.value : 0;
  const reasons = Array.isArray(score.selection_reasons) ? score.selection_reasons.join("；") : "";
  return {
    line: `总分 ${score.total_score.value} | 影响力 ${influence} | 方法 ${method} | 实验 ${experiment}`,
    reasons: reasons ? `入选原因：${reasons}` : ""
  };
}

function TopicPackModulePanel({
  title,
  description,
  items,
  refreshing,
  onRefresh,
  refreshLabel,
  onGenerate,
  generatingTopicId = ""
}: {
  title: string;
  description: string;
  items: TopicPackItem[];
  refreshing: boolean;
  onRefresh: () => void;
  refreshLabel: string;
  onGenerate?: (item: TopicPackItem) => void;
  generatingTopicId?: string;
}) {
  return (
    <section className="topic-pack-panel">
      <div className="topic-pack-panel__header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <button disabled={refreshing} onClick={onRefresh} type="button">
          <Repeat size={16} /> {refreshing ? "刷新中" : refreshLabel}
        </button>
      </div>
      <div className="topic-pack-list">
        {items.map((item) => {
          const scoreSummary = item.module === "long_articles" ? topicPackScoreSummary(item) : null;
          return (
            <article className="topic-pack-item" key={item.id}>
              <span>{String(item.rank).padStart(2, "0")}</span>
              <div>
                <h4>{item.title}</h4>
                <p>{item.summary}</p>
                <small>{item.angle}</small>
                {scoreSummary ? (
                  <div className="topic-pack-item__score">
                    <strong>{scoreSummary.line}</strong>
                    {scoreSummary.reasons ? <span>{scoreSummary.reasons}</span> : null}
                  </div>
                ) : null}
                {item.source_urls.length ? (
                  <div className="topic-pack-item__sources" aria-label={`${item.title} 来源`}>
                    <span>来源</span>
                    {item.source_urls.map((url) => (
                      <a href={url} key={url} rel="noreferrer" target="_blank">
                        {url}
                      </a>
                    ))}
                  </div>
                ) : null}
                {onGenerate && item.topic_id ? (
                  <button
                    className="topic-pack-item__action"
                    disabled={generatingTopicId === item.topic_id}
                    onClick={() => onGenerate(item)}
                    type="button"
                  >
                    {generatingTopicId === item.topic_id ? "选择中" : "选择选题"}
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ProviderPanel({
  title,
  description,
  configured,
  maskedKey,
  children
}: {
  title: string;
  description: string;
  configured: boolean;
  maskedKey: string;
  children: ReactNode;
}) {
  return (
    <section className="provider-panel">
      <div className="provider-panel__header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <div className="provider-state">
          <span className={`state-chip ${configured ? "state-chip--ready" : ""}`}>{configured ? "已配置" : "未配置"}</span>
          {maskedKey ? <code>{maskedKey}</code> : <small>未保存 key</small>}
        </div>
      </div>
      <div className="provider-fields">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function parseArticleModules(markdown: string) {
  const definitions = [
    {
      id: "article-module-main",
      label: "主文章",
      title: "长论文解读",
      marker: "## 主文章：长论文解读",
      anchor: "#article-module-main",
      fallback: "深度拆解论文问题、方法、实验可信度和学术价值。"
    },
    {
      id: "article-module-hotspots",
      label: "次文章 1",
      title: "AI 热点",
      marker: "## 次文章 1：AI 热点",
      anchor: "#article-module-hotspots",
      fallback: "快速判断当天 AI 新闻、产品和开源项目的研究价值。"
    },
    {
      id: "article-module-arxiv",
      label: "次文章 2",
      title: "arXiv 高热度文章速报",
      marker: "## 次文章 2：arXiv 高热度文章速报",
      anchor: "#article-module-arxiv",
      fallback: "筛出值得加入阅读列表或后续展开的高热论文。"
    }
  ];

  return definitions.map((definition) => {
    const start = markdown.indexOf(definition.marker);
    const next = start >= 0 ? markdown.indexOf("\n## ", start + definition.marker.length) : -1;
    const body = start >= 0 ? markdown.slice(start + definition.marker.length, next >= 0 ? next : undefined) : "";
    const summary = body
      .split("\n")
      .map((line) => line.replace(/^#+\s*/, "").trim())
      .find((line) => line && !line.startsWith(">") && !line.startsWith("-"));
    return {
      id: definition.id,
      label: definition.label,
      title: definition.title,
      anchor: definition.anchor,
      body: body.trim() || definition.fallback,
      summary: summary ?? definition.fallback
    };
  });
}

function moduleToArticleModuleId(module: RefreshModule) {
  return {
    main: "article-module-main",
    hotspots: "article-module-hotspots",
    arxiv: "article-module-arxiv"
  }[module];
}

function articleModuleToPreviewMarkdown(module: ReturnType<typeof parseArticleModules>[number]) {
  if (/^#{1,3}\s+/m.test(module.body)) {
    return module.body;
  }
  return `## ${module.title}\n\n${module.body}`.trim();
}

function markdownToPreviewHtml(markdown: string) {
  const blocks = markdown
    .split("\n")
    .map((rawLine) => {
      const line = rawLine.trim();
      if (!line) {
        return "";
      }
      if (line.startsWith("# ")) {
        return `<h1>${escapeHtml(line.slice(2))}</h1>`;
      }
      if (line.startsWith("## ")) {
        return `<h2>${escapeHtml(line.slice(3))}</h2>`;
      }
      if (line.startsWith("### ")) {
        return `<h3>${escapeHtml(line.slice(4))}</h3>`;
      }
      if (line.startsWith("> ")) {
        return `<blockquote>${escapeHtml(line.slice(2))}</blockquote>`;
      }
      if (line.startsWith("- ")) {
        return `<p class="preview-list-item">${escapeHtml(line.slice(2))}</p>`;
      }
      return `<p>${escapeHtml(line)}</p>`;
    })
    .filter(Boolean);
  return blocks.join("");
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function firstLine(value: string) {
  return value.split("\n").find(Boolean) ?? "";
}

function restLines(value: string) {
  return value
    .split("\n")
    .slice(1)
    .map((line) => line.trim())
    .filter(Boolean);
}

function formatDuration(totalSeconds: number) {
  const safeSeconds = Math.max(0, totalSeconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  return [hours, minutes, seconds].map((item) => String(item).padStart(2, "0")).join(":");
}

export default App;
