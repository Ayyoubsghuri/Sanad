package ma.sanad.app;

import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;

/** The law pack on the phone: passages + keyword index (sanad_mobile.db) and vectors (sanad_mobile.vec). */
public final class Pack {
    public static final class Passage {
        public int id, authority;
        public String lawTitle, lawNumber, article, bo, body, kind, domain, validFrom, validTo;
    }

    public final SQLiteDatabase db;
    public final VecIndex vec;
    public final Set<String> stop = new HashSet<>();
    public final Map<String, String> meta = new HashMap<>();
    /** true when the pack carries every version with its dates (valid_to); older packs hold one date only. */
    public final boolean dated;
    private String allowDate;
    private java.util.BitSet allow;

    public Pack(File dir) throws IOException {
        db = SQLiteDatabase.openDatabase(new File(dir, "sanad_mobile.db").getPath(), null,
                SQLiteDatabase.OPEN_READONLY | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
        vec = new VecIndex(new File(dir, "sanad_mobile.vec"));
        try (Cursor c = db.rawQuery("SELECT w FROM stopword", null)) { while (c.moveToNext()) stop.add(c.getString(0)); }
        try (Cursor c = db.rawQuery("SELECT key, value FROM meta", null)) { while (c.moveToNext()) meta.put(c.getString(0), c.getString(1)); }
        boolean hasTo = false;
        try (Cursor c = db.rawQuery("PRAGMA table_info(passage)", null)) { while (c.moveToNext()) if ("valid_to".equals(c.getString(1))) hasTo = true; }
        dated = hasTo;
    }

    /** The passages in force on a date (yyyy-mm-dd), as a set of passage ids; null = no filter (a pack without dates). */
    public synchronized java.util.BitSet inForce(String date) {
        if (!dated || date == null) return null;
        if (date.equals(allowDate)) return allow;
        java.util.BitSet b = new java.util.BitSet();
        try (Cursor c = db.rawQuery("SELECT id FROM passage WHERE (valid_from IS NULL OR valid_from<=?) AND (valid_to IS NULL OR valid_to>?)", new String[]{date, date})) {
            while (c.moveToNext()) b.set(c.getInt(0));
        }
        allowDate = date;
        allow = b;
        return b;
    }

    public static boolean present(File dir) {
        return new File(dir, "sanad_mobile.db").exists() && new File(dir, "sanad_mobile.vec").exists();
    }

    /** Best passage ids for the keyword query, ranked with BM25 (the same formula as the PC app). */
    public int[] keyword(String fts, int k) { return keyword(fts, k, null); }

    public int[] keyword(String fts, int k, java.util.BitSet allowed) {
        if (fts == null || fts.isEmpty()) return new int[0];
        PriorityQueue<double[]> top = new PriorityQueue<>((a, b) -> Double.compare(a[0], b[0]));
        try (Cursor c = db.rawQuery("SELECT docid, matchinfo(passage_fts,'pcnalx') FROM passage_fts WHERE passage_fts MATCH ? LIMIT 30000", new String[]{fts})) {
            while (c.moveToNext()) {
                if (allowed != null && !allowed.get(c.getInt(0))) continue; // not in force on the chosen date
                double s = Bm25.score(Bm25.ints(c.getBlob(1)));
                if (top.size() < k) top.add(new double[]{s, c.getInt(0)});
                else if (s > top.peek()[0]) { top.poll(); top.add(new double[]{s, c.getInt(0)}); }
            }
        } catch (RuntimeException e) {
            return new int[0]; // a query the index cannot parse: the meaning search still runs
        }
        int[] out = new int[top.size()];
        for (int i = out.length - 1; i >= 0; i--) out[i] = (int) top.poll()[1];
        return out;
    }

    /** Best passage ids by meaning (vector rows are passage id - 1). */
    public int[] meaning(float[] q, int k) { return meaning(q, k, null); }

    public int[] meaning(float[] q, int k, java.util.BitSet allowed) {
        int[] rows = vec.search(q, k, allowed);
        for (int i = 0; i < rows.length; i++) rows[i] += 1;
        return rows;
    }

    public List<Passage> passages(List<Integer> ids) {
        Map<Integer, Passage> by = new HashMap<>();
        if (ids.isEmpty()) return new ArrayList<>();
        StringBuilder in = new StringBuilder();
        for (int id : ids) in.append(in.length() == 0 ? "" : ",").append(id);
        String cols = "id, law_title, law_number, article, bo, body, kind, authority, domain, valid_from" + (dated ? ", valid_to" : "");
        try (Cursor c = db.rawQuery("SELECT " + cols + " FROM passage WHERE id IN (" + in + ")", null)) {
            while (c.moveToNext()) {
                Passage p = new Passage();
                p.id = c.getInt(0); p.lawTitle = c.getString(1); p.lawNumber = c.getString(2); p.article = c.getString(3); p.bo = c.getString(4);
                p.body = c.getString(5); p.kind = c.getString(6); p.authority = c.getInt(7); p.domain = c.getString(8);
                p.validFrom = c.getString(9); p.validTo = dated ? c.getString(10) : null;
                by.put(p.id, p);
            }
        }
        List<Passage> out = new ArrayList<>();
        for (int id : ids) if (by.containsKey(id)) out.add(by.get(id));
        return out;
    }
}
