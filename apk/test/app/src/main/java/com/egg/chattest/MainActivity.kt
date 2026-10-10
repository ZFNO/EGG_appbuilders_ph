package com.egg.chattest

import android.annotation.SuppressLint
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
import androidx.webkit.WebViewAssetLoader
import java.util.HashMap

class MainActivity : AppCompatActivity() {

    private lateinit var container: ViewGroup
    private var web: WebView? = null
    private lateinit var assetLoader: WebViewAssetLoader
    private var rendererCrashes = 0

    private val appUrl = "https://appassets.androidplatform.net/assets/index.html"

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
            // Without this, Chromium aborts the whole process:
            //   crashpad_client_linux.cc(798): Render process's crash wasn't
            //   handled by all associated webviews, triggering application crash.
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                val crashed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) detail.didCrash() else true
                Log.e("CHATTEST", "Renderer gone: didCrash=$crashed -> recovering")
                if (crashed) rendererCrashes++

                // Tear down the dead WebView and rebuild a fresh one.
                (view.parent as? ViewGroup)?.removeView(view)
                view.destroy()
                web = null

                if (rendererCrashes >= 2) {
                    // Deterministic crash on load: stop the loop and show a notice.
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
        w.loadUrl(appUrl)
    }

    private fun showFatal() {
        val w = WebView(this)
        w.settings.javaScriptEnabled = false
        val msg = "<html><body style='font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:24px'>" +
            "<h3>On-device model could not start</h3>" +
            "<p>The WebView renderer crashed while loading the model " +
            "(repeatedly). This build renders the model in the page's WASM " +
            "sandbox, which this WebView build cannot complete.</p></body></html>"
        container.addView(w, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        web = w
        w.loadDataWithBaseURL(null, msg, "text/html", "utf-8", null)
    }
}
