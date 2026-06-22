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
  fetchDraftDetail,
  fetchProviderSettings,
  fetchRadar,
  fetchRefreshStatus,
  fetchTopics,
  generateTopicDraft,
  refreshDraftModule,
  refreshIfDue,
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
};

type SettingsForm = {
  llm: {
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

const scoreLabels: Record<string, string> = {
  heat: "Heat",
  relevance: "Relevance",
  writeability: "Writeability",
  conversion: "Conversion"
};

const rerunActions = [
  { label: "重跑标题", stage: "title", icon: NotePencil },
  { label: "重跑导语", stage: "outline", icon: Repeat },
  { label: "重跑整篇", stage: "article", icon: Article },
  { label: "重跑风格", stage: "style", icon: Repeat },
  { label: "重跑封面", stage: "cover", icon: Image },
  { label: "重跑机制图", stage: "mechanism", icon: Image },
  { label: "生成 HTML", stage: "wechat", icon: FileHtml }
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
    base_url: "",
    model: "",
    configured: false,
    api_key_masked: "",
    size: "1536x1024",
    quality: "high",
    output_format: "png"
  },
  image2: {
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

function App({ initialRadar, initialTopics, initialDraftDetail, initialProviderSettings, initialRefreshStatus }: AppProps) {
  const [radar, setRadar] = useState<RadarToday | null>(initialRadar ?? null);
  const [topics, setTopics] = useState<Topic[]>(initialTopics ?? []);
  const [draftDetail, setDraftDetail] = useState<DraftDetail | null>(initialDraftDetail ?? null);
  const [providerSettings, setProviderSettings] = useState<ProvidersSettings>(initialProviderSettings ?? emptyProviderSettings);
  const [refreshStatus, setRefreshStatus] = useState<RefreshStatus | null>(initialRefreshStatus ?? null);
  const [countdownSeconds, setCountdownSeconds] = useState(initialRefreshStatus?.seconds_until_next_refresh ?? 0);
  const [settingsForm, setSettingsForm] = useState<SettingsForm>(() =>
    settingsToForm(initialProviderSettings ?? emptyProviderSettings)
  );
  const [activeTopicId, setActiveTopicId] = useState(initialRadar?.recommended_topic.id ?? initialTopics?.[0]?.id ?? "");
  const [status, setStatus] = useState(initialRadar ? "ready" : "loading");
  const [settingsStatus, setSettingsStatus] = useState(initialProviderSettings ? "ready" : "loading");
  const [settingsMessage, setSettingsMessage] = useState("");
  const [refreshingModule, setRefreshingModule] = useState<RefreshModule | "">("");
  const [rerunningStage, setRerunningStage] = useState("");
  const [generatingTopicId, setGeneratingTopicId] = useState("");
  const [dueRefreshing, setDueRefreshing] = useState(false);
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
        const nextDetail = await fetchDraftDetail(nextRadar.draft.id);
        if (!cancelled) {
          setRadar(nextRadar);
          setTopics(nextTopics);
          setDraftDetail(nextDetail);
          setActiveTopicId(nextRadar.recommended_topic.id);
          setStatus("ready");
        }
      } catch (error) {
        if (!cancelled) {
          setStatus(error instanceof Error ? error.message : "Load failed");
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

  const activeTopic = useMemo(
    () => topics.find((topic) => topic.id === activeTopicId) ?? radar?.recommended_topic ?? topics[0],
    [activeTopicId, radar, topics]
  );
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
      setEditorStatus(`已重跑${rerunFeedbackLabels[stage] ?? stage} v${nextDetail.draft.version}`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? `重跑失败：${error.message}` : "重跑失败");
    } finally {
      setRerunningStage("");
    }
  }

  function handleTopicSelect(topicId: string) {
    setActiveTopicId(topicId);
    window.history.replaceState(null, "", "#workshop");
    document.getElementById("workshop")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleGenerateTopicDraft(topicId: string) {
    if (!radar) {
      return;
    }
    handleTopicSelect(topicId);
    setGeneratingTopicId(topicId);
    setEditorStatus("正在选择并生成草稿...");
    try {
      const nextDraft = await generateTopicDraft(topicId, radar.date);
      const nextDetail = await fetchDraftDetail(nextDraft.id);
      setDraftDetail(nextDetail);
      setActiveModuleId("article-module-main");
      setEditorStatus(`已生成选题草稿 v${nextDetail.draft.version}`);
    } catch (error) {
      setEditorStatus(error instanceof Error ? `生成草稿失败：${error.message}` : "生成草稿失败");
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
      const nextDetail = await fetchDraftDetail(nextRadar.draft.id);
      setRefreshStatus(nextRefresh);
      setCountdownSeconds(nextRefresh.seconds_until_next_refresh);
      setRadar(nextRadar);
      setTopics(nextTopics);
      setDraftDetail(nextDetail);
      setActiveTopicId(nextRadar.recommended_topic.id);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Scheduled refresh failed");
    } finally {
      setDueRefreshing(false);
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
        [field]: value
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

  if (!radar || !activeTopic || !draftDetail) {
    return (
      <main className="app-shell app-shell--loading">
        <section className="loading-panel">
          <Pulse size={30} weight="duotone" />
          <h1>AI 内容雷达启动中</h1>
          <p>{status === "loading" ? "正在生成今日雷达、选题池和稿件包。" : status}</p>
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
              系统已把过去 24 小时的论文、新闻、项目和产品发布压缩成一组可写选题。优先看评分高、证据风险低、能自然转成论文方向的内容。
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
            <span className="quiet-badge">5-10 candidates</span>
          </div>

          <div className="topic-grid">
            {topics.map((topic) => (
              <TopicCard
                key={topic.id}
                topic={topic}
                active={topic.id === activeTopic.id}
                onSelect={() => handleTopicSelect(topic.id)}
                onGenerate={() => handleGenerateTopicDraft(topic.id)}
                generating={generatingTopicId === topic.id}
              />
            ))}
          </div>
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
              <Field label="LLM Base URL">
                <input
                  aria-label="LLM Base URL"
                  value={settingsForm.llm.base_url}
                  onChange={(event) => updateSettingsForm("llm", "base_url", event.target.value)}
                  placeholder="https://relay.example.com/v1"
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
              description="用于封面和机制图重跑。未配置时会继续生成本地占位 PNG。"
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

function TopicCard({
  topic,
  active,
  onSelect,
  onGenerate,
  generating
}: {
  topic: Topic;
  active: boolean;
  onSelect: () => void;
  onGenerate: () => void;
  generating: boolean;
}) {
  return (
    <article
      className={`topic-card ${active ? "topic-card--active" : ""}`}
      data-testid={`topic-${topic.id}`}
      onClick={onSelect}
      tabIndex={0}
    >
      <span className="topic-card__type">{topic.article_type.replace("_", " ")}</span>
      <h3>{topic.title}</h3>
      <p>{topic.recommendation}</p>
      <div className="score-stack">
        {Object.entries(topic.score_detail).map(([key, score]) => (
          <div className="score-row" key={key}>
            <span>{scoreLabels[key]}</span>
            <meter min="0" max="100" value={score.value} />
            <strong>{score.value}</strong>
          </div>
        ))}
      </div>
      <div className="topic-card__footer">
        <span>{topic.source_count} sources</span>
        <span>{topic.evidence_risk} risk</span>
      </div>
      <p className="business-hook">{topic.business_hook}</p>
      <button
        className="topic-card__action"
        disabled={generating}
        onClick={(event) => {
          event.stopPropagation();
          onGenerate();
        }}
        type="button"
      >
        {generating ? "选择中" : "选择选题"}
      </button>
    </article>
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
      fallback: "深度拆解论文问题、方法、实验可信度和复现价值。"
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
