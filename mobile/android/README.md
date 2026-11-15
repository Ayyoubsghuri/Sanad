# Sanad for Android

The phone version of Sanad, with the same interface as the desktop app. It works on its own: the law pack lives on the phone,
the question is turned into a bge-m3 vector by Cloudflare Workers AI, and the answer is written by OpenAI, Gemini or Claude (or any
OpenAI-compatible API).

## First start

Before the app opens, a setup page asks for:

1. **AI answers**: choose **OpenAI**, **Gemini**, **Claude** or **Other** (any OpenAI-compatible service), paste its API key and
   pick the model. The model list is read from the provider with your key; the defaults are the desktop app's (`gpt-4o` for
   OpenAI, `claude-opus-5-5` for Claude) and, for Gemini, the newest Flash model your key offers. Gemini is called through
   Google's OpenAI-compatible endpoint, Claude through Anthropic's official Java SDK (`Claude.java`), with the API's
   refusal fallbacks switched on for Claude Opus 5.5 and Sonnet 5.5;
2. **Search by meaning**: your Cloudflare **Account ID** and an **API token** with Workers AI access
   (Cloudflare dashboard → AI → Workers AI → “Use REST API”).

It checks both keys, then downloads the law pack (use Wi-Fi). The keys stay in the app's private storage on the phone.
Later, **API keys** in the app's menu opens the same page (to change a key or download a newer law pack).

## Updates

Every APK is signed with the same release key, so a new version installs over the old one and keeps your keys, your
chats and the law pack. When a newer version is published, the app shows **A new version of Sanad is available ·
Update**: it downloads the APK and opens Android's installer (the first time, Android asks you to allow Sanad to install
updates).

The key is a GitHub secret of the repository (Settings → Secrets and variables → Actions):

- `ANDROID_KEYSTORE_BASE64`: the keystore file, base64-encoded;
- `ANDROID_KEYSTORE_PASSWORD`: its password.

Keep a copy of the keystore and its password somewhere safe: an APK signed with another key can never update the app.
Without the secret, the build is signed with a throw-away key (it still works, but must be installed fresh).

## How it is built

- `frontend/` is the interface (React). The Android build bundles its `dist/` folder into the app, together with
  `web-extra/bridge.js` and `web-extra/setup.html` (Gradle task `copyWeb`).
- The interface is shown in a WebView (`MainActivity`). Its calls to the backend (`http://127.0.0.1:8765/v1/...`) are routed
  by `bridge.js` to the Java engine (`Api` → `Engine`), so no server runs on the phone. Desktop-only features
  (operating modes, Bulletin Officiel update, document upload) are hidden or answer "not available in the phone app".

GitHub Actions builds the APK (`.github/workflows/android.yml`) on every push to `main` that changes `mobile/android/` or
`frontend/`, and publishes it on the Releases page as **Sanad for Android (latest build)** (`Sanad.apk`).

To build on a PC with the Android SDK (JDK 17, Gradle 8.7+):

```
cd frontend && npm ci --legacy-peer-deps && npm run build
cd ../mobile/android && gradle assembleDebug
```

## The law pack for the phone

The publisher builds it from the full pack (every dated version of each article, so the app can answer with the law in
force on the date chosen in its top bar) and uploads it to the folder `mobile/` of the Hugging Face dataset; the tools for
that are kept on the publisher's computer, not in this repository. The app downloads `manifest.json`,
`sanad_mobile.db` and `sanad_mobile.vec` from there and checks their SHA-256.

## How a question is answered

1. (optional) the question is rewritten in formal Arabic by the model, for search only;
2. keyword search on the phone (SQLite FTS4, BM25 ranking — the same words and formula as the PC app);
3. meaning search on the phone over the int8 vectors (memory-mapped, so they barely use RAM), with the question's vector from Cloudflare;
4. the two lists are fused (reciprocal rank fusion), the 12 best passages are sent with the question to the model,
   which answers citing them as [n]; the app shows the cited passages.

There is no reranker on the phone and no claim-by-claim verification as on the PC: read the quoted sources.
The question is sent as typed to Cloudflare and to the AI service (the desktop app masks names first).
