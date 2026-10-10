package com.egg.chattest

import android.annotation.SuppressLint
import android.content.res.AssetManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.HashMap
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var container: ViewGroup
    private var web: WebView? = null
    private lateinit var assetLoader: WebViewAssetLoader
    private var rendererCrashes = 0

    private val appUrl = "https://appassets.androidplatform.net/assets/index.html"
    private val appOrigin = "https://appassets.androidplatform.net"

    // JS <-> native bridge
    private val io = Executors.newSingleThreadExecutor()
    @Volatile private var replyProxy: JavaScriptReplyProxy? = null
    @Volatile private var engine: LlmEngine? = null
    @Volatile private var prepStarted = false

    private val modelAsset = "models/onnx-community/Qwen2.5-0.5B-Instruct/onnx/model_q4.onnx"
    private val modelFile: File get() = File(filesDir, "model_q4.onnx")

    // Qwen2.5 special tokens: <|endoftext|>, <|im_end|>
    private val eosIds = intArrayOf(151643, 151645)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(true)

        container = android.widget.FrameLayout(this)
        setContentView(container)

        assetLoader = WebViewAssetLoader.Builder()
            .setDomain("appassets.androidplatform.net")
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        buildWebView()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val w = web
                if (w != null && w.canGoBack()) w.goBack() else finish()
            }
        })
    }

    override fun onDestroy() {
        io.execute { engine?.close() }
        io.shutdown()
        super.onDestroy()
    }

    private fun buildWebView() {
        val w = WebView(this)
        w.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
        }

        w.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val resp = assetLoader.shouldInterceptRequest(request.url) ?: return null
                val name = request.url.lastPathSegment ?: ""
                val mime = when {
                    name.endsWith(".mjs") || name.endsWith(".js") -> "text/javascript"
                    name.endsWith(".wasm") -> "application/wasm"
                    name.endsWith(".json") -> "application/json"
                    name.endsWith(".onnx") -> "application/octet-stream"
                    else -> resp.mimeType
                }
                if (mime != null) resp.mimeType = mime
                val headers = HashMap<String, String>()
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                headers["Cross-Origin-Embedder-Policy"] = "require-corp"
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                resp.responseHeaders = headers
                return resp
            }

            // API 26+: a renderer crash must NOT take down the host app.
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                val crashed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) detail.didCrash() else true
                Log.e("CHATTEST", "Renderer gone: didCrash=$crashed -> recovering")
                if (crashed) rendererCrashes++

                (view.parent as? ViewGroup)?.removeView(view)
                view.destroy()
                web = null

                if (rendererCrashes >= 2) {
                    showFatal()
                } else {
                    buildWebView()
                }
                return true
            }
        }

        w.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.d("CHATTEST", "${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                return true
            }
        }

        container.addView(w, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        web = w
        installBridge(w)
        w.loadUrl(appUrl)
    }

    // ------------------------------------------------------------------ bridge

    private fun installBridge(w: WebView) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            Log.e("CHATTEST", "WebMessageListener unsupported on this WebView build")
            return
        }
        WebViewCompat.addWebMessageListener(
            w, "nativeBridge", setOf(appOrigin),
            object : WebViewCompat.WebMessageListener {
                override fun onPostMessage(
                    view: WebView,
                    message: WebMessageCompat,
                    sourceOrigin: Uri,
                    isMainFrame: Boolean,
                    proxy: JavaScriptReplyProxy
                ) {
                    replyProxy = proxy
                    val txt = message.data ?: return
                    try {
                        handle(JSONObject(txt))
                    } catch (e: Exception) {
                        Log.e("CHATTEST", "bad bridge message: $txt", e)
                    }
                }
            }
        )
    }

    private fun send(json: String) {
        replyProxy?.postMessage(json)
    }

    private fun handle(o: JSONObject) {
        when (o.optString("type")) {
            "init" -> ensureEngine()
            "generate" -> doGenerate(o)
            "cancel" -> engine?.cancel()
        }
    }

    // ------------------------------------------------------------------ model

    private fun assetLength(am: AssetManager, path: String): Long =
        try { am.openFd(path).use { it.length } } catch (_: Throwable) { -1L }

    private fun ensureEngine() {
        if (prepStarted) return
        prepStarted = true
        io.execute {
            try {
                val f = modelFile
                val am = assets
                val want = assetLength(am, modelAsset)
                val needCopy = !f.exists() || (want > 0 && f.length() != want)
                if (needCopy) {
                    send(JSONObject().put("type", "status").put("text", "copying model").toString())
                    copyAsset(am, modelAsset, f)
                }
                send(JSONObject().put("type", "status").put("text", "loading engine").toString())
                engine = LlmEngine(f)
                send(JSONObject().put("type", "ready").toString())
            } catch (t: Throwable) {
                Log.e("CHATTEST", "engine prep failed", t)
                send(JSONObject().put("type", "error")
                    .put("message", t.message ?: t.toString()).toString())
            }
        }
    }

    private fun copyAsset(am: AssetManager, path: String, dst: File) {
        val tmp = File(dst.parentFile, dst.name + ".part")
        am.open(path).use { input ->
            FileOutputStream(tmp).use { out ->
                val buf = ByteArray(1 shl 20)
                var done = 0L
                while (true) {
                    val n = input.read(buf)
                    if (n <= 0) break
                    out.write(buf, 0, n)
                    done += n
                    if (done % (8L shl 20) < buf.size) {
                        send(JSONObject().put("type", "progress").put("done", done).toString())
                    }
                }
                out.flush()
            }
        }
        if (dst.exists()) dst.delete()
        tmp.renameTo(dst)
    }

    // ------------------------------------------------------------------ generate

    private fun doGenerate(o: JSONObject) {
        val eng = engine
        if (eng == null) {
            send(JSONObject().put("type", "error").put("message", "engine not ready").toString())
            return
        }
        val ids = o.getJSONArray("ids").toIntArray()
        val maxNew = o.optInt("max_new", 256)
        val temp = o.optDouble("temperature", 0.7).toFloat()
        val topK = o.optInt("top_k", 20)
        val topP = o.optDouble("top_p", 0.8).toFloat()
        val rep = o.optDouble("repetition_penalty", 1.1).toFloat()

        io.execute {
            eng.generate(ids, maxNew, temp, topK, topP, rep, eosIds, object : LlmEngine.Sink {
                override fun onToken(id: Int) {
                    send(JSONObject().put("type", "token").put("id", id).toString())
                }
                override fun onDone() {
                    send(JSONObject().put("type", "done").toString())
                }
                override fun onError(message: String) {
                    send(JSONObject().put("type", "error").put("message", message).toString())
                }
            })
        }
    }

    private fun JSONArray.toIntArray(): IntArray {
        val a = IntArray(length())
        for (i in 0 until length()) a[i] = getInt(i)
        return a
    }

    private fun showFatal() {
        val w = WebView(this)
        w.settings.javaScriptEnabled = false
        val msg = "<html><body style='font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:24px'>" +
            "<h3>UI renderer kept crashing</h3>" +
            "<p>Inference now runs natively, but the WebView renderer failed repeatedly. " +
            "Check logcat tag CHATTEST.</p></body></html>"
        container.addView(w, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        web = w
        w.loadDataWithBaseURL(null, msg, "text/html", "utf-8", null)
    }
}
