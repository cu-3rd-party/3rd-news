/**
 * Thin wrapper over the admin API.
 *
 * Authentication is the session cookie set by `POST /api/v1/auth/login`, so
 * every request goes out with `credentials: "include"` and the browser does
 * the rest. Nothing here knows about tokens.
 */

const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // A non-JSON error body is not worth a second failure.
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

// --- types mirroring the server schemas ------------------------------------

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
  attachments: NewsAttachment[];
  effective: Record<string, string[]>;
  opinions: LabelOpinion[];
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

  facets: () => get<Facet[]>("/api/v1/admin/facets"),
  createFacet: (body: unknown) => post<Facet>("/api/v1/admin/facets", body),
  updateFacet: (id: string, body: unknown) => patch<Facet>(`/api/v1/admin/facets/${id}`, body),
  deleteFacet: (id: string) => del(`/api/v1/admin/facets/${id}`),
  createValue: (facetId: string, body: unknown) =>
    post<FacetValue>(`/api/v1/admin/facets/${facetId}/values`, body),
  updateValue: (id: string, body: unknown) => patch<FacetValue>(`/api/v1/admin/values/${id}`, body),
  deleteValue: (id: string) => del(`/api/v1/admin/values/${id}`),

  news: (query: string) => get<{ items: NewsItem[]; total: number }>(`/api/v1/admin/news${query}`),
  setLabels: (id: string, labels: Record<string, string[]>, releaseFacets: string[] = []) =>
    put<NewsItem>(`/api/v1/admin/news/${id}/labels`, {
      labels,
      release_facets: releaseFacets,
    }),
  setStatus: (id: string, status: string) =>
    post<NewsItem>(`/api/v1/admin/news/${id}/status`, { status }),
  reclassify: (id: string) => post<NewsItem>(`/api/v1/admin/news/${id}/reclassify`),
  deleteNews: (id: string) => del(`/api/v1/admin/news/${id}`),

  sources: () => get<Source[]>("/api/v1/admin/sources"),
  createSource: (body: unknown) => post<Source>("/api/v1/admin/sources", body),
  updateSource: (id: string, body: unknown) => patch<Source>(`/api/v1/admin/sources/${id}`, body),

  apiKeys: () => get<ApiKey[]>("/api/v1/admin/api-keys"),
  createApiKey: (body: unknown) =>
    post<{ key: ApiKey; secret: string }>("/api/v1/admin/api-keys", body),
  revokeApiKey: (id: string) => post<ApiKey>(`/api/v1/admin/api-keys/${id}/revoke`),

  classifiers: () => get<Classifier[]>("/api/v1/admin/classifiers"),
  createClassifier: (body: unknown) => post<Classifier>("/api/v1/admin/classifiers", body),
  updateClassifier: (id: string, body: unknown) =>
    patch<Classifier>(`/api/v1/admin/classifiers/${id}`, body),
  deleteClassifier: (id: string) => del(`/api/v1/admin/classifiers/${id}`),
  probeClassifier: (id: string) =>
    post<{ ok: boolean; manifest?: unknown; error?: string }>(
      `/api/v1/admin/classifiers/${id}/probe`,
    ),
};
