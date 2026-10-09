// src/extract.js  -  OFFLINE receipt-field extraction on the BROWSER runtime.
// Runtime: @huggingface/transformers v4 -> onnxruntime-web (WASM).
// This is the WebView-usable twin of spike/extract.mjs (which ran onnxruntime-node).
// No CDN: env.allowRemoteModels=false, localModelPath='./models/', wasmPaths='./ort/'.
import { pipeline, env } from '@huggingface/transformers';

export const MODEL_ID = 'onnx-community/Qwen2.5-0.5B-Instruct';
export const DTYPE = 'q4';

const SYS = 'You are a receipt field extractor. From the user text, reply with ONLY one compact JSON object, no prose, no code fences: {"name":string,"amount":string,"date":string}. amount = digits with a dot, no commas or currency symbols. date = the date exactly as written. Use "" if a field is missing.';
const EX1U = 'SM SUPERMARKET CEBU\n12/03/25  14:22\nTOTAL PHP 1,248.75\nCARD ****4417\nSalamat!';
const EX1A = '{"name":"SM Supermarket Cebu","amount":"1248.75","date":"12/03/25"}';

export const SAMPLES = [
  { text: 'SM SUPERMARKET CEBU\n12/03/25  14:22\nTOTAL PHP 1,248.75\nCARD ****4417\nSalamat!', gold: { name: 'SM Supermarket Cebu', amount: '1248.75', date: '12/03/25' } },
  { text: 'Jollibee - Ayala\nOrder #A21\nNov 18, 2025\nAmount Due: 356.00 pesos', gold: { name: 'Jollibee - Ayala', amount: '356.00', date: 'Nov 18, 2025' } },
  { text: 'paid Meralco bill\nacct 1192-883\nPHP 2,340.10\n2025-10-09', gold: { name: 'Meralco', amount: '2340.10', date: '2025-10-09' } },
  { text: 'Grab ride to BGC\n09 Oct 2025 07:41\nFare 187.50\npls rate', gold: { name: 'Grab', amount: '187.50', date: '09 Oct 2025' } },
  { text: 'Coffee at Starbucks BGC\n10/09/2025\nTotal: P 215.00', gold: { name: 'Starbucks BGC', amount: '215.00', date: '10/09/2025' } },
  { text: 'WATSONS PHARMACY\n2025/09/30\n3 items\nPHP 640.25\nSukat', gold: { name: 'Watsons Pharmacy', amount: '640.25', date: '2025/09/30' } },
  { text: 'Lalamove delivery\nSept 9 2025\n88.00 PHP\nTaguig', gold: { name: 'Lalamove', amount: '88.00', date: 'Sept 9 2025' } },
  { text: 'Puregold receipt\n09-10-25\nTOTAL 1,102.40\nThank you', gold: { name: 'Puregold', amount: '1102.40', date: '09-10-25' } },
  { text: 'PayMaya load\n2025-11-02\nSent PHP 500.00 to 0917xxxxxxx', gold: { name: 'PayMaya load', amount: '500.00', date: '2025-11-02' } },
  { text: 'Netflix subscription\nOctober 1, 2025\nAmount: 549.00', gold: { name: 'Netflix', amount: '549.00', date: 'October 1, 2025' } },
];

// ---- network hard-block + accounting -------------------------------------
let netAttempts = 0;
let guardInstalled = false;
const isLocalUrl = (u) => /^(file:|blob:|data:|about:|https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$))/i.test(u || '');
function installFetchGuard() {
  if (guardInstalled || typeof window === 'undefined' || !window.fetch) return;
  guardInstalled = true;
  const real = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (!isLocalUrl(url)) { netAttempts++; return Promise.reject(new Error('NETWORK BLOCKED: ' + url)); }
    return real(input, init);
  };
}
function remoteResources() {
  try {
    return performance.getEntriesByType('resource')
      .map(e => e.name)
      .filter(n => /^https?:/i.test(n) && !/^https?:\/\/(localhost|127\.0\.0\.1)/i.test(n)).length;
  } catch { return -1; }
}

export function configureOffline() {
  installFetchGuard();
  env.allowRemoteModels = false;
  env.allowLocalModels = true;
  env.useBrowserCache = false;
  env.localModelPath = new URL('models/', document.baseURI).href;
  env.backends.onnx.wasm.numThreads = 1;   // file:// has no SharedArrayBuffer
  env.backends.onnx.wasm.proxy = false;
  env.backends.onnx.wasm.simd = true;
  env.backends.onnx.wasm.wasmPaths = new URL('ort/', document.baseURI).href;
}

// ---- field normalisation (identical to the Node spike) -------------------
const norm = (x) => String(x ?? '').toLowerCase().replace(/[,\u20b1\u00a2\u00a3\s]|php/g, '').replace(/[^a-z0-9./-]/g, '');
const num = (x) => { const m = String(x ?? '').match(/[\d,]+\.?\d*/); return m ? m[0].replace(/,/g, '') : ''; };
const reAmount = (t) => { const m = t.match(/(?:php|\u20b1|p\s?)\s*([\d,]+\.\d{2})/i) || t.match(/([\d,]+\.\d{2})/); return m ? m[1].replace(/,/g, '') : ''; };
const reDate = (t) => { const m = t.match(/\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}/) || t.match(/[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}/); return m ? m[0] : ''; };
function parseJson(s) { const m = s.match(/\{[\s\S]*?\}/); if (!m) return null; try { return JSON.parse(m[0]); } catch { return null; } }

// ---- sha256 (WebCrypto, with pure-JS fallback for non-secure contexts) ----
function rrot(x, n) { return (x >>> n) | (x << (32 - n)); }
function sha256js(str) {
  const K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  let H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const bytes = [];
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    if (c < 128) bytes.push(c);
    else if (c < 2048) bytes.push(192 | (c >> 6), 128 | (c & 63));
    else bytes.push(224 | (c >> 12), 128 | ((c >> 6) & 63), 128 | (c & 63));
  }
  const l = bytes.length * 8;
  bytes.push(0x80); while (bytes.length % 64 !== 56) bytes.push(0);
  for (let i = 7; i >= 0; i--) bytes.push((l / Math.pow(2, i * 8)) & 0xff);
  const w = new Array(64);
  for (let i = 0; i < bytes.length; i += 64) {
    for (let j = 0; j < 16; j++) w[j] = (bytes[i+j*4]<<24) | (bytes[i+j*4+1]<<16) | (bytes[i+j*4+2]<<8) | (bytes[i+j*4+3]);
    for (let j = 16; j < 64; j++) { const s0 = rrot(w[j-15],7)^rrot(w[j-15],18)^(w[j-15]>>>3); const s1 = rrot(w[j-2],17)^rrot(w[j-2],19)^(w[j-2]>>>10); w[j] = (w[j-16]+s0+w[j-7]+s1)|0; }
    let [a,b,c,d,e,f,g,h] = H;
    for (let j = 0; j < 64; j++) {
      const S1 = rrot(e,6)^rrot(e,11)^rrot(e,25); const ch = (e&f)^(~e&g); const t1 = (h+S1+ch+K[j]+w[j])|0;
      const S0 = rrot(a,2)^rrot(a,13)^rrot(a,22); const maj = (a&b)^(a&c)^(b&c); const t2 = (S0+maj)|0;
      h=g; g=f; f=e; e=(d+t1)|0; d=c; c=b; b=a; a=(t1+t2)|0;
    }
    H = [(H[0]+a)|0,(H[1]+b)|0,(H[2]+c)|0,(H[3]+d)|0,(H[4]+e)|0,(H[5]+f)|0,(H[6]+g)|0,(H[7]+h)|0];
  }
  return H.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
}
async function sha256Hex(s) {
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    try { const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)); return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join(''); } catch {}
  }
  return sha256js(s);
}

// ---- main gate check ------------------------------------------------------
export async function runGateCheck(opts = {}) {
  const limit = Number.isFinite(opts.limit) ? opts.limit : SAMPLES.length;
  configureOffline();
  const tLoad = performance.now();
  const gen = await pipeline('text-generation', MODEL_ID, { dtype: DTYPE });
  const loadS = (performance.now() - tLoad) / 1000;

  const samples = SAMPLES.slice(0, limit);
  const hit = { name: 0, amount: 0, date: 0 }, hyb = { name: 0, amount: 0, date: 0 };
  const times = [], receipts = [];
  let prev = 'genesis';

  for (let idx = 0; idx < samples.length; idx++) {
    const s = samples[idx];
    const tt = performance.now();
    const out = await gen([
      { role: 'system', content: SYS },
      { role: 'user', content: EX1U }, { role: 'assistant', content: EX1A },
      { role: 'user', content: s.text },
    ], { max_new_tokens: 64, do_sample: false });
    times.push((performance.now() - tt) / 1000);
    const raw = String(out[0].generated_text.at(-1)?.content ?? '').trim();
    const j = parseJson(raw) || {};
    const g = s.gold;
    const nk = norm(g.name).split(' ')[0];
    const okName = norm(j.name).includes(nk) && nk.length > 2;
    const okAmt = num(j.amount) === num(g.amount);
    const okDate = norm(j.date) === norm(g.date) || norm(j.date).includes(norm(g.date).slice(0, 6));
    hit.name += okName ? 1 : 0; hit.amount += okAmt ? 1 : 0; hit.date += okDate ? 1 : 0;
    const hName = okName;
    const hAmt = num(reAmount(s.text) || j.amount) === num(g.amount);
    const hDate = norm(reDate(s.text) || j.date) === norm(g.date) || norm(reDate(s.text) || j.date).includes(norm(g.date).slice(0, 6));
    hyb.name += hName ? 1 : 0; hyb.amount += hAmt ? 1 : 0; hyb.date += hDate ? 1 : 0;

    const fields = { name: j.name || '', amount: reAmount(s.text) || j.amount || '', date: reDate(s.text) || j.date || '' };
    const body = JSON.stringify({ ts: new Date().toISOString(), input_hash: await sha256Hex(s.text), fields, prev });
    const receipt = Object.assign(JSON.parse(body), { receipt_hash: await sha256Hex(body) });
    receipts.push(receipt); prev = receipt.receipt_hash;

    if (typeof opts.onProgress === 'function') opts.onProgress({ idx: idx + 1, total: samples.length });
  }

  let chainValid = true;
  for (let i = 1; i < receipts.length; i++) if (receipts[i].prev !== receipts[i - 1].receipt_hash) chainValid = false;
  const n = samples.length || 1;
  const avg = times.reduce((a, b) => a + b, 0) / n;
  return {
    backend: 'onnxruntime-web (WASM)', model: MODEL_ID, dtype: DTYPE,
    load_s: +loadS.toFixed(2),
    items: samples.length,
    avg_s: +avg.toFixed(2),
    max_s: +Math.max(...times).toFixed(2),
    raw: { name: hit.name + '/' + n, amount: hit.amount + '/' + n, date: hit.date + '/' + n, pct: +(((hit.name + hit.amount + hit.date) / (3 * n)) * 100).toFixed(1) },
    hybrid: { name: hyb.name + '/' + n, amount: hyb.amount + '/' + n, date: hyb.date + '/' + n, pct: +(((hyb.name + hyb.amount + hyb.date) / (3 * n)) * 100).toFixed(1) },
    net_attempts: netAttempts,
    remote_resources: remoteResources(),
    receipts: receipts.length,
    chain_valid: chainValid,
  };
}

export function getNetAttempts() { return netAttempts; }
