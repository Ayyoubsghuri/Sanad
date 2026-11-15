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
        public String question, searchText, text;
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

    static final String ANSWER = "You are Sanad, an assistant for Moroccan law. You receive a question and numbered passages of Moroccan legislation in force today.\n"
            + "Rules:\n"
            + "1. Use ONLY the passages. Every sentence that states what the law says ends with the number of its passage in brackets, like [3] or [2][5].\n"
            + "2. Quote the decisive words of the law exactly, between «».\n"
            + "3. If the passages do not answer the question, or answer only part of it, say so plainly and say what is missing. Never invent an article, a number, a deadline, a fee or a court.\n"
            + "4. When the question asks HOW to do something, first list the routes the passages offer (one line each, with the condition that decides it), then the steps in the order the law gives them.\n"
            + "5. Do not assume facts about the user (who they are, whether the other party agrees); say which rule fits which situation. No advice on what to choose.\n"
            + "6. Answer in the language of the question: Moroccan Darija if it is written in Darija, French if French, English if English, otherwise formal Arabic. Quotes stay in the language of the passage.\n"
            + "7. Name the law and the article in words when you use them (for example: المادة 82 من مدونة الأسرة).\n"
            + "8. Finish with one short line saying this is legal information, not legal advice.";

    private final Prefs prefs;
    private final Pack pack;

    public Engine(Prefs prefs, Pack pack) { this.prefs = prefs; this.pack = pack; }

    public Answer ask(String question, Step step) throws Exception {
        Answer a = new Answer();
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
        lists.add(pack.keyword(Norm.ftsQuery(words, pack.stop, 24), 50));
        try {
            List<String> texts = new ArrayList<>();
            texts.add(a.searchText);
            if (!a.searchText.equals(a.question)) texts.add(a.question);
            for (float[] v : embed(texts)) lists.add(pack.meaning(v, 50));
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
        StringBuilder user = new StringBuilder("Question: ").append(a.question).append("\n\nPassages:\n");
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

    public static String label(Pack.Passage p) {
        StringBuilder s = new StringBuilder();
        if (p.lawTitle != null && !p.lawTitle.isEmpty()) s.append(p.lawTitle);
        if (p.lawNumber != null && !p.lawNumber.isEmpty()) s.append(" (").append(p.lawNumber).append(")");
        if (p.article != null && !p.article.isEmpty()) s.append(" — المادة/الفصل ").append(p.article);
        if (p.bo != null && !p.bo.isEmpty()) s.append(" — ").append(p.bo);
        return s.toString();
    }

    String chat(String system, String user, int maxTokens) throws Exception {
        JSONObject body = new JSONObject();
        body.put("model", prefs.openaiModel());
        JSONArray msgs = new JSONArray();
        msgs.put(new JSONObject().put("role", "system").put("content", system));
        msgs.put(new JSONObject().put("role", "user").put("content", user));
        body.put("messages", msgs);
        body.put("max_completion_tokens", maxTokens);
        Map<String, String> h = new HashMap<>();
        h.put("Authorization", "Bearer " + prefs.openaiKey());
        String res;
        try {
            res = Net.postJson(prefs.openaiBase() + "/chat/completions", h, body.toString(), 120000);
        } catch (Net.HttpError e) {
            if (e.code == 400 && e.getMessage().contains("max_completion_tokens")) { // older OpenAI-compatible servers
                body.remove("max_completion_tokens");
                body.put("max_tokens", maxTokens);
                res = Net.postJson(prefs.openaiBase() + "/chat/completions", h, body.toString(), 120000);
            } else if (e.code == 401) {
                throw new Exception("OpenAI refused the key (401): check it in Settings");
            } else throw e;
        }
        return new JSONObject(res).getJSONArray("choices").getJSONObject(0).getJSONObject("message").optString("content", "").trim();
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
