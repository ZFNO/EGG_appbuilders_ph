// Invisible Secretary - in-browser API + fetch shim (port of server.py routes).
//
// The static build has no backend. This module assembles the same object graph
// as the Python server (bus + engine + worker) and installs a tiny fetch shim
// that maps the documented routes onto the in-browser engine. Pages keep their
// near-verbatim fetch("/api/...") calls; nothing ever hits the network.
//
//   POST /api/route                         -> engine (via the bus)
//   POST /api/preview                        -> engine.preview
//   GET  /api/scope, POST /api/scope         -> scope_store
//   POST /api/approvals/{id}/{approve|reject}-> engine (via the bus)
//   GET  /api/activity, /api/nodes, /api/model, /api/jobs/{id}

import "./sidecar_client.js"; // installs globalThis.__IS_ONNX_BACKEND__ + status
import { Message } from "./bus.js";
import { buildRuntime, startWorkers } from "./runtime.js";
import * as scopeStore from "./scope_store.js";

// One shared runtime for the page lifetime.
const { bus, ctx, engine } = buildRuntime({ useModel: true });
startWorkers(bus, ctx, { workers: 1 });

const UUID = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx".replace(/x/g, () => Math.floor(Math.random() * 16).toString(16));
};

async function submit(msg, wait) {
  if (bus.full() && !wait) {
    const e = new Error("queue saturated; retry");
    e.status = 503;
    throw e;
  }
  if (wait) msg.replies = new (await import("./bus.js")).Deferred();
  await bus.publish(msg);
  if (!wait) return { job_id: msg.id, state: "accepted" };
  return await msg.replies.promise;
}

// Core dispatcher: mirrors the FastAPI handlers in server.py.
export async function handle(method, path, body) {
  const url = new URL(path, "http://local");
  const p = url.pathname;
  const m = method.toUpperCase();
  body = body || {};

  if (m === "GET" && p === "/api/scope") {
    return { status: 200, data: await scopeStore.overview() };
  }
  if (m === "POST" && p === "/api/scope") {
    const kws = body.out_of_scope_keywords === undefined ? [] : body.out_of_scope_keywords;
    if (!Array.isArray(kws)) return { status: 400, data: { error: "out_of_scope_keywords must be a list" } };
    return { status: 200, data: scopeStore.save(kws) };
  }
  if (m === "POST" && p === "/api/preview") {
    return { status: 200, data: await engine.preview(body.text || "") };
  }
  if (m === "GET" && p === "/api/model") {
    return { status: 200, data: engine.router.model.describe() };
  }
  if (m === "POST" && p === "/api/route") {
    const mode = url.searchParams.get("mode") || "sync";
    const opts = { source: "http" };
    if (body.request_id) opts.id = body.request_id;
    const msg = new Message("secretary.request", { text: body.text || "" }, opts);
    try {
      const data = await submit(msg, mode !== "async");
      return { status: 200, data };
    } catch (exc) {
      return { status: 500, data: { detail: String(exc && exc.message ? exc.message : exc) } };
    }
  }
  if (m === "POST" && p.startsWith("/api/approvals/")) {
    const parts = p.replace(/^\/+|\/+$/g, "").split("/"); // api, approvals, id, action
    if (parts.length !== 4) return { status: 400, data: { error: "bad_approval_path" } };
    const [, , approvalId, action] = parts;
    if (action !== "approve" && action !== "reject") {
      return { status: 400, data: { error: "bad_action" } };
    }
    const payload = { approval_id: approvalId };
    if (action === "approve" && body && Object.prototype.hasOwnProperty.call(body, "payload")) {
      payload.payload = body.payload;
    }
    const kind = action === "approve" ? "secretary.approve" : "secretary.reject";
    try {
      const data = await submit(new Message(kind, payload, { source: "http" }), true);
      return { status: 200, data };
    } catch (exc) {
      if (exc && exc.name === "KeyError") return { status: 404, data: { error: "unknown_approval" } };
      return { status: 409, data: { error: String(exc && exc.message ? exc.message : exc) } };
    }
  }
  if (m === "GET" && p === "/api/activity") {
    return { status: 200, data: [...engine.events.values()].map((e) => e.toDict()) };
  }
  if (m === "GET" && p === "/api/nodes") {
    return { status: 200, data: Object.values(engine.nodes).map((n) => n.health()) };
  }
  if (m === "GET" && p.startsWith("/api/jobs/")) {
    const jobId = decodeURIComponent(p.slice("/api/jobs/".length));
    const ev = engine.events.get(jobId);
    if (!ev) return { status: 404, data: { detail: "unknown job" } };
    return { status: 200, data: ev.toDict() };
  }
  return { status: 404, data: { error: "not_found" } };
}

// A Response-like object good enough for the pages' `.json()` usage.
function responseLike({ status, data }) {
  const text = JSON.stringify(data);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => JSON.parse(text),
    text: async () => text,
  };
}

// Install the shim over the global fetch. Only /api/* is intercepted; every
// other request is delegated to the original fetch (there should be none).
export function installFetchShim(target = globalThis) {
  const original = target.fetch ? target.fetch.bind(target) : null;
  target.fetch = async (input, init = {}) => {
    const raw = typeof input === "string" ? input : (input && input.url) || String(input);
    const path = raw.replace(/^https?:\/\/[^/]+/, "");
    if (path.startsWith("/api/")) {
      let body = {};
      if (init && init.body) {
        try { body = JSON.parse(init.body); } catch (e) { body = {}; }
      }
      const method = (init && init.method) || (typeof input === "object" && input.method) || "GET";
      const res = await handle(method, path, body);
      return responseLike(res);
    }
    if (original) return original(input, init);
    throw new Error(`no fetch available for ${raw}`);
  };
  return target.fetch;
}

// Auto-install when loaded inside a page (module in a browser-like env).
if (typeof globalThis !== "undefined" && typeof globalThis.fetch !== "undefined") {
  installFetchShim(globalThis);
}

export const api = { handle, engine, bus, ctx, submit, installFetchShim };
export default api;
