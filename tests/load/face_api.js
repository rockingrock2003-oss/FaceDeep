// FaceDeep API Load Test
// Run: k6 run tests/load/face_api.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const errorRate = new Rate('errors');
const latency = new Trend('api_latency');
const requests = new Counter('total_requests');

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || '';

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up
    { duration: '1m', target: 50 },    // Stay at 50
    { duration: '30s', target: 100 },  // Spike to 100
    { duration: '2m', target: 100 },   // Stay at 100
    { duration: '30s', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    errors: ['rate<0.1'],
  },
};

const headers = {
  'Content-Type': 'application/json',
  'X-API-Key': API_KEY,
};

export default function () {
  const scenarios = [
    () => testHealthCheck(),
    () => testRecognize(),
    () => testListFaces(),
  ];

  const scenario = scenarios[Math.floor(Math.random() * scenarios.length)];
  scenario();

  sleep(Math.random() * 2);
}

function testHealthCheck() {
  const res = http.get(`${BASE_URL}/api/v2/health`, { headers });
  check(res, {
    'health status is 200': (r) => r.status === 200,
    'health response time < 200ms': (r) => r.timings.duration < 200,
  });
  errorRate.add(res.status !== 200);
  latency.add(res.timings.duration);
  requests.add(1);
}

function testRecognize() {
  const payload = JSON.stringify({
    image: 'base64_encoded_image_data_here',
  });

  const res = http.post(`${BASE_URL}/api/v2/face/recognize`, payload, {
    headers,
    timeout: '10s',
  });

  check(res, {
    'recognize status is 200 or 404': (r) => r.status === 200 || r.status === 404,
    'recognize response time < 2s': (r) => r.timings.duration < 2000,
  });

  errorRate.add(res.status >= 500);
  latency.add(res.timings.duration);
  requests.add(1);
}

function testListFaces() {
  const res = http.get(`${BASE_URL}/api/v2/face/all`, { headers });
  check(res, {
    'list status is 200': (r) => r.status === 200,
    'list response time < 500ms': (r) => r.timings.duration < 500,
  });
  errorRate.add(res.status !== 200);
  latency.add(res.timings.duration);
  requests.add(1);
}

export function handleSummary(data) {
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
    'tests/load/summary.json': JSON.stringify(data),
  };
}

function textSummary(data, options) {
  let out = '\n=== FaceDeep Load Test Results ===\n';
  out += `Requests: ${data.metrics.http_reqs?.values?.count || 0}\n`;
  out += `Duration: ${data.metrics.http_req_duration?.values?.avg?.toFixed(2) || 0}ms avg\n`;
  out += `Errors: ${(data.metrics.errors?.values?.rate * 100 || 0).toFixed(2)}%\n`;
  out += `p95: ${data.metrics.http_req_duration?.values?.['p(95)']?.toFixed(2) || 0}ms\n`;
  out += `p99: ${data.metrics.http_req_duration?.values?.['p(99)']?.toFixed(2) || 0}ms\n`;
  return out;
}
