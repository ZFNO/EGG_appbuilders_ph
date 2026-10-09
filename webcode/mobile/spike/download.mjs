// SPIKE step A: acquire self-hosted model weights into ./models (ONLINE, setup only).
import { pipeline, env } from '@huggingface/transformers';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const dir = path.dirname(fileURLToPath(import.meta.url));
env.cacheDir = path.join(dir, 'models');
env.allowRemoteModels = true;
env.allowLocalModels = true;

const MODEL = process.env.SPIKE_MODEL || 'onnx-community/Qwen2.5-0.5B-Instruct';
const DTYPE = process.env.SPIKE_DTYPE || 'q4';

console.log('[dl] cacheDir =', env.cacheDir);
console.log('[dl] model =', MODEL, 'dtype =', DTYPE);
const t0 = Date.now();
const gen = await pipeline('text-generation', MODEL, { dtype: DTYPE });
console.log('[dl] ready in', ((Date.now() - t0) / 1000).toFixed(1), 's');
const out = await gen('Reply with only the word OK.', { max_new_tokens: 8 });
console.log('[dl] smoke =', JSON.stringify(out[0].generated_text).slice(0, 200));
