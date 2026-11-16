## Sanad {version}

Sanad answers questions on Moroccan law from the official texts, with the articles it relies on.

### New in 0.3.6

- **API keys in Offline mode:** online providers (OpenAI, Anthropic, others) are shown greyed out as "Disabled in Offline
  mode" and can no longer be tested, edited or selected; only a local model can be added and chosen. The button on a
  local model now reads "Use in Offline mode" / "Used in Offline mode".

### New in 0.3.5

- **One law pack on disk:** updating the law pack no longer keeps the old one as `previous.db`. The copy left by earlier
  versions is deleted at the next start, which frees about 2 GB.

### New in 0.3.4

- The titles of "What you can do now" and "Similar Court of Cassation rulings" are now on their own line.

### New in 0.3.3

- **What you can do now:** when you describe your own situation, the answer now ends with practical steps in the order to
  take them: what to do, where, which papers to prepare, within which time limit, and when to see a professional. On
  Windows every step is checked: it can only cite the articles of the answer, and a step giving a time limit or a number
  that no cited article contains is removed. A general question about the law gets no such section. (Windows and Android.)

### New in 0.3.2

- **Similar court rulings under every answer:** once the court rulings are downloaded (Professional Toolkit →
  Download court rulings), each answer ends with the closest Court of Cassation rulings: number, date, chamber, outcome,
  the principle and a link to the PDF, plus how the most similar rulings were decided. They are shown apart from the law,
  as an aid to interpretation, and searched on this computer only (nothing is sent).

### New in 0.3.1

- **Court rulings download:** the Professional Toolkit now offers **Download court rulings** (about 26,000 Court of
  Cassation decisions, 2008–2025). The file is checked (SHA-256) before it is installed; **Update** appears when a newer
  set is published. Stopped downloads continue where they left off.
- **Offline mode with a local model:** in API keys, add a **Local model** (Ollama or LM Studio, found automatically) and
  pick it for Offline mode: answers and the toolkit then run entirely on this computer.
- **Fixed:** in Hybrid mode the toolkit, the guides and the contract check were refused by the privacy gateway.
- Rulings now show every outcome (cassation, rejected, inadmissible, lapsed, withdrawn, reversed, affirmed, corrected).

### Professional Toolkit (Pro Lawyer mode)

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
