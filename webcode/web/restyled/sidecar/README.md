# Invisible Secretary - local model sidecar

A tiny **localhost HTTP service** that runs the on-device Qwen model *outside*
the browser. The restyled dashboard calls it over `http` instead of loading
onnxruntime inside the page (no wasm, no 750 MB browser download).

Everything the sidecar needs lives **under this project** - nothing above the
project root is ever read:

```
restyled/
  sidecar/            <- this service (pure stdlib + onnxruntime/transformers)
    server.py
    qwen_onnx.py      <- self-contained port of invisible_secretary/local_qwen.py
    run_sidecar.bat
    requirements.txt
  models/             <- vendored, self-hosted model bundle
    Qwen2.5-0.5B-Instruct/
      config.json  tokenizer.json  tokenizer_config.json
      onnx/model_q4.onnx
```

## Run

```
sidecar\run_sidecar.bat          :: installs deps on first run, then serves :8765
```

Or manually:

```
python sidecar\server.py --port 8765
```

## Endpoints

| method | path        | body / result |
|--------|-------------|---------------|
| GET    | `/health`   | `{"ready":bool,"model":name,"model_dir":path,...}` |
| POST   | `/classify` | `{"text":"..."}` -> `{"status":"ok","intent":...,"parameters":{...}}` |

CORS is open (`*`) so the page served from `localhost:8080` can call it.

## Wire-up

The page (`sidecar_client.js`, imported by `api.js`) installs
`globalThis.__IS_ONNX_BACKEND__`, probes `/health` at boot, and forwards
`classify()` to `/classify`. If the sidecar is down the system falls back to the
deterministic rules automatically - classification is an enhancement, never a
requirement, and there is no cloud fallback.

Override the URL when needed:

```html
<script>globalThis.IS_SIDECAR_URL = "http://127.0.0.1:9000";</script>
```
