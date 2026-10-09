// Runtime wiring: assemble bus + engine + pipeline, and start worker tasks.
// Port of runtime.py. Kept in one place so api.js, the pages and tests build the
// same object graph. Includes a thin AsyncEngine facade for async callers.

import { Bus } from "./bus.js";
import { Engine } from "./engine.js";
import { defaultAdapter } from "./factory.js";
import { PIPELINE, Context, worker } from "./pipeline.js";

// Simple event-like stop flag (mirrors asyncio.Event.set() / .is_set()).
export class StopFlag {
  constructor() {
    this._set = false;
  }

  is_set() {
    return this._set;
  }

  set() {
    this._set = true;
  }
}

export function buildEngine(opts = {}) {
  const useModel = opts.useModel === undefined ? true : opts.useModel;
  return new Engine(defaultAdapter({ useModel, model: opts.model }));
}

// Return { bus, ctx, engine } -- the spine and its shared state.
export function buildRuntime(opts = {}) {
  const useModel = opts.useModel === undefined ? true : opts.useModel;
  const maxsize = opts.maxsize === undefined ? 256 : opts.maxsize;
  const engine = buildEngine({ useModel, model: opts.model });
  const bus = new Bus(maxsize);
  return { bus, ctx: new Context(engine), engine };
}

// Spawn worker task(s) on the spine. Fan-out via `workers` (default 1).
export function startWorkers(bus, ctx, opts = {}) {
  const stages = opts.stages || PIPELINE;
  const workers = opts.workers === undefined ? 1 : opts.workers;
  const stop = opts.stop || new StopFlag();
  const tasks = [];
  for (let i = 0; i < Math.max(1, workers); i++) {
    tasks.push(worker(bus, stages, ctx, { stop }));
  }
  return { tasks, stop };
}

// Thin async facade over the sync engine.
export class AsyncEngine {
  constructor(engine) {
    this._engine = engine;
  }

  async process(requestId, text) {
    return this._engine.process(requestId, text);
  }

  async approve(approvalId, payload = null) {
    return this._engine.approve(approvalId, payload);
  }

  async reject(approvalId) {
    return this._engine.reject(approvalId);
  }
}
