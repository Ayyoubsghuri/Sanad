package ma.sanad.app;

import android.content.Context;
import android.content.SharedPreferences;

/** Your keys and settings, kept in this app's private storage on the phone (no other app can read them). */
public final class Prefs {
    public static final String DEFAULT_PACK_URL = "https://huggingface.co/datasets/Xdnh00p/sanad-lawpack/resolve/main/mobile/";
    private final SharedPreferences p;

    public Prefs(Context c) { p = c.getSharedPreferences("sanad", Context.MODE_PRIVATE); }

    public String get(String k, String def) { return p.getString(k, def); }
    public void put(String k, String v) { p.edit().putString(k, v == null ? "" : v.trim()).apply(); }
    public boolean flag(String k, boolean def) { return p.getBoolean(k, def); }
    public void flag(String k, boolean v) { p.edit().putBoolean(k, v).apply(); }

    public String openaiKey() { return get("openai_key", ""); }
    public String openaiModel() { String m = get("openai_model", ""); return m.isEmpty() ? "gpt-4o-mini" : m; }
    public String openaiBase() { String b = get("openai_base", ""); return (b.isEmpty() ? "https://api.openai.com/v1" : b).replaceAll("/+$", ""); }
    public String cfAccount() { return get("cf_account", ""); }
    public String cfToken() { return get("cf_token", ""); }
    public String packUrl() { String u = get("pack_url", ""); u = u.isEmpty() ? DEFAULT_PACK_URL : u; return u.endsWith("/") ? u : u + "/"; }

    public boolean ready() { return !openaiKey().isEmpty() && !cfAccount().isEmpty() && !cfToken().isEmpty(); }
}
