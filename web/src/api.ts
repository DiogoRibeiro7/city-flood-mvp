export type Asset = {
  asset_id: string;
  city_id: string;
  asset_type: string;
  name: string;
  geom_geojson?: any;
  props: Record<string, any>;
};

export type City = { city_id: string; name: string; country: string };

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchCities(): Promise<City[]> {
  const r = await fetch(`${API_BASE}/v1/cities`);
  if (!r.ok) throw new Error(`cities: ${r.status}`);
  return r.json();
}

export async function fetchAssets(cityId: string, type?: string, bbox?: string): Promise<Asset[]> {
  const q = new URLSearchParams();
  if (type) q.set("type", type);
  if (bbox) q.set("bbox", bbox);
  const r = await fetch(`${API_BASE}/v1/cities/${cityId}/assets?${q.toString()}`);
  if (!r.ok) throw new Error(`assets: ${r.status}`);
  return r.json();
}

export async function fetchMetrics(assetId: string): Promise<string[]> {
  const r = await fetch(`${API_BASE}/v1/assets/${assetId}/metrics`);
  if (!r.ok) throw new Error(`metrics: ${r.status}`);
  return r.json();
}

export async function fetchObservations(assetId: string, metric: string, from: string, to: string) {
  const q = new URLSearchParams();
  q.set("metric", metric);
  q.set("from", from);
  q.set("to", to);
  q.set("granularity", "5m");
  q.set("agg", "avg");
  const r = await fetch(`${API_BASE}/v1/assets/${assetId}/observations?${q.toString()}`);
  if (!r.ok) throw new Error(`observations: ${r.status}`);
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
