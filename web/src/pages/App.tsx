import React, { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Asset, fetchAssets, fetchCities, fetchCityStatus, fetchHotspots, fetchMetrics, fetchObservations } from "../api";

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

  useEffect(() => {
    fetchCities().then((c) => {
      setCities(c);
      if (c.length) setCityId(c[0].city_id);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    if (!cityId) return;
    fetchCityStatus(cityId).then(setStatus).catch(console.error);
    fetchHotspots(cityId, 10).then(setHotspots).catch(console.error);

    // broad bbox around Porto-ish for the synthetic generator
    const bbox = "-8.75,41.05,-8.45,41.25";
    Promise.all([
      fetchAssets(cityId, "pipe", bbox),
      fetchAssets(cityId, "river_segment", bbox),
      fetchAssets(cityId, "rain_gauge", bbox),
      fetchAssets(cityId, "river_gauge", bbox),
    ])
      .then(([pipes, rivers, rain, river]) => setAssets([...pipes, ...rivers, ...rain, ...river]))
      .catch(console.error);
  }, [cityId]);

  useEffect(() => {
    if (!selected) return;
    fetchMetrics(selected.asset_id).then((m) => {
      setMetrics(m);
      if (m.includes("fill_ratio")) setMetric("fill_ratio");
      else if (m.length) setMetric(m[0]);
    }).catch(console.error);
  }, [selected]);

  useEffect(() => {
    if (!selected || !metric) return;
    const { from, to } = isoNowMinus(24);
    fetchObservations(selected.asset_id, metric, from, to)
      .then((r) => setSeries((r.series ?? []).map((x: any) => ({ ts: x.ts, value: x.value }))))
      .catch(console.error);
  }, [selected, metric]);

  const geojsonFeatures = useMemo(() => {
    const feats = assets
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
    return { type: "FeatureCollection", features: feats } as any;
  }, [assets]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 12, padding: 12, height: "100vh" }}>
      <div style={{ border: "1px solid #ddd", borderRadius: 8, overflow: "hidden" }}>
        <MapContainer center={[41.15, -8.61]} zoom={12} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <GeoJSON
            data={geojsonFeatures}
            onEachFeature={(_, layer) => {
              layer.on("click", () => {
                const props: any = (layer as any).feature?.properties;
                const a = assets.find((x) => x.asset_id === props?.asset_id) ?? null;
                setSelected(a);
              });
            }}
            style={(feature: any) => {
              const t = feature?.properties?.asset_type;
              if (t === "river_segment") return { weight: 4 };
              if (t === "pipe") return { weight: 2 };
              return { radius: 6 };
            }}
          />
        </MapContainer>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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
          {status && (
            <div style={{ marginTop: 8, fontSize: 14 }}>
              <div>Risk: <b>{status.risk}</b></div>
              <div>Active events: <b>{status.active_events}</b></div>
              <div>Hotspots: <b>{status.hotspots}</b></div>
            </div>
          )}
        </div>

        <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 600 }}>Hotspots (top 10)</div>
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
            {metrics.length > 0 && (
              <select value={metric} onChange={(e) => setMetric(e.target.value)}>
                {metrics.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}
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
