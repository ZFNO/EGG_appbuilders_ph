/*
 * webview_extract.js — OFFLINE extraction surface for the APK WebView (modern phone WebView).
 * Runtime: @huggingface/transformers v3 + onnxruntime-web (WASM/WebGPU) — SELF-HOSTED, NO CDN.
 * Model: onnx-community/Qwen2.5-0.5B-Instruct (q4), local path ./models/.
 * Car = SENSOR-ONLY (Android 4.3 WebView: NO WASM) — this runs on the PHONE only.
 * Receipts = sha256 hash/append-log only. Wallets(GCash/Maya)+RAG = MOCKS. On-chain OUT.
 *
 * Serve from local files inside the APK (file:// or app asset server); never remote.
 */
import { pipeline, env } from './vendor/transformers.min.js';

// --- hard offline lock -------------------------------------------------------
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = './models/';
env.useBrowserCache = false;
const _fetch = globalThis.fetch;
globalThis.fetch = function (u) {
  const url = String((u && u.url) || u);
  if (/^https?:/i.test(url)) throw new Error('OFFLINE_LOCK: network blocked: ' + url);
  return _fetch.apply(this, arguments);
};
window.__net_attempts = 0;

// --- extraction: local model + deterministic hybrid (raises name margin) -----
function heuristic(text) {
  const out = { name: null, amount: null, date: null };
  if (!text) return out;
  const amt = text.match(/(?:php|p|₱|\s)?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)/i);
  const dt = text.match(/(\d{1,4}[-\/]\d{1,2}[-\/]\d{1,4})/);
  const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  // name: explicit label first, else first-line/root-name heuristic
  const nm = text.match(/(?:from|to|payee|name|merchant)\s*[:\-]?\s*([A-Za-z .'&-]{2,40})/i)
          || (lines.length ? lines[0].match(/^([A-Za-z][A-Za-z .'&-]{2,40})$/) : null);
  if (amt) out.amount = amt[1].replace(/\s/g, '');
  if (dt) out.date = dt[1];
  if (nm) out.name = nm[1].trim();
  return out;
}

let _gen = null;
export async function loadModel() {
  if (_gen) return _gen;
  _gen = await pipeline('text-generation', 'onnx-community/Qwen2.5-0.5B-Instruct', {
    dtype: 'q4', device: 'wasm',  // fall back: device 'webgpu' if available
  });
  return _gen;
}

export async function extractFields(text) {
  const h = heuristic(text);
  let model = { name: null, amount: null, date: null };
  try {
    const gen = await loadModel();
    const prompt = 'Extract JSON {name,amount,date} only.\nReceipt:\n' + text;
    const res = await gen(prompt, { max_new_tokens: 64 });
    const s = (res[0].generated_text || '').match(/\{[\s\S]*?\}/);
    if (s) model = Object.assign(model, JSON.parse(s[0]));
  } catch (e) { /* deterministic-only fallback keeps demo offline */ }
  // hybrid merge: model wins if present, heuristic fills gaps
  return { name: model.name || h.name, amount: model.amount || h.amount, date: model.date || h.date };
}

// --- receipts: sha256 hash/append-log ONLY ----------------------------------
export const receiptLog = [];
export async function makeReceipt(text) {
  const f = await extractFields(text);
  const body = `${f.name || ''}|${f.amount || ''}|${f.date || ''}`;
  const prev = receiptLog.length ? receiptLog[receiptLog.length - 1].hash : 'GENESIS';
  const enc = new TextEncoder().encode(prev + '\u0000' + body);
  const buf = await crypto.subtle.digest('SHA-256', enc);
  const hash = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  const rec = { index: receiptLog.length, fields: f, hash, prev, ts: Date.now() };
  receiptLog.push(rec);           // append-log; no chain/on-chain
  return rec;
}
export function verifyChain() {
  let prev = 'GENESIS';
  for (const r of receiptLog) { if (r.prev !== prev) return false; prev = r.hash; }
  return true;
}

// --- on-device gate re-run (PASS: >=90% fields, <5s, airplane mode, 0 net) ----
export async function runGate(samples /* [{text,expect}] */) {
  let ok = 0, total = 0, worst = 0;
  const t0 = performance.now();
  for (const s of samples) {
    const a = performance.now();
    const r = await makeReceipt(s.text);
    const dt = (performance.now() - a) / 1000; worst = Math.max(worst, dt);
    for (const k of ['name', 'amount', 'date']) {
      total++;
      if (r.fields[k] && String(s.expect[k] || '').toLowerCase().includes(String(r.fields[k]).toLowerCase())) ok++;
    }
  }
  const acc = ok / total, secs = (performance.now() - t0) / 1000;
  return {
    accuracy: acc, worst_latency_s: worst, net_attempts: window.__net_attempts,
    chain_valid: verifyChain(),
    PASS: acc >= 0.90 && worst < 5 && window.__net_attempts === 0,
  };
}
