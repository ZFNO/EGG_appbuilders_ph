// EGG Chat Test - on-device chatbot (isolated test APK).
// Runtime: @huggingface/transformers -> onnxruntime-web (WASM). SELF-HOSTED, NO CDN.
// Model: onnx-community/Qwen2.5-0.5B-Instruct (q4) under ./models/ . Zero network.
import { pipeline, env, TextStreamer } from '@huggingface/transformers';

const BASE = new URL('.', location.href).href; // app root inside the APK WebView

// ---- hard offline lock (zero network) --------------------------------------
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = BASE + 'models/';
env.useBrowserCache = false;
// Force the smaller NON-asyncify ORT wasm pair. The default entry resolves
// to ort-wasm-simd-threaded.asyncify.wasm (26.8 MB); compiling that inside
// the 32-bit Huawei WebView (Chromium 114) aborts the renderer (V8 CHECK in
// ThreadPoolForegroundWorker -> SIGTRAP). The plain threaded build is ~11 MB.
env.backends.onnx.wasm.wasmPaths = {
  mjs:  BASE + 'ort/ort-wasm-simd-threaded.mjs',
  wasm: BASE + 'ort/ort-wasm-simd-threaded.wasm',
};
env.backends.onnx.wasm.numThreads = 1;              // single-thread: no COOP/COEP needed
env.backends.onnx.wasm.proxy = false;

const _fetch = globalThis.fetch;
globalThis.fetch = function (u) {
  const url = String((u && u.url) || u);
  if (/^https?:/i.test(url) && url.indexOf(location.origin) !== 0) {
    throw new Error('OFFLINE_LOCK: ' + url);
  }
  return _fetch.apply(this, arguments);
};

const MODEL = 'onnx-community/Qwen2.5-0.5B-Instruct';
const SYS = 'You are a helpful, friendly assistant running fully on the user device. Keep answers short and clear.';
const MAX_NEW = 256;

// ---- UI --------------------------------------------------------------------
const list = document.getElementById('list');
const input = document.getElementById('in');
const sendBtn = document.getElementById('send');
const stateEl = document.getElementById('state');
const dot = document.getElementById('dot');

const history = [{ role: 'system', content: SYS }];
let generator = null;

function setState(txt, cls) {
  stateEl.textContent = txt;
  dot.className = 'dot ' + (cls || '');
}
function scroll() { list.scrollTop = list.scrollHeight; }
function addMsg(cls, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text || '';
  list.appendChild(d);
  scroll();
  return d;
}

// ---- boot ------------------------------------------------------------------
async function boot() {
  setState('loading model...', 'load');
  const t0 = performance.now();
  try {
    generator = await pipeline('text-generation', MODEL, {
      dtype: 'q4',
      progress_callback: (p) => {
        if (p && p.status === 'progress' && p.file) {
          setState('loading ' + p.file + ' ' + Math.round(p.progress || 0) + '%', 'load');
        }
      },
    });
    const dt = ((performance.now() - t0) / 1000).toFixed(1);
    setState('ready (' + dt + 's)', 'ready');
    sendBtn.disabled = false;
    addMsg('sys', 'Model loaded on-device via WASM in ' + dt + 's. Everything is local - no network.');
  } catch (e) {
    setState('error', 'err');
    addMsg('sys', 'Failed to load model: ' + ((e && e.message) || e));
    console.error(e);
  }
}

// ---- streaming reply -------------------------------------------------------
async function reply(userText) {
  history.push({ role: 'user', content: userText });
  const el = addMsg('bot typing', '');
  let acc = '';
  const streamer = new TextStreamer(generator.tokenizer, {
    skip_prompt: true,
    skip_special_tokens: true,
    callback_function: (t) => { acc += t; el.textContent = acc; scroll(); },
  });
  try {
    const out = await generator(history, {
      max_new_tokens: MAX_NEW,
      do_sample: true,
      temperature: 0.7,
      top_p: 0.8,
      top_k: 20,
      repetition_penalty: 1.1,
      streamer,
    });
    let text = acc;
    if (!text.trim()) {
      const last = out && out[0] && out[0].generated_text;
      text = Array.isArray(last)
        ? String((last.at(-1) || {}).content || '')
        : String(last || '');
    }
    text = text.trim();
    el.textContent = text || '(no output)';
    history.push({ role: 'assistant', content: text });
  } catch (e) {
    el.textContent = 'Error: ' + ((e && e.message) || e);
    console.error(e);
  } finally {
    el.classList.remove('typing');
  }
}

async function onSend() {
  const text = input.value.trim();
  if (!text || !generator) return;
  input.value = '';
  input.style.height = 'auto';
  addMsg('user', text);
  sendBtn.disabled = true;
  try { await reply(text); } finally { sendBtn.disabled = false; }
}

sendBtn.addEventListener('click', onSend);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

boot();
