package ma.sanad.app;

import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.models.beta.messages.BetaMessage;
import com.anthropic.models.beta.messages.BetaOutputConfig;
import com.anthropic.models.beta.messages.BetaStopReason;
import com.anthropic.models.beta.messages.MessageCreateParams;
import com.anthropic.models.models.ModelInfo;

import java.util.ArrayList;
import java.util.List;

/** Answers with Claude through Anthropic's official Java SDK (the "Claude" choice of the setup page). */
final class Claude {
    static final String DEFAULT_MODEL = "claude-opus-5-5";

    private Claude() { }

    private static AnthropicClient client(String key) {
        return AnthropicOkHttpClient.builder().apiKey(key).build();
    }

    /**
     * One answer. Effort: "low" for the short helper calls (question rewrite, key check), "high" for the answer itself.
     * On Claude Opus 5.5 and Sonnet 5.5, a request the safety classifiers decline is retried by the API on another model
     * (server-side fallbacks); a refusal that still comes back is reported as an error.
     */
    static String chat(String key, String model, String system, String user, int maxTokens, boolean deep) throws Exception {
        MessageCreateParams.Builder b = MessageCreateParams.builder()
                .model(model)
                .maxTokens(Math.max(1024, maxTokens))
                .system(system)
                .addUserMessage(user)
                .outputConfig(BetaOutputConfig.builder().effort(deep ? BetaOutputConfig.Effort.HIGH : BetaOutputConfig.Effort.LOW).build());
        if (model.startsWith("claude-opus-5-5") || model.startsWith("claude-sonnet-5-5") || model.startsWith("claude-fable-5")) {
            b.addBeta("server-side-fallback-2026-07-01").fallbacksDefault();
        }
        AnthropicClient c = client(key);
        try {
            BetaMessage m = c.beta().messages().create(b.build());
            if (m.stopReason().isPresent() && m.stopReason().get().equals(BetaStopReason.REFUSAL)) {
                throw new Exception("Claude declined to answer this question.");
            }
            StringBuilder out = new StringBuilder();
            m.content().forEach(block -> block.text().ifPresent(t -> out.append(t.text())));
            return out.toString().trim();
        } finally {
            c.close();
        }
    }

    /** The models this key can use (newest first, as the API lists them). */
    static List<String> models(String key) {
        List<String> ids = new ArrayList<>();
        AnthropicClient c = client(key);
        try {
            for (ModelInfo m : c.models().list().autoPager()) ids.add(m.id());
        } finally {
            c.close();
        }
        return ids;
    }
}
