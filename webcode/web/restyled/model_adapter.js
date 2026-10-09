// Invisible Secretary - local model adapter (port of model_adapter.py).
//
// The model performs BOUNDED intent classification + parameter extraction only.
// It never executes tools, never grants permissions, never decides authorization.
//
// Safety-first ordering: a deterministic rule classifier is the PRIMARY path.
// A local small model ENHANCES it. If the two DISAGREE the hybrid ABSTAINS
// (confidence below the router floor) so the system asks for clarification
// rather than guessing. There is never a hidden cloud fallback.

import * as scopeStore from "./scope_store.js";

// A rule is (intent, [keyword groups]). The intent fires when the most groups
// match; score = number of distinct groups matched (0..2 -> confidence band).
const RULES = [
  ["out_of_scope", [["pay", "payment", "purchase", "buy", "transfer", "wire",
                     "delete", "erase", "refund money", "legal", "lawsuit",
                     "hire", "fire", "terminate employee"]]],
  ["schedule_change", [["schedule", "calendar", "appointment", "meeting",
                        "reschedule", "rebook", "slot", "book a"],
                       ["change", "move", "shift", "cancel", "adjust", "propose",
                        "today", "tomorrow", "thursday", "friday"]]],
  ["customer_followup", [["customer", "client", "buyer", "patron"],
                         ["follow up", "follow-up", "chase", "remind", "confirm",
                          "reply", "get back"]]],
  ["supplier_followup", [["supplier", "vendor", "distributor", "delivery",
                          "shipment", "order #", "purchase order"],
                         ["follow up", "follow-up", "confirm", "chase", "remind",
                          "has not", "not confirmed", "expected today", "deliver"]]],
  ["customer_request", [["customer", "client", "buyer", "patron", "complaint",
                         "ticket", "support"],
                        ["request", "complain", "issue", "broken", "problem",
                         "bug", "refund", "help", "asks"]]],
];

// Adversarial instruction markers -> never allowed to change policy.
const INJECTION = /(ignore (all|previous|the) (instructions|rules|polic)|you are now|system prompt|allow-?list|bypass (auth|policy)|disregard (all|the) (rules|policy))/i;

const NAME_RE = /(?:with|to|ask|from|for)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*)*)/;
const DATE_RE = /\b(\d{4}-\d{2}-\d{2})\b/;

// Deterministic primary classifier. Fast, offline, no weights required.
export class RuleClassifier {
  constructor() {
    this.name = "rule-deterministic";
  }

  classify(text) {
    const t = (text || "").toLowerCase();
    const notes = [];

    if (INJECTION.test(text || "")) {
      notes.push("adversarial_instruction_detected_ignored");
    }

    // The out-of-scope keyword list is editable live (localStorage); read it
    // here so /scope edits change classification immediately.
    const oos = scopeStore.outOfScopeKeywords();
    let bestIntent = "unknown";
    let bestScore = 0;
    for (const [intent, groups0] of RULES) {
      const groups = intent === "out_of_scope" ? [oos] : groups0;
      let hits = 0;
      for (const g of groups) {
        if (g.some((k) => t.includes(k))) hits += 1;
      }
      if (hits > bestScore) {
        bestIntent = intent;
        bestScore = hits;
      }
    }

    // A single weak signal is not enough: do not force a known intent.
    if (bestScore < 2 && bestIntent !== "out_of_scope") {
      bestIntent = "unknown";
    }

    // confidence is a heuristic, not a calibrated probability.
    const confidence = bestScore === 0 ? 0.30 : bestScore === 1 ? 0.62 : 0.88;

    const params = {};
    const m = (text || "").match(NAME_RE);
    if (m) params.entity_name = m[1].trim();
    const d = (text || "").match(DATE_RE);
    if (d) params.deadline = d[1];

    if (bestIntent === "supplier_followup" || bestIntent === "customer_followup") {
      if (params.entity_type === undefined) {
        params.entity_type = bestIntent === "supplier_followup" ? "supplier" : "customer";
      }
      if (t.includes("confirm") && t.includes("deliver")) {
        if (params.topic === undefined) params.topic = "delivery confirmation";
      } else if (t.includes("follow")) {
        if (params.topic === undefined) params.topic = "follow-up";
      } else if (params.topic === undefined) {
        params.topic = "open item";
      }
    } else if (bestIntent === "schedule_change") {
      if (params.entity_type === undefined) params.entity_type = "schedule";
      if (params.topic === undefined) params.topic = "schedule change";
    } else if (bestIntent === "customer_request") {
      if (params.topic === undefined) params.topic = "customer request";
    }

    return {
      intent: bestIntent,
      parameters: params,
      confidence,
      urgency_hint: (t.includes("today") || t.includes("urgent")) ? "high" : "normal",
      notes,
    };
  }
}

// Local small-model adapter behind a stable interface.
//
// Delegates to the on-device backend when one is provisioned (see
// local_qwen.js). Deliberately inert otherwise: classification is an
// ENHANCEMENT to the rule path, and there is NO cloud fallback.
export class QwenLocalAdapter {
  constructor(modelPath = null, backend = null) {
    this.name = "qwen-local";
    this.model_path = modelPath;
    this._impl = backend;
  }

  available() {
    if (this._impl && typeof this._impl.available === "function") {
      return this._impl.available();
    }
    return Boolean(this.model_path);
  }

  classify(text) {
    const backend = this._impl;
    if (backend === null) {
      throw new Error("local model not provisioned; no cloud fallback permitted");
    }
    return backend.classify(text);
  }
}

// Rules primary; local model enhances. Disagreement -> abstain.
//
// Agreement boosts confidence; a model/rule conflict drives confidence below
// the router floor so the system abstains (clarifies) instead of guessing.
export class HybridAdapter {
  static ABSTAIN = 0.10; // below the router's confidence floor

  constructor(model = null, opts = {}) {
    this.rules = new RuleClassifier();
    this.model = model;
    this.use_model = opts.useModel === undefined ? true : opts.useModel;
  }

  get name() {
    if (this._modelReady()) return `${this.rules.name}+${this.model.name}`;
    return this.rules.name;
  }

  get model_path() {
    return this._modelReady() ? (this.model.model_path ?? null) : null;
  }

  _modelReady() {
    return Boolean(this.use_model && this.model &&
      (typeof this.model.available === "function" ? this.model.available() : false));
  }

  // What is actually running: mode, model name and its path.
  describe() {
    if (this._modelReady()) {
      const path = this.model_path;
      const display = path ? path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() : null;
      return {
        mode: "rules+model",
        adapter: this.name,
        model: display || (this.model.name || "local-model"),
        path,
        reason: "loaded",
      };
    }
    let reason;
    if (!this.use_model) reason = "disabled (IS_NO_MODEL / --no-model)";
    else if (this.model === null || this.model === undefined) {
      reason = "no local model found (rules only; no cloud fallback)";
    } else reason = "model unavailable";
    return { mode: "rules-only", adapter: this.rules.name, model: null, path: null, reason };
  }

  classify(text) {
    const out = this.rules.classify(text);
    out.model_used = this.rules.name;
    if (!this._modelReady()) return out;

    let m;
    try {
      m = this.model.classify(text);
    } catch (exc) {
      // local runtime must never break routing
      out.model_error = `${exc && exc.name ? exc.name : "Error"}: ${exc && exc.message ? exc.message : exc}`;
      return out;
    }

    out.model_used = `${this.rules.name}+${this.model.name}`;
    out.model_intent = m.intent;
    out.rules_intent = out.intent;

    // Bound rule extraction: the model may fill parameters the rules missed,
    // but never overrides a rule-derived value.
    const mp = m.parameters || {};
    for (const [k, v] of Object.entries(mp)) {
      if (out.parameters[k] === undefined) out.parameters[k] = v;
    }

    if (m.parse_error || !m.intent) {
      out.conflict = "model_parse_error";
      out.confidence = Math.min(out.confidence, HybridAdapter.ABSTAIN);
    } else if (m.intent !== out.intent) {
      out.conflict = `rules=${out.intent} model=${m.intent}`;
      out.confidence = Math.min(out.confidence, HybridAdapter.ABSTAIN);
    } else {
      out.confidence = Math.min(0.98, out.confidence + 0.08);
    }
    return out;
  }
}
