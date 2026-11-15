package ma.sanad.app;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.util.ArrayList;
import java.util.List;
import java.util.PriorityQueue;

/** The pack's vectors, read from disk (memory-mapped, so they barely use RAM): int8 numbers with one scale per passage. */
public final class VecIndex {
    public final int count, dim;
    private final float[] scales;
    private final List<MappedByteBuffer> parts = new ArrayList<>();
    private final int rowsPerPart;
    private final long dataStart;

    public VecIndex(File f) throws IOException {
        try (RandomAccessFile raf = new RandomAccessFile(f, "r"); FileChannel ch = raf.getChannel()) {
            ByteBuffer head = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN);
            ch.read(head, 0);
            head.flip();
            byte[] magic = new byte[8];
            head.get(magic);
            if (!new String(magic, "ISO-8859-1").startsWith("SNDVEC1")) throw new IOException("not a Sanad vector file");
            count = head.getInt();
            dim = head.getInt();
            ByteBuffer sb = ByteBuffer.allocate(4 * count).order(ByteOrder.LITTLE_ENDIAN);
            ch.read(sb, 16);
            sb.flip();
            scales = new float[count];
            sb.asFloatBuffer().get(scales);
            dataStart = 16L + 4L * count;
            rowsPerPart = Math.max(1, (int) (1_000_000_000L / dim)); // a mapping is limited to 2 GB: map in parts of about 1 GB
            for (long r = 0; r < count; r += rowsPerPart) {
                long rows = Math.min(rowsPerPart, count - r);
                parts.add(ch.map(FileChannel.MapMode.READ_ONLY, dataStart + r * dim, rows * dim));
            }
        }
    }

    /** Top-k rows by cosine with q (q need not be normalised).  Returns row numbers (passage id = row + 1). */
    public int[] search(float[] q, int k) {
        double n = 0;
        for (float x : q) n += x * x;
        n = Math.sqrt(n);
        float[] qq = new float[dim];
        for (int i = 0; i < dim; i++) qq[i] = (float) (q[i] / (n == 0 ? 1 : n));
        PriorityQueue<double[]> top = new PriorityQueue<>((a, b) -> Double.compare(a[0], b[0]));
        byte[] row = new byte[dim];
        int r = 0;
        for (MappedByteBuffer part : parts) {
            ByteBuffer bb = part.duplicate();
            bb.position(0);
            while (bb.remaining() >= dim) {
                bb.get(row);
                float s = scales[r];
                if (s != 0f) {
                    float dot = 0;
                    for (int i = 0; i < dim; i++) dot += qq[i] * row[i];
                    double score = dot * s;
                    if (top.size() < k) top.add(new double[]{score, r});
                    else if (score > top.peek()[0]) { top.poll(); top.add(new double[]{score, r}); }
                }
                r++;
            }
        }
        int[] out = new int[top.size()];
        for (int i = out.length - 1; i >= 0; i--) out[i] = (int) top.poll()[1];
        return out;
    }
}
