package ma.sanad.app;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

/** HTTPS calls (OpenAI, Cloudflare) and resumable downloads (the law pack). */
public final class Net {
    private Net() {}

    public static class HttpError extends IOException {
        public final int code;
        public HttpError(int code, String body) { super("HTTP " + code + ": " + body); this.code = code; }
    }

    public static String postJson(String url, Map<String, String> headers, String body, int timeoutMs) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod("POST");
        c.setConnectTimeout(20000);
        c.setReadTimeout(timeoutMs);
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        for (Map.Entry<String, String> h : headers.entrySet()) c.setRequestProperty(h.getKey(), h.getValue());
        try (OutputStream o = c.getOutputStream()) { o.write(body.getBytes(StandardCharsets.UTF_8)); }
        int code = c.getResponseCode();
        InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
        String text = in == null ? "" : read(in);
        c.disconnect();
        if (code >= 400) throw new HttpError(code, text.length() > 400 ? text.substring(0, 400) : text);
        return text;
    }

    public static String get(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(20000);
        c.setReadTimeout(60000);
        c.setInstanceFollowRedirects(true);
        int code = c.getResponseCode();
        if (code >= 400) throw new HttpError(code, url);
        String s = read(c.getInputStream());
        c.disconnect();
        return s;
    }

    /** GET with headers (the providers' model lists). */
    public static String getJson(String url, Map<String, String> headers) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(20000);
        c.setReadTimeout(30000);
        for (Map.Entry<String, String> h : headers.entrySet()) c.setRequestProperty(h.getKey(), h.getValue());
        int code = c.getResponseCode();
        InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
        String text = in == null ? "" : read(in);
        c.disconnect();
        if (code >= 400) throw new HttpError(code, text.length() > 300 ? text.substring(0, 300) : text);
        return text;
    }

    static String read(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
        in.close();
        return b.toString("UTF-8");
    }

    public interface Progress { void update(long done, long total); boolean cancelled(); }

    /** Downloads url into dest, continuing a partial file (dest.part) if one is there.  Hugging Face redirects to its file store: followed by hand. */
    public static void download(String url, File dest, long expectedSize, Progress p) throws IOException {
        File part = new File(dest.getPath() + ".part");
        for (int attempt = 1; attempt <= 8; attempt++) {
            long have = part.exists() ? part.length() : 0;
            if (expectedSize > 0 && have == expectedSize) break;
            if (expectedSize > 0 && have > expectedSize) { part.delete(); have = 0; }
            try {
                HttpURLConnection c = open(url, have);
                int code = c.getResponseCode();
                if (code == 416) { c.disconnect(); break; }
                if (code >= 400) throw new HttpError(code, url);
                boolean append = have > 0 && code == 206;
                if (!append) have = 0;
                long total = expectedSize > 0 ? expectedSize : have + Math.max(0, c.getContentLengthLong());
                try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(part, append)) {
                    byte[] buf = new byte[1 << 16];
                    int n;
                    long last = 0;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n);
                        have += n;
                        if (p != null) {
                            if (p.cancelled()) throw new IOException("stopped");
                            if (have - last > (1 << 20)) { p.update(have, total); last = have; }
                        }
                    }
                }
                c.disconnect();
                if (expectedSize <= 0 || part.length() == expectedSize) break;
            } catch (IOException e) {
                if ("stopped".equals(e.getMessage()) || attempt == 8) throw e;
                try { Thread.sleep(Math.min(30000, 2000L * attempt)); } catch (InterruptedException ie) { throw new IOException("stopped"); }
            }
        }
        if (expectedSize > 0 && part.length() != expectedSize) throw new IOException("download incomplete: " + part.length() + " of " + expectedSize + " bytes");
        if (dest.exists()) dest.delete();
        if (!part.renameTo(dest)) throw new IOException("could not save " + dest.getName());
    }

    private static HttpURLConnection open(String url, long from) throws IOException {
        String u = url;
        for (int hop = 0; hop < 6; hop++) {
            HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection();
            c.setInstanceFollowRedirects(false);
            c.setConnectTimeout(20000);
            c.setReadTimeout(60000);
            if (from > 0) c.setRequestProperty("Range", "bytes=" + from + "-");
            int code = c.getResponseCode();
            if (code >= 300 && code < 400 && c.getHeaderField("Location") != null) {
                u = new URL(new URL(u), c.getHeaderField("Location")).toString();
                c.disconnect();
                continue;
            }
            return c;
        }
        throw new IOException("too many redirects");
    }

    public static String sha256(File f, Progress p) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        long done = 0, total = f.length();
        try (InputStream in = new FileInputStream(f)) {
            byte[] buf = new byte[1 << 20];
            int n;
            while ((n = in.read(buf)) > 0) {
                md.update(buf, 0, n);
                done += n;
                if (p != null) p.update(done, total);
            }
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : md.digest()) sb.append(String.format("%02x", b));
        return sb.toString();
    }
}
