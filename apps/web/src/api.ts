export type ScoreItem = {
  value: number;
  reason: string;
};

export type Source = {
  id: string;
  name: string;
  type: "rss" | "api" | "github" | "arxiv" | "manual";
  url: string;
  enabled: boolean;
  fetch_interval_minutes: number;
  last_success_at: string | null;
  last_error: string | null;
  status: "healthy" | "degraded" | "failed";
  created_at: string;
};

export type Signal = {
  id: string;
  source_id: string;
  kind: "news" | "paper" | "repo" | "product" | "post";
  title: string;
  summary: string;
  url: string;
  published_at: string;
  tags: string[];
  heat: number;
  entities: Record<string, string[]>;
};

export type Topic = {
  id: string;
  slug: string;
  cluster_id: string;
  paper_id: string | null;
  title: string;
  angle: string;
  article_type: "long_paper" | "industry_analysis" | "topic_inspiration" | "short_hotspot";
  status: "candidate" | "selected" | "drafted" | "published" | "rejected";
  score_total: number;
  score_detail: Record<"heat" | "relevance" | "writeability" | "conversion", ScoreItem>;
  business_hook: string;
  source_count: number;
  evidence_risk: "low" | "medium" | "high";
  recommendation: string;
  signal_ids: string[];
  created_at: string;
};

export type DraftAsset = {
  id: string;
  draft_id: string;
  kind: "cover" | "mechanism" | "quote" | "source_file";
  prompt: string;
  revised_prompt: string | null;
  path: string;
  width: number;
  height: number;
  provider: string;
  provider_request_id: string | null;
  created_at: string;
};

export type Draft = {
  id: string;
  topic_id: string;
  title: string;
  subtitle: string;
  status: "generating" | "review" | "ready" | "published" | "rejected";
  markdown_path: string;
  html_path: string;
  sources_path: string;
  checklist_path: string;
  evidence_path: string;
  topic_path: string;
  version: number;
  assets: DraftAsset[];
  last_rerun_stage: string;
  created_at: string;
  updated_at: string;
};

export type EvidenceItem = {
  id: string;
  topic_id: string;
  source_url: string;
  source_title: string;
  claim: string;
  snippet: string;
  confidence: "high" | "medium" | "low";
  risk_note: string;
  created_at: string;
};

export type RadarToday = {
  date: string;
  signal_count: number;
  ai_relevant_count: number;
  topic_count: number;
  source_health: Source[];
  top_hotspots: Signal[];
  categories: Record<string, number>;
  recommended_topic: Topic;
  draft: Draft;
};

export type DraftDetail = {
  draft: Draft;
  topic: Topic;
  evidence_items: EvidenceItem[];
  markdown: string;
  html: string;
  sources: string;
  review_checklist: string;
};

export type ProviderSettings = {
  base_url: string;
  model: string;
  configured: boolean;
  api_key_masked: string;
  size: string;
  quality: string;
  output_format: string;
};

export type ProvidersSettings = {
  llm: ProviderSettings;
  image2: ProviderSettings;
};

export type ProviderSettingsUpdate = {
  base_url: string;
  api_key: string;
  model: string;
  size?: string;
  quality?: string;
  output_format?: string;
};

export type ProvidersSettingsUpdate = {
  llm: ProviderSettingsUpdate;
  image2: ProviderSettingsUpdate;
};

export type RefreshModule = "main" | "hotspots" | "arxiv";

export type RefreshStatus = {
  date: string;
  refresh_time: string;
  today_refreshed: boolean;
  last_refresh_at: string | null;
  next_refresh_at: string;
  seconds_until_next_refresh: number;
};

const API_BASE = "";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Request failed"));
  }
  return response.json() as Promise<T>;
}

async function responseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) {
      return `${fallback}: ${payload.detail}`;
    }
  } catch {
    // Ignore non-JSON error bodies and fall back to the status code.
  }
  return `${fallback}: ${response.status}`;
}

export async function fetchRadar(): Promise<RadarToday> {
  return getJson<RadarToday>("/api/radar/today");
}

export async function fetchRefreshStatus(): Promise<RefreshStatus> {
  return getJson<RefreshStatus>("/api/refresh/status");
}

export async function refreshIfDue(): Promise<RefreshStatus> {
  const response = await fetch("/api/refresh/due", {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Refresh due check failed: ${response.status}`);
  }
  return response.json() as Promise<RefreshStatus>;
}

export async function fetchTopics(): Promise<Topic[]> {
  return getJson<Topic[]>("/api/topics");
}

export async function fetchDraftDetail(draftId: string): Promise<DraftDetail> {
  return getJson<DraftDetail>(`/api/drafts/${draftId}`);
}

export async function generateTopicDraft(topicId: string, date?: string): Promise<Draft> {
  const suffix = date ? `?date=${encodeURIComponent(date)}` : "";
  const response = await fetch(`/api/topics/${topicId}/draft${suffix}`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Generate draft failed"));
  }
  return response.json() as Promise<Draft>;
}

export async function refreshDraftModule(draftId: string, module: RefreshModule): Promise<Draft> {
  const response = await fetch(`/api/drafts/${draftId}/refresh-module`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module, reason: "manual module refresh" })
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Refresh module failed"));
  }
  return response.json() as Promise<Draft>;
}

export async function saveDraftContent(draftId: string, markdown: string): Promise<DraftDetail> {
  const response = await fetch(`/api/drafts/${draftId}/content`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markdown, reason: "manual editor save" })
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Save draft content failed"));
  }
  return response.json() as Promise<DraftDetail>;
}

export async function fetchProviderSettings(): Promise<ProvidersSettings> {
  return getJson<ProvidersSettings>("/api/settings/providers");
}

export async function saveProviderSettings(payload: ProvidersSettingsUpdate): Promise<ProvidersSettings> {
  const response = await fetch("/api/settings/providers", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Save settings failed"));
  }
  return response.json() as Promise<ProvidersSettings>;
}

export async function rerunDraft(draftId: string, stage: string): Promise<Draft> {
  const response = await fetch(`/api/drafts/${draftId}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage, reason: "manual workspace rerun" })
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Rerun failed"));
  }
  return response.json() as Promise<Draft>;
}
