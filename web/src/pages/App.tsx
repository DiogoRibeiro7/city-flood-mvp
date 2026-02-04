import React, { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import {
  Asset,
  fetchAssets,
  fetchCities,
  fetchCityStatus,
  fetchCitySummary,
  fetchEvents,
  fetchHotspots,
  fetchMetrics,
  fetchObservations,
  fetchScenarios,
} from "../api";
import "./App.css";

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
  const [events, setEvents] = useState<any[]>([]);
  const [rangeHours, setRangeHours] = useState<number>(24);
  const [loadingAssets, setLoadingAssets] = useState<boolean>(false);
  const [loadingSeries, setLoadingSeries] = useState<boolean>(false);
  const [loadingCity, setLoadingCity] = useState<boolean>(false);
  const [loadingHotspots, setLoadingHotspots] = useState<boolean>(false);
  const [loadingEvents, setLoadingEvents] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [tagFilter, setTagFilter] = useState<string>("");
  const [tagInput, setTagInput] = useState<string>("");
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("latest");
  const [eventType, setEventType] = useState<string>("");
  const [showPipes, setShowPipes] = useState<boolean>(true);
  const [showRiver, setShowRiver] = useState<boolean>(true);
  const [showGauges, setShowGauges] = useState<boolean>(true);
  const [showHotspots, setShowHotspots] = useState<boolean>(true);
  const [denseView, setDenseView] = useState<boolean>(false);
  const assetCache = useRef<Map<string, Asset[]>>(new Map());
  const eventCache = useRef<Map<string, any[]>>(new Map());

  useEffect(() => {
    fetchCities()
      .then((c) => {
        setCities(c);
        if (c.length) setCityId(c[0].city_id);
      })
      .catch((err) => {
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
    const handle = setTimeout(() => setTagFilter(tagInput), 400);
    return () => clearTimeout(handle);
  }, [tagInput]);

  useEffect(() => {
    if (!cityId) return;
    setLoadingCity(true);
    Promise.all([fetchCityStatus(cityId).then(setStatus), fetchCitySummary(cityId, 15).then(setSummary)])
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

    const bbox = "-8.75,41.05,-8.45,41.25";
    const tags = tagFilter
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const pipeLimit = denseView ? 1000 : 250;
    const riverLimit = 400;
    const gaugeLimit = 400;
    const cacheKey = `${cityId}|${tagFilter}|${denseView ? "dense" : "standard"}`;
    const cached = assetCache.current.get(cacheKey);
    if (cached) {
      setAssets(cached);
      return;
    }
    setLoadingAssets(true);
    Promise.all([
      fetchAssets(cityId, "pipe", bbox, tags, pipeLimit),
      fetchAssets(cityId, "river_segment", bbox, tags, riverLimit),
      fetchAssets(cityId, "rain_gauge", bbox, tags, gaugeLimit),
      fetchAssets(cityId, "river_gauge", bbox, tags, gaugeLimit),
    ])
      .then(([pipes, rivers, rain, river]) => {
        const merged = [...pipes, ...rivers, ...rain, ...river];
        assetCache.current.set(cacheKey, merged);
        setAssets(merged);
      })
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load assets");
        console.error(err);
      })
      .finally(() => setLoadingAssets(false));
  }, [cityId, tagFilter, denseView]);

  useEffect(() => {
    if (!cityId) return;
    const { from, to } = isoNowMinus(rangeHours);
    const cacheKey = `${cityId}|${rangeHours}|${eventType || "all"}`;
    const cached = eventCache.current.get(cacheKey);
    if (cached) {
      setEvents(cached);
      return;
    }
    setLoadingEvents(true);
    fetchEvents(cityId, from, to, eventType || undefined, 50)
      .then((rows) => {
        eventCache.current.set(cacheKey, rows);
        setEvents(rows);
      })
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load events");
        console.error(err);
      })
      .finally(() => setLoadingEvents(false));
  }, [cityId, rangeHours, eventType]);

  useEffect(() => {
    if (!selected) return;
    fetchMetrics(selected.asset_id, scenarioId)
      .then((m) => {
        setMetrics(m);
        if (m.includes("fill_ratio")) setMetric("fill_ratio");
        else if (m.length) setMetric(m[0]);
      })
      .catch((err) => {
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

  useEffect(() => {
    if (!selected) return;
    if (!assets.find((a) => a.asset_id === selected.asset_id)) {
      setSelected(null);
      setSeries([]);
      setMetrics([]);
    }
  }, [assets, selected]);

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

  const assetCounts = useMemo(
    () => ({
      pipes: assets.filter((a) => a.asset_type === "pipe").length,
      rivers: assets.filter((a) => a.asset_type === "river_segment").length,
      gauges: assets.filter((a) => a.asset_type === "rain_gauge" || a.asset_type === "river_gauge").length,
    }),
    [assets]
  );

  const cityName = useMemo(() => cities.find((c) => c.city_id === cityId)?.name ?? "", [cities, cityId]);

  const eventSummary = useMemo(() => {
    if (!events.length) return { critical: 0, moderate: 0 };
    return {
      critical: events.filter((e) => Number(e.severity) >= 3).length,
      moderate: events.filter((e) => Number(e.severity) === 2).length,
    };
  }, [events]);

  const onFeatureClick = (_: any, layer: any) => {
    layer.on("click", () => {
      const props: any = layer.feature?.properties;
      const a = assets.find((x) => x.asset_id === props?.asset_id) ?? null;
      setSelected(a);
    });
  };

  const topProps = useMemo(() => {
    if (!selected?.props) return [];
    return Object.entries(selected.props).slice(0, 6);
  }, [selected]);

  return (
    <div className="app-root">
      <section className="panel map-panel">
        <div className="map-header">
          <div>
            <div className="app-title">City Flood MVP</div>
            <div className="app-subtitle">Synthetic assets, telemetry, analytics, and QA</div>
          </div>
          <div className="header-actions">
            <div className="control-group">
              <label htmlFor="city-select">City</label>
              <select id="city-select" value={cityId} onChange={(e) => setCityId(e.target.value)}>
                {cities.map((c) => (
                  <option key={c.city_id} value={c.city_id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="control-group">
              <label htmlFor="scenario-select">Scenario</label>
              <select id="scenario-select" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
                <option value="latest">Latest</option>
                {scenarios.map((s) => (
                  <option key={s.scenario_id} value={s.scenario_id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="map-frame">
          <MapContainer center={[41.15, -8.61]} zoom={12} style={{ height: "100%", width: "100%" }}>
            <TileLayer
              attribution='&copy; OpenStreetMap contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {showRiver && (
              <GeoJSON
                data={featuresByType.river}
                onEachFeature={onFeatureClick}
                style={() => ({ color: "#1d4ed8", weight: 4, opacity: 0.85 })}
              />
            )}
            {showPipes && (
              <GeoJSON
                data={featuresByType.pipes}
                onEachFeature={onFeatureClick}
                style={(feature: any) => {
                  const id = feature?.properties?.asset_id;
                  const isSelected = selected?.asset_id === id;
                  const isHotspot = showHotspots && hotspotSet.has(id);
                  return {
                    color: isSelected ? "#e11d48" : isHotspot ? "#f59e0b" : "#334155",
                    weight: isSelected ? 5 : isHotspot ? 4 : 2,
                    opacity: isSelected ? 1 : 0.8,
                  };
                }}
              />
            )}
            {showGauges && (
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
            )}
          </MapContainer>

          <div className="map-toolbar">
            <button className={showRiver ? "toggle-on" : ""} onClick={() => setShowRiver((v) => !v)}>
              River
            </button>
            <button className={showPipes ? "toggle-on" : ""} onClick={() => setShowPipes((v) => !v)}>
              Pipes
            </button>
            <button className={showGauges ? "toggle-on" : ""} onClick={() => setShowGauges((v) => !v)}>
              Gauges
            </button>
            <button className={showHotspots ? "toggle-on" : ""} onClick={() => setShowHotspots((v) => !v)}>
              Hotspots
            </button>
          </div>

          <div className="map-status">
            <div className="status-pill">City<span>{cityName || "-"}</span></div>
            <div className="status-pill">Risk<span>{status?.risk ?? "-"}</span></div>
          </div>

          <div className="map-legend">
            <div className="legend-item">
              <span className="legend-swatch legend-river" /> River segments
            </div>
            <div className="legend-item">
              <span className="legend-swatch legend-pipe" /> Pipes
            </div>
            <div className="legend-item">
              <span className="legend-swatch legend-hotspot" /> Hotspots
            </div>
            <div className="legend-item">
              <span className="legend-swatch legend-selected" /> Selected
            </div>
            <div className="legend-item">
              <span className="legend-swatch legend-gauge" /> Gauges
            </div>
          </div>

          {loadingAssets && <div className="map-loading">Loading assets...</div>}
        </div>
      </section>

      <section className="side-panel">
        {errorMsg && <div className="error-banner">{errorMsg}</div>}

        <div className="card">
          <div className="card-title">Filters</div>
          <div className="control-group">
            <label htmlFor="tag-filter">Filter tags</label>
            <input
              id="tag-filter"
              type="text"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              placeholder="basin:basin_ne, neighborhood:neighborhood_1_2"
            />
          </div>
          <div className="metrics-grid">
            <div className="metric-tile">
              Pipes
              <div className="metric-value">{assetCounts.pipes}</div>
            </div>
            <div className="metric-tile">
              Rivers
              <div className="metric-value">{assetCounts.rivers}</div>
            </div>
            <div className="metric-tile">
              Gauges
              <div className="metric-value">{assetCounts.gauges}</div>
            </div>
            <div className="metric-tile">
              Assets loaded
              <div className="metric-value">{assets.length}</div>
            </div>
          </div>
          <div className="metrics-grid">
            <div className="metric-tile">
              Density
              <div className="asset-meta">
                <span className="badge">{denseView ? "Dense" : "Standard"}</span>
                <button onClick={() => setDenseView((v) => !v)}>{denseView ? "Reduce" : "Increase"}</button>
              </div>
            </div>
            <div className="metric-tile">
              Selection
              <div className="asset-meta">
                <span className="badge">{selected ? "Active" : "None"}</span>
                <button onClick={() => setSelected(null)} disabled={!selected}>
                  Clear
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-title">City pulse</div>
          {loadingCity && <div className="empty-state">Loading city summary...</div>}
          {!loadingCity && status && summary && (
            <div className="metrics-grid">
              <div className="metric-tile">
                Risk level
                <div className="metric-value">{status.risk}</div>
              </div>
              <div className="metric-tile">
                Active events
                <div className="metric-value">{status.active_events}</div>
              </div>
              <div className="metric-tile">
                Rain 15m avg
                <div className="metric-value">{Number(summary.rain_mmph).toFixed(1)} mm/h</div>
              </div>
              <div className="metric-tile">
                River 15m avg
                <div className="metric-value">{Number(summary.river_level_m).toFixed(2)} m</div>
              </div>
            </div>
          )}
        </div>

        {showHotspots && (
          <div className="card">
            <div className="card-title">Hotspots (top 10)</div>
            {loadingHotspots && <div className="empty-state">Loading hotspots...</div>}
            {!loadingHotspots && hotspots.length === 0 && <div className="empty-state">No hotspots yet.</div>}
            <ul className="hotspot-list">
              {hotspots.map((h) => (
                <li key={h.asset_id} className="hotspot-item">
                  <div>
                    <div>{h.asset_id}</div>
                    <div className="app-subtitle">score {Number(h.score).toFixed(1)}</div>
                  </div>
                  <button
                    onClick={() => {
                      const asset = assets.find((a) => a.asset_id === h.asset_id) ?? null;
                      setSelected(asset);
                    }}
                  >
                    Focus
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="card">
          <div className="card-title">Events</div>
          <div className="asset-meta">
            <div className="control-group">
              <label htmlFor="event-range">Range</label>
              <select
                id="event-range"
                value={rangeHours}
                onChange={(e) => setRangeHours(Number(e.target.value))}
              >
                <option value={6}>Last 6h</option>
                <option value={24}>Last 24h</option>
                <option value={168}>Last 7d</option>
              </select>
            </div>
            <div className="control-group">
              <label htmlFor="event-type">Type</label>
              <select id="event-type" value={eventType} onChange={(e) => setEventType(e.target.value)}>
                <option value="">All</option>
                <option value="rain">Rain</option>
                <option value="overflow">Overflow</option>
              </select>
            </div>
          </div>
          <div className="metrics-grid">
            <div className="metric-tile">
              Total events
              <div className="metric-value">{events.length}</div>
            </div>
            <div className="metric-tile">
              Critical
              <div className="metric-value">{eventSummary.critical}</div>
            </div>
            <div className="metric-tile">
              Moderate
              <div className="metric-value">{eventSummary.moderate}</div>
            </div>
          </div>
          {loadingEvents && <div className="empty-state">Loading events...</div>}
          {!loadingEvents && events.length === 0 && <div className="empty-state">No events in range.</div>}
          <ul className="event-list">
            {events.slice(0, 6).map((evt) => (
              <li key={evt.event_id} className="event-item">
                <div>
                  <div className="event-title">{evt.event_type}</div>
                  <div className="app-subtitle">
                    {evt.start_ts} → {evt.end_ts}
                  </div>
                </div>
                <span className={`event-sev event-sev-${Number(evt.severity)}`}>S{evt.severity}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card asset-detail">
          <div className="asset-meta">
            <div>
              <div className="card-title">Asset detail</div>
              <div className="app-subtitle">{selected ? selected.name : "Click an asset on the map"}</div>
            </div>
            <div className="asset-badges">
              {selected && <span className="badge">{selected.asset_type}</span>}
              {selected && hotspotSet.has(selected.asset_id) && <span className="badge badge-accent">Hotspot</span>}
            </div>
          </div>

          <div className="asset-meta">
            <div className="control-group">
              <label htmlFor="range-select">Range</label>
              <select id="range-select" value={rangeHours} onChange={(e) => setRangeHours(Number(e.target.value))}>
                <option value={6}>Last 6h</option>
                <option value={24}>Last 24h</option>
                <option value={168}>Last 7d</option>
              </select>
            </div>
            {metrics.length > 0 && (
              <div className="control-group">
                <label htmlFor="metric-select">Metric</label>
                <select id="metric-select" value={metric} onChange={(e) => setMetric(e.target.value)}>
                  {metrics.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="chart-wrap">
            {selected ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series}>
                  <XAxis dataKey="ts" hide />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" dot={false} stroke="#2563eb" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">No asset selected.</div>
            )}
          </div>
          {loadingSeries && <div className="empty-state">Loading chart...</div>}
          {!loadingSeries && selected && series.length === 0 && <div className="empty-state">No data in range.</div>}

          {selected && (
            <div className="metrics-grid">
              <div className="metric-tile">
                Asset ID
                <div className="metric-value">{selected.asset_id}</div>
              </div>
              <div className="metric-tile">
                Tags
                <div className="metric-value">{Object.keys(selected.props ?? {}).length}</div>
              </div>
            </div>
          )}

          {selected && topProps.length > 0 && (
            <div>
              <div className="app-subtitle">Key props</div>
              <div className="metrics-grid">
                {topProps.map(([key, value]) => (
                  <div className="metric-tile" key={key}>
                    {key}
                    <div className="metric-value">{String(value)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
