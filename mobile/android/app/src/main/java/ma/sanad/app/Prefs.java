package ma.sanad.app;

import android.content.Context;
import android.content.SharedPreferences;

/** Your keys and settings, kept in this app's private storage on the phone (no other app can read them). */
public final class Prefs {
    public static final String DEFAULT_PACK_URL = "https://huggingface.co/datasets/Xdnh00p/sanad-lawpack/resolve/main/mobile/";

    /** The AI services the setup page offers. Gemini is reached through Google's OpenAI-compatible endpoint, Claude through Anthropic's SDK. */
    public static final String[] PROVIDERS = {"openai", "gemini", "anthropic", "compat"};
    public static final String GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai";

    private final SharedPreferences p;

    public Prefs(Context c) { p = c.getSharedPreferences("sanad", Context.MODE_PRIVATE); }

    public String get(String k, String def) { return p.getString(k, def); }
    public void put(String k, String v) { p.edit().putString(k, v == null ? "" : v.trim()).apply(); }
    public boolean flag(String k, boolean def) { return p.getBoolean(k, def); }
    public void setFlag(String k, boolean v) { p.edit().putBoolean(k, v).apply(); }

    public String provider() {
        String v = get("ai_provider", "openai");
        for (String x : PROVIDERS) if (x.equals(v)) return v;
        return "openai";
    }

    /** Each service keeps its own key, so switching back and forth does not lose one. (OpenAI keeps its old name.) */
    public static String keyName(String provider) { return "openai".equals(provider) ? "openai_key" : provider + "_key"; }
    public static String modelName(String provider) { return "openai".equals(provider) ? "openai_model" : provider + "_model"; }

    /** The default model when none was chosen: the desktop app's default for OpenAI (gpt-4o), Claude Opus 5.5 for Claude. */
    public static String defaultModel(String provider) {
        switch (provider) {
            case "anthropic": return Claude.DEFAULT_MODEL;
            case "openai": return "gpt-4o";
            default: return "";
        }
    }

    public String aiKey() { return aiKey(provider()); }
    public String aiKey(String provider) { return get(keyName(provider), ""); }

    public String aiModel() {
        String m = get(modelName(provider()), "");
        return m.isEmpty() ? defaultModel(provider()) : m;
    }

    public String aiBase() { return aiBase(provider()); }
    public String aiBase(String provider) {
        if ("gemini".equals(provider)) return GEMINI_BASE;
        String b = get("openai".equals(provider) ? "openai_base" : "compat_base", "");
        return (b.isEmpty() ? "https://api.openai.com/v1" : b).replaceAll("/+$", "");
    }

    public String cfAccount() { return get("cf_account", ""); }
    public String cfToken() { return get("cf_token", ""); }
    public String packUrl() { String u = get("pack_url", ""); u = u.isEmpty() ? DEFAULT_PACK_URL : u; return u.endsWith("/") ? u : u + "/"; }

    public boolean ready() { return !aiKey().isEmpty() && !aiModel().isEmpty() && !cfAccount().isEmpty() && !cfToken().isEmpty(); }
}
