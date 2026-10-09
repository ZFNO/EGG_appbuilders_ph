// Invisible Secretary - event state machine, audit log, approvals, idempotency.
// Port of engine.py.
//
// Lifecycle: received -> classified -> validated -> awaiting_approval | routed
//            -> running -> succeeded | failed | needs_clarification | rejected.
// Every transition is logged. Success is never claimed until a node confirms it.
// Approvals are bound to the exact action payload; a changed payload invalidates
// the approval and requires a new one.

import { Router } from "./router.js";
import { DEFAULT_POLICIES, defaultNodes } from "./nodes.js";
import { Status, decisionToDict, resultToDict } from "./schemas.js";

// -- synchronous SHA-256 (matches Python hashlib.sha256(...).hexdigest()[:16]) --
const K512 = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

const rotr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0;

function sha256Hex(input) {
  const bytes = new TextEncoder().encode(input);
  const l = bytes.length;
  const withOne = l + 1;
  const pad = (56 - (withOne % 64) + 64) % 64;
  const total = withOne + pad + 8;
  const buf = new Uint8Array(total);
  buf.set(bytes);
  buf[l] = 0x80;
  const dv = new DataView(buf.buffer);
  const bitLen = l * 8;
  dv.setUint32(total - 8, Math.floor(bitLen / 0x100000000));
  dv.setUint32(total - 4, bitLen >>> 0);

  let H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
           0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const w = new Uint32Array(64);
  for (let i = 0; i < total; i += 64) {
    for (let t = 0; t < 16; t++) w[t] = dv.getUint32(i + t * 4);
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      const s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let t = 0; t < 64; t++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K512[t] + w[t]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H = [(H[0] + a) >>> 0, (H[1] + b) >>> 0, (H[2] + c) >>> 0, (H[3] + d) >>> 0,
         (H[4] + e) >>> 0, (H[5] + f) >>> 0, (H[6] + g) >>> 0, (H[7] + h) >>> 0];
  }
  return H.map((x) => x.toString(16).padStart(8, "0")).join("");
}

// Python-compatible json.dumps(payload, sort_keys=True): ", " and ": "
// separators, keys sorted, ASCII. Keeps the payload hash identical to Python.
function pyDumps(o) {
  if (o === null) return "null";
  if (o === true) return "true";
  if (o === false) return "false";
  if (typeof o === "number") return String(o);
  if (typeof o === "string") return JSON.stringify(o);
  if (Array.isArray(o)) return "[" + o.map(pyDumps).join(", ") + "]";
  if (typeof o === "object") {
    const keys = Object.keys(o).sort();
    return "{" + keys.map((k) => JSON.stringify(k) + ": " + pyDumps(o[k])).join(", ") + "}";
  }
  return JSON.stringify(o);
}

export function payloadHash(payload) {
  return sha256Hex(pyDumps(payload || {})).slice(0, 16);
}

export class KeyError extends Error {
  constructor(message) {
    super(message);
    this.name = "KeyError";
  }
}

class Event {
  constructor(requestId, text) {
    this.request_id = requestId;
    this.text = text;
    this.created = Date.now() / 1000;
    this.state = "received";
    this.decision = null;
    this.result = null;
    this.history = [];
    this.pending_approval = null;
  }

  log(transition, extra = {}) {
    this.history.push({ ts: Math.round(Date.now()) / 1000, state: transition, ...extra });
  }

  toDict() {
    return {
      request_id: this.request_id,
      text: this.text,
      state: this.state,
      decision: this.decision ? decisionToDict(this.decision) : null,
      result: this.result ? resultToDict(this.result) : null,
      pending_approval: this.pending_approval,
      history: this.history,
    };
  }
}

export class Engine {
  constructor(model, opts = {}) {
    this.router = new Router(model);
    this.nodes = opts.nodes || defaultNodes();
    this.policies = new Set(opts.policies === undefined || opts.policies === null
      ? DEFAULT_POLICIES : opts.policies);
    this.events = new Map();
    this._approvals = new Map(); // approval_id -> request_id
  }

  // Dry-run classification: report what WOULD happen. Executes nothing.
  preview(text) {
    const rid = `preview_${Date.now()}`;
    const decision = this.router.route(rid, text);
    const blocked = [...(decision._blocked || [])];
    const intent = decision.intent;
    const node = decision.node;

    let verdict;
    let says;
    if (intent === "out_of_scope") {
      verdict = "rejected";
      says = "That request is outside what I do on purpose. I can't pay, buy, delete, refund, or handle legal/hiring work.";
    } else if (node === null || blocked.includes("low_confidence") ||
               blocked.some((b) => b.startsWith("missing_params"))) {
      verdict = "needs_clarification";
      says = this._clarifyPrompt(decision);
    } else if (!(node in this.nodes)) {
      verdict = "failed";
      says = `No node '${node}' is wired up for that.`;
    } else {
      verdict = "routed";
      if (decision.requires_approval) {
        says = `That maps to '${node}' (${decision.risk_level}). I'll prepare it and ` +
               `pause for your approval before anything is sent or committed.`;
      } else {
        says = `That maps to '${node}' (${decision.risk_level}), which is pre-authorized, ` +
               `so I can run it directly.`;
      }
    }

    return { verdict, says, decision, blocked };
  }

  // -- public API -----------------------------------------------------
  process(requestId, text) {
    if (this.events.has(requestId)) {
      const ev = this.events.get(requestId);
      ev.log("duplicate_ignored", { note: "idempotency key already seen" });
      return ev; // idempotent: no duplicate side effects
    }

    const ev = new Event(requestId, text);
    this.events.set(requestId, ev);
    ev.log("received");

    const decision = this.router.route(requestId, text);
    ev.decision = decision;
    ev.log("classified", {
      intent: decision.intent,
      node: decision.node === null ? null : decision.node,
    });

    const blocked = decision._blocked || [];

    if (decision.intent === "out_of_scope") {
      ev.state = "rejected";
      ev.log("rejected", { reason: "out_of_scope_action_blocked" });
      return ev;
    }
    if (decision.node === null || blocked.includes("low_confidence") ||
        blocked.some((b) => b.startsWith("missing_params"))) {
      ev.state = "needs_clarification";
      ev.result = {
        request_id: requestId,
        status: Status.NEEDS_CLARIFICATION,
        summary: this._clarifyPrompt(decision),
        side_effect_performed: false,
        approval_request: null,
        error: null,
        simulated: true,
      };
      ev.log("needs_clarification", { blocked });
      return ev;
    }

    ev.log("validated");

    if (!(decision.node in this.nodes)) {
      ev.state = "failed";
      ev.log("failed", { reason: "unknown_node_rejected" });
      return ev;
    }

    ev.state = "routed";
    ev.log("routed", { node: decision.node });
    return this._runNode(ev);
  }

  approve(approvalId, payload = null) {
    const ev = this._eventForApproval(approvalId);
    const pending = ev.pending_approval;
    if (pending === null || pending === undefined) {
      throw new KeyError("no pending approval");
    }
    if (payload !== null && payload !== undefined &&
        payloadHash(payload) !== pending.payload_hash) {
      // payload changed -> old approval does not carry over
      ev.log("approval_invalidated", { reason: "payload_changed" });
      throw new Error("payload changed; a new approval is required");
    }
    ev.log("approved", { approval_id: approvalId });
    ev.pending_approval = null;
    this._approvals.delete(approvalId);
    // re-run the node WITH the specific action authorized
    return this._runNode(ev, pending.action);
  }

  reject(approvalId) {
    const ev = this._eventForApproval(approvalId);
    ev.pending_approval = null;
    this._approvals.delete(approvalId);
    ev.state = "rejected";
    ev.log("rejected", { approval_id: approvalId });
    return ev;
  }

  // -- internals ------------------------------------------------------
  _eventForApproval(approvalId) {
    const rid = this._approvals.get(approvalId);
    if (rid === undefined || !this.events.has(rid)) {
      throw new KeyError(`unknown approval ${JSON.stringify(approvalId)}`);
    }
    return this.events.get(rid);
  }

  _runNode(ev, extraPolicy = null) {
    const node = this.nodes[ev.decision.node];
    const policies = new Set(this.policies);
    if (extraPolicy) policies.add(extraPolicy);
    ev.state = "running";
    ev.log("running", { node: node.name });
    const res = node.handle(ev.decision, policies);
    ev.result = res;

    if (res.status === Status.NEEDS_APPROVAL) {
      const appr = res.approval_request || {};
      const hash = payloadHash(appr.payload || {});
      const approvalId = `apr_${ev.request_id}_${hash}`;
      const pending = {
        approval_id: approvalId,
        ...appr,
        payload_hash: hash,
        simulated: true,
      };
      ev.pending_approval = pending;
      this._approvals.set(approvalId, ev.request_id);
      ev.state = "awaiting_approval";
      ev.log("awaiting_approval", { approval_id: approvalId, action: appr.action });
    } else if (res.status === Status.SUCCEEDED) {
      ev.state = "succeeded";
      ev.log("succeeded", { side_effect: res.side_effect_performed });
    } else if (res.status === Status.NEEDS_CLARIFICATION) {
      ev.state = "needs_clarification";
      ev.log("needs_clarification", { summary: res.summary });
    } else {
      ev.state = "failed";
      ev.log("failed", { error: res.error });
    }
    return ev;
  }

  _clarifyPrompt(decision) {
    if (decision.node === null || decision.node === undefined) {
      return "I couldn't map that to a supported capability. Which of these did you mean?";
    }
    return "I need a bit more detail before I route this. Could you clarify?";
  }
}
