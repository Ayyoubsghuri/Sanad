## Sanad {version}

Sanad answers questions on Moroccan law from the official texts, with the articles it relies on.

### New: Professional Toolkit (Pro Lawyer mode)

Switch the sidebar's audience button to **Pro Lawyer**, then open **Professional Toolkit**:

- **AI Courtroom**: Lawyer A builds your client's case, Lawyer B attacks it, and an independent judge weighs both: the
  issues and which side each favours, risks, what to do, and an estimated chance of success.
- **Case Analyzer**: the legal issues of a file, the law in force on the date, what similar rulings decided and which
  arguments won or lost there.
- **Jurisprudence Finder**: comparable Court of Cassation rulings with their outcome and accepted or rejected grounds.
- 24 tools for lawyers, judges and researchers, notaries, company legal departments and judicial officers (defence
  memorandum, contract review, appeal grounds, comparing decisions, inheritance checklist, compliance, notices,
  execution checklist and more).

Every point cites its articles and rulings; citations the model invents are removed. On Windows the text is masked
before it is sent and shown to you first. Court rulings appear once the rulings database is installed; until then the
tools rely on the law alone.

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
