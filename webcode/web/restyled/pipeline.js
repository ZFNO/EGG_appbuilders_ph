// Processing pipeline: ordered stages run by the bus worker (port of pipeline.py).
//
// Each Message flows through the ordered `stages`; the first stage that produces
// a result wins and handled=false short-circuits the rest. The worker is the
// single consumer of the Bus and MUST be unkillable by a bad message: a failing
// stage resolves its reply future with a *structured* failure payload (never
// set_exception), so no traceback - and no reference to the worker frame - ever
// escapes the loop.

export class StageOutcome {
  constructor(result = null, handled = true, meta = {}) {
    this.result = result;
    this.handled = handled;
    this.meta = meta;
  }
}

export class CancelledError extends Error {
  constructor(message = "cancelled") {
    super(message);
    this.name = "CancelledError";
  }
}

export class Context {
  constructor(engine) {
    this.engine = engine;
  }

  // Convenience "offload" hook; in the browser this is just an await.
  async inThread(fn, ...args) {
    return await fn(...args);
  }
}

export async function secretaryStage(msg, ctx) {
  const eng = ctx.engine;
  let ev;
  if (msg.kind === "secretary.request") {
    ev = await ctx.inThread((id, text) => eng.process(id, text), msg.id, msg.payload.text || "");
  } else if (msg.kind === "secretary.approve") {
    ev = await ctx.inThread(
      (approvalId, payload) => eng.approve(approvalId, payload === undefined ? null : payload),
      msg.payload.approval_id, msg.payload.payload);
  } else if (msg.kind === "secretary.reject") {
    ev = await ctx.inThread((approvalId) => eng.reject(approvalId), msg.payload.approval_id);
  } else {
    throw new Error(`unknown message kind ${JSON.stringify(msg.kind)}`);
  }
  return new StageOutcome(ev.toDict());
}

export const PIPELINE = [secretaryStage];
export const STAGE_REGISTRY = { secretary: secretaryStage };

export async function runPipeline(stages, msg, ctx) {
  let result = null;
  for (const stage of stages) {
    const outcome = await stage(msg, ctx);
    if (outcome.result !== null && outcome.result !== undefined) {
      result = outcome.result;
    }
    if (!outcome.handled) break;
  }
  return result;
}

// Structured, JSON-serialisable failure for a stage that raised.
export function failurePayload(exc) {
  return {
    state: "failed",
    error: {
      type: (exc && exc.name) ? exc.name : "Error",
      message: exc && exc.message !== undefined ? String(exc.message) : String(exc),
    },
  };
}

// Dequeue and process exactly one message; never rejects for a bad message.
async function _runOne(bus, stages, ctx) {
  const msg = await bus.get();
  try {
    let result;
    try {
      result = await runPipeline(stages, msg, ctx);
    } catch (exc) {
      // A failing stage must not kill the worker.
      const payload = failurePayload(exc);
      // In Python a live traceback held a frame of the worker coroutine; here we
      // simply never let a raw exception reach a caller through the future.
      msg.resolve(payload);
      return;
    }
    msg.resolve(result);
  } finally {
    bus.taskDone();
  }
}

// Single consumer of the bus.
//
// Bullet-proof: a failing stage is turned into a structured reply, and a
// defensive outer guard ensures nothing can escape the loop and strand later
// messages. Shutdown is by cancelling the task (CancelledError ends it).
export async function worker(bus, stages, ctx, opts = {}) {
  const stop = opts.stop;
  while (!stop.is_set()) {
    try {
      await _runOne(bus, stages, ctx);
    } catch (exc) {
      if (exc instanceof CancelledError) {
        break; // cooperative shutdown
      }
      // Nothing - bad payloads, stray errors - may kill the worker.
      if (typeof console !== "undefined" && console.warn) {
        console.warn("worker guard swallowed", exc, "; continuing");
      }
      await new Promise((r) => setTimeout(r, 0));
    }
  }
}
