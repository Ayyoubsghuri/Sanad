package ma.sanad.app;

/** BM25 from SQLite FTS4 matchinfo(...,'pcnalx'), the same formula as FTS5's bm25() (k1 = 1.2, b = 0.75) that the PC app ranks with. */
public final class Bm25 {
    private Bm25() {}

    /** info = the matchinfo blob read as 32-bit little-endian integers. */
    public static double score(int[] info) {
        int p = info[0], c = info[1];
        long n = info[2] & 0xffffffffL;
        int iA = 3, iL = 3 + c, iX = 3 + 2 * c;
        double k1 = 1.2, b = 0.75, total = 0;
        for (int col = 0; col < c; col++) {
            double avgdl = Math.max(1, info[iA + col]);
            double dl = info[iL + col];
            for (int ph = 0; ph < p; ph++) {
                int base = iX + 3 * (col + ph * c);
                double tf = info[base];
                double df = info[base + 2];
                if (tf <= 0) continue;
                double idf = Math.log((n - df + 0.5) / (df + 0.5));
                if (idf < 1e-6) idf = 1e-6;
                total += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl));
            }
        }
        return total;
    }

    public static int[] ints(byte[] blob) {
        int[] out = new int[blob.length / 4];
        for (int i = 0; i < out.length; i++) {
            int o = i * 4;
            out[i] = (blob[o] & 0xff) | (blob[o + 1] & 0xff) << 8 | (blob[o + 2] & 0xff) << 16 | (blob[o + 3] & 0xff) << 24;
        }
        return out;
    }
}
