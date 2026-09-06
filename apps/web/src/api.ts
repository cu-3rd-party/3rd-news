const BASE = "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const csrf = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("thirdnews_csrf="))
    ?.slice("thirdnews_csrf=".length);
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(method !== "GET" && method !== "HEAD" && csrf
        ? { "X-CSRF-Token": decodeURIComponent(csrf) }
        : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const del = (path: string) => request<void>(path, { method: "DELETE" });



export interface Me {
  kind: string;
  subject: string;
  display_name: string;
  scopes: string[];
  role: string | null;
}

export interface FacetValue {
  id: string;
  slug: string;
  title: string;
  description?: string | null;
  ai_hint?: string | null;
  synonyms: string[];
  match_patterns: string[];
  is_active: boolean;
  position: number;
}

export interface Facet {
  id: string;
  slug: string;
  title: string;
  description?: string | null;
  ai_hint?: string | null;
  type: "single" | "multi";
  required: boolean;
  is_active: boolean;
  position: number;
  values: FacetValue[];
}

export interface NewsAttachment {
  id: string;
  kind: string;
  url: string | null;
  filename: string | null;
  mime: string | null;
  size: number | null;
  status: string;
  caption: string | null;
}

export interface LabelOpinion {
  facet: string;
  value: string;
  origin: string;
  origin_key: string;
  confidence: number;
  reason: string | null;
  created_at: string | null;
}

export interface NewsItem {
  id: string;
  title: string | null;
  body_md: string;
  source_key: string | null;
  source_link: string | null;
  source_text: string | null;
  published_at: string | null;
  received_at: string;
  status: string;
  lang: string | null;
  extra: Record<string, unknown>;
  manual_facets: string[];
  classified_at: string | null;
  
  is_gold: boolean;
  attachments: NewsAttachment[];
  effective: Record<string, string[]>;
  opinions: LabelOpinion[];
}

type Collection<T> = { items: T[] };

function generatedSlug(value: string): string {
  const normalized = value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 100);
  return normalized || `item-${Date.now().toString(36)}`;
}

function facetPayload(body: any) {
  return {
    slug: body.slug || generatedSlug(body.title),
    title: body.title,
    description: body.description ?? null,
    ai_hint: body.ai_hint ?? null,
    kind: body.type ?? body.kind ?? "single",
    required: body.required ?? false,
    enabled: body.is_active ?? body.enabled ?? true,
    position: body.position ?? 0,
  };
}

function valuePayload(body: any) {
  return {
    slug: body.slug || generatedSlug(body.title),
    title: body.title,
    description: body.description ?? null,
    ai_hint: body.ai_hint ?? null,
    synonyms: body.synonyms ?? [],
    match_patterns: body.match_patterns ?? [],
    enabled: body.is_active ?? body.enabled ?? true,
    position: body.position ?? 0,
  };
}

function sourcePayload(body: any) {
  return {
    slug: body.slug || generatedSlug(body.title),
    title: body.title,
    kind: body.kind ?? "other",
    url: body.url || null,
    description: body.description ?? null,
    enabled: body.is_active ?? body.enabled ?? true,
    skip_classification: body.skip_classification ?? false,
    default_labels: body.default_labels ?? {},
  };
}

function classifierPayload(body: any) {
  return {
    slug: body.slug || generatedSlug(body.name),
    name: body.name,
    endpoint: body.base_url ?? body.endpoint,
    allowed_axes: body.facets ?? body.allowed_axes ?? [],
    config: body.config ?? {},
    signing_public_key: body.signing_public_key || undefined,
    enabled: body.is_active ?? body.enabled ?? true,
    shadow: body.auto_apply === undefined ? (body.shadow ?? false) : !body.auto_apply,
    priority: body.priority ?? 100,
    min_confidence: body.min_confidence ?? 0.5,
    timeout_seconds: body.timeout_s ?? body.timeout_seconds ?? 30,
  };
}

function normalizeFacet(item: Record<string, any>): Facet {
  return {
    ...item,
    type: item.kind,
    is_active: item.enabled,
    values: (item.values ?? []).map((value: Record<string, any>) => ({
      ...value,
      is_active: value.enabled,
    })),
  } as Facet;
}

export function normalizeNews(item: Record<string, any>): NewsItem {
  const labels = (item.labels ?? []) as LabelOpinion[];
  const effective: Record<string, string[]> = {};
  for (const label of labels) {
    (effective[label.facet] ??= []).push(label.value);
  }
  return {
    ...item,
    source_key: item.source ?? null,
    lang: item.language ?? null,
    classified_at: null,
    opinions: labels.map((label) => ({ ...label, origin_key: label.origin, reason: null })),
    effective,
    extra: item.extra ?? {},
    manual_facets: item.manual_facets ?? [],
    attachments: item.attachments ?? [],
  } as NewsItem;
}

export interface Source {
  id: string;
  slug: string;
  title: string;
  kind: string;
  url: string | null;
  description: string | null;
  is_active: boolean;
  default_labels: Record<string, string[]>;
  skip_classification: boolean;
  last_ingest_at: string | null;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  source_id: string | null;
  filter_preset: Record<string, unknown>;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export interface Classifier {
  id: string;
  slug: string;
  name: string;
  base_url: string;
  facets: string[];
  config: Record<string, unknown>;
  is_active: boolean;
  priority: number;
  min_confidence: number;
  auto_apply: boolean;
  timeout_s: number;
  last_ok_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  has_secret: boolean;
}

export interface ClassificationContext {
  text: string;
  example_count: number;
  examples_configured: number;
}

export interface Stats {
  news_total: number;
  by_status: Record<string, number>;
  pending_jobs: number;
  sources: number;
  classifiers_active: number;
}

export const api = {
  login: (email: string, password: string) =>
    post<Me>("/api/v1/auth/login", { email, password }),
  logout: () => post<void>("/api/v1/auth/logout"),
  me: () => get<Me>("/api/v1/auth/me"),

  stats: () => get<Stats>("/api/v1/admin/stats"),

  classificationContext: () =>
    get<ClassificationContext>("/api/v1/admin/classification-context"),
  saveClassificationContext: (text: string) =>
    put<ClassificationContext>("/api/v1/admin/classification-context", { text }),

  facets: async () => (await get<Collection<Record<string, any>>>("/api/v1/admin/facets")).items.map(normalizeFacet),
  createFacet: (body: any) => post<Facet>("/api/v1/admin/facets", facetPayload(body)),
  updateFacet: (id: string, body: any) => patch<Facet>(`/api/v1/admin/facets/${id}`, facetPayload(body)),
  deleteFacet: (id: string) => del(`/api/v1/admin/facets/${id}`),
  createValue: (facetId: string, body: any) =>
    post<FacetValue>(`/api/v1/admin/facets/${facetId}/values`, valuePayload(body)),
  updateValue: (id: string, body: any) => patch<FacetValue>(`/api/v1/admin/facet-values/${id}`, valuePayload(body)),
  deleteValue: (id: string) => del(`/api/v1/admin/facet-values/${id}`),

  news: async (query: string) => {
    const page = await get<{ items: Record<string, any>[]; total: number }>(`/api/v1/admin/news${query}`);
    return { ...page, items: page.items.map(normalizeNews) };
  },
  setLabels: async (id: string, labels: Record<string, string[]>, releaseFacets: string[] = []) =>
    normalizeNews(await put<Record<string, any>>(`/api/v1/admin/news/${id}/labels`, {
      labels,
      release_facets: releaseFacets,
    })),
  setStatus: async (id: string, status: string) => normalizeNews(await post<Record<string, any>>(`/api/v1/admin/news/${id}/${status === "published" ? "publish" : "reject"}`)),
  reclassify: async (id: string) => {
    await post(`/api/v1/admin/news/${id}/reprocess`);
    return normalizeNews(await get<Record<string, any>>(`/api/v1/admin/news/${id}`));
  },
  setGold: (ids: string[], isGold: boolean) =>
    post<{ updated: number }>("/api/v1/admin/news/gold", { ids, is_gold: isGold }),
  deleteNews: (id: string) => del(`/api/v1/admin/news/${id}`),

  sources: async () => (await get<Collection<Record<string, any>>>("/api/v1/admin/sources")).items.map((item) => ({ ...item, is_active: item.enabled, last_ingest_at: null }) as Source),
  createSource: (body: any) => post<Source>("/api/v1/admin/sources", sourcePayload(body)),
  updateSource: (id: string, body: any) => patch<Source>(`/api/v1/admin/sources/${id}`, sourcePayload(body)),

  apiKeys: async () => (await get<Collection<Record<string, any>>>("/api/v1/admin/api-keys")).items.map((item) => ({ ...item, is_active: item.enabled }) as ApiKey),
  createApiKey: (body: unknown) =>
    post<{ key: ApiKey; secret: string }>("/api/v1/admin/api-keys", body),
  revokeApiKey: (id: string) => post<ApiKey>(`/api/v1/admin/api-keys/${id}/revoke`),

  classifiers: async () => (await get<Collection<Record<string, any>>>("/api/v1/admin/classifiers")).items.map((item) => ({ ...item, base_url: item.endpoint, facets: item.allowed_axes, is_active: item.enabled, auto_apply: !item.shadow, timeout_s: item.timeout_seconds, has_secret: item.has_signing_key, last_error_at: null }) as Classifier),
  createClassifier: (body: any) => post<Classifier>("/api/v1/admin/classifiers", classifierPayload(body)),
  updateClassifier: (id: string, body: any) =>
    patch<Classifier>(`/api/v1/admin/classifiers/${id}`, classifierPayload(body)),
  deleteClassifier: (id: string) => del(`/api/v1/admin/classifiers/${id}`),
  probeClassifier: (id: string) =>
    post<{ ok: boolean; manifest?: unknown; error?: string }>(
      `/api/v1/admin/classifiers/${id}/probe`,
    ),
};
