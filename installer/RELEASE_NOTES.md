## Sanad {version}

Sanad answers questions on Moroccan law from the official texts, with the articles it relies on.

### What's new

- **Download the models from inside the app.** **API keys → Search by meaning** now has install buttons, with progress
  and a Stop button (a stopped download continues the next time):
  - **Install the small model (about 1 GB):** sorts the results by meaning; for every computer, also under 16 GB.
  - **Install the models on this computer (about 5 GB):** search by meaning without Cloudflare, also in Offline mode;
    only on computers with 16 GB of memory or more. Once installed, Sanad switches to them.
  - No need to run "Sanad - repair setup" any more for this. Not available in Offline mode (nothing is downloaded).

Earlier versions: see [CHANGELOG.md](https://github.com/Ayyoubsghuri/Sanad/blob/main/CHANGELOG.md).

### Downloads

| File | For |
|---|---|
| `SanadSetup-{version}.exe` | Windows 10/11: setup wizard |
| `Sanad-{version}.msi` | Windows 10/11: Windows Installer package (same app as the .exe; pick either) |
| `Sanad-{version}.apk` | Android 8 and later |
| `SHA256SUMS.txt` | checksums of the files above |

**Windows:** the first start downloads the law pack and the local models (about 7 GB) and then opens Sanad in its own window.

**Android:** open the `.apk` on the phone and allow installing from that source. If Android refuses to install over an
older Sanad, uninstall that one first (it was signed with another key).
On first start the app asks for the AI service (OpenAI, Gemini or Claude) and its key, and for a Cloudflare account ID and
API token (search by meaning), then downloads the phone's law pack (use Wi-Fi).

**Law at a date:** the **Law today** chip in the top bar picks the date whose law applies (on Windows and on Android).
On the phone this needs the newest phone law pack (it carries every dated version): download it from the setup page
(API keys in the menu → Download the latest version).

### What the Android app does not do (yet)

The phone app has the same interface as the desktop app, but a lighter engine. Compared with Windows:

- **No claim-by-claim verification.** The desktop app checks every sentence of the answer against the cited articles; on the
  phone, read the quoted articles under the answer.
- **No reranker.** Passages are ranked by keyword and meaning search only.
- **Questions are sent as typed.** The desktop app masks names and personal details before anything leaves the computer;
  on the phone the question goes as written to Cloudflare and to the AI service you chose.
- **No Bulletin Officiel update, no operating modes, no document upload.** To get newer texts on the phone, download the
  newest law pack from the setup page (API keys in the menu).

Sanad is a reading aid, not legal advice.
