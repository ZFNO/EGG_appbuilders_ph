// Invisible Secretary - deterministic router (port of router.py).
//
// The router is the policy engine. It validates schema, rejects unknown
// intents/nodes, computes urgency from explicit rules (never from model
// confidence), applies risk/authorization policy, and dispatches ONLY to
// allow-listed nodes. High urgency never bypasses authorization.

import {
  Intent, RiskLevel, ValidationError, INTENT_TO_NODE, ALLOWED_NODES,
  decisionToDict, validateDecision,
} from "./schemas.js";
import * as configStore from "./config_store.js";

export const CONFIDENCE_FLOOR = 0.80; // below this -> clarify, never guess

// Required parameters per intent (validated before dispatch).
export const REQUIRED_PARAMS = {
  supplier_followup: ["entity_type"],
  customer_followup: ["entity_type"],
  schedule_change: ["topic"],
  customer_request: ["topic"],
};

// Consequential actions by intent -> risk level when the action is committed.
export const ACTION_RISK = {
  supplier_followup: RiskLevel.R3,   // send external message
  customer_followup: RiskLevel.R3,   // send external message
  schedule_change: RiskLevel.R3,     // commit a schedule change
  customer_request: RiskLevel.R2,    // route to a queue (reversible, low impact)
};

const INTENT_VALUES = new Set(Object.values(Intent));

export class Router {
  constructor(model, opts = {}) {
    this.model = model;
    this._floorOverride = opts.confidenceFloor;
    this.audit = [];
  }

  // Effective confidence floor: read live from the Options config on every
  // request, unless a caller pinned one explicitly at construction.
  get confidence_floor() {
    return this._floorOverride === undefined
      ? configStore.load().confidence_floor
      : this._floorOverride;
  }

  // -- policy helpers -------------------------------------------------
  static _urgency(text, hint) {
    const t = (text || "").toLowerCase();
    const cfg = configStore.load();
    const crit = (cfg.urgency_critical && cfg.urgency_critical.length)
      ? cfg.urgency_critical : ["immediately", "asap", "as soon as possible"];
    const high = (cfg.urgency_high && cfg.urgency_high.length)
      ? cfg.urgency_high : ["today", "urgent", "overdue", "late"];
    if (crit.some((k) => t.includes(k))) {
      return ["critical", "explicit immediacy signal"];
    }
    if (high.some((k) => t.includes(k))) {
      return ["high", "same-day / urgent signal"];
    }
    if (hint === "high") {
      return ["high", "model urgency hint (rule-confirmed only)"];
    }
    return ["normal", "no urgency signal"];
  }

  async route(requestId, text) {
    const modelOut = await this.model.classify(text);
    let intent = modelOut.intent === undefined ? "unknown" : modelOut.intent;
    const params = Object.assign({}, modelOut.parameters || {});
    const confidence = Number(modelOut.confidence === undefined ? 0.0 : modelOut.confidence);

    if (!INTENT_VALUES.has(intent)) intent = "unknown";

    const node = INTENT_TO_NODE[intent];
    const [level, reason] = Router._urgency(text, modelOut.urgency_hint || "normal");
    const risk = ACTION_RISK[intent] || RiskLevel.R1;

    let decision = {
      request_id: requestId,
      intent,
      node,
      parameters: params,
      urgency_level: level,
      urgency_reason: reason,
      confidence,
      risk_level: risk,
      requires_approval: risk === RiskLevel.R2 || risk === RiskLevel.R3,
    };

    // --- policy gate (independent of model confidence) -------------
    const blocked = [];
    if (intent === "out_of_scope") {
      decision.node = null;
      blocked.push("out_of_scope_action");
    } else if (intent === "unknown") {
      decision.node = null;
    }

    if (decision.node !== null && decision.node !== undefined) {
      if (!ALLOWED_NODES.has(decision.node)) {
        decision.node = null;
        blocked.push("unknown_node_rejected");
      }
      const missing = (REQUIRED_PARAMS[intent] || []).filter((p) => !(p in params));
      if (missing.length) blocked.push("missing_params:" + missing.join(","));
      if (confidence < this.confidence_floor) blocked.push("low_confidence");
    }

    // Re-validate the object against the contract before it leaves.
    try {
      decision = validateDecision(decisionToDict(decision));
    } catch (exc) {
      if (exc instanceof ValidationError) {
        throw new ValidationError(`router produced invalid decision: ${exc.message}`);
      }
      throw exc;
    }

    this.audit.push({
      request_id: requestId,
      transition: "classified",
      intent: decision.intent,
      node: decision.node === null ? null : decision.node,
      confidence: decision.confidence,
      urgency: decision.urgency_level,
      risk_level: decision.risk_level,
      requires_approval: decision.requires_approval,
      blocked,
      model: this.model.name !== undefined ? this.model.name : "unknown",
    });
    decision._blocked = blocked; // consumed by the engine
    return decision;
  }
}
