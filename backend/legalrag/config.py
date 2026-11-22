"""Static (environment) configuration.

Runtime preferences the user can change in the app (mode, auto-approve, keep-places...)
live in the user database and are exposed through /v1/settings; this module only holds
deployment-level values. All variables use the LEGALRAG_ prefix.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["offline", "hybrid", "cloud_assisted"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGALRAG_", env_file=".env", extra="ignore")

    # ---- server ---------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8765
    # search by meaning: "local" (bge-m3 on this computer, installed by the setup) or "cloudflare" (Workers AI, no local models);
    # the setup writes the choice made on first start, the app's settings can change it
    embeddings_source: str = "local"
    api_token: str | None = None  # generated + persisted on first run when unset
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["tauri://localhost", "http://tauri.localhost", "http://localhost:1420", "http://127.0.0.1:1420",
                                  "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
    )
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost", "testserver"])
    max_upload_mb: int = 25
    frontend_dir: Path | None = None  # a built frontend (frontend/dist): served at / by the backend itself, so the installed app needs no Node server

    # ---- storage --------------------------------------------------------------
    data_dir: Path = Path.home() / ".moroccan-legal-rag"
    lawpack_path: Path | None = None  # default: <data_dir>/lawpack/current.db
    lawpack_public_key_hex: str | None = None  # Ed25519 public key (hex) of the pack publisher
    allow_unsigned_pack: bool = False  # dev only: serve an unsigned pack, flagged on every answer
    pack_max_age_days: int = 45
    pack_release_url: str = "https://raw.githubusercontent.com/Ayyoubsghuri/Sanad/main/backend/pack_release.json"  # the published pack (checked by "Law pack" in the app)
    rulings_manifest_url: str = "https://huggingface.co/datasets/Xdnh00p/sanad-lawpack/resolve/main/rulings/manifest.json"  # Court of Cassation rulings (Professional Toolkit)

    # ---- operating mode default (user can change at runtime) -------------------
    default_mode: Mode = "hybrid"

    # ---- retrieval parameters (starting values from the blueprint; tune on the golden set)
    dense_k: int = 50
    bm25_k: int = 50
    primary_k: int = 30  # second search limited to laws and codes: a general question is not drowned by thousands of ministerial orders
    primary_pool: int = 12  # best passages of that second search that always reach the reranker
    rrf_k: int = 60
    rerank_in: int = 50
    rerank_keep: int = 14
    rerank_in_weak: int = 25
    rerank_keep_weak: int = 8
    graph_budget_tokens: int = 2500
    max_subquestions: int = 5
    query_rewrite: bool = True  # Darija / French / English questions are also searched as formal Arabic (needs the language model; off in offline mode)
    cloud_timeout_s: float = 60.0
    # coverage / abstention thresholds (scores are reranker scores in 0..1)
    coverage_min_top_score: float = 0.30
    broad_mode: bool = True  # open "how do I" questions: pick passages by search rank when the reranker is flat
    broad_min_agree: int = 6
    broad_keep: int = 16
    focus_bonus: float = 0.25  # added to the score of a passage of a law the question names by number ("قرار 1432.26")
    coverage_min_margin: float = 0.0
    coverage_min_supports: int = 1
    domain_boost: float = 0.05

    # ---- embedder ---------------------------------------------------------------
    # The query MUST be embedded by the same model as the pack's vectors (embedder_id).
    embedder_id: str = "hash-ngram-v1"
    embedder_local_kind: Literal["hash", "ollama", "sentence_transformers"] = "hash"
    embedder_local_model: str = "bge-m3"
    embedder_local_url: str = "http://127.0.0.1:11434"
    embedder_cloud_url: str | None = None  # OpenAI-compatible /embeddings endpoint serving the SAME model
    embedder_cloud_model: str | None = None
    embedder_cloud_secret: str = "embedder_cloud"

    # ---- reranker -----------------------------------------------------------------
    reranker_local_kind: Literal["lexical", "cross_encoder", "none"] = "cross_encoder"  # falls back to "lexical" by itself if the model cannot be loaded
    reranker_local_model: str = "BAAI/bge-reranker-v2-m3"  # multilingual cross-encoder (Apache-2.0, ~570M parameters, same family as the bge-m3 embedder); a folder <data_dir>/models/bge-reranker-v2-m3 is used first (offline)
    reranker_max_length: int = 1024  # tokens of question + passage; 512 is faster, the model was trained up to 3072
    reranker_batch_size: int = 8
    reranker_trust_remote_code: bool = False
    reranker_cloud_url: str | None = None  # Jina/TEI/Cohere-style /rerank endpoint
    reranker_cloud_model: str | None = None
    reranker_cloud_secret: str = "reranker_cloud"

    # ---- generation (cloud) ---------------------------------------------------------
    llm_provider: Literal["none", "anthropic", "openai_compat"] = "none"
    llm_model: str | None = None  # pin a dated model version; recorded in every trace
    llm_base_url: str | None = None  # e.g. your zero-retention region endpoint or gateway
    llm_region: str | None = None
    llm_secret: str = "llm_main"
    claim_check_provider: Literal["local", "anthropic", "openai_compat"] = "local"
    claim_check_model: str | None = None
    claim_check_base_url: str | None = None
    claim_check_secret: str = "llm_claim_check"
    understanding_via_llm: bool = False  # optional structured understanding call (cloud)

    # ---- pseudonymisation -------------------------------------------------------------
    document_min_confidence: float = 0.85
    query_min_confidence: float = 0.60  # below this, a cloud send needs explicit user review

    # ---- optional Arabic NER (extra layer over the rule-based detectors; needs: pip install -e .[ner]) -----
    ner_enabled: bool = True
    ner_model: str = "MutazYoune/Arabic-NER-PII"  # Hugging Face id, or a local directory for offline use
    ner_min_score: float = 0.5
    ner_kinds: list[str] = Field(default_factory=lambda: ["PII", "CONTACT", "NETWORK", "IDENTIFIER"])  # add NUMERIC_ID at your own risk: it can match article numbers

    # ---- Bulletin Officiel auto-update (the "Check for new BO" button) ---------------------------------------
    bo_pipeline_dir: Path | None = None  # optional override; by default the scripts bundled in legalrag/bo_pipeline are used
    bo_dir: Path | None = None  # work folder for downloaded PDFs / extracted md (default: <data_dir>/bo)
    bo_url_template: str = "https://www.sgg.gov.ma/BO/AR/3111/{year}/BO_{num}_Ar.pdf"  # {num} = 7498 or 7498-bis; check against the SGG site
    bo_listing_urls: list[str] = Field(default_factory=list)  # optional SGG listing pages to read links from (any page that links BO_<n>_Ar.pdf files)
    bo_text_cleanup: bool = True  # BO update: repair words the PDF damaged (split words, backwards lam-alef) before indexing
    bo_probe_ahead: int = 12  # how many numbers after the newest one we already have to try
    bo_download_timeout_s: float = 120.0
    bo_max_pdf_mb: int = 400
    bo_extract_timeout_s: int = 3600
    # new issues are chunked + embedded with the pipeline's own scripts when the pack was built from pipeline chunks (pack_meta chunk_source=pipeline)
    bo_chunk_args: list[str] = Field(default_factory=list)  # extra flags for chunk_bo.py, same as your first run (e.g. ["--target","400"])
    bo_embed_args: list[str] = Field(default_factory=lambda: ["--max-seq", "2048", "--batch", "16"])  # flags for embed_chunks.py = your own run (the device is chosen automatically: cuda when there is a GPU)
    bo_embed_model_dir: Path | None = None  # where the embedding model lives (default: <data_dir>/models/<name>, downloaded on first use)
    bo_embed_timeout_s: int = 7200
    pack_private_key_hex: str | None = None  # signing key of the pack publisher (needed to update a SIGNED pack; keep it only on your own machine)

    # ---- misc ---------------------------------------------------------------------------
    trace_retention_days: int = 30
    report_endpoint: str | None = None  # optional: where the user may send reviewed error reports

    def resolved_bo_pipeline_dir(self) -> Path:
        return self.bo_pipeline_dir or Path(__file__).parent / "bo_pipeline"

    def resolved_embed_model_dir(self, model: str) -> Path:
        return self.bo_embed_model_dir or (self.data_dir / "models" / model.split("/")[-1])

    def resolved_reranker_model(self) -> str:
        """The local copy (python -m legalrag.fetch_models) when it exists, else the model name (downloaded from Hugging Face on first use)."""
        d = self.data_dir / "models" / self.reranker_local_model.split("/")[-1]
        return str(d) if (d / "config.json").exists() else self.reranker_local_model

    def resolved_bo_dir(self) -> Path:
        return self.bo_dir or (self.data_dir / "bo")

    def resolved_lawpack_path(self) -> Path:
        return self.lawpack_path or (self.data_dir / "lawpack" / "current.db")
