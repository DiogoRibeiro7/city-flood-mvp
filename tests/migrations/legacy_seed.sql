-- Synthetic rows at revision 0012. Future timestamps avoid retention expiry.
INSERT INTO city (city_id, name, country)
VALUES ('city_legacy', 'Migration fixture', 'PT');
INSERT INTO asset (asset_id, city_id, asset_type, name, geom, props)
VALUES ('asset_legacy', 'city_legacy', 'node', 'Legacy node',
        ST_SetSRID(ST_MakePoint(-8.61, 41.15), 4326), '{"source":"migration fixture"}');
INSERT INTO asset_tag (asset_id, key, value) VALUES ('asset_legacy', 'fixture', 'legacy');
INSERT INTO scenario_run (scenario_id, name, start_ts, end_ts)
VALUES ('scenario_legacy', 'Legacy scenario', '2030-01-01 00:00:00+00', '2030-01-01 01:00:00+00');
INSERT INTO telemetry_observation (asset_id, metric, ts, value, scenario_id)
VALUES ('asset_legacy', 'fill_ratio', '2030-01-01 01:00:00+01', 0.75, 'scenario_legacy');
INSERT INTO ingest_idempotency (idempotency_key, device_id, response)
VALUES ('key_legacy', 'asset_legacy', '{"inserted":1,"payload_hash":"fixture"}');
INSERT INTO export_job (job_id, job_type, status, query)
VALUES ('export_legacy', 'export_csv', 'queued', '{"metric":"fill_ratio"}');
INSERT INTO export_job_log (log_id, job_id, level, message)
VALUES ('log_legacy', 'export_legacy', 'info', 'Migration fixture');
INSERT INTO job_queue (job_id, job_type, payload, scheduled_at)
VALUES ('queue_legacy', 'export_csv', '{"export_job_id":"export_legacy"}', '2030-01-01 00:00:00+00');
INSERT INTO analytics_run (run_id, city_id, start_ts, end_ts, status, version, created_at)
VALUES
    ('run_older', 'city_legacy', '2030-01-01 00:00:00+00', '2030-01-01 01:00:00+00',
     'completed', 'fixture-v1', '2030-01-01 01:00:00+00'),
    ('run_latest', 'city_legacy', '2030-01-01 00:00:00+00', '2030-01-01 01:00:00+00',
     'completed', 'fixture-v2', '2030-01-01 02:00:00+00');
INSERT INTO analytics_event (event_id, city_id, event_type, severity, start_ts, end_ts, asset_ids, summary)
VALUES ('event_legacy', 'city_legacy', 'overflow', 2, '2030-01-01 00:00:00+00',
        '2030-01-01 00:05:00+00', ARRAY['asset_legacy'], 'Synthetic migration fixture');
INSERT INTO analytics_hotspot_daily (city_id, day, metric, asset_id, score)
VALUES ('city_legacy', '2030-01-01', 'fill_ratio', 'asset_legacy', 0.75);
INSERT INTO asset_status_latest (asset_id, city_id, status, risk_score)
VALUES ('asset_legacy', 'city_legacy', 'watch', 0.75);
INSERT INTO telemetry_qa_daily (city_id, day, metric, assets, buckets_expected, buckets_present, gaps, suspect_count)
VALUES ('city_legacy', '2030-01-01', 'fill_ratio', 1, 12, 1, 11, 0);
