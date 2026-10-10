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

test("out-of-scope rejects before routing", async () => {
  const eng = newEngine();
  const ev = await eng.process("oos1", "Pay the Acme invoice 88213 today");
  assert.equal(ev.state, "rejected");
  assert.equal(ev.decision.intent, "out_of_scope");
  assert.equal(ev.decision.node, null);
});

test("low-confidence request asks to clarify (never guesses)", async () => {
  const eng = newEngine();
  const ev = await eng.process("low1", "Please reschedule something");
  assert.equal(ev.state, "needs_clarification");
  assert.equal(ev.result.status, "needs_clarification");
});

test("R3 consequential request needs approval (bound to exact payload)", async () => {
  const eng = newEngine();
  const ev = await eng.process("r3a", "Follow up with Acme supplier - order #4471 not confirmed");
  assert.equal(ev.state, "awaiting_approval");
  assert.equal(ev.decision.risk_level, "R3");
  assert.equal(ev.decision.requires_approval, true);
  assert.ok(ev.pending_approval && ev.pending_approval.approval_id);
  assert.equal(ev.pending_approval.simulated, true);
});

test("R2 route_to_queue is pre-authorized and succeeds", async () => {
  const eng = newEngine();
  const ev = await eng.process("r2a", "Customer reports a broken widget, asks for help");
  assert.equal(ev.state, "succeeded");
  assert.equal(ev.decision.risk_level, "R2");
  assert.equal(ev.result.side_effect_performed, true);
  assert.equal(ev.result.simulated, true);
});

test("high urgency never bypasses authorization", async () => {
  const eng = newEngine();
  const ev = await eng.process("urg1",
    "URGENT today: follow up with Acme supplier - order #4471 not confirmed, ASAP");
  assert.equal(ev.decision.requires_approval, true);
  assert.equal(ev.state, "awaiting_approval");
  assert.ok(["high", "critical"].includes(ev.decision.urgency_level));
});

test("approval re-runs the node; a changed payload is invalidated", async () => {
  const eng = newEngine();
  const ev = await eng.process("appr1", "Follow up with Acme supplier - order #4471 not confirmed");
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

test("identity profile: rules read the doc into suggested options", async () => {
  const { infer, inferRules, DEFAULT_PROFILE } = await import("../profile_store.js");

  const r = inferRules(DEFAULT_PROFILE);
  assert.equal(r.suggestions.confidence_floor, 0.65);            // "move fast"
  assert.deepEqual(r.suggestions.urgency_critical, ["pronto"]);  // quoted critical word
  assert.ok(r.suggestions.urgency_high.includes("later today"));
  assert.deepEqual(r.suggestions.out_of_scope_keywords, ["payroll", "refunds", "legal"]);
  assert.ok(r.why.confidence_floor && r.why.confidence_floor.length > 0);

  const cautious = inferRules("Be careful and always confirm with me before acting.");
  assert.equal(cautious.suggestions.confidence_floor, 0.9);

  const base = await infer(DEFAULT_PROFILE);
  assert.equal(base.source, "rules");
});

test("identity profile: the model enhances, and falls back to rules on failure", async () => {
  const { infer, DEFAULT_PROFILE } = await import("../profile_store.js");

  const merged = await infer(DEFAULT_PROFILE, {
    llm: async () => ({ suggestions: { confidence_floor: 0.5 }, summary: "from the model" }),
  });
  assert.equal(merged.source, "rules+model");
  assert.equal(merged.suggestions.confidence_floor, 0.5);            // model wins
  assert.ok(merged.suggestions.out_of_scope_keywords.includes("payroll")); // rules kept
  assert.equal(merged.summary, "from the model");

  const failed = await infer(DEFAULT_PROFILE, { llm: async () => { throw new Error("down"); } });
  assert.equal(failed.source, "rules");
  assert.ok(failed.notes.some((n) => /model unavailable/.test(n)));
});

test("identity profile: /api/profile saves, infers and applies (no network)", async () => {
  const before = await api.handle("GET", "/api/config");
  const floor0 = before.data.policy.confidence_floor;

  const saved = await api.handle("POST", "/api/profile",
    { text: "Move fast and stay hands-off. Never touch invoices." });
  assert.equal(saved.status, 200);
  assert.ok(saved.data.profile.updated);
  assert.equal(saved.data.inference.source, "rules");
  assert.equal(saved.data.inference.suggestions.confidence_floor, 0.65);
  assert.deepEqual(saved.data.inference.suggestions.out_of_scope_keywords, ["invoices"]);

  const applied = await api.handle("POST", "/api/profile/apply",
    { suggestions: { confidence_floor: 0.65, out_of_scope_keywords: ["invoices"] } });
  assert.equal(applied.status, 200);
  assert.equal(applied.data.policy.confidence_floor, 0.65);
  assert.ok(applied.data.scope.out_of_scope_keywords.includes("invoices"));
  assert.ok(applied.data.scope.out_of_scope_keywords.includes("pay")); // merged, not replaced

  // an applied out-of-scope word now rejects before routing
  const ev = await api.engine.process("profrej", "Handle the invoices today");
  assert.equal(ev.state, "rejected");

  // restore
  await api.handle("POST", "/api/config",
    { confidence_floor: floor0, out_of_scope_keywords: before.data.defaults.out_of_scope_keywords });
  await api.handle("POST", "/api/profile/clear");
  const after = await api.handle("GET", "/api/config");
  assert.equal(after.data.policy.confidence_floor, floor0);
});

test("example profiles are a rich, distinct set - each one yields suggestions", async () => {
  const { EXAMPLES, DEFAULT_PROFILE, inferRules, randomExample } = await import("../profile_store.js");

  assert.ok(EXAMPLES.length >= 5, "expected several example personas");
  assert.equal(new Set(EXAMPLES).size, EXAMPLES.length, "examples must be distinct");
  assert.equal(EXAMPLES[0], DEFAULT_PROFILE, "the first example is the starter");

  for (const ex of EXAMPLES) {
    assert.ok(ex.length > 250, "each example should be a comprehensive document");
    assert.match(ex, /# Who I am/, "each example names an identity");
    assert.match(ex, /# Never touch/, "each example says what to never touch");
    const r = inferRules(ex);
    assert.ok(r.suggestions.confidence_floor !== undefined, "each example sets a confidence floor");
    assert.ok(r.suggestions.out_of_scope_keywords.length >= 2, "each example names rejected terms");
    assert.ok(r.suggestions.urgency_critical.length >= 1, "each example names a critical word");
    assert.ok(r.suggestions.urgency_high.length >= 1, "each example names a high-urgency word");
  }
});

test("randomExample never repeats the text already on screen", async () => {
  const { EXAMPLES, DEFAULT_PROFILE, randomExample } = await import("../profile_store.js");

  for (const ex of EXAMPLES) {
    for (let i = 0; i < 50; i++) {
      const picked = randomExample(ex);
      assert.notEqual(picked, ex);
      assert.ok(EXAMPLES.includes(picked));
    }
  }
  // a deterministic pick still avoids the excluded text
  assert.notEqual(randomExample(DEFAULT_PROFILE, () => 0), DEFAULT_PROFILE);
  // exclusive-matches-everything still returns a valid example
  assert.ok(EXAMPLES.includes(randomExample(EXAMPLES.join(""))));
});

test("the profile API exposes the example set for reroll", async () => {
  const o = await api.handle("GET", "/api/profile");
  assert.equal(o.status, 200);
  assert.ok(Array.isArray(o.data.examples));
  assert.ok(o.data.examples.length >= 5);
  assert.equal(o.data.examples[0], o.data.defaults);
});
