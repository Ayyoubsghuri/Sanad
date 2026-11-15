package ma.sanad.app;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The part of the PC backend's API that the interface needs on the phone, answered by the phone's own engine.
 * The web interface (frontend/) calls http://127.0.0.1:8765/...; in the app those calls arrive here through Bridge.
 * Desktop-only features answer 404 "not available in the phone app".
 */
final class Api {
    static final class Reply {
        final int status; final String body;
        Reply(int status, String body) { this.status = status; this.body = body; }
    }

    interface Host {
        Engine engine();          // null while the law pack is not installed
        Pack pack();
        Prefs prefs();
    }

    private static final class Query {
        String question, asOf;
        final List<JSONObject> steps = new ArrayList<>();
        volatile boolean done, cancelled;
    }

    private final Host host;
    private final Map<String, Query> queries = new ConcurrentHashMap<>();

    Api(Host host) { this.host = host; }

    Reply handle(String method, String path, String body) {
        try {
            String p = path.split("\\?")[0];
            if (p.equals("/health")) return ok(new JSONObject().put("status", "ok").put("pack_loaded", host.pack() != null).put("pack_usable", host.pack() != null));
            if (p.equals("/pair")) return ok(new JSONObject().put("token", "android"));
            if (p.equals("/v1/status")) return ok(status());
            if (p.equals("/v1/settings")) return ok(new JSONObject());
            if (p.equals("/v1/history") || p.equals("/v1/traces")) return ok(p.equals("/v1/traces") ? new JSONArray() : new JSONObject());
            if (p.equals("/v1/queries") && method.equals("POST")) return prepare(new JSONObject(body.isEmpty() ? "{}" : body));
            Matcher m = Pattern.compile("^/v1/queries/([^/]+)/(run|progress|cancel)$").matcher(p);
            if (m.find()) {
                Query q = queries.get(m.group(1));
                if (q == null) return error(404, "unknown question");
                switch (m.group(2)) {
                    case "run": return run(m.group(1), q);
                    case "progress": return ok(new JSONObject().put("steps", new JSONArray(q.steps)).put("done", q.done));
                    default: q.cancelled = true; return ok(new JSONObject().put("cancelled", true));
                }
            }
            return error(404, "Not available in the phone app.");
        } catch (Exception e) {
            return error(500, e.getMessage() == null ? e.toString() : e.getMessage());
        }
    }

    private JSONObject status() throws Exception {
        Pack pk = host.pack();
        JSONObject pack = new JSONObject().put("loaded", pk != null).put("usable", pk != null);
        if (pk != null) pack.put("version", pk.meta.get("version"));
        else pack.put("error", "The law pack is not installed: open Settings to download it.");
        return new JSONObject().put("mode", "hybrid").put("platform", "android").put("pack", pack)
                .put("providers", new JSONObject().put("llm", new JSONObject().put("provider", host.prefs().provider()).put("model", host.prefs().aiModel())));
    }

    private Reply prepare(JSONObject b) throws Exception {
        String id = UUID.randomUUID().toString();
        Query q = new Query();
        q.question = b.optString("question", "").trim();
        q.asOf = b.isNull("as_of") ? null : b.optString("as_of", "").trim();
        if (q.asOf != null && q.asOf.isEmpty()) q.asOf = null;
        queries.put(id, q);
        return ok(new JSONObject().put("query_id", id).put("case_id", JSONObject.NULL).put("mode", "hybrid")
                .put("pseudonymised_text", q.question).put("confidence", 1).put("warnings", new JSONArray())
                .put("requires_review", false).put("requires_approval", false).put("planned_outbound_calls", new JSONArray()));
    }

    private static final String[][] STEPS = {{"rewrite", "thinking"}, {"search", "search"}, {"answer", "artifact"}};

    private Reply run(String id, Query q) throws Exception {
        Engine engine = host.engine();
        JSONObject a = new JSONObject().put("query_id", id).put("mode", "hybrid").put("language", language(q.question));
        if (engine == null) {
            q.done = true;
            return ok(a.put("status", "unavailable").put("reason", "The law pack is not installed on this phone: open Settings (API keys) to download it."));
        }
        final long[] started = {0};
        Engine.Answer ans;
        try {
            ans = engine.ask(q.question, q.asOf, what -> {
                long now = System.currentTimeMillis();
                closeRunning(q, now - started[0]);
                started[0] = now;
                String kind = "search";
                for (String[] s : STEPS) if (s[0].equals(what)) kind = s[1];
                try {
                    q.steps.add(new JSONObject().put("id", what).put("kind", kind).put("title", what).put("detail", "").put("status", "running").put("duration_ms", JSONObject.NULL));
                } catch (Exception ignored) { }
            });
        } finally {
            closeRunning(q, System.currentTimeMillis() - started[0]);
            q.done = true;
        }
        if (q.cancelled) return ok(a.put("status", "cancelled"));
        a.put("as_of", ans.asOf);
        a.put("steps", new JSONArray(q.steps));
        JSONArray sources = new JSONArray();
        for (int i = 0; i < ans.passages.size(); i++) sources.put(source(ans.passages.get(i), i, ans.passages.size()));
        a.put("sources", sources);
        JSONArray notices = new JSONArray();
        for (String n : ans.notes) notices.put(n);
        if (ans.passages.isEmpty()) {
            return ok(a.put("status", "abstained").put("claims", new JSONArray()).put("notices", notices)
                    .put("abstain", new JSONObject().put("reason", ans.text)));
        }
        notices.put("On the phone the answer is not checked claim by claim: read the quoted articles.");
        a.put("notices", notices).put("status", "answered").put("claims", claims(ans));
        return ok(a);
    }

    private static void closeRunning(Query q, long ms) {
        for (JSONObject s : q.steps) {
            if ("running".equals(s.optString("status"))) {
                try { s.put("status", "done").put("duration_ms", ms); } catch (Exception ignored) { }
            }
        }
    }

    /** One claim per paragraph of the model's answer; its [n] markers become the claim's sources (the interface numbers them again). */
    private static JSONArray claims(Engine.Answer ans) throws Exception {
        JSONArray out = new JSONArray();
        Pattern ref = Pattern.compile("\\s*\\[(\\d{1,2})]");
        for (String para : (ans.text == null ? "" : ans.text).split("\\n\\s*\\n")) {
            if (para.trim().isEmpty()) continue;
            JSONArray src = new JSONArray();
            List<String> seen = new ArrayList<>();
            Matcher m = ref.matcher(para);
            while (m.find()) {
                int n = Integer.parseInt(m.group(1));
                if (n >= 1 && n <= ans.passages.size()) {
                    String id = "p" + ans.passages.get(n - 1).id;
                    if (!seen.contains(id)) { seen.add(id); src.put(id); }
                }
            }
            String text = src.length() > 0 ? ref.matcher(para).replaceAll("").trim() : para.trim();
            out.put(new JSONObject().put("type", "statement").put("text", text).put("sources", src)
                    .put("calculators", new JSONArray()).put("verified", false));
        }
        return out;
    }

    private static JSONObject source(Pack.Passage p, int i, int n) throws Exception {
        String law = p.lawTitle == null ? "" : p.lawTitle;
        if (p.lawNumber != null && !p.lawNumber.isEmpty()) law = law.isEmpty() ? p.lawNumber : law + " (" + p.lawNumber + ")";
        String article = p.article == null || p.article.isEmpty() ? "" : "المادة " + p.article;
        JSONObject bo = new JSONObject();
        Matcher m = Pattern.compile("BO\\s+(\\S+)\\s*(.*)").matcher(p.bo == null ? "" : p.bo);
        if (m.find()) bo.put("number", m.group(1)).put("date", m.group(2).isEmpty() ? JSONObject.NULL : m.group(2));
        return new JSONObject().put("id", "p" + p.id).put("law", law).put("article", article).put("text", p.body == null ? "" : p.body)
                .put("bo", bo).put("valid_from", p.validFrom == null ? "" : p.validFrom).put("valid_to", p.validTo == null ? JSONObject.NULL : p.validTo).put("kind", "article").put("relevance", 1.0 - (double) i / Math.max(1, n))
                .put("has_pdf", false).put("in_force_on_as_of", true);
    }

    static String language(String q) {
        if (Norm.arabicRatio(q) >= 0.3) return "ar";
        String l = " " + q.toLowerCase() + " ";
        if (l.matches(".*[éèêàçù].*") || l.matches(".*\\b(le|la|les|des|est|une|pour|que|quel|quelle|comment|mon|ma)\\b.*")) return "fr";
        return "en";
    }

    private static Reply ok(Object o) { return new Reply(200, o.toString()); }

    private static Reply error(int code, String msg) {
        try { return new Reply(code, new JSONObject().put("detail", msg).toString()); }
        catch (Exception e) { return new Reply(code, "{}"); }
    }
}
