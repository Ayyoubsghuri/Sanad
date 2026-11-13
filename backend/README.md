# Moroccan Legal RAG: FastAPI backend

Local, source-verified backend for the blueprint "Moroccan Legal RAG: Local, Source-Verified Revision".
It binds to 127.0.0.1, requires a bearer token, and sends nothing to the cloud except pseudonymised text through one gateway.

## Folder layout

```
legalrag/    the application code (API, retrieval, builder, verification)
data/
  codes/     the 7 code texts (markdown)       data/cpp/   criminal procedure (PDF + repaired text)
  sgg/       66 SGG consolidated texts         data/boct/  47 local-authority gazettes
batches/     lists of laws to import (codes.json, sgg.json, template_laws_to_add.json)
reports/     what the checks write (amendments_report.json, crosscheck_report.json)
scripts/     INSTALL_CODES_AND_SGG.bat, INSTALL_BOCT.bat, CHECK_GPU.bat, OPTIONAL_OCR_CPP.bat
tools/       repair_arabic_text.py, ocr_pdf_pages.py
docs/        LAW_IMPORT.md
tests/
```

## Run
    pip install -e .[dev]
    pytest                                   # 64 tests
    legalrag-build fixture --out fixture.db  # builds a signed SYNTHETIC pack (see legalrag-build --help)
    LEGALRAG_LAWPACK_PATH=fixture.db LEGALRAG_ALLOW_UNSIGNED_PACK=true legalrag
    # OpenAPI docs: http://127.0.0.1:8765/docs   (send "Authorization: Bearer <token>")
    legalrag-eval --pack fixture.db --allow-unsigned   # golden set + release gates; non-zero exit if a gate fails

## Flow
1. `POST /v1/queries` pseudonymises on the device and returns the send preview. Nothing leaves yet.
2. `POST /v1/queries/{id}/run` (user approves, optionally edits). Pipeline: understand, date-aware hybrid retrieval, cloud generation (structured JSON), code-side verification, regenerate once, then fall back to verified claims, then to quoted passages only. Names are restored locally after the checks pass.
3. Statuses: answered, partial, extractive_only, abstained, needs_clarification, needs_input, review_required, unavailable, payload_preview.

Other areas: law pack (signed, versioned, trust levels), law status cards and time travel, wizard, navigator, term finder, calculators, documents, export, error reports, coverage-gap log, outbound log, traces, settings and secrets, evaluation.

## Honest limitations
- No real law text is shipped. The pack is a synthetic fixture; real metadata is in `legalrag/data/registry*.json`. Build real packs with `legalrag-build` from sources you have verified.
- The default hashing embedder is lexical, not semantic. Use the optional BGE-M3 / Ollama / cloud embedders for real use.
- The default claim checker is lexical and weak. Use a second-LLM or NLI checker for real use.
- Only the 2% cash-surcharge calculator is checked against an official worked example; the others are labelled unverified.
- The claim-support release gate is not measured here (it needs real-model runs); all other gates run.
- Sensitive columns use app-level Fernet encryption, not SQLCipher.
- Pseudonymisation is pattern- and dictionary-based; unusual names are caught only by the confidence check and the user preview.
- This is a reading aid, not legal advice.

## Arabic PII NER (optional)
`pip install -e .[ner]` adds `MutazYoune/Arabic-NER-PII` (BERT token classifier, Apache-2.0) as an extra detector in the pseudonymiser, run on the device. Weights are downloaded once from Hugging Face on first Arabic text (or set `LEGALRAG_NER_MODEL` to a local folder for offline use). Disable with `LEGALRAG_NER_ENABLED=false`. Its exact-span accuracy is weak (partial F1 0.53), so spans are grown to whole words and it only ever adds detections to the rule-based ones; unavailable model = rules only (see `arabic_ner` in `GET /v1/status`).

## API token (automatic)

The browser app pairs itself: on first use it calls `POST /pair` (answered only to local origins: the desktop shell or a
loopback dev server) and stores the token. Users never copy anything. `LEGALRAG_API_TOKEN` / `VITE_LEGALRAG_TOKEN` are optional overrides.

## Building the law pack from Bulletin Officiel PDFs

    python extract_bo_pdf.py <pdf_folder>            # your extractor: PDFs -> .md (next to each PDF)
    legalrag-build from-bo <md_folder> --pdf-dir <pdf_folder> --out sources.json --report ingest_report.json
    legalrag-build build sources.json --out lawpack.db --version 2026.11.01 --private-key-hex <key>

`from-bo` (1) copies each PDF unchanged into `<md_folder>/_frozen` (read-only) with a sha256 manifest, (2) refuses Arabic text with
presentation forms, (3) splits each BO issue into legal texts and articles (المادة and الفصل, مكرر, ordinals) with the parser from
`chunk_bo.py` (vendored as `builder/bo_structure.py`), (4) writes one dated provision version per article (`valid_from` = BO date,
`single_source`), (5) adds amends / repeals / implements links read from each text's title, and (6) runs the builder checks.
Read `ingest_report.json`: texts that were skipped, effective dates that were assumed from the BO date (review them), unresolved links.
Chunking (7) is done by `build`.
