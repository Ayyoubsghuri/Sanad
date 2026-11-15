# Sanad for Android

A phone version of Sanad that works on its own: the law pack lives on the phone, the question is turned into a bge-m3 vector by
Cloudflare Workers AI, and the answer is written by OpenAI (or any OpenAI-compatible API). You enter your own keys in the app's
Settings; they stay on the phone.

## Build

GitHub Actions builds the APK (`.github/workflows/android.yml`): open the repository's **Actions** tab, the latest
"Android APK" run, and download the `sanad-apk` artifact. Unzip it and install `app-debug.apk` on the phone
(allow "install unknown apps" for your browser or file manager).

To build on a PC with the Android SDK: `gradle assembleDebug` in this folder (Gradle 8.7+, JDK 17).

## The law pack for the phone

On the PC with the full pack: `py backend\tools\make_mobile_pack.py`, then upload `mobile_out\` to the Hugging Face dataset
in the folder `mobile/` (`backend\scripts\PUBLISH_MOBILE_PACK_HF.bat`). The app downloads `manifest.json`,
`sanad_mobile.db` and `sanad_mobile.vec` from there and checks their SHA-256.

## How a question is answered

1. (optional) the question is rewritten in formal Arabic by the model, for search only;
2. keyword search on the phone (SQLite FTS4, BM25 ranking — the same words and formula as the PC app);
3. meaning search on the phone over the int8 vectors (memory-mapped, so they barely use RAM), with the question's vector from Cloudflare;
4. the two lists are fused (reciprocal rank fusion), the 12 best passages are sent with the question to the model,
   which answers citing them as [n]; the app shows the cited passages.

There is no reranker on the phone and no claim-by-claim verification as on the PC: read the quoted sources.
