package ma.sanad.app;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Sanad on the phone: the same interface as the desktop app (frontend/, built into assets/web) in a WebView.
 * Its calls to the backend are answered by this app's own engine (Api); the first-run page (assets/web/setup.html) asks for
 * the Cloudflare account ID and token and the AI provider's key, then downloads the law pack, before the interface opens.
 */
public class MainActivity extends Activity implements Api.Host {
    static final String ORIGIN = "https://sanad.local";

    Prefs prefs;
    volatile Pack pack;
    volatile Engine engine;
    File packDir;
    WebView web;
    Api api;
    final ExecutorService pool = Executors.newFixedThreadPool(3);
    volatile boolean downloading, cancelDownload;

    @Override public Engine engine() { return engine; }
    @Override public Pack pack() { return pack; }
    @Override public Prefs prefs() { return prefs; }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = new Prefs(this);
        packDir = new File(getFilesDir(), "pack");
        packDir.mkdirs();
        api = new Api(this);
        openPack();

        boolean dark = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        getWindow().setStatusBarColor(dark ? Color.parseColor("#0B0B0B") : Color.parseColor("#F4F3F0"));
        getWindow().setNavigationBarColor(dark ? Color.parseColor("#0B0B0B") : Color.parseColor("#F4F3F0"));
        if (!dark) getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);

        web = new WebView(this);
        web.setBackgroundColor(dark ? Color.parseColor("#0B0B0B") : Color.parseColor("#F4F3F0"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        web.addJavascriptInterface(new Bridge(), "SanadNative");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (!"sanad.local".equals(u.getHost())) return null;
                return asset(u.getPath());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if ("sanad.local".equals(u.getHost())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true; // links to official sources open in the browser
            }
        });
        setContentView(web);
        web.loadUrl(ORIGIN + (prefs.ready() && pack != null ? "/" : "/setup.html"));
    }

    boolean openPack() {
        if (!Pack.present(packDir)) return false;
        try {
            if (pack == null) pack = new Pack(packDir);
            engine = new Engine(prefs, pack);
            return true;
        } catch (Exception e) {
            pack = null;
            engine = null;
            return false;
        }
    }

    /** Files of the interface, from assets/web. Pages get bridge.js first, so their calls to the backend reach this app. */
    WebResourceResponse asset(String path) {
        if (path == null || path.equals("/") || path.isEmpty()) path = "/index.html";
        String file = path.substring(1);
        boolean page = file.endsWith(".html");
        try {
            InputStream in;
            try {
                in = getAssets().open("web/" + file);
            } catch (Exception notFound) {
                if (file.contains(".") && !file.startsWith("c/")) return new WebResourceResponse("text/plain", "utf-8", 404, "Not found", new HashMap<>(), new ByteArrayInputStream(new byte[0]));
                file = "index.html"; // an address of the app itself (/c/<session>): the interface handles it
                page = true;
                in = getAssets().open("web/index.html");
            }
            if (page) {
                String html = new String(readAll(in), StandardCharsets.UTF_8).replaceFirst("<head>", "<head><script src=\"/bridge.js\"></script>");
                in = new ByteArrayInputStream(html.getBytes(StandardCharsets.UTF_8));
            }
            Map<String, String> h = new HashMap<>();
            h.put("Cache-Control", page ? "no-cache" : "max-age=31536000");
            return new WebResourceResponse(mime(file), "utf-8", 200, "OK", h, in);
        } catch (Exception e) {
            return new WebResourceResponse("text/plain", "utf-8", 500, "Error", new HashMap<>(), new ByteArrayInputStream(new byte[0]));
        }
    }

    static byte[] readAll(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
        in.close();
        return out.toByteArray();
    }

    static String mime(String f) {
        if (f.endsWith(".html")) return "text/html";
        if (f.endsWith(".js")) return "application/javascript";
        if (f.endsWith(".css")) return "text/css";
        if (f.endsWith(".svg")) return "image/svg+xml";
        if (f.endsWith(".png")) return "image/png";
        if (f.endsWith(".jpg") || f.endsWith(".jpeg")) return "image/jpeg";
        if (f.endsWith(".woff2")) return "font/woff2";
        if (f.endsWith(".json")) return "application/json";
        if (f.endsWith(".pdf")) return "application/pdf";
        return "application/octet-stream";
    }

    void js(String code) { runOnUiThread(() -> web.evaluateJavascript(code, null)); }

    void reply(String id, int status, String body) {
        js("window.__sanadReply&&window.__sanadReply(" + JSONObject.quote(id) + "," + status + "," + JSONObject.quote(body) + ")");
    }

    void progress(JSONObject o) { js("window.__sanadProgress&&window.__sanadProgress(" + o + ")"); }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    // ------------------------------------------------------------------ what the pages can call
    final class Bridge {
        /** A call of the interface to the backend: answered on a worker thread, the reply goes back to window.__sanadReply. */
        @JavascriptInterface
        public void request(String id, String method, String path, String body) {
            pool.execute(() -> {
                Api.Reply r = api.handle(method == null ? "GET" : method.toUpperCase(), path == null ? "/" : path, body == null ? "" : body);
                reply(id, r.status, r.body);
            });
        }

        /** What the setup page shows: which keys are saved (never the secret values) and the installed law pack. */
        @JavascriptInterface
        public String state() {
            try {
                JSONObject k = new JSONObject()
                        .put("ai_key", !prefs.openaiKey().isEmpty()).put("ai_model", prefs.get("openai_model", "")).put("ai_base", prefs.get("openai_base", ""))
                        .put("cf_account", prefs.cfAccount()).put("cf_token", !prefs.cfToken().isEmpty())
                        .put("rewrite", prefs.flag("rewrite", true)).put("pack_url", prefs.get("pack_url", ""));
                JSONObject p = new JSONObject().put("present", pack != null).put("version", pack != null ? pack.meta.get("version") : JSONObject.NULL)
                        .put("downloading", downloading);
                return new JSONObject().put("keys", k).put("pack", p).put("ready", prefs.ready()).toString();
            } catch (Exception e) {
                return "{}";
            }
        }

        /** Saves the keys; an empty secret field keeps the key already saved. */
        @JavascriptInterface
        public void save(String json) {
            try {
                JSONObject o = new JSONObject(json);
                if (!o.optString("ai_key").trim().isEmpty()) prefs.put("openai_key", o.optString("ai_key"));
                if (!o.optString("cf_token").trim().isEmpty()) prefs.put("cf_token", o.optString("cf_token"));
                prefs.put("cf_account", o.optString("cf_account"));
                prefs.put("openai_model", o.optString("ai_model"));
                prefs.put("openai_base", o.optString("ai_base"));
                prefs.put("pack_url", o.optString("pack_url"));
                prefs.setFlag("rewrite", o.optBoolean("rewrite", true));
                if (pack != null) engine = new Engine(prefs, pack);
            } catch (Exception ignored) { }
        }

        /** Tries both services with the saved keys; the result goes to window.__sanadReply(id, 200, {cloudflare, ai}). */
        @JavascriptInterface
        public void test(String id) {
            pool.execute(() -> {
                JSONObject r = new JSONObject();
                Engine e = new Engine(prefs, null);
                try {
                    e.embed(java.util.Collections.singletonList("test"));
                    r.put("cloudflare", new JSONObject().put("ok", true));
                } catch (Exception ex) {
                    try { r.put("cloudflare", new JSONObject().put("ok", false).put("error", String.valueOf(ex.getMessage()))); } catch (Exception ignored) { }
                }
                try {
                    e.chat("Reply with the single word OK.", "OK?", 20);
                    r.put("ai", new JSONObject().put("ok", true));
                } catch (Exception ex) {
                    try { r.put("ai", new JSONObject().put("ok", false).put("error", String.valueOf(ex.getMessage()))); } catch (Exception ignored) { }
                }
                reply(id, 200, r.toString());
            });
        }

        @JavascriptInterface
        public void download() {
            if (downloading) return;
            downloading = true;
            cancelDownload = false;
            runOnUiThread(() -> getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
            pool.execute(MainActivity.this::downloadPack);
        }

        @JavascriptInterface
        public void cancel() { cancelDownload = true; }

        @JavascriptInterface
        public void openApp() { runOnUiThread(() -> { web.clearHistory(); web.loadUrl(ORIGIN + "/"); }); }

        @JavascriptInterface
        public void openSetup() { runOnUiThread(() -> web.loadUrl(ORIGIN + "/setup.html?from=app")); }
    }

    // ------------------------------------------------------------------ law pack download
    void downloadPack() {
        try {
            progress(new JSONObject().put("phase", "list"));
            JSONObject m = new JSONObject(Net.get(prefs.packUrl() + "manifest.json"));
            JSONObject files = m.getJSONObject("files");
            String[] keys = {"db", "vec"};
            long all = 0, before = 0;
            for (String k : keys) all += files.getJSONObject(k).getLong("size");
            for (String k : keys) {
                JSONObject f = files.getJSONObject(k);
                String name = f.getString("name");
                long size = f.getLong("size");
                final long base = before, total = all;
                File dest = new File(packDir, name + ".new");
                Net.download(prefs.packUrl() + name, dest, size, new Net.Progress() {
                    long last;
                    public void update(long done, long t) {
                        long now = System.currentTimeMillis();
                        if (now - last < 300) return;
                        last = now;
                        try { progress(new JSONObject().put("phase", "download").put("file", name).put("done", base + done).put("total", total)); } catch (Exception ignored) { }
                    }
                    public boolean cancelled() { return cancelDownload; }
                });
                progress(new JSONObject().put("phase", "check").put("file", name).put("done", base + size).put("total", all));
                String sha = Net.sha256(dest, null);
                if (!sha.equalsIgnoreCase(f.getString("sha256"))) {
                    dest.delete();
                    throw new Exception(name + " is damaged (SHA-256 does not match): download it again");
                }
                before += size;
            }
            if (pack != null) { pack.db.close(); pack = null; engine = null; }
            for (String k : keys) {
                String name = files.getJSONObject(k).getString("name");
                File fin = new File(packDir, name);
                fin.delete();
                if (!new File(packDir, name + ".new").renameTo(fin)) throw new Exception("could not install " + name);
            }
            java.nio.file.Files.write(new File(packDir, "manifest.json").toPath(), m.toString().getBytes(StandardCharsets.UTF_8));
            if (!openPack()) throw new Exception("the law pack was downloaded but could not be opened");
            progress(new JSONObject().put("phase", "done").put("version", pack.meta.get("version")));
        } catch (Exception e) {
            try {
                progress(new JSONObject().put("phase", cancelDownload ? "stopped" : "error").put("error", String.valueOf(e.getMessage())));
            } catch (Exception ignored) { }
        } finally {
            downloading = false;
            runOnUiThread(() -> getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
        }
    }
}
