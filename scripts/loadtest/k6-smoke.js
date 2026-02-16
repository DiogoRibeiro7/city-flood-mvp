import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const INGEST_TOKEN = __ENV.INGEST_TOKEN || "dev-ingest-token";

export const options = {
  vus: 5,
  duration: "1m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:health}": ["p(95)<200"],
    "http_req_duration{endpoint:cities}": ["p(95)<300"],
    "http_req_duration{endpoint:city_assets}": ["p(95)<750"],
    "http_req_duration{endpoint:ingest}": ["p(95)<1500"],
  },
};

export function setup() {
  const citiesRes = http.get(`${BASE_URL}/v1/cities`, {
    tags: { endpoint: "cities" },
  });
  check(citiesRes, { "cities 200": (r) => r.status === 200 });

  const cities = citiesRes.status === 200 ? citiesRes.json() : [];
  if (!cities.length) {
    return { cityId: null, assetId: null };
  }

  const cityId = cities[0].city_id;
  const assetsRes = http.get(`${BASE_URL}/v1/cities/${cityId}/assets?limit=50`, {
    tags: { endpoint: "city_assets" },
  });
  check(assetsRes, { "assets 200": (r) => r.status === 200 });
  const assets = assetsRes.status === 200 ? assetsRes.json() : [];
  const assetId = assets.length ? assets[0].asset_id : null;

  return { cityId, assetId };
}

export default function (data) {
  const healthRes = http.get(`${BASE_URL}/v1/health`, {
    tags: { endpoint: "health" },
  });
  check(healthRes, { "health 200": (r) => r.status === 200 });

  const citiesRes = http.get(`${BASE_URL}/v1/cities`, {
    tags: { endpoint: "cities" },
  });
  check(citiesRes, { "cities 200": (r) => r.status === 200 });

  if (data.cityId) {
    const assetsRes = http.get(
      `${BASE_URL}/v1/cities/${data.cityId}/assets?limit=200`,
      { tags: { endpoint: "city_assets" } }
    );
    check(assetsRes, { "assets 200": (r) => r.status === 200 });
  }

  if (data.assetId) {
    const now = new Date().toISOString();
    const payload = JSON.stringify({
      device_id: data.assetId,
      events: [
        {
          ts: now,
          type: "rainfall",
          value: 1.2,
          quality_flag: "ok",
        },
      ],
    });
    const ingestRes = http.post(
      `${BASE_URL}/v1/telemetry/events:batch`,
      payload,
      {
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${INGEST_TOKEN}`,
        },
        tags: { endpoint: "ingest" },
      }
    );
    check(ingestRes, { "ingest 200": (r) => r.status === 200 });
  }

  sleep(1);
}
