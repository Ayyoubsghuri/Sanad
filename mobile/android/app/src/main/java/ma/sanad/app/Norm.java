package ma.sanad.app;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/** The same text normalisation as the PC app (legalrag/text/arabic.py), so the phone's keyword search matches the pack's keyword index. */
public final class Norm {
    private Norm() {}

    private static final Pattern WS = Pattern.compile("\\s+");
    private static final String[] PREFIXES = {"وال", "بال", "كال", "فال", "لل", "ال"};

    public static String normalize(String text) {
        if (text == null || text.isEmpty()) return "";
        String t = Normalizer.normalize(text, Normalizer.Form.NFKD);
        StringBuilder sb = new StringBuilder(t.length());
        for (int i = 0; i < t.length(); ) {
            int cp = t.codePointAt(i);
            i += Character.charCount(cp);
            if (Character.getType(cp) == Character.NON_SPACING_MARK) continue;
            if (cp == 'ـ') continue; // tatweel
            sb.appendCodePoint(map(cp));
        }
        String s = sb.toString().replace("œ", "oe").replace("æ", "ae").toLowerCase(Locale.ROOT);
        return WS.matcher(s).replaceAll(" ").trim();
    }

    private static int map(int cp) {
        if (cp >= 0x0660 && cp <= 0x0669) return '0' + (cp - 0x0660); // Arabic-Indic digits
        if (cp >= 0x06F0 && cp <= 0x06F9) return '0' + (cp - 0x06F0); // Persian digits
        switch (cp) {
            case '’': case '‘': return '\'';
            case '“': case '”': case '«': case '»': return '"';
            case '،': return ',';
            case '؛': return ';';
            case '؟': return '?';
            case '–': case '—': return '-';
            case 0x00A0: return ' ';
            case 'ى': case 'ی': return 'ي';
            case 'ة': case 'ھ': case 'ۃ': return 'ه';
            case 'ٱ': return 'ا';
            case 'ک': return 'ك';
            default: return cp;
        }
    }

    /** Python's \\w: letters, digits, other numbers and "_" (not marks); written by hand because Android's regex differs from Java's. */
    static boolean isWord(int cp) {
        if (cp == '_' || Character.isLetter(cp) || Character.isDigit(cp)) return true;
        int t = Character.getType(cp);
        return t == Character.LETTER_NUMBER || t == Character.OTHER_NUMBER;
    }

    public static List<String> tokens(String text) {
        List<String> out = new ArrayList<>();
        String s = normalize(text);
        int start = -1;
        for (int i = 0; i < s.length(); ) {
            int cp = s.codePointAt(i);
            boolean w = isWord(cp);
            if (w && start < 0) start = i;
            if (!w && start >= 0) { out.add(s.substring(start, i)); start = -1; }
            i += Character.charCount(cp);
        }
        if (start >= 0) out.add(s.substring(start));
        return out;
    }

    static boolean isArabic(int cp) {
        return (cp >= 0x0600 && cp <= 0x06FF) || (cp >= 0x0750 && cp <= 0x077F) || (cp >= 0xFB50 && cp <= 0xFDFF) || (cp >= 0xFE70 && cp <= 0xFEFF);
    }

    public static String lightStem(String tok) {
        if (tok.codePointCount(0, tok.length()) > 4 && isArabic(tok.codePointAt(0))) {
            for (String p : PREFIXES) {
                if (tok.startsWith(p) && tok.codePointCount(0, tok.length()) - p.length() >= 3) return tok.substring(p.length());
            }
        }
        return tok;
    }

    public static String keywordText(String text) {
        StringBuilder sb = new StringBuilder();
        for (String t : tokens(text)) {
            if (sb.length() > 0) sb.append(' ');
            sb.append(lightStem(t));
        }
        return sb.toString();
    }

    /** Same as build_fts_query in the PC app: stemmed terms, no stopwords, joined with OR, at most maxTerms. */
    public static String ftsQuery(List<String> words, Set<String> stop, int maxTerms) {
        Set<String> seen = new LinkedHashSet<>();
        for (String w : words) {
            String t = lightStem(w);
            if (stop.contains(t) || t.codePointCount(0, t.length()) < 2) continue;
            seen.add(t.replace("\"", ""));
            if (seen.size() >= maxTerms) break;
        }
        StringBuilder sb = new StringBuilder();
        for (String t : seen) {
            if (sb.length() > 0) sb.append(" OR ");
            sb.append('"').append(t).append('"');
        }
        return sb.toString();
    }

    public static double arabicRatio(String text) {
        int letters = 0, ar = 0;
        for (int i = 0; i < text.length(); ) {
            int cp = text.codePointAt(i);
            i += Character.charCount(cp);
            if (Character.isLetter(cp)) {
                letters++;
                if (isArabic(cp)) ar++;
            }
        }
        return letters == 0 ? 0 : (double) ar / letters;
    }
}
