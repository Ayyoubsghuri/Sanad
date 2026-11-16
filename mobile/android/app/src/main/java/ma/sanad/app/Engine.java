package ma.sanad.app;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** One question: (rewrite to formal Arabic) -> keyword + meaning search on the phone -> answer by your OpenAI key, citing the passages. */
public final class Engine {
    public static final class Answer {
        public String question, searchText, text, asOf;
        public List<Pack.Passage> passages = new ArrayList<>();
        public List<Integer> cited = new ArrayList<>();
        public List<String> notes = new ArrayList<>();
    }

    public interface Step { void on(String what); }

    static final String REWRITE = "You prepare a question about Moroccan law for a search engine whose documents are Moroccan laws written in formal Arabic (فصحى).\n"
            + "Rewrite the user's question as ONE clear question in formal Arabic, using the vocabulary the legislation itself uses (for example: الطلاق، التطليق، "
            + "الشقاق، النفقة، الحضانة، عقد الشغل، الفصل التعسفي، التعويض عن الفصل، مدة الشغل، الأجر، الكراء، التقادم، الشيك، الإفلاس، المخالفة، السياقة).\n"
            + "The input may be Moroccan Darija, French, English or already Arabic. Rules: keep every number, date, amount, article number and law number exactly as "
            + "written; keep the meaning and the situation; add no fact, no law and no article that the user did not mention; do NOT answer the question. "
            + "If the user asks HOW to do something (start a procedure, claim a right), also name in the same sentence the kinds of procedure the legislation "
            + "distinguishes (for example for a divorce: الطلاق بإذن المحكمة، الطلاق الاتفاقي، التطليق للشقاق، الخلع، التمليك). Return only the Arabic question, nothing else.";

    static final String ANSWER = "You are Sanad, an assistant for Moroccan law. You receive a question and numbered passages of Moroccan legislation in force on the date given with the question.\n"
            + "Rules:\n"
            + "1. Use ONLY the passages. Every sentence that states what the law says ends with the number of its passage in brackets, like [3] or [2][5].\n"
            + "2. Quote the decisive words of the law exactly, between «».\n"
            + "3. If the passages do not answer the question, or answer only part of it, say so plainly and say what is missing. Never invent an article, a number, a deadline, a fee or a court.\n"
            + "4. When the question asks HOW to do something, first list the routes the passages offer (one line each, with the condition that decides it), then the steps in the order the law gives them.\n"
            + "5. Do not assume facts about the user (who they are, whether the other party agrees); say which rule fits which situation. No advice on what to choose.\n"
            + "6. Answer in the language of the question: Moroccan Darija if it is written in Darija, French if French, English if English, otherwise formal Arabic. Quotes stay in the language of the passage.\n"
            + "7. Name the law and the article in words when you use them (for example: المادة 82 من مدونة الأسرة).\n"
            + "8. When the user describes their OWN situation (not a general question about the law), end with a section titled \"What you can do now\" in the "
            + "language of the answer (ما يمكنك فعله الآن / Ce que vous pouvez faire maintenant): 3 to 6 numbered steps in the order to do them, the most urgent "
            + "first. Each step is one concrete action: who does what, where (the court or office the passages name), with which papers, within which time limit, "
            + "and ends with the number of the passage it rests on, like [3]. A time limit, an amount, a court or an authority may appear only if a passage you cite "
            + "states it; if the passages give no time limit, say it must be checked with the clerk's office. A step that only organises the person (gather the "
            + "papers, keep the proof) needs no passage but must contain no number. Add one line saying when a lawyer or another professional is needed. "
            + "For a general question, do not add this section.\n"
            + "9. Finish with one short line saying this is legal information, not legal advice.";

    private final Prefs prefs;
    private final Pack pack;

    public Engine(Prefs prefs, Pack pack) { this.prefs = prefs; this.pack = pack; }

    public Answer ask(String question, Step step) throws Exception { return ask(question, null, step); }

    /** asOf: the date (yyyy-mm-dd) whose law applies; null = today. */
    public Answer ask(String question, String asOf, Step step) throws Exception {
        Answer a = new Answer();
        a.asOf = asOf == null || !asOf.matches("\\d{4}-\\d{2}-\\d{2}") ? java.time.LocalDate.now().toString() : asOf;
        java.util.BitSet allowed = pack.inForce(a.asOf);
        if (!pack.dated && asOf != null && !asOf.equals(java.time.LocalDate.now().toString()))
            a.notes.add("This law pack holds only the texts in force on " + pack.meta.getOrDefault("as_of", "its build date") + ": download the newest law pack (Settings) to answer for another date.");
        a.question = question.trim();
        a.searchText = a.question;
        if (prefs.flag("rewrite", true)) {
            step.on("rewrite");
            try {
                String r = chat(REWRITE, a.question, 300);
                if (r != null && Norm.arabicRatio(r) >= 0.6 && r.length() >= 3 && r.length() <= 900) a.searchText = r.trim().replaceAll("^\"|\"$", "");
            } catch (Exception e) {
                a.notes.add("rewrite skipped: " + e.getMessage());
            }
        }
        step.on("search");
        List<String> words = new ArrayList<>(Norm.tokens(a.searchText));
        if (!a.searchText.equals(a.question)) words.addAll(Norm.tokens(a.question));
        List<int[]> lists = new ArrayList<>();
        lists.add(pack.keyword(Norm.ftsQuery(words, pack.stop, 24), 50, allowed));
        try {
            List<String> texts = new ArrayList<>();
            texts.add(a.searchText);
            if (!a.searchText.equals(a.question)) texts.add(a.question);
            for (float[] v : embed(texts)) lists.add(pack.meaning(v, 50, allowed));
        } catch (Exception e) {
            a.notes.add("meaning search unavailable (" + e.getMessage() + "): keyword search only");
        }
        List<Integer> ids = Fuse.rrf(lists, 60, 12);
        a.passages = pack.passages(ids);
        if (a.passages.isEmpty()) {
            a.text = "لم أجد في النصوص المتوفرة على الهاتف ما يجيب عن هذا السؤال.";
            return a;
        }
        step.on("answer");
        StringBuilder user = new StringBuilder("Question: ").append(a.question)
                .append("\nDate: the law in force on ").append(a.asOf).append("\n\nPassages:\n");
        for (int i = 0; i < a.passages.size(); i++) {
            Pack.Passage p = a.passages.get(i);
            user.append("\n[").append(i + 1).append("] ").append(label(p)).append("\n").append(p.body).append("\n");
        }
        a.text = chat(ANSWER, user.toString(), 4000);
        Matcher m = Pattern.compile("\\[(\\d{1,2})]").matcher(a.text == null ? "" : a.text);
        while (m.find()) {
            int n = Integer.parseInt(m.group(1));
            if (n >= 1 && n <= a.passages.size() && !a.cited.contains(n)) a.cited.add(n);
        }
        return a;
    }

    /** Keyword + meaning search over the law in force on asOf (no rewrite, no answer): the professional tools use it. */
    List<Pack.Passage> search(String text, String asOf, int k) throws Exception {
        java.util.BitSet allowed = pack.inForce(asOf);
        List<int[]> lists = new ArrayList<>();
        lists.add(pack.keyword(Norm.ftsQuery(new ArrayList<>(Norm.tokens(text)), pack.stop, 24), 50, allowed));
        try {
            List<String> one = new ArrayList<>();
            one.add(text);
            for (float[] v : embed(one)) lists.add(pack.meaning(v, 50, allowed));
        } catch (Exception ignored) {
            // keyword search alone
        }
        return pack.passages(Fuse.rrf(lists, 60, k));
    }

    /** A model call that must return one JSON object following `schema` (all providers, through chat()). */
    JSONObject chatJson(String system, JSONObject payload, JSONObject schema, int maxTokens) throws Exception {
        String sys = system + "\n\nReply with ONLY one JSON object that follows this JSON schema, with no text before or after it:\n" + schema.toString();
        String out = chat(sys, payload.toString(), maxTokens);
        if (out == null) throw new Exception("the model returned nothing");
        int a = out.indexOf('{'), b = out.lastIndexOf('}');
        if (a < 0 || b <= a) throw new Exception("the model did not return JSON");
        return new JSONObject(out.substring(a, b + 1));
    }

    public static String label(Pack.Passage p) {
        StringBuilder s = new StringBuilder();
        if (p.lawTitle != null && !p.lawTitle.isEmpty()) s.append(p.lawTitle);
        if (p.lawNumber != null && !p.lawNumber.isEmpty()) s.append(" (").append(p.lawNumber).append(")");
        if (p.article != null && !p.article.isEmpty()) s.append(" — المادة/الفصل ").append(p.article);
        if (p.bo != null && !p.bo.isEmpty()) s.append(" — ").append(p.bo);
        return s.toString();
    }

    /** One call to the AI service chosen in the setup page (OpenAI, Gemini, Claude or another OpenAI-compatible service). */
    String chat(String system, String user, int maxTokens) throws Exception {
        String provider = prefs.provider();
        if ("anthropic".equals(provider)) {
            try {
                return Claude.chat(prefs.aiKey(), prefs.aiModel(), system, user, maxTokens, maxTokens >= 1000);
            } catch (com.anthropic.errors.UnauthorizedException e) {
                throw new Exception("Anthropic refused the key (401): check it in Settings");
            }
        }
        JSONObject body = new JSONObject();
        body.put("model", prefs.aiModel());
        JSONArray msgs = new JSONArray();
        msgs.put(new JSONObject().put("role", "system").put("content", system));
        msgs.put(new JSONObject().put("role", "user").put("content", user));
        body.put("messages", msgs);
        boolean gemini = "gemini".equals(provider);
        body.put(gemini ? "max_tokens" : "max_completion_tokens", maxTokens);
        Map<String, String> h = new HashMap<>();
        h.put("Authorization", "Bearer " + prefs.aiKey());
        String url = prefs.aiBase() + "/chat/completions";
        String name = gemini ? "Google" : "openai".equals(provider) ? "OpenAI" : "The AI service";
        String res;
        try {
            res = Net.postJson(url, h, body.toString(), 120000);
        } catch (Net.HttpError e) {
            if (e.code == 400 && e.getMessage().contains("max_completion_tokens")) { // older OpenAI-compatible servers
                body.remove("max_completion_tokens");
                body.put("max_tokens", maxTokens);
                res = Net.postJson(url, h, body.toString(), 120000);
            } else if (e.code == 401 || e.code == 403) {
                throw new Exception(name + " refused the key (" + e.code + "): check it in Settings");
            } else throw e;
        }
        return new JSONObject(res).getJSONArray("choices").getJSONObject(0).getJSONObject("message").optString("content", "").trim();
    }

    /** The chat models a key can use, for the model dropdown of the setup page. */
    static List<String> models(String provider, String key, String base) throws Exception {
        if ("anthropic".equals(provider)) return Claude.models(key);
        Map<String, String> h = new HashMap<>();
        h.put("Authorization", "Bearer " + key);
        JSONArray data = new JSONObject(Net.getJson(base + "/models", h)).getJSONArray("data");
        List<String> out = new ArrayList<>();
        for (int i = 0; i < data.length(); i++) {
            String id = data.getJSONObject(i).optString("id", "").replaceFirst("^models/", "");
            String l = id.toLowerCase();
            if (l.isEmpty() || l.matches(".*(embed|audio|tts|transcribe|realtime|image|dall-e|whisper|moderation|search|vision|live|veo|imagen|aqa).*")) continue;
            if ("openai".equals(provider) && !l.matches("^(gpt-|o\\d|chatgpt).*")) continue;
            if ("gemini".equals(provider) && !l.startsWith("gemini")) continue;
            out.add(id);
        }
        return out;
    }

    List<float[]> embed(List<String> texts) throws Exception {
        JSONObject body = new JSONObject().put("text", new JSONArray(texts));
        Map<String, String> h = new HashMap<>();
        h.put("Authorization", "Bearer " + prefs.cfToken());
        String url = "https://api.cloudflare.com/client/v4/accounts/" + prefs.cfAccount() + "/ai/run/@cf/baai/bge-m3";
        String res;
        try {
            res = Net.postJson(url, h, body.toString(), 30000);
        } catch (Net.HttpError e) {
            if (e.code == 401 || e.code == 403) throw new Exception("Cloudflare refused the token (" + e.code + ")");
            throw e;
        }
        JSONObject r = new JSONObject(res).getJSONObject("result");
        JSONArray data = r.has("data") ? r.getJSONArray("data") : r.getJSONArray("response");
        List<float[]> out = new ArrayList<>();
        for (int i = 0; i < data.length(); i++) {
            JSONArray v = data.getJSONArray(i);
            float[] f = new float[v.length()];
            for (int j = 0; j < f.length; j++) f[j] = (float) v.getDouble(j);
            if (pack != null && f.length != pack.vec.dim) throw new Exception("Cloudflare returned " + f.length + " numbers, the pack has " + pack.vec.dim);
            out.add(f);
        }
        return out;
    }
}
