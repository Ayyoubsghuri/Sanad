package ma.sanad.app;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.File;
import java.util.Locale;

public class MainActivity extends Activity {
    static final int BG = Color.parseColor("#14161A"), CARD = Color.parseColor("#1E2127"), TEXT = Color.parseColor("#E8E6E1"),
            MUTED = Color.parseColor("#9AA0A6"), ACCENT = Color.parseColor("#C8A55A"), ERR = Color.parseColor("#E57373");

    Prefs prefs;
    Pack pack;
    Engine engine;
    File packDir;
    volatile boolean busy, cancel;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = new Prefs(this);
        packDir = new File(getFilesDir(), "pack");
        packDir.mkdirs();
        route();
    }

    void route() {
        if (!prefs.ready()) showSettings();
        else if (!Pack.present(packDir)) showDownload();
        else if (openPack()) showChat();
        else showDownload();
    }

    boolean openPack() {
        if (pack != null) return true;
        try {
            pack = new Pack(packDir);
            engine = new Engine(prefs, pack);
            return true;
        } catch (Exception e) {
            pack = null;
            toastText = "The law pack could not be opened (" + e.getMessage() + "): download it again.";
            return false;
        }
    }

    String toastText;

    // ------------------------------------------------------------------ helpers
    TextView text(String s, float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        t.setLineSpacing(0, 1.25f);
        t.setTextIsSelectable(true);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    GradientDrawable round(int color, int radiusDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(radiusDp));
        return g;
    }

    int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    Button button(String s, boolean primary) {
        Button btn = new Button(this);
        btn.setText(s);
        btn.setAllCaps(false);
        btn.setTextColor(primary ? BG : TEXT);
        btn.setBackground(round(primary ? ACCENT : CARD, 10));
        return btn;
    }

    LinearLayout column(int padDp) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(padDp), dp(padDp), dp(padDp), dp(padDp));
        return l;
    }

    LinearLayout.LayoutParams fill(int topDp) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(topDp);
        return lp;
    }

    EditText field(String hint, String value, boolean secret) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(value);
        e.setTextColor(TEXT);
        e.setHintTextColor(MUTED);
        e.setSingleLine(true);
        e.setTextDirection(View.TEXT_DIRECTION_LTR);
        if (secret) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        e.setBackground(round(CARD, 8));
        e.setPadding(dp(12), dp(10), dp(12), dp(10));
        return e;
    }

    View root(View content) {
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        sv.setFillViewport(true);
        sv.addView(content);
        return sv;
    }

    // ------------------------------------------------------------------ settings
    void showSettings() {
        LinearLayout c = column(20);
        c.addView(text("سند · Sanad", 26, ACCENT, true));
        c.addView(text("Settings. Your keys stay on this phone, in this app's private storage.", 14, MUTED, false), fill(6));
        c.addView(text("OpenAI API key (answers)", 14, TEXT, true), fill(18));
        EditText ok = field("sk-...", prefs.openaiKey(), true);
        c.addView(ok, fill(6));
        c.addView(text("Model", 14, TEXT, true), fill(12));
        EditText om = field("gpt-4o-mini", prefs.get("openai_model", ""), false);
        c.addView(om, fill(6));
        c.addView(text("Cloudflare account ID (question → bge-m3 vector)", 14, TEXT, true), fill(18));
        EditText ca = field("32 characters", prefs.cfAccount(), false);
        c.addView(ca, fill(6));
        c.addView(text("Cloudflare Workers AI token", 14, TEXT, true), fill(12));
        EditText ct = field("token", prefs.cfToken(), true);
        c.addView(ct, fill(6));
        CheckBox rw = new CheckBox(this);
        rw.setText("Rewrite questions into formal Arabic before searching (better for Darija, French, English)");
        rw.setTextColor(TEXT);
        rw.setChecked(prefs.flag("rewrite", true));
        c.addView(rw, fill(14));
        c.addView(text("Advanced", 14, MUTED, true), fill(18));
        EditText ob = field("OpenAI-compatible base URL (default https://api.openai.com/v1)", prefs.get("openai_base", ""), false);
        c.addView(ob, fill(6));
        EditText pu = field("Law pack folder URL (default: your Hugging Face)", prefs.get("pack_url", ""), false);
        c.addView(pu, fill(6));
        TextView err = text("", 14, ERR, false);
        c.addView(err, fill(10));
        Button save = button("Save", true);
        c.addView(save, fill(14));
        save.setOnClickListener(v -> {
            prefs.put("openai_key", ok.getText().toString());
            prefs.put("openai_model", om.getText().toString());
            prefs.put("cf_account", ca.getText().toString());
            prefs.put("cf_token", ct.getText().toString());
            prefs.put("openai_base", ob.getText().toString());
            prefs.put("pack_url", pu.getText().toString());
            prefs.setFlag("rewrite", rw.isChecked());
            if (!prefs.ready()) { err.setText("Fill in the OpenAI key, the Cloudflare account ID and the Cloudflare token."); return; }
            engine = pack == null ? null : new Engine(prefs, pack);
            route();
        });
        if (Pack.present(packDir)) {
            Button pk = button("Law pack: check for an update / download again", false);
            c.addView(pk, fill(10));
            pk.setOnClickListener(v -> showDownload());
        }
        if (prefs.ready() && pack != null) {
            Button back = button("Back to questions", false);
            c.addView(back, fill(10));
            back.setOnClickListener(v -> showChat());
        }
        setContentView(root(c));
    }

    // ------------------------------------------------------------------ download
    void showDownload() {
        LinearLayout c = column(20);
        c.addView(text("سند · Sanad", 26, ACCENT, true));
        c.addView(text("The law pack (the laws in force, their keyword index and their vectors) is downloaded once and stays on the phone. "
                + "Use Wi-Fi: it is about 1–2 GB. If the connection drops, press Download again: it continues where it stopped.", 15, TEXT, false), fill(10));
        if (toastText != null) { c.addView(text(toastText, 14, ERR, false), fill(10)); toastText = null; }
        TextView status = text(Pack.present(packDir) ? "A pack is installed: " + (pack != null ? pack.meta.get("version") : "") : "No pack yet.", 14, MUTED, false);
        c.addView(status, fill(14));
        ProgressBar bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(1000);
        c.addView(bar, fill(10));
        Button go = button("Download", true);
        c.addView(go, fill(14));
        Button stop = button("Stop", false);
        c.addView(stop, fill(8));
        Button settings = button("Settings", false);
        c.addView(settings, fill(8));
        settings.setOnClickListener(v -> { if (!busy) showSettings(); });
        stop.setOnClickListener(v -> cancel = true);
        go.setOnClickListener(v -> {
            if (busy) return;
            busy = true;
            cancel = false;
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            new Thread(() -> download(status, bar)).start();
        });
        setContentView(root(c));
    }

    void download(TextView status, ProgressBar bar) {
        try {
            say(status, "Reading the list of files ...");
            JSONObject m = new JSONObject(Net.get(prefs.packUrl() + "manifest.json"));
            JSONObject files = m.getJSONObject("files");
            String[] keys = {"db", "vec"};
            for (String k : keys) {
                JSONObject f = files.getJSONObject(k);
                String name = f.getString("name");
                long size = f.getLong("size");
                File dest = new File(packDir, name + ".new");
                Net.download(prefs.packUrl() + name, dest, size, new Net.Progress() {
                    public void update(long done, long total) {
                        runOnUiThread(() -> {
                            bar.setProgress((int) (1000 * done / Math.max(1, total)));
                            status.setText(String.format(Locale.ROOT, "%s: %,d / %,d MB", name, done / 1_000_000, total / 1_000_000));
                        });
                    }
                    public boolean cancelled() { return cancel; }
                });
                say(status, "Checking " + name + " ...");
                String sha = Net.sha256(dest, null);
                if (!sha.equalsIgnoreCase(f.getString("sha256"))) {
                    dest.delete();
                    throw new Exception(name + " is damaged (SHA-256 does not match): press Download again");
                }
            }
            if (pack != null) { pack.db.close(); pack = null; engine = null; }
            for (String k : keys) {
                String name = files.getJSONObject(k).getString("name");
                File fin = new File(packDir, name);
                fin.delete();
                if (!new File(packDir, name + ".new").renameTo(fin)) throw new Exception("could not install " + name);
            }
            new File(packDir, "manifest.json").delete();
            java.nio.file.Files.write(new File(packDir, "manifest.json").toPath(), m.toString().getBytes("UTF-8"));
            runOnUiThread(() -> {
                busy = false;
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                route();
            });
        } catch (Exception e) {
            String msg = e.getMessage();
            runOnUiThread(() -> {
                busy = false;
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                status.setTextColor(ERR);
                status.setText(cancel ? "Stopped. Press Download to continue." : "Error: " + msg);
            });
        }
    }

    void say(TextView t, String s) { runOnUiThread(() -> t.setText(s)); }

    // ------------------------------------------------------------------ chat
    LinearLayout thread;
    ScrollView threadScroll;

    void showChat() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setBackgroundColor(BG);

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(16), dp(12), dp(8), dp(8));
        TextView title = text("سند · Sanad", 22, ACCENT, true);
        title.setTextIsSelectable(false);
        bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button st = button("Settings", false);
        bar.addView(st);
        st.setOnClickListener(v -> { if (!busy) showSettings(); });
        page.addView(bar);

        threadScroll = new ScrollView(this);
        thread = column(14);
        threadScroll.addView(thread);
        page.addView(threadScroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        if (thread.getChildCount() == 0) {
            String v = pack != null ? pack.meta.get("version") + " · " + pack.meta.get("passages") + " passages" : "";
            thread.addView(text("اسأل عن القانون المغربي بالدارجة أو العربية أو الفرنسية أو الإنجليزية.\nAsk about Moroccan law.\n\n" + v, 14, MUTED, false));
        }

        LinearLayout input = new LinearLayout(this);
        input.setPadding(dp(10), dp(8), dp(10), dp(12));
        input.setGravity(Gravity.BOTTOM);
        EditText q = new EditText(this);
        q.setHint("سؤالك… / Your question…");
        q.setTextColor(TEXT);
        q.setHintTextColor(MUTED);
        q.setMaxLines(5);
        q.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        q.setBackground(round(CARD, 12));
        q.setPadding(dp(12), dp(10), dp(12), dp(10));
        input.addView(q, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button send = button("→", true);
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(dp(56), dp(48));
        sp.leftMargin = dp(8);
        input.addView(send, sp);
        page.addView(input);
        send.setOnClickListener(v -> {
            String s = q.getText().toString().trim();
            if (s.isEmpty() || busy) return;
            q.setText("");
            ((InputMethodManager) getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(q.getWindowToken(), 0);
            ask(s);
        });
        setContentView(page);
    }

    void ask(String question) {
        busy = true;
        LinearLayout card = column(14);
        card.setBackground(round(CARD, 14));
        LinearLayout.LayoutParams lp = fill(12);
        thread.addView(card, lp);
        card.addView(text(question, 16, ACCENT, true));
        TextView status = text("…", 14, MUTED, false);
        card.addView(status, fill(8));
        scrollDown();
        new Thread(() -> {
            try {
                Engine.Answer a = engine.ask(question, what -> say(status,
                        "rewrite".equals(what) ? "Preparing the search…" : "search".equals(what) ? "Searching the law on the phone…" : "Writing the answer…"));
                runOnUiThread(() -> { render(card, status, a); busy = false; scrollDown(); });
            } catch (Exception e) {
                String msg = e.getMessage();
                runOnUiThread(() -> { status.setTextColor(ERR); status.setText("Error: " + msg); busy = false; });
            }
        }).start();
    }

    void render(LinearLayout card, TextView status, Engine.Answer a) {
        card.removeView(status);
        card.addView(text(a.text == null ? "" : a.text, 16, TEXT, false), fill(10));
        for (String n : a.notes) card.addView(text("⚠ " + n, 12, MUTED, false), fill(6));
        if (a.passages.isEmpty()) return;
        card.addView(text(a.cited.isEmpty() ? "Passages found" : "Sources", 14, ACCENT, true), fill(14));
        for (int i = 0; i < a.passages.size(); i++) {
            int n = i + 1;
            boolean cited = a.cited.contains(n);
            if (!a.cited.isEmpty() && !cited) continue;
            Pack.Passage p = a.passages.get(i);
            LinearLayout src = column(10);
            src.setBackground(round(BG, 10));
            src.addView(text("[" + n + "] " + Engine.label(p), 13, ACCENT, true));
            TextView body = text(p.body, 14, TEXT, false);
            body.setMaxLines(4);
            src.addView(body, fill(6));
            TextView more = text("▾", 13, MUTED, false);
            more.setTextIsSelectable(false);
            src.addView(more);
            src.setOnClickListener(v -> {
                boolean open = body.getMaxLines() > 4;
                body.setMaxLines(open ? 4 : Integer.MAX_VALUE);
                more.setText(open ? "▾" : "▴");
            });
            card.addView(src, fill(8));
        }
        int others = a.passages.size() - (a.cited.isEmpty() ? a.passages.size() : a.cited.size());
        if (others > 0) card.addView(text("+" + others + " other passage(s) found but not cited.", 12, MUTED, false), fill(6));
    }

    void scrollDown() { threadScroll.post(() -> threadScroll.fullScroll(View.FOCUS_DOWN)); }

    @Override
    public void onBackPressed() {
        if (busy) return;
        super.onBackPressed();
    }
}
