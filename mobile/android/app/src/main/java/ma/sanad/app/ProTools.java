package ma.sanad.app;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The professional toolkit on the phone (/v1/pro/...): the same tools, prompts and result format as the PC backend
 * (legalrag/pro), read from web/pro_toolkit.json. Differences: no rulings database yet on the phone, and the text is
 * sent as typed (the phone does not mask names), which the preview says.
 */
final class ProTools {
    static final class Out {
        final int status; final String body;
        Out(int status, String body) { this.status = status; this.body = body; }
    }

    private static final class Job {
        String id, asOf, lang, status = "preview";
        JSONObject tool, fields = new JSONObject(), result, error;
        final JSONArray steps = new JSONArray();
        final JSONArray preview = new JSONArray();
        long stepStart;
    }

    private final Api.Host host;
    private JSONObject kit;
    private final Map<String, Job> jobs = new ConcurrentHashMap<>();

    ProTools(Api.Host host) { this.host = host; }

    private synchronized JSONObject kit() throws Exception {
        if (kit == null) kit = new JSONObject(host.asset("pro_toolkit.json"));
        return kit;
    }

    private JSONObject tool(String id) throws Exception {
        JSONArray t = kit().getJSONArray("tools");
        for (int i = 0; i < t.length(); i++) if (t.getJSONObject(i).getString("id").equals(id)) return t.getJSONObject(i);
        return null;
    }

    Out handle(String method, String path, String body) {
        try {
            if (path.equals("/v1/pro/catalog")) return ok(catalog());
            if (path.equals("/v1/pro/rulings/stats")) return ok(new JSONObject().put("available", false));
            if (path.equals("/v1/pro/jobs") && method.equals("POST")) return prepare(new JSONObject(body == null || body.isEmpty() ? "{}" : body));
            Matcher m = Pattern.compile("^/v1/pro/jobs/([^/]+)(/run)?$").matcher(path);
            if (m.find()) {
                Job j = jobs.get(m.group(1));
                if (j == null) return err(404, "job not found or expired: prepare it again");
                if (m.group(2) != null) return start(j, new JSONObject(body == null || body.isEmpty() ? "{}" : body));
                if (method.equals("DELETE")) { jobs.remove(j.id); return new Out(204, ""); }
                return ok(view(j));
            }
            return err(404, "Not available in the phone app.");
        } catch (Exception e) {
            return err(500, e.getMessage() == null ? e.toString() : e.getMessage());
        }
    }

    private JSONObject catalog() throws Exception {
        JSONArray tools = new JSONArray();
        JSONArray all = kit().getJSONArray("tools");
        for (int i = 0; i < all.length(); i++) {
            JSONObject t = new JSONObject(all.getJSONObject(i).toString());
            t.remove("instructions");
            tools.put(t);
        }
        return new JSONObject().put("groups", kit().getJSONArray("groups")).put("tools", tools).put("rulings_available", false);
    }

    private Out prepare(JSONObject b) throws Exception {
        JSONObject t = tool(b.optString("tool"));
        if (t == null) return err(404, "unknown tool");
        JSONObject f = b.optJSONObject("fields") == null ? new JSONObject() : b.optJSONObject("fields");
        JSONArray defs = t.getJSONArray("fields");
        Job j = new Job();
        for (int i = 0; i < defs.length(); i++) {
            JSONObject d = defs.getJSONObject(i);
            String v = f.optString(d.getString("id"), "").trim();
            if (d.optBoolean("required") && v.isEmpty()) return err(422, "missing field: " + d.getString("id"));
            if (v.isEmpty()) continue;
            j.fields.put(d.getString("id"), v);
            if (!"choice".equals(d.optString("kind"))) j.preview.put(new JSONObject().put("field", d.getString("id")).put("label", d.get("label")).put("text", v));
        }
        j.id = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        j.tool = t;
        String asOf = b.optString("as_of", "");
        j.asOf = asOf.matches("\\d{4}-\\d{2}-\\d{2}") ? asOf : java.time.LocalDate.now().toString();
        j.lang = b.optString("lang", "ar");
        jobs.put(j.id, j);
        return ok(view(j));
    }

    private boolean hasModel() {
        Prefs p = host.prefs();
        return p != null && p.aiKey() != null && !p.aiKey().isEmpty();
    }

    private int plannedCalls(Job j) throws Exception {
        if (!hasModel()) return 0;
        return "courtroom".equals(j.tool.getString("kind")) ? 4 : 2;
    }

    private JSONObject view(Job j) throws Exception {
        return new JSONObject().put("job_id", j.id).put("tool", j.tool.getString("id")).put("kind", j.tool.getString("kind"))
                .put("status", j.status).put("as_of", j.asOf).put("preview", j.preview).put("entity_counts", new JSONObject())
                .put("planned_calls", plannedCalls(j)).put("model", hasModel() ? host.prefs().aiModel() : JSONObject.NULL)
                .put("mode", "hybrid").put("phone_unmasked", true).put("steps", j.steps)
                .put("result", j.result == null ? JSONObject.NULL : j.result).put("error", j.error == null ? JSONObject.NULL : j.error);
    }

    private Out start(Job j, JSONObject b) throws Exception {
        if (!"preview".equals(j.status)) return ok(view(j));
        JSONObject ed = b.optJSONObject("edited");
        if (ed != null) {
            for (Iterator<String> it = ed.keys(); it.hasNext(); ) {
                String k = it.next();
                if (j.fields.has(k)) j.fields.put(k, ed.getString(k));
            }
        }
        j.status = "running";
        new Thread(() -> {
            try {
                run(j);
                j.status = "done";
            } catch (Exception e) {
                try { j.error = new JSONObject().put("code", "failed").put("message", e.getMessage() == null ? e.toString() : e.getMessage()); } catch (Exception ignored) { }
                j.status = "error";
            }
            closeSteps(j, "error".equals(j.status) ? "failed" : "done");
        }).start();
        return ok(view(j));
    }

    // ------------------------------------------------------------------------------------------------ the run
    private void step(Job j, String id) throws Exception {
        closeSteps(j, "done");
        j.stepStart = System.currentTimeMillis();
        j.steps.put(new JSONObject().put("id", id).put("label", kit().getJSONObject("steps").get(id)).put("status", "running"));
    }

    private void closeSteps(Job j, String status) {
        for (int i = 0; i < j.steps.length(); i++) {
            JSONObject s = j.steps.optJSONObject(i);
            if (s != null && "running".equals(s.optString("status"))) {
                try { s.put("status", status).put("ms", System.currentTimeMillis() - j.stepStart); } catch (Exception ignored) { }
            }
        }
    }

    private void run(Job j) throws Exception {
        Engine engine = host.engine();
        if (engine == null) throw new Exception("The law pack is not installed on this phone: open Settings (API keys) to download it.");
        JSONObject k = kit(), pr = k.getJSONObject("prompts"), sc = k.getJSONObject("schemas");
        String kind = j.tool.getString("kind");
        StringBuilder cb = new StringBuilder();
        for (String f : new String[]{"facts", "document", "document_b", "goal", "question"}) {
            if (j.fields.has(f)) { if (cb.length() > 0) cb.append("\n\n"); cb.append(j.fields.getString(f)); }
        }
        String caseText = cb.toString();
        boolean model = hasModel();
        JSONArray warnings = new JSONArray();
        JSONArray issues = new JSONArray();
        List<String> queries = new ArrayList<>();
        String summary = "";

        if (model) {
            step(j, "plan");
            try {
                JSONObject got = engine.chatJson(pr.getString("plan"), new JSONObject().put("case", cut(caseText, 12000)).put("tool", j.tool.getString("id")).put("date", j.asOf),
                        sc.getJSONObject("plan"), 1200);
                JSONArray is = got.optJSONArray("issues"), qs = got.optJSONArray("queries");
                if (is != null) issues = is;
                if (qs != null) for (int i = 0; i < qs.length() && queries.size() < 6; i++) if (!qs.optString(i).trim().isEmpty()) queries.add(qs.optString(i));
                summary = got.optString("summary", "");
            } catch (Exception e) {
                warnings.put("plan: " + e.getMessage());
            }
        }
        if (queries.isEmpty()) queries.add(cut(caseText, 600));

        step(j, "law");
        Map<String, Pack.Passage> srcs = new LinkedHashMap<>();
        Set<Integer> seen = new HashSet<>();
        int perQ = queries.size() > 3 ? 4 : 6;
        for (String q : queries) {
            for (Pack.Passage p : engine.search(q, j.asOf, perQ)) {
                if (srcs.size() >= 16) break;
                if (seen.add(p.id)) srcs.put("S" + (srcs.size() + 1), p);
            }
        }
        if (j.tool.optBoolean("uses_rulings")) {
            step(j, "rulings");
            warnings.put("no_rulings_db");
        }
        JSONArray articles = new JSONArray();
        for (Map.Entry<String, Pack.Passage> e : srcs.entrySet()) articles.put(article(e.getKey(), e.getValue()));
        JSONObject notice = k.getJSONObject("notice");
        JSONObject result = new JSONObject().put("tool", j.tool.getString("id")).put("kind", kind).put("as_of", j.asOf).put("issues", issues)
                .put("case_summary", summary).put("articles", articles).put("rulings", new JSONArray()).put("similar_outcomes", new JSONObject())
                .put("rulings_db", 0).put("warnings", warnings).put("status", "sources_only").put("output", JSONObject.NULL)
                .put("notice", notice.optString(j.lang, notice.getString("ar")));
        j.result = result;
        if (!model || srcs.isEmpty()) {
            if (!model) warnings.put("no_model");
            if (srcs.isEmpty()) warnings.put("nothing_found");
            return;
        }

        JSONArray passages = new JSONArray();
        for (Map.Entry<String, Pack.Passage> e : srcs.entrySet()) {
            Pack.Passage p = e.getValue();
            passages.put(new JSONObject().put("id", e.getKey()).put("source", Engine.label(p)).put("in_force_from", p.validFrom == null ? "" : p.validFrom)
                    .put("text", cut(p.body == null ? "" : p.body, 1600)));
        }
        String langName = k.getJSONObject("lang_name").optString(j.lang, "Arabic");
        String base = pr.getString("base").replace("{lang}", langName);
        JSONObject payload = new JSONObject().put("date", j.asOf).put("case", cut(caseText, 16000)).put("issues", issues)
                .put("passages", passages).put("rulings", new JSONArray());
        Set<String> valid = new HashSet<>(srcs.keySet());
        JSONObject out;
        if ("courtroom".equals(kind)) {
            String side = "defendant".equals(j.fields.optString("side")) ? "defendant" : "claimant";
            String sideTxt = k.getJSONObject("side").getString(side);
            step(j, "lawyer_a");
            JSONObject a = engine.chatJson(base + pr.getString("lawyer_a").replace("{side}", sideTxt), copy(payload).put("client_side", side), sc.getJSONObject("lawyer_a"), 6000);
            step(j, "lawyer_b");
            JSONObject b = engine.chatJson(base + pr.getString("lawyer_b"), copy(payload).put("client_side", side).put("lawyer_a", a), sc.getJSONObject("lawyer_b"), 6000);
            step(j, "judge");
            JSONObject ju = engine.chatJson(base + pr.getString("judge"), copy(payload).put("client_side", side).put("lawyer_a", a).put("lawyer_b", b)
                    .put("similar_rulings_outcomes", new JSONObject()), sc.getJSONObject("judge"), 6000);
            step(j, "check");
            int c = ju.optInt("chance_of_success", 50);
            ju.put("chance_of_success", Math.max(5, Math.min(95, c)));
            out = new JSONObject().put("lawyer_a", a).put("lawyer_b", b).put("judge", ju).put("side", side);
        } else {
            step(j, "write");
            String tpl = pr.getString("finder".equals(kind) ? "finder" : "report");
            JSONArray secs = j.tool.getJSONArray("sections");
            StringBuilder sl = new StringBuilder();
            for (int i = 0; i < secs.length(); i++) { if (i > 0) sl.append("; "); sl.append(secs.getString(i)); }
            String sys = base + tpl.replace("{instructions}", j.tool.optString("instructions")).replace("{sections}", sl.toString());
            out = engine.chatJson(sys, payload, sc.getJSONObject("report"), 6000);
            step(j, "check");
        }
        int removed = checkSources(out, valid);
        result.put("output", out).put("status", "generated").put("unsupported_citations", removed);
        closeSteps(j, "done");
    }

    /** Drops citations of ids the model was not given and marks items left without a source (as the PC does). */
    static int checkSources(Object node, Set<String> valid) throws Exception {
        int removed = 0;
        if (node instanceof JSONObject) {
            JSONObject o = (JSONObject) node;
            JSONArray s = o.optJSONArray("sources");
            if (s != null) {
                JSONArray keep = new JSONArray();
                for (int i = 0; i < s.length(); i++) {
                    String v = s.optString(i, "").trim();
                    if (valid.contains(v)) keep.put(v); else removed++;
                }
                o.put("sources", keep).put("unsourced", keep.length() == 0);
            }
            for (Iterator<String> it = o.keys(); it.hasNext(); ) removed += checkSources(o.get(it.next()), valid);
        } else if (node instanceof JSONArray) {
            JSONArray a = (JSONArray) node;
            for (int i = 0; i < a.length(); i++) removed += checkSources(a.get(i), valid);
        }
        return removed;
    }

    private static JSONObject article(String id, Pack.Passage p) throws Exception {
        String law = p.lawTitle == null ? "" : p.lawTitle;
        if (p.lawNumber != null && !p.lawNumber.isEmpty()) law = law.isEmpty() ? p.lawNumber : law + " (" + p.lawNumber + ")";
        return new JSONObject().put("id", id).put("law", law).put("article", p.article == null || p.article.isEmpty() ? "" : "المادة " + p.article)
                .put("text", p.body == null ? "" : p.body).put("valid_from", p.validFrom == null ? JSONObject.NULL : p.validFrom)
                .put("valid_to", p.validTo == null ? JSONObject.NULL : p.validTo).put("in_force_on_as_of", true).put("provision_id", "p" + p.id);
    }

    private static JSONObject copy(JSONObject o) throws Exception { return new JSONObject(o.toString()); }

    private static String cut(String s, int n) { return s.length() <= n ? s : s.substring(0, n); }

    private static Out ok(Object o) { return new Out(200, o.toString()); }

    private static Out err(int code, String msg) {
        try { return new Out(code, new JSONObject().put("detail", msg).toString()); }
        catch (Exception e) { return new Out(code, "{}"); }
    }
}
