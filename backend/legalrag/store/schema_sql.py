"""DDL for the read-only, signed law pack (shared by the pack builder and the runtime reader).

Dates are ISO text. `valid_to` is EXCLUSIVE and NULL means "still in force".
"""

TRUSTED_STATUSES = ("verified", "single_source", "derived")

LAWPACK_DDL = """
CREATE TABLE source_file (
  source_id   INTEGER PRIMARY KEY,
  url         TEXT,
  fetched_at  TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  kind        TEXT NOT NULL,                 -- bo_pdf | sgg_consolidated | adala | other
  edition     TEXT NOT NULL CHECK (edition IN ('official','unofficial_translation')),
  label       TEXT
);

CREATE TABLE instrument (
  instrument_id TEXT PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('constitution','organic_law','law','dahir_law','code','decree','order','circular','treaty','court_decision','administrative_guidance')),
  number        TEXT,
  short_code    TEXT,
  title_ar      TEXT,
  title_fr      TEXT,
  bo_number     TEXT,
  bo_date       TEXT,
  promulgation_date TEXT,
  effective_date    TEXT,
  ratification_date TEXT,
  language_availability TEXT,                -- JSON: {"ar":"official","fr":"official_translation"}
  implementation_status TEXT NOT NULL DEFAULT 'unknown' CHECK (implementation_status IN ('self_executing','issued','pending','unknown')),
  implementation_checked_on TEXT,
  status_flag   TEXT,                        -- NULL | ACTIVE_CONTESTED
  status_note   TEXT,
  consolidated_text_available INTEGER NOT NULL DEFAULT 0,
  official_article_count INTEGER,
  domain        TEXT                         -- labor | civil_procedure | family | criminal | tax | commercial | property | obligations ...
);

CREATE TABLE instrument_alias (
  alias         TEXT NOT NULL,
  instrument_id TEXT NOT NULL REFERENCES instrument(instrument_id),
  PRIMARY KEY (alias, instrument_id)
);

CREATE TABLE provision (
  provision_id  TEXT PRIMARY KEY,            -- e.g. MA_DOC_1913_ART_230
  instrument_id TEXT NOT NULL REFERENCES instrument(instrument_id),
  path          TEXT,                        -- book / title / chapter heading path
  number        TEXT NOT NULL,
  number_int    INTEGER,
  suffix        TEXT NOT NULL DEFAULT '',    -- bis | ter | ...
  ordinal       INTEGER NOT NULL DEFAULT 0,
  is_definition   INTEGER NOT NULL DEFAULT 0,
  is_transitional INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_provision_instr ON provision(instrument_id, number_int, suffix);

CREATE TABLE provision_version (
  pv_id        INTEGER PRIMARY KEY,
  provision_id TEXT NOT NULL REFERENCES provision(provision_id),
  valid_from   TEXT NOT NULL,
  valid_to     TEXT,
  controlling_lang TEXT NOT NULL DEFAULT 'ar',
  amended_by   TEXT REFERENCES instrument(instrument_id),
  source_id    INTEGER NOT NULL REFERENCES source_file(source_id),
  checksum     TEXT NOT NULL,
  verification_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (verification_status IN ('verified','single_source','derived','disputed','draft'))
);
CREATE INDEX idx_pv_prov ON provision_version(provision_id, valid_from);

CREATE TABLE provision_text (
  pv_id   INTEGER NOT NULL REFERENCES provision_version(pv_id),
  lang    TEXT NOT NULL,
  edition TEXT NOT NULL CHECK (edition IN ('official','unofficial_translation')),
  text    TEXT NOT NULL,
  PRIMARY KEY (pv_id, lang)
);

CREATE TABLE transitional_rule (
  rule_id       INTEGER PRIMARY KEY,
  instrument_id TEXT NOT NULL REFERENCES instrument(instrument_id),
  applies_when  TEXT NOT NULL CHECK (applies_when IN ('filed_before','filed_after','facts_before','facts_after','judgment_before','judgment_after')),
  cutoff_date   TEXT,
  note          TEXT NOT NULL,               -- literal text of the rule
  source_provision_id TEXT REFERENCES provision(provision_id),
  governs_version_before TEXT,               -- provision_id/instrument that governs, informational
  governs_version_after  TEXT
);

CREATE TABLE edge (
  from_kind TEXT NOT NULL CHECK (from_kind IN ('provision','instrument','decision')),
  from_id   TEXT NOT NULL,
  to_kind   TEXT NOT NULL CHECK (to_kind IN ('provision','instrument','decision')),
  to_id     TEXT NOT NULL,
  type      TEXT NOT NULL CHECK (type IN ('refers_to','amends','repeals','replaces','suspends','implements','interprets')),
  source    TEXT NOT NULL CHECK (source IN ('regex','llm','manual')),
  confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (from_kind, from_id, to_kind, to_id, type)
);
CREATE INDEX idx_edge_from ON edge(from_kind, from_id);
CREATE INDEX idx_edge_to ON edge(to_kind, to_id);

CREATE TABLE rate_table (
  rate_id INTEGER PRIMARY KEY,
  key     TEXT NOT NULL,
  value   REAL,
  unit    TEXT,
  valid_from TEXT NOT NULL,
  valid_to   TEXT,
  source_decree TEXT,
  extra_json TEXT,
  note    TEXT
);
CREATE INDEX idx_rate_key ON rate_table(key, valid_from);

CREATE TABLE deadline_rule (
  rule_id INTEGER PRIMARY KEY,
  kind    TEXT NOT NULL CHECK (kind IN ('appeal','limitation','other')),
  case_type TEXT NOT NULL,
  court   TEXT,
  regime  TEXT NOT NULL DEFAULT 'default',
  trigger TEXT NOT NULL CHECK (trigger IN ('notification','decision','start')),
  amount  INTEGER NOT NULL,
  unit    TEXT NOT NULL CHECK (unit IN ('days','months','years')),
  valid_from TEXT,                           -- applicability by decision/start date
  valid_to   TEXT,
  provision_id TEXT REFERENCES provision(provision_id),
  note    TEXT
);

CREATE TABLE holiday (
  date TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('civil','religious')), source TEXT,
  PRIMARY KEY (date, name)
);

CREATE TABLE decision (
  decision_id TEXT PRIMARY KEY,
  court TEXT, decision_date TEXT, number TEXT, chamber TEXT,
  full_text TEXT NOT NULL, source_id INTEGER REFERENCES source_file(source_id)
);
CREATE TABLE decision_provision (
  decision_id TEXT NOT NULL REFERENCES decision(decision_id),
  provision_id TEXT NOT NULL REFERENCES provision(provision_id),
  pv_id INTEGER REFERENCES provision_version(pv_id),   -- version valid on the decision date
  PRIMARY KEY (decision_id, provision_id)
);

CREATE TABLE pending_bill (
  bill_no TEXT PRIMARY KEY, title TEXT, stage TEXT, last_checked TEXT, instrument_id TEXT REFERENCES instrument(instrument_id), note TEXT
);

CREATE TABLE concordance (
  old_provision_id TEXT NOT NULL, new_provision_id TEXT NOT NULL, note TEXT, source TEXT NOT NULL DEFAULT 'derived',
  PRIMARY KEY (old_provision_id, new_provision_id)
);

CREATE TABLE chunk (
  chunk_id INTEGER PRIMARY KEY,
  pv_id    INTEGER NOT NULL REFERENCES provision_version(pv_id),
  lang     TEXT NOT NULL,
  edition  TEXT NOT NULL,
  paragraph_no INTEGER,                      -- NULL = whole article; else paragraph-level chunk
  body     TEXT NOT NULL,                    -- the quotable text (no context prefix)
  text     TEXT NOT NULL,                    -- context-prefixed text that was embedded
  keyword_text TEXT NOT NULL,
  token_count INTEGER NOT NULL
);
CREATE INDEX idx_chunk_pv ON chunk(pv_id);
CREATE VIRTUAL TABLE chunk_fts USING fts5(keyword_text, content='chunk', content_rowid='chunk_id', tokenize='unicode61 remove_diacritics 2');

CREATE TABLE embedder (embedder_id TEXT PRIMARY KEY, model TEXT NOT NULL, version TEXT, dim INTEGER NOT NULL);
CREATE TABLE chunk_embedding (
  chunk_id INTEGER NOT NULL REFERENCES chunk(chunk_id),
  embedder_id TEXT NOT NULL REFERENCES embedder(embedder_id),
  vector BLOB NOT NULL,
  PRIMARY KEY (chunk_id, embedder_id)
);

CREATE TABLE provision_page (          -- where the article sits in its source PDF (PDF page numbers, 1-based)
  provision_id TEXT NOT NULL REFERENCES provision(provision_id),
  source_id INTEGER NOT NULL REFERENCES source_file(source_id),
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  PRIMARY KEY (provision_id, source_id)
);

CREATE TABLE pack_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

AUTHORITY_RANK = {
    "constitution": 0,
    "organic_law": 1,
    "treaty": 2,
    "law": 2,
    "dahir_law": 2,
    "code": 2,
    "decree": 3,
    "order": 4,
    "circular": 5,
    "administrative_guidance": 6,
    "court_decision": 7,
}
