// Async message bus: the single queue spine (port of bus.py).
//
// Every input (fetch shim, future watchers) is published as a Message onto ONE
// Bus. A long-running worker task (see pipeline.worker) consumes the queue and
// runs each message through the ordered pipeline. This module owns the
// concurrency primitives only; business logic stays in the sync engine.

function randHex(n) {
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    const a = new Uint8Array(n);
    crypto.getRandomValues(a);
    return [...a].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
  }
  let s = "";
  while (s.length < n) s += Math.floor(Math.random() * 16).toString(16);
  return s.slice(0, n);
}

// Minimal awaitable future, mirroring the subset of asyncio.Future used here.
export class Deferred {
  constructor() {
    this.done = false;
    this.promise = new Promise((resolve, reject) => {
      this._resolve = resolve;
      this._reject = reject;
    });
  }

  setResult(value) {
    if (this.done) return;
    this.done = true;
    this._resolve(value);
  }

  setException(exc) {
    if (this.done) return;
    this.done = true;
    this._reject(exc);
  }
}

// A unit of work on the spine. `replies` optionally carries the result back to
// the producer; when set, the worker resolves it. `id` doubles as the engine's
// idempotency key.
export class Message {
  constructor(kind, payload, opts = {}) {
    this.kind = kind;
    this.payload = payload;
    this.id = opts.id || `msg_${randHex(10)}`;
    this.source = opts.source === undefined ? "unknown" : opts.source;
    this.created = Date.now() / 1000;
    this.replies = opts.replies === undefined ? null : opts.replies;
  }

  resolve(value) {
    if (this.replies !== null && this.replies !== undefined && !this.replies.done) {
      this.replies.setResult(value);
    }
  }

  fail(exc) {
    if (this.replies !== null && this.replies !== undefined && !this.replies.done) {
      this.replies.setException(exc);
    }
  }
}

// A bounded queue plus lightweight counters.
// Bounded => publishers await when the spine is full (natural backpressure).
export class Bus {
  constructor(maxsize = 256) {
    this.maxsize = maxsize;
    this.q = [];
    this.published = 0;
    this.dequeued = 0;
    this._pending = 0;
    this._getWaiters = [];
    this._putWaiters = [];
    this._joinWaiters = [];
  }

  async publish(msg) {
    while (this.q.length >= this.maxsize) {
      await new Promise((res) => this._putWaiters.push(res));
    }
    this.q.push(msg);
    this._pending += 1;
    this.published += 1;
    const w = this._getWaiters.shift();
    if (w) w();
  }

  async get() {
    while (this.q.length === 0) {
      await new Promise((res) => this._getWaiters.push(res));
    }
    const msg = this.q.shift();
    this.dequeued += 1;
    const p = this._putWaiters.shift();
    if (p) p();
    return msg;
  }

  taskDone() {
    if (this._pending > 0) this._pending -= 1;
    if (this._pending === 0) {
      const ws = this._joinWaiters.splice(0);
      for (const w of ws) w();
    }
  }

  join() {
    if (this._pending === 0 && this.q.length === 0) return Promise.resolve();
    return new Promise((res) => this._joinWaiters.push(res));
  }

  full() {
    return this.q.length >= this.maxsize;
  }

  qsize() {
    return this.q.length;
  }
}
