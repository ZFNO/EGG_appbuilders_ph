// SPIKE step C (v2): hash/append-log receipts. prev advances per record -> valid chain.
import { pipeline, env } from '@huggingface/transformers';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const dir = path.dirname(fileURLToPath(import.meta.url));
env.cacheDir = path.join(dir, 'models');
env.allowRemoteModels = false; env.allowLocalModels = true; env.localModelPath = path.join(dir, 'models');
let netAttempts = 0; globalThis.fetch = async (u) => { netAttempts++; throw new Error('NET BLOCKED ' + u); };

const MODEL = 'onnx-community/Qwen2.5-0.5B-Instruct';
const SYS = 'You are a receipt field extractor. From the user text, reply with ONLY one compact JSON object, no prose, no code fences: {"name":string,"amount":string,"date":string}. amount = digits with a dot, no commas or currency symbols. date = the date exactly as written. Use "" if a field is missing.';
const EX1A = '{"name":"SM Supermarket Cebu","amount":"1248.75","date":"12/03/25"}';
const SAMPLES = [
  'SM SUPERMARKET CEBU\n12/03/25 14:22\nTOTAL PHP 1,248.75',
  'Jollibee - Ayala\nNov 18, 2025\nAmount Due: 356.00 pesos',
  'Coffee at Starbucks BGC\n10/09/2025\nTotal: P 215.00',
  'PayMaya load\n2025-11-02\nSent PHP 500.00 to 0917xxxxxxx',
];
const reAmount = (t) => { const m = t.match(/(?:php|\u20b1|p\s?)\s*([\d,]+\.\d{2})/i) || t.match(/([\d,]+\.\d{2})/); return m ? m[1].replace(/,/g, '') : ''; };
const reDate = (t) => { const m = t.match(/\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}/) || t.match(/[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}/); return m ? m[0] : ''; };
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');
function parseJson(s) { const m = s.match(/\{[\s\S]*?\}/); if (!m) return null; try { return JSON.parse(m[0]); } catch { return null; } }

const gen = await pipeline('text-generation', MODEL, { dtype: 'q4' });
const LOG = path.join(dir, 'receipts.log');
if (fs.existsSync(LOG)) fs.unlinkSync(LOG);
let prev = 'genesis';
for (const text of SAMPLES) {
  const out = await gen([{ role: 'system', content: SYS }, { role: 'user', content: 'SM SUPERMARKET CEBU\n12/03/25 14:22\nTOTAL PHP 1,248.75' }, { role: 'assistant', content: EX1A }, { role: 'user', content: text }], { max_new_tokens: 64, do_sample: false });
  const j = parseJson((out[0].generated_text.at(-1)?.content ?? '').trim()) || {};
  const fields = { name: j.name || '', amount: reAmount(text) || j.amount || '', date: reDate(text) || j.date || '' };
  const body = JSON.stringify({ ts: new Date().toISOString(), input_hash: sha(text), fields, prev });
  const receipt = { ...JSON.parse(body), receipt_hash: sha(body) };
  fs.appendFileSync(LOG, JSON.stringify(receipt) + '\n');
  prev = receipt.receipt_hash;
}
const all = fs.readFileSync(LOG, 'utf8').trim().split('\n').map(JSON.parse);
let ok = true;
for (let i = 1; i < all.length; i++) if (all[i].prev !== all[i - 1].receipt_hash) ok = false;
console.log('[receipts] total =', all.length, ' chain_valid =', ok, ' net_attempts =', netAttempts);
all.forEach((r) => console.log('  ', r.fields.name, '|', r.fields.amount, '|', r.fields.date, '|', r.receipt_hash.slice(0, 12)));
