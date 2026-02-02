import React, { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Asset, fetchAssets, fetchCities, fetchCityStatus, fetchCitySummary, fetchHotspots, fetchMetrics, fetchObservations, fetchScenarios } from "../api";

function isoNowMinus(hours: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date(to.getTime() - hours * 3600 * 1000);
  return { from: from.toISOString(), to: to.toISOString() };
}

export default function App() {
  const [cities, setCities] = useState<{ city_id: string; name: string }[]>([]);
  const [cityId, setCityId] = useState<string>("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [metric, setMetric] = useState<string>("fill_ratio");
  const [series, setSeries] = useState<{ ts: string; value: number }[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [hotspots, setHotspots] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [rangeHours, setRangeHours] = useState<number>(24);
  const [loadingAssets, setLoadingAssets] = useState<boolean>(false);
  const [loadingSeries, setLoadingSeries] = useState<boolean>(false);
  const [loadingCity, setLoadingCity] = useState<boolean>(false);
  const [loadingHotspots, setLoadingHotspots] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [tagFilter, setTagFilter] = useState<string>("");
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("latest");

  useEffect(() => {
    fetchCities().then((c) => {
      setCities(c);
      if (c.length) setCityId(c[0].city_id);
    }).catch((err) => {
      setErrorMsg(err?.message ?? "Failed to load cities");
      console.error(err);
    });
    fetchScenarios()
      .then(setScenarios)
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load scenarios");
        console.error(err);
      });
  }, []);

  useEffect(() => {
    if (!cityId) return;
    setLoadingCity(true);
    Promise.all([
      fetchCityStatus(cityId).then(setStatus),
      fetchCitySummary(cityId, 15).then(setSummary),
    ])
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load city summary");
        console.error(err);
      })
      .finally(() => setLoadingCity(false));

    setLoadingHotspots(true);
    fetchHotspots(cityId, 10)
      .then(setHotspots)
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load hotspots");
        console.error(err);
      })
      .finally(() => setLoadingHotspots(false));

    // broad bbox around Porto-ish for the synthetic generator
    const bbox = "-8.75,41.05,-8.45,41.25";
    const tags = tagFilter
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    setLoadingAssets(true);
    Promise.all([
      fetchAssets(cityId, "pipe", bbox, tags),
      fetchAssets(cityId, "river_segment", bbox, tags),
      fetchAssets(cityId, "rain_gauge", bbox, tags),
      fetchAssets(cityId, "river_gauge", bbox, tags),
    ])
      .then(([pipes, rivers, rain, river]) => setAssets([...pipes, ...rivers, ...rain, ...river]))
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load assets");
        console.error(err);
      })
      .finally(() => setLoadingAssets(false));
  }, [cityId, tagFilter]);

  useEffect(() => {
    if (!selected) return;
    fetchMetrics(selected.asset_id, scenarioId).then((m) => {
      setMetrics(m);
      if (m.includes("fill_ratio")) setMetric("fill_ratio");
      else if (m.length) setMetric(m[0]);
    }).catch((err) => {
      setErrorMsg(err?.message ?? "Failed to load metrics");
      console.error(err);
    });
  }, [selected, scenarioId]);

  useEffect(() => {
    if (!selected || !metric) return;
    const { from, to } = isoNowMinus(rangeHours);
    setLoadingSeries(true);
    fetchObservations(selected.asset_id, metric, from, to, scenarioId)
      .then((r) => setSeries((r.series ?? []).map((x: any) => ({ ts: x.ts, value: x.value }))))
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load observations");
        console.error(err);
      })
      .finally(() => setLoadingSeries(false));
  }, [selected, metric, rangeHours, scenarioId]);

  const hotspotSet = useMemo(() => new Set(hotspots.map((h) => h.asset_id)), [hotspots]);

  const featuresByType = useMemo(() => {
    const base = assets
      .filter((a) => a.geom_geojson)
      .map((a) => ({
        type: "Feature",
        geometry: a.geom_geojson,
        properties: {
          asset_id: a.asset_id,
          name: a.name,
          asset_type: a.asset_type,
        },
      }));
    const byType = {
      river: base.filter((f) => f.properties.asset_type === "river_segment"),
      pipes: base.filter((f) => f.properties.asset_type === "pipe"),
      gauges: base.filter(
        (f) => f.properties.asset_type === "rain_gauge" || f.properties.asset_type === "river_gauge"
      ),
    };
    return {
      river: { type: "FeatureCollection", features: byType.river } as any,
      pipes: { type: "FeatureCollection", features: byType.pipes } as any,
      gauges: { type: "FeatureCollection", features: byType.gauges } as any,
    };
  }, [assets]);

  const onFeatureClick = (_: any, layer: any) => {
    layer.on("click", () => {
      const props: any = layer.feature?.properties;
      const a = assets.find((x) => x.asset_id === props?.asset_id) ?? null;
      setSelected(a);
    });
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 12, padding: 12, height: "100vh" }}>
      <div style={{ border: "1px solid #ddd", borderRadius: 8, overflow: "hidden", position: "relative" }}>
        <MapContainer center={[41.15, -8.61]} zoom={12} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <GeoJSON
            data={featuresByType.river}
            onEachFeature={onFeatureClick}
            style={() => ({ color: "#2b6cb0", weight: 4, opacity: 0.9 })}
          />
          <GeoJSON
            data={featuresByType.pipes}
            onEachFeature={onFeatureClick}
            style={(feature: any) => {
              const id = feature?.properties?.asset_id;
              const isSelected = selected?.asset_id === id;
              const isHotspot = hotspotSet.has(id);
              return {
                color: isSelected ? "#e11d48" : isHotspot ? "#f59e0b" : "#334155",
                weight: isSelected ? 5 : isHotspot ? 4 : 2,
                opacity: isSelected ? 1 : 0.8,
              };
            }}
          />
          <GeoJSON
            data={featuresByType.gauges}
            onEachFeature={onFeatureClick}
            pointToLayer={(_, latlng) => {
              return L.circleMarker(latlng, {
                radius: 5,
                weight: 1,
                color: "#0f766e",
                fillColor: "#14b8a6",
                fillOpacity: 0.8,
              });
            }}
          />
        </MapContainer>
        {loadingAssets && (
          <div style={{ position: "absolute", top: 18, left: 18, background: "rgba(255,255,255,0.9)", padding: "6px 10px", borderRadius: 6, fontSize: 12 }}>
            Loading assets…
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {errorMsg && (
          <div style={{ border: "1px solid #fca5a5", background: "#fef2f2", color: "#991b1b", padding: 8, borderRadius: 8, fontSize: 12 }}>
            {errorMsg}
          </div>
        )}
        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>City Flood MVP</div>
              <div style={{ fontSize: 12, color: "#666" }}>Synthetic assets + telemetry + analytics</div>
            </div>
            <select value={cityId} onChange={(e) => setCityId(e.target.value)}>
              {cities.map((c) => (
                <option key={c.city_id} value={c.city_id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 12, color: "#666" }}>Filter tags</label>
            <input
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              placeholder="basin:basin_ne, neighborhood:neighborhood_1_2"
              style={{ flex: 1, padding: "4px 8px", fontSize: 12 }}
            />
          </div>
          <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 12, color: "#666" }}>Scenario</label>
            <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
              <option value="latest">Latest</option>
              {scenarios.map((s) => (
                <option key={s.scenario_id} value={s.scenario_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          {loadingCity && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>Loading summary…</div>
          )}
          {status && !loadingCity && (
            <div style={{ marginTop: 8, fontSize: 14 }}>
              <div>Risk: <b>{status.risk}</b></div>
              <div>Active events: <b>{status.active_events}</b></div>
              <div>Hotspots: <b>{status.hotspots}</b></div>
            </div>
          )}
          {summary && !loadingCity && (
            <div style={{ marginTop: 8, fontSize: 13 }}>
              <div>Rain (15m avg): <b>{Number(summary.rain_mmph).toFixed(1)} mm/h</b></div>
              <div>River level (15m avg): <b>{Number(summary.river_level_m).toFixed(2)} m</b></div>
              <div>Status: <b>{summary.status_counts?.normal ?? 0}</b> normal, <b>{summary.status_counts?.watch ?? 0}</b> watch, <b>{summary.status_counts?.warning ?? 0}</b> warning</div>
            </div>
          )}
        </div>

        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 600 }}>Hotspots (top 10)</div>
          {loadingHotspots && <div style={{ fontSize: 12, color: "#666" }}>Loading hotspots…</div>}
          <ol>
            {hotspots.map((h) => (
              <li key={h.asset_id} style={{ fontSize: 12 }}>
                {h.asset_id} — score {Number(h.score).toFixed(1)}
              </li>
            ))}
          </ol>
        </div>

        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>Asset detail</div>
              <div style={{ fontSize: 12, color: "#666" }}>{selected ? selected.name : "Click an asset on the map"}</div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <select value={rangeHours} onChange={(e) => setRangeHours(Number(e.target.value))}>
                <option value={6}>Last 6h</option>
                <option value={24}>Last 24h</option>
                <option value={168}>Last 7d</option>
              </select>
            {metrics.length > 0 && (
              <select value={metric} onChange={(e) => setMetric(e.target.value)}>
                {metrics.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}
            </div>
          </div>

          <div style={{ height: 240, marginTop: 8 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series}>
                <XAxis dataKey="ts" hide />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="value" dot={false} />
              </LineChart>
            </ResponsiveContainer>
            {loadingSeries && <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>Loading chart…</div>}
          </div>

          {selected && (
            <pre style={{ marginTop: 8, fontSize: 11, background: "#fafafa", padding: 8, borderRadius: 6, overflow: "auto", maxHeight: 160 }}>
{JSON.stringify({ asset_id: selected.asset_id, asset_type: selected.asset_type, props: selected.props }, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
