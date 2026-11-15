package ma.sanad.app;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Reciprocal rank fusion of the keyword and meaning searches (k = 60, as on the PC). */
public final class Fuse {
    private Fuse() {}

    public static List<Integer> rrf(List<int[]> lists, int k, int keep) {
        Map<Integer, Double> s = new HashMap<>();
        for (int[] l : lists) for (int i = 0; i < l.length; i++) s.merge(l[i], 1.0 / (k + i + 1), Double::sum);
        List<Map.Entry<Integer, Double>> e = new ArrayList<>(s.entrySet());
        e.sort((a, b) -> Double.compare(b.getValue(), a.getValue()));
        List<Integer> out = new ArrayList<>();
        for (int i = 0; i < Math.min(keep, e.size()); i++) out.add(e.get(i).getKey());
        return out;
    }
}
