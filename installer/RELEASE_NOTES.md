## Sanad {version}

Sanad answers questions on Moroccan law from the official texts, with the articles it relies on.

### Downloads

| File | For |
|---|---|
| `SanadSetup-{version}.exe` | Windows 10/11: setup wizard |
| `Sanad-{version}.msi` | Windows 10/11: Windows Installer package (same app as the .exe; pick either) |
| `Sanad-{version}.apk` | Android 8 and later |
| `SHA256SUMS.txt` | checksums of the files above |

**Windows:** the first start downloads the law pack and the local models (about 7 GB) and then opens Sanad in its own window.

**Android:** open the `.apk` on the phone and allow installing from that source. If an older Sanad is installed,
uninstall it first (each build is signed with a different key, so Android refuses to update over it).
On first start the app asks for the AI service (OpenAI, Gemini or Claude) and its key, and for a Cloudflare account ID and
API token (search by meaning), then downloads the phone's law pack (use Wi-Fi).

### What the Android app does not do (yet)

The phone app has the same interface as the desktop app, but a lighter engine. Compared with Windows:

- **Law in force today only.** The phone always answers with the texts in force today. The desktop's date setting
  ("the law as it was on a given date") has no effect on the phone, and older versions of an article are not searched.
- **No claim-by-claim verification.** The desktop app checks every sentence of the answer against the cited articles; on the
  phone, read the quoted articles under the answer.
- **No reranker.** Passages are ranked by keyword and meaning search only.
- **Questions are sent as typed.** The desktop app masks names and personal details before anything leaves the computer;
  on the phone the question goes as written to Cloudflare and to the AI service you chose.
- **No Bulletin Officiel update, no operating modes, no document upload.** To get newer texts on the phone, download the
  newest law pack from the setup page (API keys in the menu).

Sanad is a reading aid, not legal advice.
