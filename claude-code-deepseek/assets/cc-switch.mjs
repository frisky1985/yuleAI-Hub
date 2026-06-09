#!/usr/bin/env node
/**
 * CC Switch — Claude Code → DeepSeek 智能代理
 * 
 * /v1/*       → DeepSeek (LLM API)
 * /api/*      → mock (Anthropic 遥测/boot/feature flags)
 * 其他        → mock
 */

import http from "node:http";
import https from "node:https";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const TARGET = "api.deepseek.com";
const PREFIX = "/anthropic";
const PORT = parseInt(process.argv[2] || "8787", 10);
const CERT_DIR = path.join(import.meta.dirname, "..", "certs");

function ensureCerts() {
  fs.mkdirSync(CERT_DIR, { recursive: true });
  const k = path.join(CERT_DIR, "key.pem");
  const c = path.join(CERT_DIR, "crt.pem");
  if (!fs.existsSync(k)) {
    execSync(`openssl req -x509 -newkey rsa:2048 -keyout "${k}" -out "${c}" -days 3650 -nodes -subj "/CN=localhost"`, { stdio: "pipe" });
  }
  return { key: fs.readFileSync(k), cert: fs.readFileSync(c) };
}

// ── Mock 响应：捣糨糊让 Claude Code 满意 ──
const MOCK_OK = JSON.stringify({ ok: true });
const MOCK_BOOTSTRAP = JSON.stringify({
  flags: {},
  settings: {},
  endpoint: "https://api.anthropic.com",
});

function sendMock(res, body, status = 200) {
  res.writeHead(status, { "content-type": "application/json", "access-control-allow-origin": "*" });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

function handleRequest(clientReq, clientRes) {
  const { method, url } = clientReq;
  const h = { ...clientReq.headers };
  delete h.host;

  // OPTIONS preflight
  if (method === "OPTIONS") {
    clientRes.writeHead(204, { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" });
    return clientRes.end();
  }

  // ── API 调用 → 转发到 DeepSeek ──
  if (url.startsWith("/v1/")) {
    return forwardToDeepSeek(method, url, h, clientReq, clientRes);
  }

  // ── 其他所有 → Mock ──
  console.log(`Ⓜ ${method} ${url}  → mock`);

  if (url.startsWith("/api/claude_cli/bootstrap")) return sendMock(clientRes, MOCK_BOOTSTRAP);
  if (url.startsWith("/api/claude_code_penguin_mode")) return sendMock(clientRes, { enabled: false });
  if (url.startsWith("/api/eval/")) return sendMock(clientRes, { status: "ok" });
  if (url.startsWith("/api/event_logging")) return sendMock(clientRes, MOCK_OK);
  if (url.includes("mcp-registry")) return sendMock(clientRes, { servers: [] });
  if (url === "/api/hello") return sendMock(clientRes, { message: "hello" });

  // 兜底
  sendMock(clientRes, MOCK_OK);
}

function forwardToDeepSeek(method, url, headers, clientReq, clientRes) {
  const targetPath = PREFIX + url;
  console.log(`→ ${method} ${url}  → DeepSeek`);

  const upstream = https.request(
    { hostname: TARGET, port: 443, path: targetPath, method, headers: { ...headers, host: TARGET } },
    (up) => {
      const rh = {};
      for (const [k, v] of Object.entries(up.headers))
        if (!["transfer-encoding", "connection", "keep-alive"].includes(k.toLowerCase())) rh[k] = v;
      rh["access-control-allow-origin"] = "*";
      clientRes.writeHead(up.statusCode, rh);
      up.pipe(clientRes);
    }
  );
  upstream.on("error", () => { if (!clientRes.headersSent) clientRes.writeHead(502); clientRes.end(); });
  clientReq.pipe(upstream);
}

// ── 服务器 ──
const handler = (req, res) => {
  try { handleRequest(req, res); } catch (e) {
    if (!res.headersSent) res.writeHead(500);
    res.end();
  }
};

// HTTP 8787
const httpSrv = http.createServer(handler);
httpSrv.on("error", (e) => { if (e.code !== "EADDRINUSE") throw e; });
httpSrv.listen(PORT, "127.0.0.1", () => console.log(`🔥 HTTP  → http://127.0.0.1:${PORT}`));

// HTTPS 443
try {
  const { key, cert } = ensureCerts();
  const httpsSrv = https.createServer({ key, cert }, handler);
  httpsSrv.on("error", (e) => { if (e.code !== "EADDRINUSE") console.error("HTTPS err:", e.message); });
  httpsSrv.listen(443, "127.0.0.1", () => console.log(`🔥 HTTPS → https://127.0.0.1:443`));
} catch (e) {
  console.error("HTTPS不可用:", e.message);
}
