// SPIKE step B (v2): OFFLINE local-model extraction  name/amount/date -> receipt.
// Fix: use the model's own chat template. Airplane-mode guard = runtime network HARD-block.
import { pipeline, env, AutoTokenizer } from '@huggingface/transformers';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const dir = path.dirname(fileURLToPath(import.meta.url));
env.cacheDir = path.join(dir, 'models');
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = path.join(dir, 'models');

let netAttempts = 0;
globalThis.fetch = async (u) => { netAttempts++; throw new Error('NETWORK BLOCKED: ' + u); };

const MODEL = process.env.SPIKE_MODEL || 'onnx-community/Qwen2.5-0.5B-Instruct';
const DTYPE = process.env.SPIKE_DTYPE || 'q4';
const DBG = process.env.SPIKE_DEBUG === '1';

const SAMPLES = [
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

const SYS = 'You are a receipt field extractor. From the user text, reply with ONLY one compact JSON object, no prose, no code fences: {"name":string,"amount":string,"date":string}. amount = digits with a dot, no commas or currency symbols. date = the date exactly as written. Use "" if a field is missing.';
const EX1U = 'SM SUPERMARKET CEBU\n12/03/25  14:22\nTOTAL PHP 1,248.75\nCARD ****4417\nSalamat!';
const EX1A = '{"name":"SM Supermarket Cebu","amount":"1248.75","date":"12/03/25"}';

const norm = (x) => String(x ?? '').toLowerCase().replace(/[,₱\s]|php/g, '').replace(/[^a-z0-9./-]/g, '');
const num = (x) => { const m = String(x ?? '').match(/[\d,]+\.?\d*/); return m ? m[0].replace(/,/g, '') : ''; };
const reAmount = (t) => { const m = t.match(/(?:php|₱|p\s?)\s*([\d,]+\.\d{2})/i) || t.match(/([\d,]+\.\d{2})/); return m ? m[1].replace(/,/g, '') : ''; };
const reDate = (t) => { const m = t.match(/\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}/) || t.match(/[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}/); return m ? m[0] : ''; };
function parseJson(s) { const m = s.match(/\{[\s\S]*?\}/); if (!m) return null; try { return JSON.parse(m[0]); } catch { return null; } }

const t0 = Date.now();
const gen = await pipeline('text-generation', MODEL, { dtype: DTYPE });
console.log('[spike] model loaded offline in', ((Date.now() - t0) / 1000).toFixed(1), 's');

let hit = { name: 0, amount: 0, date: 0 }, hyb = { name: 0, amount: 0, date: 0 };
let times = [];
for (const s of SAMPLES) {
  const messages = [
    { role: 'system', content: SYS },
    { role: 'user', content: EX1U }, { role: 'assistant', content: EX1A },
    { role: 'user', content: s.text },
  ];
  const tt = Date.now();
  const out = await gen(messages, { max_new_tokens: 64, do_sample: false });
  times.push((Date.now() - tt) / 1000);
  const raw = (out[0].generated_text.at(-1)?.content ?? '').trim();
  const j = parseJson(raw) || {};
  if (DBG) console.log('    raw:', JSON.stringify(raw.slice(0, 160)));
  const g = s.gold;
  const nk = norm(g.name).split(' ')[0];
  const okName = norm(j.name).includes(nk) && nk.length > 2;
  const okAmt = num(j.amount) === num(g.amount);
  const okDate = norm(j.date) === norm(g.date) || norm(j.date).includes(norm(g.date).slice(0, 6));
  hit.name += okName; hit.amount += okAmt; hit.date += okDate;
  const hName = okName;
  const hAmt = num(reAmount(s.text) || j.amount) === num(g.amount);
  const hDate = norm(reDate(s.text) || j.date) === norm(g.date) || norm(reDate(s.text) || j.date).includes(norm(g.date).slice(0, 6));
  hyb.name += hName; hyb.amount += hAmt; hyb.date += hDate;
  console.log(`  ${okName && okAmt && okDate ? 'OK  ' : 'MISS'} ${JSON.stringify({ n: j.name, a: j.amount, d: j.date })}`);
}
const n = SAMPLES.length;
console.log('[spike] net attempts during run =', netAttempts);
console.log('[spike] avg latency/item =', (times.reduce((a, b) => a + b, 0) / n).toFixed(2), 's   max =', Math.max(...times).toFixed(2), 's');
console.log('[spike] RAW  model : name', hit.name + '/' + n, 'amount', hit.amount + '/' + n, 'date', hit.date + '/' + n, '=> fields', ((hit.name + hit.amount + hit.date) / (3 * n) * 100).toFixed(1) + '%');
console.log('[spike] HYBRID(m+f): name', hyb.name + '/' + n, 'amount', hyb.amount + '/' + n, 'date', hyb.date + '/' + n, '=> fields', ((hyb.name + hyb.amount + hyb.date) / (3 * n) * 100).toFixed(1) + '%');
