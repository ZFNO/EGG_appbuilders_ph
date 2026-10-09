// Invisible Secretary - data contracts (port of schemas.py).
// Pure-JS validation of the router decision and node result contracts.
// Nothing here executes actions or trusts free-form model output.

export class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ValidationError";
  }
}

export const Intent = Object.freeze({
  SUPPLIER_FOLLOWUP: "supplier_followup",
  CUSTOMER_FOLLOWUP: "customer_followup",
  SCHEDULE_CHANGE: "schedule_change",
  CUSTOMER_REQUEST: "customer_request",
  UNKNOWN: "unknown",
  OUT_OF_SCOPE: "out_of_scope",
});

export const NodeName = Object.freeze({
  FOLLOWUP: "followup",
  SCHEDULING: "scheduling",
  CUSTOMER_REQUEST: "customer_request",
});

export const Urgency = Object.freeze({
  LOW: "low",
  NORMAL: "normal",
  HIGH: "high",
  CRITICAL: "critical",
});

// R0 classify/summarize only; R1 draft/recommendation, no side effect;
// R2 reversible low-impact action (needs a configured permission);
// R3 consequential: send / pay / delete / commit -> explicit auth.
export const RiskLevel = Object.freeze({ R0: "R0", R1: "R1", R2: "R2", R3: "R3" });

export const Status = Object.freeze({
  SUCCEEDED: "succeeded",
  NEEDS_APPROVAL: "needs_approval",
  NEEDS_CLARIFICATION: "needs_clarification",
  FAILED: "failed",
  REJECTED: "rejected",
});

// Allow-listed intent -> node mapping. Single source of truth for dispatch.
export const INTENT_TO_NODE = Object.freeze({
  supplier_followup: "followup",
  customer_followup: "followup",
  schedule_change: "scheduling",
  customer_request: "customer_request",
  unknown: null,
  out_of_scope: null,
});

export const ALLOWED_NODES = new Set(Object.values(NodeName));

const INTENT_VALUES = new Set(Object.values(Intent));
const URGENCY_VALUES = new Set(Object.values(Urgency));
const RISK_VALUES = new Set(Object.values(RiskLevel));
const STATUS_VALUES = new Set(Object.values(Status));

const isNum = (x) => typeof x === "number" && Number.isFinite(x);

const isPlainObject = (x) =>
  x !== null && typeof x === "object" && !Array.isArray(x);

// Validate a raw decision dict against the router decision schema.
// Accepts either the flat wire form (urgency_level / urgency_reason) or a
// nested urgency object, exactly like schemas.validate_decision.
export function validateDecision(raw) {
  if (!isPlainObject(raw)) throw new ValidationError("decision must be an object");

  const requestId = raw.request_id;
  if (typeof requestId !== "string" || !requestId.trim()) {
    throw new ValidationError("request_id: non-empty string required");
  }

  if (!INTENT_VALUES.has(raw.intent)) {
    throw new ValidationError(`intent: unknown value ${JSON.stringify(raw.intent)}`);
  }
  const intent = raw.intent;

  const nodeRaw = raw.node;
  if (nodeRaw !== undefined && nodeRaw !== null && !ALLOWED_NODES.has(nodeRaw)) {
    throw new ValidationError(`node: not allow-listed: ${JSON.stringify(nodeRaw)}`);
  }
  const expectedNode = INTENT_TO_NODE[intent];
  if (nodeRaw !== undefined && nodeRaw !== null && expectedNode !== null && nodeRaw !== expectedNode) {
    throw new ValidationError(`node: ${JSON.stringify(nodeRaw)} does not match allow-list for ${intent}`);
  }

  const params = raw.parameters === undefined ? {} : raw.parameters;
  if (!isPlainObject(params)) throw new ValidationError("parameters: object required");

  let uLevelRaw;
  let uReason;
  const urgency = raw.urgency;
  if (urgency === undefined || urgency === null) {
    uLevelRaw = raw.urgency_level === undefined ? "normal" : raw.urgency_level;
    uReason = String(raw.urgency_reason === undefined ? "" : raw.urgency_reason);
  } else {
    if (!isPlainObject(urgency)) throw new ValidationError("urgency: object required");
    uLevelRaw = urgency.level === undefined ? "normal" : urgency.level;
    uReason = String(urgency.reason === undefined ? "" : urgency.reason);
  }
  if (!URGENCY_VALUES.has(uLevelRaw)) {
    throw new ValidationError(`urgency.level: invalid ${JSON.stringify(uLevelRaw)}`);
  }

  const conf = raw.confidence === undefined ? 0.0 : raw.confidence;
  if (!isNum(conf) || !(conf >= 0.0 && conf <= 1.0)) {
    throw new ValidationError("confidence: number in [0,1] required");
  }

  const riskRaw = raw.risk_level === undefined ? "R1" : raw.risk_level;
  if (!RISK_VALUES.has(riskRaw)) {
    throw new ValidationError(`risk_level: invalid ${JSON.stringify(riskRaw)}`);
  }

  const reqAppr = raw.requires_approval === undefined ? false : raw.requires_approval;
  if (typeof reqAppr !== "boolean") {
    throw new ValidationError("requires_approval: boolean required");
  }

  return {
    request_id: requestId,
    intent,
    node: nodeRaw === undefined || nodeRaw === null ? null : nodeRaw,
    parameters: params,
    urgency_level: uLevelRaw,
    urgency_reason: uReason,
    confidence: conf,
    risk_level: riskRaw,
    requires_approval: reqAppr,
  };
}

// RoutingDecision.to_dict() equivalent (stable field order, snake_case).
export function decisionToDict(d) {
  return {
    request_id: d.request_id,
    intent: d.intent,
    node: d.node === undefined || d.node === null ? null : d.node,
    parameters: d.parameters === undefined ? {} : d.parameters,
    urgency_level: d.urgency_level === undefined ? "normal" : d.urgency_level,
    urgency_reason: d.urgency_reason === undefined ? "" : d.urgency_reason,
    confidence: d.confidence === undefined ? 0.0 : d.confidence,
    risk_level: d.risk_level === undefined ? "R1" : d.risk_level,
    requires_approval: d.requires_approval === undefined ? false : d.requires_approval,
  };
}

export function validateResult(raw) {
  if (!isPlainObject(raw)) throw new ValidationError("result must be an object");
  if (typeof raw.request_id !== "string" || !raw.request_id) {
    throw new ValidationError("result.request_id: non-empty string required");
  }
  if (!STATUS_VALUES.has(raw.status)) {
    throw new ValidationError(`result.status: invalid ${JSON.stringify(raw.status)}`);
  }
  const sideEffect = raw.side_effect_performed === undefined ? false : raw.side_effect_performed;
  if (typeof sideEffect !== "boolean") {
    throw new ValidationError("result.side_effect_performed: boolean required");
  }
  return {
    request_id: raw.request_id,
    status: raw.status,
    summary: String(raw.summary === undefined ? "" : raw.summary),
    side_effect_performed: sideEffect,
    approval_request: raw.approval_request === undefined ? null : raw.approval_request,
    error: raw.error === undefined ? null : raw.error,
    simulated: raw.simulated === undefined ? true : Boolean(raw.simulated),
  };
}

// NodeResult.to_dict() equivalent.
export function resultToDict(r) {
  return {
    request_id: r.request_id,
    status: r.status,
    summary: r.summary === undefined ? "" : r.summary,
    side_effect_performed: r.side_effect_performed === undefined ? false : r.side_effect_performed,
    approval_request: r.approval_request === undefined ? null : r.approval_request,
    error: r.error === undefined ? null : r.error,
    simulated: r.simulated === undefined ? true : r.simulated,
  };
}
