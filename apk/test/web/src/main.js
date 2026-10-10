// EGG Chat Test - on-device chatbot (isolated test APK).
// UI + tokenizer only. Inference runs NATIVELY (ONNX Runtime, Kotlin) and is bridged
// via WebMessagePort ("nativeBridge"). The WebView no longer loads the model, so the
// 483 MB weights never touch WASM linear memory (which killed the renderer before).
// Tokenizer + chat template + detokenize stay here (tiny); the heavy matmuls are native.
import { AutoTokenizer, env } from '@huggingface/transformers';

const BASE = new URL('.', location.href).href; // app root inside the APK WebView

// ---- hard offline lock (zero network) --------------------------------------
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = BASE + 'models/';
env.useBrowserCache = false;

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
let tokenizer = null;
let gen = null; // active generation callbacks

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

// ---- native bridge ---------------------------------------------------------
const bridge = window.nativeBridge;
function toNative(obj) { bridge.postMessage(JSON.stringify(obj)); }

function onNative(m) {
  switch (m.type) {
    case 'status':
      setState(m.text || 'working...', 'load'); break;
    case 'progress':
      setState('copying model ' + Math.round((m.done / 507000000) * 100) + '%', 'load'); break;
    case 'ready':
      setState('ready', 'ready');
      sendBtn.disabled = false;
      addMsg('sys', 'Native engine ready. On-device, no network.');
      break;
    case 'token':
      if (gen) gen.onToken(m.id); break;
    case 'done':
      if (gen) gen.onDone(); break;
    case 'error':
      if (gen) gen.onError(m.message);
      else { setState('error', 'err'); addMsg('sys', 'Error: ' + m.message); }
      break;
  }
}

if (bridge) {
  bridge.onmessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    onNative(m);
  };
} else {
  addMsg('sys', 'Native bridge unavailable in this WebView.');
  setState('error', 'err');
}

// ---- boot ------------------------------------------------------------------
async function boot() {
  setState('loading tokenizer...', 'load');
  try {
    tokenizer = await AutoTokenizer.from_pretrained(MODEL);
  } catch (e) {
    setState('error', 'err');
    addMsg('sys', 'Tokenizer failed: ' + ((e && e.message) || e));
    return;
  }
  setState('starting engine...', 'load');
  toNative({ type: 'init' });
}

// ---- streaming reply -------------------------------------------------------
async function reply(userText) {
  history.push({ role: 'user', content: userText });
  const el = addMsg('bot typing', '');

  let ids;
  try {
    const text = await tokenizer.apply_chat_template(history, {
      tokenize: false,
      add_generation_prompt: true,
    });
    const enc = await tokenizer(text, { add_special_tokens: false });
    ids = Array.from(enc.input_ids.data).map(Number);
  } catch (e) {
    el.classList.remove('typing');
    el.textContent = 'Prompt error: ' + ((e && e.message) || e);
    return;
  }

  let accIds = [];
  let shown = '';

  gen = {
    onToken: (id) => {
      accIds.push(id);
      const t = tokenizer.decode(accIds, { skip_special_tokens: true });
      if (t.length >= shown.length) { shown = t; el.textContent = t; scroll(); }
    },
    onDone: () => {
      el.classList.remove('typing');
      if (!shown.trim()) el.textContent = '(no output)';
      history.push({ role: 'assistant', content: shown });
      gen = null;
    },
    onError: (msg) => {
      el.classList.remove('typing');
      el.textContent = 'Error: ' + msg;
      gen = null;
    },
  };

  toNative({
    type: 'generate',
    ids,
    max_new: MAX_NEW,
    temperature: 0.7,
    top_k: 20,
    top_p: 0.8,
    repetition_penalty: 1.1,
  });
}

// ---- input wiring ----------------------------------------------------------
function submit() {
  const v = input.value.trim();
  if (!v || !tokenizer || gen) return;
  input.value = '';
  input.style.height = 'auto';
  addMsg('user', v);
  reply(v);
}

sendBtn.addEventListener('click', submit);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

boot();
