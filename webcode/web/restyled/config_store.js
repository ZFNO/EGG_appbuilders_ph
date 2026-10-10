// EGG - consolidated runtime configuration for the Options page.
//
// One persisted home for the parts of the app that are configurable at runtime.
// Stored in localStorage under "data/config.json" (mirrors the data/*.json
// files of the original project) with an in-memory fallback so the module also
// works under Node (smoke tests) where localStorage may be absent.
//
// Live-applied (read on every request):  confidence_floor, urgency_critical,
//                                        urgency_high
// Applied on load (read once when the runtime is assembled): use_model, model,
//                                        sidecar_url, workers, bus_maxsize
// Out-of-scope keywords live in scope_store.js (shared with the /scope page);
// the Options page reads/writes them through /api/config so both share one truth.

export const CONFIG_KEY = "data/config.json";

export const DEFAULT_CONFIG = Object.freeze({
  use_model: true,
  model: null,
  sidecar_url: "http://127.0.0.1:8765",
  confidence_floor: 0.80,
  urgency_critical: ["immediately", "asap", "as soon as possible"],
  urgency_high: ["today", "urgent", "overdue", "late"],
  workers: 1,
  bus_maxsize: 256,
  updated: null,
});

const _mem = new Map();

function _store() {
  if (typeof globalThis.localStorage !== "undefined" && globalThis.localStorage) {
    return globalThis.localStorage;
  }
  return {
    getItem: (k) => (_mem.has(k) ? _mem.get(k) : null),
    setItem: (k, v) => { _mem.set(k, String(v)); },
    removeItem: (k) => { _mem.delete(k); },
  };
}

function _kw(arr) {
  const out = [];
  const seen = new Set();
  for (const raw of arr || []) {
    if (typeof raw !== "string") continue;
    const k = raw.trim().toLowerCase();
    if (k && !seen.has(k)) { seen.add(k); out.push(k); }
  }
  return out;
}

function _num(v, d, min) {
  const n = Number(v);
  return Number.isFinite(n) && n >= min ? n : d;
}

function normalise(cfg) {
  const d = DEFAULT_CONFIG;
  const out = {
    use_model: cfg.use_model === undefined ? d.use_model : !!cfg.use_model,
    model: (cfg.model === undefined || cfg.model === null || cfg.model === "")
      ? null : String(cfg.model),
    sidecar_url: String(
      cfg.sidecar_url === undefined || cfg.sidecar_url === null ? d.sidecar_url : cfg.sidecar_url
    ).trim().replace(/\/+$/, ""),
    confidence_floor: Math.min(1, Math.max(0, _num(cfg.confidence_floor, d.confidence_floor, 0))),
    urgency_critical: _kw(cfg.urgency_critical !== undefined ? cfg.urgency_critical : d.urgency_critical),
    urgency_high: _kw(cfg.urgency_high !== undefined ? cfg.urgency_high : d.urgency_high),
    workers: Math.max(1, Math.floor(_num(cfg.workers, d.workers, 1))),
    bus_maxsize: Math.max(1, Math.floor(_num(cfg.bus_maxsize, d.bus_maxsize, 1))),
    updated: cfg.updated === undefined ? null : cfg.updated,
  };
  if (!out.sidecar_url) out.sidecar_url = d.sidecar_url;
  return out;
}

export function defaults() { return normalise({ ...DEFAULT_CONFIG }); }

export function load() {
  let stored = {};
  try {
    const raw = _store().getItem(CONFIG_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (data && typeof data === "object" && !Array.isArray(data)) stored = data;
    }
  } catch (e) { /* fall back to defaults */ }
  return normalise({ ...DEFAULT_CONFIG, ...stored });
}

export function save(partial = {}, opts = {}) {
  const merged = { ...load(), ...(partial && typeof partial === "object" ? partial : {}) };
  merged.updated = opts.updated || new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const cfg = normalise(merged);
  try { _store().setItem(CONFIG_KEY, JSON.stringify(cfg, null, 2) + "\n"); } catch (e) {}
  return cfg;
}

export function reset() {
  try { _store().removeItem(CONFIG_KEY); } catch (e) {}
  return defaults();
}
