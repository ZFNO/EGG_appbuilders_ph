package com.egg.appbuildersph

import android.annotation.SuppressLint
import android.os.Bundle
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewAssetLoader
import java.util.HashMap

/**
 * WebView host for the offline on-device receipt pipeline.
 *
 * The web bundle (webcode/mobile/dist, produced by copy_to_apk.bat into src/main/assets/)
 * runs @huggingface/transformers + onnxruntime-web (WASM) with a SELF-HOSTED model:
 *   assets/models/onnx-community/Qwen2.5-0.5B-Instruct/...   (weights + tokenizer)
 *   assets/ort/ort-wasm-simd-threaded.asyncify.{mjs,wasm}    (ORT WASM runtime)
 *
 * Assets are served through WebViewAssetLoader on https://appassets.androidplatform.net/
 * (a real origin) so ES-module <script> and dynamic import() of the .mjs work, and we can
 * force correct MIME types (.mjs -> text/javascript, .wasm -> application/wasm). No network.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var assetLoader: WebViewAssetLoader

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(true)

        web = WebView(this)
        setContentView(web)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
        }

        assetLoader = WebViewAssetLoader.Builder()
            .setDomain("appassets.androidplatform.net")
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        web.webViewClient = object : WebViewClient() {
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
        }

        web.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.d("EGGWEB", "${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                return true
            }
        }

        web.loadUrl("https://appassets.androidplatform.net/assets/index.html")

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
    }
}
