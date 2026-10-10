// EGG - the user identity profile document.
//
// A plain-language description of who you are and how you like the assistant to
// work. From it the model SUGGESTS values for the Options page (see infer()).
//
// Safety-first, matching the rest of the project: a deterministic rule parser
// ALWAYS produces a baseline suggestion set offline; the local model only
// ENHANCES it when a real backend is present. Nothing is applied until you
// confirm, and there is never a cloud fallback.
//
// Stored in localStorage under "data/profile.json" (mirrors the data/*.json
// files of the original project) with an in-memory fallback so the module also
// works under Node (smoke tests) where localStorage may be absent.

import * as configStore from "./config_store.js";
import * as scopeStore from "./scope_store.js";

export const PROFILE_KEY = "data/profile.json";

// A friendly starter document. Users edit this in their own words.
export const DEFAULT_PROFILE = `# Who I am
I run a small bicycle-repair shop and do all the admin myself. I like to move
fast and stay hands-off, so only stop me when money or a customer complaint is
involved.

# My urgency words
When I write "pronto" I mean right now.
"later today" just means before the day ends.

# Never touch
Never touch payroll or refunds, and nothing legal.`;

// Only these keys are ever produced/applied.
export const SUGGESTION_KEYS = [
  "use_model", "model", "confidence_floor",
  "urgency_critical", "urgency_high", "out_of_scope_keywords",
];

const _mem = new Map();

function _store() {
  if (typeof globalThis.localStorage !== "undefined" && globalThis.localStorage) {
    return globalThis.localStorage;
  }
  return {
    getItem: (k) => (_mem.has(k) ? _mem.get(k) : null),
    setItem: (k, v) => { _mem.set(k, String(v)); },
    removeItem: (k) => { _mem.delete(k); },
  };
}

export function defaults() { return { text: DEFAULT_PROFILE, updated: null }; }

export function load() {
  const out = defaults();
  try {
    const raw = _store().getItem(PROFILE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (data && typeof data === "object" && !Array.isArray(data)) {
        if (typeof data.text === "string") out.text = data.text;
        if (data.updated !== undefined) out.updated = data.updated;
      }
    }
  } catch (e) { /* fall back to defaults */ }
  return out;
}

export function save(text, opts = {}) {
  const cfg = {
    text: typeof text === "string" ? text : "",
    updated: opts.updated || new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  };
  try { _store().setItem(PROFILE_KEY, JSON.stringify(cfg, null, 2) + "\n"); } catch (e) {}
  return cfg;
}

export function clear() {
  try { _store().removeItem(PROFILE_KEY); } catch (e) {}
  return defaults();
}

// ---------------------------------------------------------------------------
// deterministic rule parser (always available, offline)
// ---------------------------------------------------------------------------

// Drop markdown heading lines (they are labels, not statements).
function _body(text) {
  return String(text || "").split(/\r?\n/).filter((l) => !/^\s*#/.test(l)).join("\n");
}

// One flat line (newlines within a paragraph are just spaces) so phrases like
// "move fast" survive a hard-wrapped document.
function _flat(text) { return _body(text).replace(/\s+/g, " ").trim(); }

// Sentence-ish chunks over the flattened text.
function _chunks(text) {
  return _flat(text).replace(/([.!?])\s+/g, "$1\u0000")
    .split("\u0000").map((s) => s.trim()).filter(Boolean);
}

function _quoted(s) {
  const out = [];
  const re = /["\u201c\u2018'"]([^"\u201d\u2019']{1,40})["\u201d\u2019'"]/g;
  let m;
  while ((m = re.exec(s))) out.push(m[1]);
  return out;
}

function _splitList(s) {
  return String(s).split(/[,;]|\band\b|\bor\b|[\u00b7\u2022]/i).map((x) => x.trim());
}

function _clean(s) {
  return String(s).toLowerCase()
    .replace(/^[\s\-*\u2022>.#]+/, "")
    .replace(/[.\s]+$/, "")
    .trim();
}

const LEAD = /^(never|avoid|don'?t|do not|no|exclude|block|forbid|touch|use|handle|process|deal with|work on|include|send|pay|issue|do|anything|nothing|all|any|every|me|my|your|the|a|an|to|of|with|from|on|in|about|want|wish|need|ever|again)\b\s*/i;
function _stripLead(w) {
  let prev = null;
  let out = w;
  while (out !== prev) { prev = out; out = out.replace(LEAD, ""); }
  return out.trim();
}

function _dedupe(arr) {
  const out = [];
  const seen = new Set();
  for (const raw of arr || []) {
    const k = _clean(raw);
    if (k && k.length <= 40 && !seen.has(k)) { seen.add(k); out.push(k); }
  }
  return out;
}

// Pull candidate terms out of a clause (quoted first, else after a colon or a
// "words/say/write/use/means" cue).
function _clauseItems(clause) {
  const q = _quoted(clause);
  if (q.length) return q.map(_clean).filter(Boolean);
  let seg = clause;
  const colon = seg.indexOf(":");
  if (colon >= 0 && colon < seg.length - 1) {
    seg = seg.slice(colon + 1);
  } else {
    const m = seg.match(/\b(?:words?|phrases?|say|says|write|use|uses|means|mean|are|is)\b[:,]?\s*(.+)$/i);
    if (m) seg = m[1];
  }
  return _splitList(seg).map(_clean).filter(Boolean);
}

function _reason(text, re) {
  for (const c of _chunks(text)) if (re.test(c)) return c;
  return null;
}

function _firstParagraph(text) {
  const out = [];
  for (const line of String(text || "").split(/\r?\n/)) {
    const s = line.trim();
    if (!s && out.length) break;
    if (!s || s.startsWith("#")) continue;
    out.push(s);
  }
  return out.join(" ").trim();
}

function _summary(text) {
  const p = _firstParagraph(text);
  if (!p) return null;
  return p.length > 160 ? p.slice(0, 157) + "\u2026" : p;
}

const C_CAUTIOUS = /(cautious|careful|conservative|risk[- ]?averse|double[- ]?check|always (ask|confirm|check)|check with me|confirm with me|ask me (first|before)|approve (everything|each)|high confidence|don'?t trust|be sure)/i;
const C_FAST = /(move fast|act fast|be fast|quick|hands?[- ]?off|automatic|autopilot|trust you|trust it|just do it|low friction|as little friction|don'?t bother me|don'?t ask|don'?t stop|no need to ask)/i;
const C_NOMODEL = /(no model|rules? only|offline only|no ai|without the model|don'?t use the model|keep it private|for privacy|privacy)/i;
const C_WANTMODEL = /(use the model|with the model|enable the model|let the (model|ai)|use ai|use the llm)/i;
const C_CRIT = /(critical|emergency|drop everything|right (now|away)|immediately|pronto|asap)/i;
const C_HIGH = /(urgent|high priority|same[- ]?day|later today|by today|soon|this week)/i;
const C_OOS = /(never|avoid|don'?t|do not|exclude|out of scope|off[- ]?limits|not allowed|block|forbid)/i;

function _collectMarked(text, marker) {
  const out = [];
  for (const c of _chunks(text)) {
    if (!marker.test(c)) continue;
    for (const it of _clauseItems(c)) out.push(it);
  }
  return _dedupe(out);
}

function _collectOos(text) {
  const out = [];
  for (const c of _chunks(text)) {
    const m = c.match(C_OOS);
    if (!m) continue;
    const seg = c.slice(m.index);            // from the trigger word on
    for (const it of _clauseItems(seg)) out.push(_stripLead(it));
  }
  return _dedupe(out).filter((w) => w.length > 1);
}

export function inferRules(doc) {
  const text = String(doc || "");
  const low = _flat(text).toLowerCase();
  const suggestions = {};
  const why = {};

  const cautious = C_CAUTIOUS.test(low);
  const fast = C_FAST.test(low);
  if (cautious && !fast) {
    suggestions.confidence_floor = 0.9;
    why.confidence_floor = _reason(text, C_CAUTIOUS);
  } else if (fast && !cautious) {
    suggestions.confidence_floor = 0.65;
    why.confidence_floor = _reason(text, C_FAST);
  }

  const noModel = C_NOMODEL.test(low);
  const wantModel = C_WANTMODEL.test(low);
  if (noModel && !wantModel) {
    suggestions.use_model = false;
    why.use_model = _reason(text, C_NOMODEL);
  } else if (wantModel && !noModel) {
    suggestions.use_model = true;
    why.use_model = _reason(text, C_WANTMODEL);
  }

  const crit = _collectMarked(text, C_CRIT);
  if (crit.length) { suggestions.urgency_critical = crit; why.urgency_critical = _reason(text, C_CRIT); }

  const high = _collectMarked(text, C_HIGH).filter((w) => !crit.includes(w));
  if (high.length) { suggestions.urgency_high = high; why.urgency_high = _reason(text, C_HIGH); }

  const oos = _collectOos(text);
  if (oos.length) { suggestions.out_of_scope_keywords = oos; why.out_of_scope_keywords = _reason(text, C_OOS); }

  return { suggestions, why };
}

// ---------------------------------------------------------------------------
// merge + normalise
// ---------------------------------------------------------------------------

function _normSuggestions(s) {
  const out = {};
  if (!s || typeof s !== "object") return out;
  if (s.use_model !== undefined) out.use_model = !!s.use_model;
  if (s.model !== undefined && s.model !== null && s.model !== "") out.model = String(s.model);
  if (s.confidence_floor !== undefined) {
    const n = Number(s.confidence_floor);
    if (Number.isFinite(n)) out.confidence_floor = Math.min(1, Math.max(0, n));
  }
  if (Array.isArray(s.urgency_critical)) out.urgency_critical = _dedupe(s.urgency_critical);
  if (Array.isArray(s.urgency_high)) out.urgency_high = _dedupe(s.urgency_high);
  if (Array.isArray(s.out_of_scope_keywords)) out.out_of_scope_keywords = _dedupe(s.out_of_scope_keywords);
  return out;
}

function _withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("model timed out")), ms);
    Promise.resolve(promise).then(
      (v) => { clearTimeout(t); resolve(v); },
      (e) => { clearTimeout(t); reject(e); },
    );
  });
}

// Rules baseline, optionally enhanced by a local model.
//   opts.llm(text) -> Promise<{ suggestions, why?, summary?, notes? }>
export async function infer(doc, opts = {}) {
  const text = String(doc === undefined || doc === null ? load().text : doc);
  const base = inferRules(text);
  const out = {
    source: "rules",
    suggestions: { ...base.suggestions },
    why: { ...base.why },
    notes: [],
    summary: _summary(text),
  };

  const llm = opts.llm;
  if (typeof llm === "function") {
    try {
      const m = await _withTimeout(llm(text), opts.timeoutMs || 8000);
      const ms = m && (m.suggestions || m);
      const norm = _normSuggestions(ms);
      if (Object.keys(norm).length) {
        out.source = "rules+model";
        for (const [k, v] of Object.entries(norm)) {
          if (base.suggestions[k] !== undefined &&
              JSON.stringify(base.suggestions[k]) !== JSON.stringify(v)) {
            out.notes.push(`rules and model differ on ${k}; using the model`);
          }
          out.suggestions[k] = v;
          out.why[k] = (m && m.why && m.why[k]) || "suggested by the model";
        }
        if (m && m.summary) out.summary = m.summary;
        if (m && Array.isArray(m.notes)) out.notes.push(...m.notes);
      } else {
        out.notes.push("model returned nothing usable; rules only");
      }
    } catch (e) {
      out.notes.push("model unavailable; rules only (" + (e && e.message ? e.message : e) + ")");
    }
  }

  out.suggestions = _normSuggestions(out.suggestions);
  return out;
}

// Persist a suggestion set: config keys to config_store, keywords to
// scope_store (merged with the existing list, never silently dropped).
export function apply(suggestions = {}) {
  const s = _normSuggestions(suggestions);
  const cfgPatch = {};
  for (const k of ["use_model", "model", "confidence_floor", "urgency_critical", "urgency_high"]) {
    if (s[k] !== undefined) cfgPatch[k] = s[k];
  }
  if (Object.keys(cfgPatch).length) configStore.save(cfgPatch);
  if (Array.isArray(s.out_of_scope_keywords)) {
    scopeStore.save([...scopeStore.outOfScopeKeywords(), ...s.out_of_scope_keywords]);
  }
  return { config: configStore.load(), scope: scopeStore.load() };
}
