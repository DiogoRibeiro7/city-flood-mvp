export type Asset = {
  asset_id: string;
  city_id: string;
  asset_type: string;
  name: string;
  geom_geojson?: any;
  props: Record<string, any>;
};

export type City = { city_id: string; name: string; country: string };
export type Note = {
  note_id: string;
  city_id: string;
  asset_id?: string | null;
  event_id?: string | null;
  title: string;
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const TOKEN_KEY = "floodmvp.jwt";

function authHeaders(): Record<string, string> {
  const token = window.localStorage.getItem(TOKEN_KEY);
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function fetchCities(): Promise<City[]> {
  const r = await fetch(`${API_BASE}/v1/cities`);
  if (!r.ok) throw new Error(`cities: ${r.status}`);
  return r.json();
}

export async function fetchAssets(
  cityId: string,
  type?: string,
  bbox?: string,
  tags?: string[],
  limit?: number,
  offset?: number
): Promise<Asset[]> {
  const q = new URLSearchParams();
  if (type) q.set("type", type);
  if (bbox) q.set("bbox", bbox);
  if (tags) {
    tags.filter(Boolean).forEach((t) => q.append("tag", t));
  }
  if (limit !== undefined) q.set("limit", String(limit));
  if (offset !== undefined) q.set("offset", String(offset));
  const r = await fetch(`${API_BASE}/v1/cities/${cityId}/assets?${q.toString()}`);
  if (!r.ok) throw new Error(`assets: ${r.status}`);
  return r.json();
}

export async function fetchMetrics(assetId: string, scenarioId?: string): Promise<string[]> {
  const q = new URLSearchParams();
  if (scenarioId) q.set("scenario_id", scenarioId);
  const r = await fetch(`${API_BASE}/v1/assets/${assetId}/metrics?${q.toString()}`);
  if (!r.ok) throw new Error(`metrics: ${r.status}`);
  return r.json();
}

export async function fetchObservations(
  assetId: string,
  metric: string,
  from: string,
  to: string,
  scenarioId?: string
) {
  const q = new URLSearchParams();
  q.set("metric", metric);
  q.set("from", from);
  q.set("to", to);
  q.set("granularity", "5m");
  q.set("agg", "avg");
  if (scenarioId) q.set("scenario_id", scenarioId);
  const r = await fetch(`${API_BASE}/v1/assets/${assetId}/observations?${q.toString()}`);
  if (!r.ok) throw new Error(`observations: ${r.status}`);
  return r.json();
}

export async function fetchObservationsCompare(
  assetId: string,
  metric: string,
  from: string,
  to: string,
  baseScenarioId: string,
  compareScenarioId: string
) {
  const q = new URLSearchParams();
  q.set("metric", metric);
  q.set("from", from);
  q.set("to", to);
  q.set("granularity", "5m");
  q.set("agg", "avg");
  q.set("base_scenario_id", baseScenarioId);
  q.set("compare_scenario_id", compareScenarioId);
  const r = await fetch(`${API_BASE}/v1/assets/${assetId}/observations:compare?${q.toString()}`);
  if (!r.ok) throw new Error(`observations compare: ${r.status}`);
  return r.json();
}

export async function fetchScenarios() {
  const r = await fetch(`${API_BASE}/v1/telemetry/scenarios`);
  if (!r.ok) throw new Error(`scenarios: ${r.status}`);
  return r.json();
}

export async function fetchCityStatus(cityId: string) {
  const r = await fetch(`${API_BASE}/v1/cities/${cityId}/status`);
  if (!r.ok) throw new Error(`status: ${r.status}`);
  return r.json();
}

export async function fetchHotspots(cityId: string, top = 20) {
  const q = new URLSearchParams();
  q.set("city_id", cityId);
  q.set("metric", "overflow_risk");
  q.set("top", String(top));
  const r = await fetch(`${API_BASE}/v1/hotspots?${q.toString()}`);
  if (!r.ok) throw new Error(`hotspots: ${r.status}`);
  return r.json();
}

export async function fetchCitySummary(cityId: string, minutes = 15) {
  const q = new URLSearchParams();
  q.set("minutes", String(minutes));
  const r = await fetch(`${API_BASE}/v1/cities/${cityId}/summary?${q.toString()}`);
  if (!r.ok) throw new Error(`summary: ${r.status}`);
  return r.json();
}

export async function fetchEvents(
  cityId: string,
  from: string,
  to: string,
  type?: string,
  limit = 50
) {
  const q = new URLSearchParams();
  q.set("city_id", cityId);
  q.set("from", from);
  q.set("to", to);
  q.set("limit", String(limit));
  if (type) q.set("type", type);
  const r = await fetch(`${API_BASE}/v1/events?${q.toString()}`);
  if (!r.ok) throw new Error(`events: ${r.status}`);
  return r.json();
}

export async function fetchNotes(
  cityId: string,
  assetId?: string,
  eventId?: string,
  limit = 50
): Promise<Note[]> {
  const q = new URLSearchParams();
  q.set("city_id", cityId);
  if (assetId) q.set("asset_id", assetId);
  if (eventId) q.set("event_id", eventId);
  q.set("limit", String(limit));
  const r = await fetch(`${API_BASE}/v1/notes?${q.toString()}`);
  if (!r.ok) throw new Error(`notes: ${r.status}`);
  return r.json();
}

export async function fetchNote(noteId: string): Promise<Note> {
  const r = await fetch(`${API_BASE}/v1/notes/${noteId}`);
  if (!r.ok) throw new Error(`note: ${r.status}`);
  return r.json();
}

export async function createNote(payload: {
  city_id: string;
  asset_id?: string | null;
  event_id?: string | null;
  title: string;
  body: string;
  author: string;
}): Promise<Note> {
  const r = await fetch(`${API_BASE}/v1/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`create note: ${r.status}`);
  return r.json();
}

export async function deleteNote(noteId: string) {
  const r = await fetch(`${API_BASE}/v1/notes/${noteId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete note: ${r.status}`);
  return r.json();
}

export async function createReportJob(payload: {
  city_id: string;
  from: string;
  to: string;
  event_type?: string;
  top_hotspots?: number;
  include_summary?: boolean;
  include_hotspots?: boolean;
  include_events?: boolean;
}) {
  const r = await fetch(`${API_BASE}/v1/analytics/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      type: "report_csv",
      query: payload,
    }),
  });
  if (!r.ok) throw new Error(`report job: ${r.status}`);
  return r.json();
}

export async function fetchJob(jobId: string) {
  const r = await fetch(`${API_BASE}/v1/analytics/jobs/${jobId}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`job: ${r.status}`);
  return r.json();
}

export async function downloadJob(jobId: string) {
  const r = await fetch(`${API_BASE}/v1/analytics/jobs/${jobId}/download`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`download: ${r.status}`);
  return r.blob();
}

export function setAuthToken(token: string) {
  if (!token) {
    window.localStorage.removeItem(TOKEN_KEY);
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
}
