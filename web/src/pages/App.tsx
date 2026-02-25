import React, { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import {
  Asset,
  Note,
  fetchAssets,
  fetchCities,
  fetchCityStatus,
  fetchCitySummary,
  createNote,
  createReportJob,
  deleteNote,
  downloadJob,
  fetchEvents,
  fetchJob,
  fetchHotspots,
  fetchMetrics,
  fetchNote,
  fetchObservations,
  fetchObservationsCompare,
  fetchNotes,
  fetchScenarios,
  setAuthToken,
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
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);
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
  const [timelineView, setTimelineView] = useState<"timeline" | "compact">("timeline");
  const [timelineLimit, setTimelineLimit] = useState<number>(8);
  const [reportIncludeSummary, setReportIncludeSummary] = useState<boolean>(true);
  const [reportIncludeHotspots, setReportIncludeHotspots] = useState<boolean>(true);
  const [reportIncludeEvents, setReportIncludeEvents] = useState<boolean>(true);
  const [reportBusy, setReportBusy] = useState<boolean>(false);
  const [reportStatus, setReportStatus] = useState<string>("");
  const [role, setRole] = useState<"viewer" | "analyst" | "admin">("viewer");
  const [storyTitle, setStoryTitle] = useState<string>("");
  const [savedViews, setSavedViews] = useState<any[]>([]);
  const [jwtToken, setJwtToken] = useState<string>("");
  const [showPipes, setShowPipes] = useState<boolean>(true);
  const [showRiver, setShowRiver] = useState<boolean>(true);
  const [showGauges, setShowGauges] = useState<boolean>(true);
  const [showHotspots, setShowHotspots] = useState<boolean>(true);
  const [denseView, setDenseView] = useState<boolean>(false);
  const [executiveMode, setExecutiveMode] = useState<boolean>(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [noteTitle, setNoteTitle] = useState<string>("");
  const [noteBody, setNoteBody] = useState<string>("");
  const [noteAuthor, setNoteAuthor] = useState<string>("Ops");
  const [attachAsset, setAttachAsset] = useState<boolean>(true);
  const [attachEvent, setAttachEvent] = useState<boolean>(false);
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null);
  const [compareBaseScenario, setCompareBaseScenario] = useState<string>("latest");
  const [compareScenario, setCompareScenario] = useState<string>("");
  const [compareSeries, setCompareSeries] = useState<
    { ts: string; base: number | null; compare: number | null; delta: number | null }[]
  >([]);
  const [loadingCompare, setLoadingCompare] = useState<boolean>(false);
  const [templateType, setTemplateType] = useState<string>("storm_response");
  const [templateDraft, setTemplateDraft] = useState<string>("");
  const assetCache = useRef<Map<string, Asset[]>>(new Map());
  const eventCache = useRef<Map<string, any[]>>(new Map());

  useEffect(() => {
    const savedRole = window.localStorage.getItem("floodmvp.role");
    if (savedRole === "viewer" || savedRole === "analyst" || savedRole === "admin") {
      setRole(savedRole);
    }
    const storedViews = window.localStorage.getItem("floodmvp.savedViews");
    if (storedViews) {
      try {
        const parsed = JSON.parse(storedViews);
        if (Array.isArray(parsed)) setSavedViews(parsed);
      } catch {
        // ignore
      }
    }
    const storedToken = window.localStorage.getItem("floodmvp.jwt");
    if (storedToken) setJwtToken(storedToken);
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
    const params = new URLSearchParams(window.location.search);
    const city = params.get("city");
    const scenario = params.get("scenario");
    const range = params.get("range");
    const event = params.get("event");
    const tags = params.get("tags");
    const note = params.get("note");
    const showRiverParam = params.get("river");
    const showPipesParam = params.get("pipes");
    const showGaugesParam = params.get("gauges");
    const showHotspotsParam = params.get("hotspots");
    const denseParam = params.get("dense");
    const selectedAssetParam = params.get("asset");
    const selectedEventParam = params.get("event_id");
    if (city) setCityId(city);
    if (scenario) setScenarioId(scenario);
    if (range && !Number.isNaN(Number(range))) setRangeHours(Number(range));
    if (event !== null) setEventType(event);
    if (tags) {
      setTagInput(tags);
      setTagFilter(tags);
    }
    if (note) setActiveNoteId(note);
    if (showRiverParam) setShowRiver(showRiverParam === "1");
    if (showPipesParam) setShowPipes(showPipesParam === "1");
    if (showGaugesParam) setShowGauges(showGaugesParam === "1");
    if (showHotspotsParam) setShowHotspots(showHotspotsParam === "1");
    if (denseParam) setDenseView(denseParam === "1");
    if (selectedAssetParam) {
      setSelected((prev: Asset | null) => prev ?? ({ asset_id: selectedAssetParam } as Asset));
    }
    if (selectedEventParam) {
      setSelectedEvent((prev: any | null) => prev ?? ({ event_id: selectedEventParam } as any));
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("floodmvp.role", role);
  }, [role]);

  useEffect(() => {
    window.localStorage.setItem("floodmvp.savedViews", JSON.stringify(savedViews));
  }, [savedViews]);

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
    if (!cityId) return;
    fetchNotes(cityId)
      .then(setNotes)
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load notes");
        console.error(err);
      });
  }, [cityId]);

  useEffect(() => {
    if (!activeNoteId) return;
    const exists = notes.some((n) => n.note_id === activeNoteId);
    if (exists) return;
    fetchNote(activeNoteId)
      .then((note) => setNotes((prev) => [note, ...prev]))
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load shared note");
        console.error(err);
      });
  }, [activeNoteId, notes]);

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
    if (!selected || !metric || !compareScenario) {
      setCompareSeries([]);
      return;
    }
    const { from, to } = isoNowMinus(rangeHours);
    setLoadingCompare(true);
    fetchObservationsCompare(
      selected.asset_id,
      metric,
      from,
      to,
      compareBaseScenario,
      compareScenario
    )
      .then((r) => {
        const rows = (r.series ?? []).map((row: any) => ({
          ts: row.ts,
          base: row.base ?? null,
          compare: row.compare ?? null,
          delta: row.delta ?? null,
        }));
        setCompareSeries(rows);
      })
      .catch((err) => {
        setErrorMsg(err?.message ?? "Failed to load scenario comparison");
        console.error(err);
      })
      .finally(() => setLoadingCompare(false));
  }, [selected, metric, rangeHours, compareScenario, compareBaseScenario]);

  useEffect(() => {
    if (!compareScenario && scenarios.length) {
      setCompareScenario(scenarios[0].scenario_id);
    }
  }, [scenarios, compareScenario]);

  useEffect(() => {
    if (!selected) return;
    if (!assets.find((a) => a.asset_id === selected.asset_id)) {
      setSelected(null);
      setSeries([]);
      setMetrics([]);
    }
  }, [assets, selected]);

  useEffect(() => {
    if (!selectedEvent) return;
    if (!events.find((e) => e.event_id === selectedEvent.event_id)) {
      setSelectedEvent(null);
    }
  }, [events, selectedEvent]);

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

  const timelineEvents = useMemo(() => {
    return [...events].sort(
      (a, b) => new Date(b.start_ts).getTime() - new Date(a.start_ts).getTime()
    );
  }, [events]);

  const formatTime = (iso: string) => {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", month: "short", day: "2-digit" });
  };

  const formatShort = (iso: string) => {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };

  const focusEventAsset = (evt: any) => {
    const assetId = evt?.asset_ids?.[0];
    if (!assetId) return;
    const asset = assets.find((a) => a.asset_id === assetId) ?? null;
    if (asset) setSelected(asset);
  };

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

  const filteredNotes = useMemo(() => {
    if (!cityId) return notes;
    return notes.filter((n) => n.city_id === cityId);
  }, [notes, cityId]);

  const activeNote = useMemo(
    () => filteredNotes.find((n) => n.note_id === activeNoteId) ?? null,
    [filteredNotes, activeNoteId]
  );

  const compareStats = useMemo(() => {
    if (!compareSeries.length) return null;
    const deltas = compareSeries.map((r) => r.delta).filter((v) => v !== null) as number[];
    if (!deltas.length) return null;
    const avg = deltas.reduce((a, b) => a + b, 0) / deltas.length;
    const max = Math.max(...deltas);
    const min = Math.min(...deltas);
    return { avg, max, min };
  }, [compareSeries]);

  const templateDraftTitle = useMemo(() => {
    const base = cityName || cityId || "City";
    const assetLabel = selected?.name ? ` · ${selected.name}` : "";
    const eventLabel = selectedEvent?.event_type ? ` · ${selectedEvent.event_type}` : "";
    return `${base}${assetLabel}${eventLabel}`;
  }, [cityName, cityId, selected, selectedEvent]);

  const buildTemplate = () => {
    const now = new Date().toISOString();
    const assetLine = selected ? `Asset: ${selected.name} (${selected.asset_id})` : "Asset: -";
    const eventLine = selectedEvent
      ? `Event: ${selectedEvent.event_type} (S${selectedEvent.severity}) ${formatTime(
          selectedEvent.start_ts
        )} → ${formatTime(selectedEvent.end_ts)}`
      : "Event: -";
    const baseHeader = `Incident Report\nCity: ${cityName || cityId}\nGenerated: ${now}\n${assetLine}\n${eventLine}\n\n`;
    if (templateType === "asset_failure") {
      return (
        baseHeader +
        "Summary:\n- What failed and where\n- Immediate impact\n\n" +
        "Root Cause (initial):\n- Suspected cause\n- Evidence and signals\n\n" +
        "Response Actions:\n- Mitigations executed\n- Owner + ETA\n\n" +
        "Recovery Plan:\n- Repair steps\n- Risk to service\n\n" +
        "Next Updates:\n- Next stakeholder update time\n"
      );
    }
    if (templateType === "maintenance") {
      return (
        baseHeader +
        "Summary:\n- Planned work scope\n- Affected assets\n\n" +
        "Impact Assessment:\n- Service risk\n- Customer impact\n\n" +
        "Execution Plan:\n- Schedule\n- Required crews\n\n" +
        "Backout Plan:\n- Rollback steps\n- Escalation contacts\n\n" +
        "Follow-up:\n- Verification checks\n- Metrics to monitor\n"
      );
    }
    return (
      baseHeader +
      "Summary:\n- Situation overview\n- Impacted zones\n\n" +
      "Storm Response:\n- Actions taken\n- Field status\n\n" +
      "Operational Impact:\n- Service disruptions\n- Safety risks\n\n" +
      "Next Steps:\n- Immediate priorities\n- Stakeholder updates\n"
    );
  };

  return (
    <div className={`app-root ${executiveMode ? "executive" : ""}`}>
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
            <div className="control-group">
              <label htmlFor="role-select">Role</label>
              <select
                id="role-select"
                value={role}
                onChange={(e) => setRole(e.target.value as "viewer" | "analyst" | "admin")}
              >
                <option value="viewer">Viewer</option>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div className="control-group">
              <label htmlFor="exec-toggle">View</label>
              <button
                id="exec-toggle"
                className={executiveMode ? "toggle-on" : ""}
                onClick={() => setExecutiveMode((v) => !v)}
              >
                {executiveMode ? "Executive" : "Standard"}
              </button>
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

        {executiveMode && (
          <div className="card exec-card">
            <div className="card-title">Executive brief</div>
            <div className="exec-grid">
              <div>
                <div className="exec-label">Risk level</div>
                <div className="exec-value">{status?.risk ?? "-"}</div>
              </div>
              <div>
                <div className="exec-label">Active events</div>
                <div className="exec-value">{status?.active_events ?? 0}</div>
              </div>
              <div>
                <div className="exec-label">Hotspots</div>
                <div className="exec-value">{hotspots.length}</div>
              </div>
              <div>
                <div className="exec-label">Rain (15m)</div>
                <div className="exec-value">
                  {summary ? `${Number(summary.rain_mmph ?? 0).toFixed(1)} mm/h` : "-"}
                </div>
              </div>
              <div>
                <div className="exec-label">River (15m)</div>
                <div className="exec-value">
                  {summary ? `${Number(summary.river_level_m ?? 0).toFixed(2)} m` : "-"}
                </div>
              </div>
              <div>
                <div className="exec-label">Critical events</div>
                <div className="exec-value">{eventSummary.critical}</div>
              </div>
            </div>
            <div className="exec-foot">
              Updated {new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
            </div>
          </div>
        )}

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

        <div className="card timeline-card">
          <div className="card-title">Incident timeline</div>
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
            <div className="control-group">
              <label htmlFor="timeline-view">View</label>
              <select
                id="timeline-view"
                value={timelineView}
                onChange={(e) => setTimelineView(e.target.value as "timeline" | "compact")}
              >
                <option value="timeline">Timeline</option>
                <option value="compact">Compact list</option>
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
          {loadingEvents && <div className="empty-state">Loading timeline...</div>}
          {!loadingEvents && events.length === 0 && <div className="empty-state">No incidents in range.</div>}
          {timelineView === "timeline" ? (
            <div className="timeline">
              {timelineEvents.slice(0, timelineLimit).map((evt) => (
                <button
                  key={evt.event_id}
                  className={`timeline-item ${selectedEvent?.event_id === evt.event_id ? "active" : ""}`}
                  onClick={() => setSelectedEvent(evt)}
                >
                  <span className={`timeline-dot timeline-dot-${evt.event_type}`} />
                  <div className="timeline-content">
                    <div className="timeline-title">{evt.event_type}</div>
                    <div className="app-subtitle">
                      {formatTime(evt.start_ts)} → {formatTime(evt.end_ts)}
                    </div>
                    <div className="timeline-summary">{evt.summary}</div>
                  </div>
                  <span className={`event-sev event-sev-${Number(evt.severity)}`}>S{evt.severity}</span>
                </button>
              ))}
            </div>
          ) : (
            <ul className="compact-list">
              {timelineEvents.slice(0, timelineLimit).map((evt) => (
                <li key={evt.event_id} className="compact-item">
                  <button
                    className={`compact-button ${selectedEvent?.event_id === evt.event_id ? "active" : ""}`}
                    onClick={() => setSelectedEvent(evt)}
                  >
                    <span className={`timeline-dot timeline-dot-${evt.event_type}`} />
                    <div>
                      <div className="timeline-title">{evt.event_type}</div>
                      <div className="app-subtitle">
                        {formatTime(evt.start_ts)} → {formatTime(evt.end_ts)}
                      </div>
                    </div>
                    <span className={`event-sev event-sev-${Number(evt.severity)}`}>S{evt.severity}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {timelineEvents.length > timelineLimit && (
            <div className="timeline-actions">
              <button onClick={() => setTimelineLimit((v) => v + 8)}>Show more</button>
            </div>
          )}
          {selectedEvent && (
            <div className="timeline-detail">
              <div className="detail-row">
                <div>
                  <div className="app-subtitle">Selected incident</div>
                  <div className="detail-title">{selectedEvent.event_type}</div>
                </div>
                <span className={`event-sev event-sev-${Number(selectedEvent.severity)}`}>
                  S{selectedEvent.severity}
                </span>
              </div>
              <div className="detail-meta">
                <div>
                  <span>Window</span>
                  <strong>{formatTime(selectedEvent.start_ts)} → {formatTime(selectedEvent.end_ts)}</strong>
                </div>
                <div>
                  <span>Confidence</span>
                  <strong>{Number(selectedEvent.confidence ?? 0).toFixed(2)}</strong>
                </div>
                <div>
                  <span>Assets</span>
                  <strong>{(selectedEvent.asset_ids ?? []).length}</strong>
                </div>
              </div>
              <div className="detail-summary">{selectedEvent.summary}</div>
              <div className="detail-actions">
                <button onClick={() => setSelectedEvent(null)}>Clear</button>
                <button onClick={() => focusEventAsset(selectedEvent)}>Focus asset</button>
              </div>
            </div>
          )}
        </div>

        <div className="card report-card">
          <div className="card-title">Report builder</div>
          {role === "viewer" && (
            <div className="empty-state">Report builder available for analyst/admin roles.</div>
          )}
          <div className="control-group">
            <label htmlFor="jwt-token">JWT token</label>
            <input
              id="jwt-token"
              type="text"
              value={jwtToken}
              onChange={(e) => {
                const next = e.target.value;
                setJwtToken(next);
                setAuthToken(next);
              }}
              placeholder="Paste bearer token"
            />
          </div>
          <div className="asset-meta">
            <div className="control-group">
              <label htmlFor="report-range">Range</label>
              <select
                id="report-range"
                value={rangeHours}
                onChange={(e) => setRangeHours(Number(e.target.value))}
                disabled={role === "viewer"}
              >
                <option value={6}>Last 6h</option>
                <option value={24}>Last 24h</option>
                <option value={168}>Last 7d</option>
              </select>
            </div>
            <div className="control-group">
              <label htmlFor="report-type">Type</label>
              <select
                id="report-type"
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
                disabled={role === "viewer"}
              >
                <option value="">All</option>
                <option value="rain">Rain</option>
                <option value="overflow">Overflow</option>
              </select>
            </div>
          </div>
          <div className="report-options">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={reportIncludeSummary}
                onChange={(e) => setReportIncludeSummary(e.target.checked)}
                disabled={role === "viewer"}
              />
              Include summary
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={reportIncludeHotspots}
                onChange={(e) => setReportIncludeHotspots(e.target.checked)}
                disabled={role === "viewer"}
              />
              Include hotspots
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={reportIncludeEvents}
                onChange={(e) => setReportIncludeEvents(e.target.checked)}
                disabled={role === "viewer"}
              />
              Include events
            </label>
          </div>
          <div className="report-actions">
            <button
              disabled={reportBusy || !cityId || role === "viewer"}
              onClick={async () => {
                if (!cityId) return;
                setReportBusy(true);
                setReportStatus("Queuing report...");
                try {
                  const { from, to } = isoNowMinus(rangeHours);
                  const job = await createReportJob({
                    city_id: cityId,
                    from,
                    to,
                    event_type: eventType || undefined,
                    top_hotspots: 10,
                    include_summary: reportIncludeSummary,
                    include_hotspots: reportIncludeHotspots,
                    include_events: reportIncludeEvents,
                  });

                  const jobId = job.job_id;
                  const started = Date.now();
                  let status = "queued";
                  while (status === "queued" || status === "running") {
                    if (Date.now() - started > 120000) {
                      throw new Error("Report job timed out");
                    }
                    await new Promise((r) => setTimeout(r, 2000));
                    const current = await fetchJob(jobId);
                    status = current.status;
                    setReportStatus(`Report status: ${status}`);
                  }
                  if (status !== "completed") {
                    throw new Error(`Report failed (${status})`);
                  }
                  const blob = await downloadJob(jobId);
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `report_${cityId}_${new Date().toISOString().slice(0, 10)}.csv`;
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                  URL.revokeObjectURL(url);
                  setReportStatus("Report downloaded");
                } finally {
                  setReportBusy(false);
                  setTimeout(() => setReportStatus(""), 3000);
                }
              }}
            >
              Download CSV
            </button>
            <button
              disabled={reportBusy || !cityId || role === "viewer"}
              onClick={async () => {
                if (!cityId) return;
                setReportBusy(true);
                try {
                  const { from, to } = isoNowMinus(rangeHours);
                  const [freshSummary, freshStatus, freshHotspots, freshEvents] = await Promise.all([
                    fetchCitySummary(cityId, 15),
                    fetchCityStatus(cityId),
                    fetchHotspots(cityId, 10),
                    fetchEvents(cityId, from, to, eventType || undefined, 200),
                  ]);
                  const win = window.open("", "_blank");
                  if (!win) return;
                  const sections: string[] = [];
                  if (reportIncludeSummary) {
                    sections.push(`
                      <section>
                        <h2>Summary</h2>
                        <div class="summary-grid">
                          <div><span>Risk</span><strong>${freshStatus?.risk ?? "-"}</strong></div>
                          <div><span>Active events</span><strong>${freshStatus?.active_events ?? "-"}</strong></div>
                          <div><span>Rain 15m avg</span><strong>${Number(freshSummary?.rain_mmph ?? 0).toFixed(1)} mm/h</strong></div>
                          <div><span>River 15m avg</span><strong>${Number(freshSummary?.river_level_m ?? 0).toFixed(2)} m</strong></div>
                        </div>
                      </section>
                    `);
                  }
                  if (reportIncludeHotspots) {
                    sections.push(`
                      <section>
                        <h2>Hotspots</h2>
                        <table>
                          <thead><tr><th>Asset</th><th>Score</th><th>Confidence</th></tr></thead>
                          <tbody>
                            ${(freshHotspots ?? [])
                              .map(
                                (h: any) =>
                                  `<tr><td>${h.asset_id}</td><td>${Number(h.score).toFixed(1)}</td><td>${Number(h.confidence ?? 0).toFixed(2)}</td></tr>`
                              )
                              .join("")}
                          </tbody>
                        </table>
                      </section>
                    `);
                  }
                  if (reportIncludeEvents) {
                    sections.push(`
                      <section>
                        <h2>Events</h2>
                        <table>
                          <thead><tr><th>Type</th><th>Severity</th><th>Window</th><th>Assets</th></tr></thead>
                          <tbody>
                            ${(freshEvents ?? [])
                              .map(
                                (e: any) =>
                                  `<tr><td>${e.event_type}</td><td>S${e.severity}</td><td>${formatTime(e.start_ts)} → ${formatTime(e.end_ts)}</td><td>${(e.asset_ids ?? []).length}</td></tr>`
                              )
                              .join("")}
                          </tbody>
                        </table>
                      </section>
                    `);
                  }

                  win.document.write(`
                    <html>
                      <head>
                        <title>City Flood MVP Report</title>
                        <style>
                          body { font-family: "Space Grotesk", Arial, sans-serif; color: #0f172a; padding: 24px; }
                          h1 { font-size: 22px; margin-bottom: 4px; }
                          h2 { font-size: 16px; margin: 18px 0 8px; }
                          .meta { font-size: 12px; color: #64748b; margin-bottom: 16px; }
                          .summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
                          .summary-grid div { border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px; background: #f8fafc; }
                          .summary-grid span { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; }
                          table { width: 100%; border-collapse: collapse; font-size: 12px; }
                          th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; }
                          th { background: #f1f5f9; }
                          section { margin-bottom: 18px; }
                        </style>
                      </head>
                      <body>
                        <h1>City Flood MVP Report</h1>
                        <div class="meta">
                          City: ${cityName || cityId}<br/>
                          Window: ${from} → ${to}<br/>
                          Generated: ${new Date().toISOString()}
                        </div>
                        ${sections.join("")}
                      </body>
                    </html>
                  `);
                  win.document.close();
                  win.focus();
                  win.print();
                } finally {
                  setReportBusy(false);
                }
              }}
            >
              Print PDF
            </button>
          </div>
          {reportStatus && <div className="report-status">{reportStatus}</div>}
        </div>

        <div className="card template-card">
          <div className="card-title">Incident templates</div>
          <div className="asset-meta">
            <div className="control-group grow">
              <label htmlFor="template-type">Template</label>
              <select
                id="template-type"
                value={templateType}
                onChange={(e) => setTemplateType(e.target.value)}
              >
                <option value="storm_response">Storm response</option>
                <option value="asset_failure">Asset failure</option>
                <option value="maintenance">Maintenance</option>
              </select>
            </div>
            <button
              onClick={() => {
                setTemplateDraft(buildTemplate());
              }}
            >
              Generate
            </button>
          </div>
          <div className="control-group">
            <label htmlFor="template-title">Title</label>
            <input id="template-title" type="text" value={templateDraftTitle} readOnly />
          </div>
          <textarea
            className="template-area"
            value={templateDraft}
            onChange={(e) => setTemplateDraft(e.target.value)}
            placeholder="Generate a template to start drafting."
          />
          <div className="report-actions">
            <button
              onClick={() => {
                if (!templateDraft) return;
                navigator.clipboard?.writeText(templateDraft);
                setErrorMsg("Template copied to clipboard.");
                setTimeout(() => setErrorMsg(null), 2500);
              }}
            >
              Copy
            </button>
            <button
              onClick={() => {
                if (!templateDraft) return;
                const win = window.open("", "_blank");
                if (!win) return;
                win.document.write(`
                  <html>
                    <head>
                      <title>Incident Report</title>
                      <style>
                        body { font-family: "Space Grotesk", Arial, sans-serif; color: #0f172a; padding: 24px; }
                        h1 { font-size: 20px; margin-bottom: 6px; }
                        pre { white-space: pre-wrap; font-size: 12px; background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 12px; }
                      </style>
                    </head>
                    <body>
                      <h1>${templateDraftTitle}</h1>
                      <pre>${templateDraft.replace(/</g, "&lt;")}</pre>
                    </body>
                  </html>
                `);
                win.document.close();
                win.focus();
                win.print();
              }}
            >
              Print
            </button>
          </div>
        </div>

        <div className="card notes-card">
          <div className="card-title">Collaborative notes</div>
          <div className="asset-meta">
            <div className="control-group grow">
              <label htmlFor="note-title">Title</label>
              <input
                id="note-title"
                type="text"
                value={noteTitle}
                onChange={(e) => setNoteTitle(e.target.value)}
                placeholder="Short summary"
              />
            </div>
            <div className="control-group">
              <label htmlFor="note-author">Author</label>
              <input
                id="note-author"
                type="text"
                value={noteAuthor}
                onChange={(e) => setNoteAuthor(e.target.value)}
              />
            </div>
          </div>
          <textarea
            className="note-area"
            value={noteBody}
            onChange={(e) => setNoteBody(e.target.value)}
            placeholder="Add context, decisions, or field updates."
          />
          <div className="note-attachments">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={attachAsset}
                onChange={(e) => setAttachAsset(e.target.checked)}
              />
              Attach to asset
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={attachEvent}
                onChange={(e) => setAttachEvent(e.target.checked)}
              />
              Attach to event
            </label>
          </div>
          <div className="report-actions">
            <button
              onClick={() => {
                if (!noteBody.trim() || !cityId) return;
                createNote({
                  city_id: cityId,
                  asset_id: attachAsset ? selected?.asset_id ?? null : null,
                  event_id: attachEvent ? selectedEvent?.event_id ?? null : null,
                  title: noteTitle || `Note ${filteredNotes.length + 1}`,
                  body: noteBody,
                  author: noteAuthor || "Ops",
                })
                  .then((newNote) => {
                    setNotes((prev) => [newNote, ...prev]);
                    setNoteTitle("");
                    setNoteBody("");
                    setActiveNoteId(newNote.note_id);
                  })
                  .catch((err) => {
                    setErrorMsg(err?.message ?? "Failed to create note");
                    console.error(err);
                  });
              }}
            >
              Add note
            </button>
            <button
              onClick={() => {
                setNoteTitle("");
                setNoteBody("");
              }}
            >
              Clear
            </button>
          </div>
          {filteredNotes.length === 0 && <div className="empty-state">No notes for this city yet.</div>}
          {filteredNotes.length > 0 && (
            <ul className="note-list">
              {filteredNotes.slice(0, 6).map((n) => (
                <li
                  key={n.note_id}
                  className={`note-item ${n.note_id === activeNoteId ? "active" : ""}`}
                >
                  <div>
                    <div className="note-title">{n.title}</div>
                    <div className="note-meta">
                      {n.author} · {formatShort(n.created_at)}
                    </div>
                  </div>
                  <div className="note-actions">
                    <button onClick={() => setActiveNoteId(n.note_id)}>Open</button>
                    <button
                      onClick={() => {
                        const params = new URLSearchParams(window.location.search);
                        params.set("note", n.note_id);
                        const url = `${window.location.origin}?${params.toString()}`;
                        navigator.clipboard?.writeText(url);
                        setErrorMsg("Note link copied to clipboard.");
                        setTimeout(() => setErrorMsg(null), 2500);
                      }}
                    >
                      Share
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {activeNote && (
            <div className="note-detail">
              <div className="detail-row">
                <div className="detail-title">{activeNote.title}</div>
                <span className="badge">{activeNote.author}</span>
              </div>
              <div className="app-subtitle">{formatTime(activeNote.created_at)}</div>
              <div className="note-body">{activeNote.body}</div>
              <div className="detail-actions">
                {activeNote.asset_id && (
                  <button
                    onClick={() => {
                      const asset = assets.find((a) => a.asset_id === activeNote.asset_id);
                      if (asset) setSelected(asset);
                    }}
                  >
                    Focus asset
                  </button>
                )}
                {activeNote.event_id && (
                  <button
                    onClick={() => {
                      const evt = events.find((e) => e.event_id === activeNote.event_id);
                      if (evt) setSelectedEvent(evt);
                    }}
                  >
                    Focus event
                  </button>
                )}
                <button
                  onClick={() => {
                    deleteNote(activeNote.note_id)
                      .then(() => {
                        setNotes((prev) => prev.filter((n) => n.note_id !== activeNote.note_id));
                        setActiveNoteId(null);
                      })
                      .catch((err) => {
                        setErrorMsg(err?.message ?? "Failed to delete note");
                        console.error(err);
                      });
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="card story-card">
          <div className="card-title">Storytelling</div>
          <div className="asset-meta">
            <div className="control-group grow">
              <label htmlFor="story-title">Save view</label>
              <input
                id="story-title"
                type="text"
                placeholder="e.g. Downtown overflow sweep"
                value={storyTitle}
                onChange={(e) => setStoryTitle(e.target.value)}
              />
            </div>
            <button
              onClick={() => {
                if (!cityId) return;
                const view = {
                  id: `view_${Date.now()}`,
                  title: storyTitle || `View ${savedViews.length + 1}`,
                  cityId,
                  scenarioId,
                  rangeHours,
                  eventType,
                  tagFilter,
                  showRiver,
                  showPipes,
                  showGauges,
                  showHotspots,
                  denseView,
                  selectedAssetId: selected?.asset_id ?? null,
                  selectedEventId: selectedEvent?.event_id ?? null,
                };
                setSavedViews((prev) => [view, ...prev]);
                setStoryTitle("");
              }}
            >
              Save
            </button>
          </div>
          {savedViews.length === 0 && <div className="empty-state">No saved views yet.</div>}
          <ul className="story-list">
            {savedViews.map((view) => (
              <li key={view.id} className="story-item">
                <div>
                  <div className="story-title">{view.title}</div>
                  <div className="app-subtitle">{view.cityId} · {view.rangeHours}h</div>
                </div>
                <div className="story-actions">
                  <button
                    onClick={() => {
                      setCityId(view.cityId);
                      setScenarioId(view.scenarioId);
                      setRangeHours(view.rangeHours);
                      setEventType(view.eventType);
                      setTagInput(view.tagFilter || "");
                      setTagFilter(view.tagFilter || "");
                      setShowRiver(view.showRiver);
                      setShowPipes(view.showPipes);
                      setShowGauges(view.showGauges);
                      setShowHotspots(view.showHotspots);
                      setDenseView(view.denseView);
                      setSelected(view.selectedAssetId ? ({ asset_id: view.selectedAssetId } as any) : null);
                      setSelectedEvent(view.selectedEventId ? ({ event_id: view.selectedEventId } as any) : null);
                    }}
                  >
                    Apply
                  </button>
                  <button
                    onClick={() => {
                      const params = new URLSearchParams();
                      params.set("city", view.cityId);
                      params.set("scenario", view.scenarioId);
                      params.set("range", String(view.rangeHours));
                      params.set("event", view.eventType ?? "");
                      if (view.tagFilter) params.set("tags", view.tagFilter);
                      params.set("river", view.showRiver ? "1" : "0");
                      params.set("pipes", view.showPipes ? "1" : "0");
                      params.set("gauges", view.showGauges ? "1" : "0");
                      params.set("hotspots", view.showHotspots ? "1" : "0");
                      params.set("dense", view.denseView ? "1" : "0");
                      if (view.selectedAssetId) params.set("asset", view.selectedAssetId);
                      if (view.selectedEventId) params.set("event_id", view.selectedEventId);
                      const url = `${window.location.origin}?${params.toString()}`;
                      navigator.clipboard?.writeText(url);
                      setErrorMsg("Shareable link copied to clipboard.");
                      setTimeout(() => setErrorMsg(null), 3000);
                    }}
                  >
                    Share
                  </button>
                  <button
                    onClick={() => {
                      setSavedViews((prev) => prev.filter((v) => v.id !== view.id));
                    }}
                  >
                    Remove
                  </button>
                </div>
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

          <div className="compare-panel">
            <div className="compare-header">
              <div>
                <div className="card-title">Scenario comparison</div>
                <div className="app-subtitle">Compare the selected metric across two scenarios.</div>
              </div>
              <button
                onClick={() => {
                  const nextBase = compareScenario;
                  const nextCompare = compareBaseScenario;
                  setCompareBaseScenario(nextBase || "latest");
                  setCompareScenario(nextCompare || "latest");
                }}
              >
                Swap
              </button>
            </div>
            <div className="asset-meta">
              <div className="control-group">
                <label htmlFor="base-scenario">Base</label>
                <select
                  id="base-scenario"
                  value={compareBaseScenario}
                  onChange={(e) => setCompareBaseScenario(e.target.value)}
                >
                  <option value="latest">Latest</option>
                  {scenarios.map((s) => (
                    <option key={`base-${s.scenario_id}`} value={s.scenario_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="control-group">
                <label htmlFor="compare-scenario">Compare</label>
                <select
                  id="compare-scenario"
                  value={compareScenario}
                  onChange={(e) => setCompareScenario(e.target.value)}
                >
                  <option value="latest">Latest</option>
                  {scenarios.map((s) => (
                    <option key={`cmp-${s.scenario_id}`} value={s.scenario_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="compare-chart">
              {compareSeries.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={compareSeries}>
                    <XAxis dataKey="ts" hide />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="base" dot={false} stroke="#0f766e" strokeWidth={2} />
                    <Line type="monotone" dataKey="compare" dot={false} stroke="#f97316" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state">Choose scenarios to compare.</div>
              )}
            </div>
            {loadingCompare && <div className="empty-state">Loading comparison...</div>}
            {compareStats && (
              <div className="compare-stats">
                <div>
                  <span>Avg delta</span>
                  <strong>{compareStats.avg.toFixed(3)}</strong>
                </div>
                <div>
                  <span>Max delta</span>
                  <strong>{compareStats.max.toFixed(3)}</strong>
                </div>
                <div>
                  <span>Min delta</span>
                  <strong>{compareStats.min.toFixed(3)}</strong>
                </div>
              </div>
            )}
          </div>

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
