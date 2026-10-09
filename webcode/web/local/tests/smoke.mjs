// Smoke test for the browser port of Invisible Secretary.
//   node --test webcode/web/local/tests/smoke.mjs
//
// Exercises the SAME engine the pages use, through the same ES modules, with no
// DOM and no network. Asserts the five safety-critical behaviours.

import test from "node:test";
import assert from "node:assert/strict";

// --- minimal localStorage so scope_store has a persistence home in Node ---
const _ls = new Map();
globalThis.localStorage = {
  getItem: (k) => (_ls.has(k) ? _ls.get(k) : null),
  setItem: (k, v) => { _ls.set(k, String(v)); },
  removeItem: (k) => { _ls.delete(k); },
};

// dynamic imports AFTER the shim above is installed
const { Engine } = await import("../engine.js");
const { defaultAdapter } = await import("../factory.js");
const apiModule = await import("../api.js");
const api = apiModule.default || apiModule.api;

const newEngine = () => new Engine(defaultAdapter({ useModel: true }));

test("out-of-scope rejects before routing", () => {
  const eng = newEngine();
  const ev = eng.process("oos1", "Pay the Acme invoice 88213 today");
  assert.equal(ev.state, "rejected");
  assert.equal(ev.decision.intent, "out_of_scope");
  assert.equal(ev.decision.node, null);
});

test("low-confidence request asks to clarify (never guesses)", () => {
  const eng = newEngine();
  const ev = eng.process("low1", "Please reschedule something");
  assert.equal(ev.state, "needs_clarification");
  assert.equal(ev.result.status, "needs_clarification");
});

test("R3 consequential request needs approval (bound to exact payload)", () => {
  const eng = newEngine();
  const ev = eng.process("r3a", "Follow up with Acme supplier - order #4471 not confirmed");
  assert.equal(ev.state, "awaiting_approval");
  assert.equal(ev.decision.risk_level, "R3");
  assert.equal(ev.decision.requires_approval, true);
  assert.ok(ev.pending_approval && ev.pending_approval.approval_id);
  assert.equal(ev.pending_approval.simulated, true);
});

test("R2 route_to_queue is pre-authorized and succeeds", () => {
  const eng = newEngine();
  const ev = eng.process("r2a", "Customer reports a broken widget, asks for help");
  assert.equal(ev.state, "succeeded");
  assert.equal(ev.decision.risk_level, "R2");
  assert.equal(ev.result.side_effect_performed, true);
  assert.equal(ev.result.simulated, true);
});

test("high urgency never bypasses authorization", () => {
  const eng = newEngine();
  const ev = eng.process("urg1",
    "URGENT today: follow up with Acme supplier - order #4471 not confirmed, ASAP");
  assert.equal(ev.decision.requires_approval, true);
  assert.equal(ev.state, "awaiting_approval");
  assert.ok(["high", "critical"].includes(ev.decision.urgency_level));
});

test("approval re-runs the node; a changed payload is invalidated", () => {
  const eng = newEngine();
  const ev = eng.process("appr1", "Follow up with Acme supplier - order #4471 not confirmed");
  const id = ev.pending_approval.approval_id;

  // a changed payload must NOT carry the old approval
  assert.throws(() => eng.approve(id, { message: "tampered" }),
    /new approval is required/);

  const done = eng.approve(id);
  assert.equal(done.state, "succeeded");
});

test("fetch shim routes /api/* to the in-browser engine (no network)", async () => {
  const routed = await api.handle("POST", "/api/route",
    { request_id: "shim1", text: "Chase the customer at Bright Co about the late delivery" });
  assert.equal(routed.status, 200);
  assert.equal(routed.data.state, "awaiting_approval");
  assert.equal(routed.data.decision.risk_level, "R3");

  const scope = await api.handle("GET", "/api/scope");
  assert.equal(scope.status, 200);
  assert.ok(Array.isArray(scope.data.out_of_scope_keywords));
  assert.ok(scope.data.out_of_scope_keywords.includes("pay"));
  assert.equal(scope.data.confidence_floor, 0.8);
});
