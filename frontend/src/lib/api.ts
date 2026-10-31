const BASE = import.meta.env.VITE_API_BASE ?? "";

export function deviceToken(): string {
  try {
    let t = localStorage.getItem("cp_device");
    if (!t) {
      t = crypto.randomUUID().replace(/-/g, "");
      localStorage.setItem("cp_device", t);
    }
    return t;
  } catch {
    return "anon" + Math.random().toString(36).slice(2, 12);
  }
}

export function myRefs(): string[] {
  try {
    return JSON.parse(localStorage.getItem("cp_refs") ?? "[]");
  } catch {
    return [];
  }
}
export function rememberRef(ref: string) {
  try {
    const refs = [ref, ...myRefs().filter((r) => r !== ref)].slice(0, 30);
    localStorage.setItem("cp_refs", JSON.stringify(refs));
  } catch {
    /* storage unavailable: the status link still works */
  }
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}
export class NetworkError extends Error {}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { "X-Device-Token": deviceToken(), ...(init.headers ?? {}) },
    });
  } catch {
    throw new NetworkError("Network unavailable");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).error ?? msg;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(msg, res.status);
  }
  return res.json() as Promise<T>;
}

export const get = <T,>(path: string) => request<T>(path);
export const postJson = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const postForm = <T,>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form });

// ------------------------------------------------------------------ types --
export interface TimelineEvent {
  status: string;
  actor: string;
  note: string;
  at: string;
  proof_url: string | null;
}
export interface Report {
  ref_no: string;
  status: string;
  category: string;
  category_label: string;
  severity_level: string;
  severity_score: number | null;
  confidence: number | null;
  rationale: string;
  description: string;
  factors: string[];
  ward: string;
  lat: number;
  lng: number;
  image_url: string | null;
  routing_reason: string;
  routing_confidence: number | null;
  authority: string | null;
  affected_count: number;
  canonical_ref: string | null;
  created_at: string;
  timeline: TimelineEvent[];
  delivery: { authority: string; status: string; mode: string; sent_at: string | null }[];
  is_owner: boolean;
  address?: string;
  clarifying_question?: string;
  transcript?: string;
  text?: string;
  ai_error?: string;
  authenticity_flags?: string[];
}
export interface Meta {
  categories: { key: string; label: string }[];
  dispatch_mode: string;
  max_audio_seconds: number;
  confidence_threshold: number;
  pilot_area: string;
}
export interface MetricRow {
  name: string;
  volume: number;
  sent: number;
  acknowledged: number;
  resolved: number;
  median_hours_to_acknowledge: number | null;
  median_hours_to_resolve: number | null;
  reopen_rate: number | null;
  aging_backlog: number;
}
export interface Metrics {
  group: string;
  rows: MetricRow[];
  totals: { reports: number; open: number; resolved: number };
  definitions: Record<string, string>;
}
export interface MapFeature {
  geometry: { coordinates: [number, number] };
  properties: {
    ref_no: string;
    category: string;
    category_label: string;
    severity: string;
    status: string;
    ward: string;
    affected: number;
    created_at: string;
  };
}
