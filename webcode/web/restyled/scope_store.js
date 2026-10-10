// Invisible Secretary - live scope configuration (port of scope_store.py).
//
// Scope is spread across modules; this module gives the one lever that changes
// live behaviour - the out_of_scope_keywords list - a single persisted home.
// In the browser the "file" data/scope.json becomes a localStorage key of the
// SAME name, so the /scope page can edit what is out of scope on the spot with
// no code edit. Everything else is surfaced read-only (informational).

import { RiskLevel } from "./schemas.js";
import * as configStore from "./config_store.js";

// localStorage key equivalent to the Python file <project>/data/scope.json.
export const SCOPE_KEY = "data/scope.json";

// The seed set of rejected keywords. Mirrors the original in-code rule.
export const DEFAULT_OUT_OF_SCOPE = [
  "pay", "payment", "purchase", "buy", "transfer", "wire", "delete",
  "erase", "refund money", "legal", "lawsuit", "hire", "fire",
  "terminate employee",
];

// In-memory fallback so the module works where localStorage is absent
// (e.g. the Node smoke test, which installs its own mock anyway).
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

export function defaultScope() {
  return { out_of_scope_keywords: [...DEFAULT_OUT_OF_SCOPE], updated: null };
}

function normalise(kws) {
  const out = [];
  const seen = new Set();
  for (const raw of kws || []) {
    if (typeof raw !== "string") continue;
    const k = raw.trim().toLowerCase();
    if (k && !seen.has(k)) {
      seen.add(k);
      out.push(k);
    }
  }
  return out;
}

// Return the effective scope config (stored over defaults), normalised.
export function load() {
  const cfg = defaultScope();
  try {
    const raw = _store().getItem(SCOPE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (data && typeof data === "object" && !Array.isArray(data)) {
        Object.assign(cfg, data);
      }
    }
  } catch (e) {
    // OSError / JSONDecodeError -> fall back to defaults.
  }
  cfg.out_of_scope_keywords = normalise(cfg.out_of_scope_keywords);
  return cfg;
}

// Persist an out-of-scope keyword list and return the stored config.
export function save(keywords, opts = {}) {
  const updated = opts.updated || new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const cfg = {
    out_of_scope_keywords: normalise(keywords),
    updated,
  };
  try {
    _store().setItem(SCOPE_KEY, JSON.stringify(cfg, null, 2) + "\n");
  } catch (e) {
    // Quota / disabled storage: keep the returned config authoritative.
  }
  return cfg;
}

// The live rejection keyword list (read on every classification).
export function outOfScopeKeywords() {
  return load().out_of_scope_keywords;
}

// --------------------------------------------------------------------------
// Informational catalogue (read-only mirror of code) used by the /scope page.
// --------------------------------------------------------------------------
export const IN_SCOPE = [
  { intent: "supplier_followup", node: "followup", risk: "R3",
    label: "Follow up with a supplier / vendor",
    required_params: ["entity_type"],
    example: "Follow up with Acme supplier - order #4471 not confirmed" },
  { intent: "customer_followup", node: "followup", risk: "R3",
    label: "Follow up with a customer / client",
    required_params: ["entity_type"],
    example: "Chase the customer at Bright Co about the late delivery" },
  { intent: "schedule_change", node: "scheduling", risk: "R3",
    label: "Reschedule / move a meeting",
    required_params: ["topic"],
    example: "Reschedule Thursday's meeting to Friday" },
  { intent: "customer_request", node: "customer_request", risk: "R2",
    label: "Triage a customer request or complaint",
    required_params: ["topic"],
    example: "Customer reports a broken widget, asks for help" },
];

export const URGENCY_KEYWORDS = {
  critical: ["immediately", "asap", "as soon as possible"],
  high: ["today", "urgent", "overdue", "late"],
};

// Assemble the full read-only scope picture for the UI.
export async function overview() {
  const [{ CONFIDENCE_FLOOR, ACTION_RISK }, { defaultNodes }] = await Promise.all([
    import("./router.js"),
    import("./nodes.js"),
  ]);

  let nodes = {};
  try {
    nodes = defaultNodes();
  } catch (e) {
    nodes = {};
  }

  const cfg = load();

  const intents = IN_SCOPE.map((row) => {
    const n = nodes[row.node];
    const risk = ACTION_RISK[row.intent] || RiskLevel.R1;
    return {
      ...row,
      requires_approval: risk === RiskLevel.R2 || risk === RiskLevel.R3,
      node_description: n ? n.description : "",
      action: n ? n.consequential_action : null,
    };
  });

  const nodeList = Object.values(nodes).map((n) => ({
    node: n.name,
    description: n.description || "",
    action: n.consequential_action || null,
    health: n.health().health || "ok",
  }));

  return {
    out_of_scope_keywords: cfg.out_of_scope_keywords,
    updated: cfg.updated === undefined ? null : cfg.updated,
    confidence_floor: configStore.load().confidence_floor,
    in_scope: intents,
    urgency_keywords: URGENCY_KEYWORDS,
    nodes: nodeList,
  };
}
