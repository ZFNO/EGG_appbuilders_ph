// Invisible Secretary - capability nodes (port of nodes.py, mock adapters).
//
// Each node validates its own inputs, enforces business rules, executes a MOCK
// integration, and returns a typed result. Mocked integrations are always
// labeled simulated=true. A node never sends, pays, deletes, or commits on its
// own: consequential actions come back as needs_approval bound to the payload.

import { Status } from "./schemas.js";

// Pre-authorized, reversible, low-impact actions the owner has explicitly
// configured. Anything consequential (send/pay/delete/commit) is NOT here and
// therefore requires fresh approval.
export const DEFAULT_POLICIES = new Set(["route_to_queue"]);

function result(requestId, status, fields = {}) {
  return {
    request_id: requestId,
    status,
    summary: fields.summary || "",
    side_effect_performed: fields.side_effect_performed || false,
    approval_request: fields.approval_request === undefined ? null : fields.approval_request,
    error: fields.error === undefined ? null : fields.error,
    simulated: fields.simulated === undefined ? true : fields.simulated,
  };
}

export class BaseNode {
  constructor(opts = {}) {
    this.name = this.constructor.name === "BaseNode" ? "base" : (this.name || "base");
    this.healthy = opts.healthy === undefined ? true : opts.healthy;
  }

  health() {
    return {
      node: this.name,
      health: this.healthy ? "ok" : "degraded",
      simulated: true,
    };
  }

  handle(decision, policies) {
    const pol = policies === undefined || policies === null ? DEFAULT_POLICIES : policies;
    if (!this.healthy) {
      return result(decision.request_id, Status.FAILED, {
        summary: `${this.name} node unavailable`,
        error: "node_unhealthy",
      });
    }
    return this._run(decision, pol);
  }

  _run() {
    throw new Error("NotImplementedError");
  }
}

export class FollowupNode extends BaseNode {
  constructor(opts = {}) {
    super(opts);
    this.name = "followup";
    this.description = "Prepare and (on approval) send a follow-up message.";
    this.consequential_action = "send_message";
  }

  _run(decision, policies) {
    const p = decision.parameters;
    if (!p.entity_type) {
      return result(decision.request_id, Status.NEEDS_CLARIFICATION, {
        summary: "Which party should be followed up?",
      });
    }
    const party = p.entity_name || `the ${p.entity_type}`;
    const topic = p.topic || "the open item";
    const draft = `Hi ${party}, quick follow-up on ${topic}.` +
      (p.deadline ? ` Needed by ${p.deadline}.` : "");
    if (policies.has(this.consequential_action)) {
      // Owner pre-authorized a narrow send policy (not the default).
      return result(decision.request_id, Status.SUCCEEDED, {
        summary: `[SIMULATED] Sent follow-up to ${party}.`,
        side_effect_performed: true,
        simulated: true,
      });
    }
    return result(decision.request_id, Status.NEEDS_APPROVAL, {
      summary: "Draft follow-up prepared; awaiting approval.",
      side_effect_performed: false,
      approval_request: {
        action: this.consequential_action,
        target: party,
        description: `Send the prepared message to ${party}`,
        payload: { message: draft, topic },
      },
      simulated: true,
    });
  }
}

export class SchedulingNode extends BaseNode {
  constructor(opts = {}) {
    super(opts);
    this.name = "scheduling";
    this.description = "Propose and (on approval) commit a schedule change.";
    this.consequential_action = "commit_schedule_change";
  }

  _run(decision, policies) {
    const p = decision.parameters;
    if (!p.topic) {
      return result(decision.request_id, Status.NEEDS_CLARIFICATION, {
        summary: "What schedule change should I propose?",
      });
    }
    const proposal = `${p.topic}` + (p.deadline ? ` by ${p.deadline}` : "");
    if (policies.has(this.consequential_action)) {
      return result(decision.request_id, Status.SUCCEEDED, {
        summary: `[SIMULATED] Committed schedule change: ${proposal}.`,
        side_effect_performed: true,
        simulated: true,
      });
    }
    return result(decision.request_id, Status.NEEDS_APPROVAL, {
      summary: "Schedule change proposed; awaiting approval.",
      side_effect_performed: false,
      approval_request: {
        action: this.consequential_action,
        target: "calendar",
        description: `Commit schedule change: ${proposal}`,
        payload: { change: proposal },
      },
      simulated: true,
    });
  }
}

export class CustomerRequestNode extends BaseNode {
  constructor(opts = {}) {
    super(opts);
    this.name = "customer_request";
    this.description = "Triage a customer request and route it to a queue.";
    this.consequential_action = "route_to_queue";
  }

  _run(decision, policies) {
    const p = decision.parameters;
    if (!p.topic) {
      return result(decision.request_id, Status.NEEDS_CLARIFICATION, {
        summary: "What is the customer request?",
      });
    }
    const queue = "support.tier1";
    if (policies.has(this.consequential_action)) {
      // reversible, pre-authorized
      return result(decision.request_id, Status.SUCCEEDED, {
        summary: `[SIMULATED] Routed customer request to ${queue}.`,
        side_effect_performed: true,
        simulated: true,
      });
    }
    return result(decision.request_id, Status.NEEDS_APPROVAL, {
      summary: "Customer request triaged; awaiting approval to route.",
      approval_request: {
        action: this.consequential_action,
        target: queue,
        description: `Route the request to ${queue}`,
        payload: { topic: p.topic, queue },
      },
      simulated: true,
    });
  }
}

export function defaultNodes() {
  const nodes = [new FollowupNode(), new SchedulingNode(), new CustomerRequestNode()];
  const out = {};
  for (const n of nodes) out[n.name] = n;
  return out;
}
