"""Application context: wires settings, stores, pack, privacy, retrieval, providers and pipeline together."""
from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass, field
from typing import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .calc.registry import CalculatorService
from .config import Settings
from .llm.providers import AnthropicProvider, ClaimChecker, LexicalChecker, LLMClaimChecker, LLMProvider, OpenAICompatProvider
from .privacy.gateway import Gateway, OutboundGuard
from .privacy.ner import NerDetector
from .privacy.pseudonymiser import Pseudonymiser
from .store.localkey import effective_public_key
from .retrieval.embedders import CloudEmbedder, Embedder, HashingEmbedder, OllamaEmbedder, SentenceTransformerEmbedder
from .retrieval.engine import RetrievalEngine
from .retrieval.rerankers import CloudReranker, CrossEncoderReranker, LexicalReranker, Reranker
from .store.crypto import KeyStore
from .store.lawpack import LawPack, PackError
from .store.signing import PackTrust, verify_pack
from .store.userdb import UserDB


@dataclass
class AppContext:
    settings: Settings
    keys: KeyStore
    db: UserDB
    gateway: Gateway
    pseudo: Pseudonymiser
    api_token: str
    pack: LawPack | None = None
    pack_trust: PackTrust | None = None
    pack_error: str | None = None
    calcs: CalculatorService | None = None
    engine: RetrievalEngine | None = None
    # test / embedding-app overrides
    llm_override: LLMProvider | None = None
    checker_override: ClaimChecker | None = None
    embedder_override: Embedder | None = None
    today_fn: Callable[[], date] = date.today
    _local_embedder: Embedder | None = field(default=None, repr=False)
    _local_reranker: Reranker | None = field(default=None, repr=False)
    reranker_error: str | None = field(default=None, repr=False)
    progress: dict = field(default_factory=dict, repr=False)  # live steps per query id (pipeline/progress.py)

    # ---- mode & user settings --------------------------------------------------------------------------
    def user_settings(self) -> dict[str, Any]:
        return self.db.get_settings()

    @property
    def mode(self) -> str:
        m = self.user_settings().get("mode") or self.settings.default_mode
        return "hybrid" if m == "cloud_assisted" else m  # cloud-assisted mode is disabled: an older saved choice runs as hybrid

    # ---- pack ------------------------------------------------------------------------------------------------
    def pack_usable(self) -> bool:
        if self.pack is None:
            return False
        return bool(self.pack_trust and (self.pack_trust.ok or (self.settings.allow_unsigned_pack and self.pack_trust.state in ("unsigned", "no_public_key"))))

    def load_pack(self, path: Path | None = None) -> None:
        path = path or self.settings.resolved_lawpack_path()
        self.pack = self.pack_trust = self.calcs = self.engine = None
        self._local_embedder = None  # the pack decides which embedder is needed (see embedder())
        self.pack_error = None
        if not path.exists():
            self.pack_error = f"no law pack at {path}"
            return
        self.pack_trust = verify_pack(path, effective_public_key(self.settings))
        try:
            self.pack = LawPack(path)
        except (PackError, Exception) as e:  # noqa: BLE001
            self.pack_error = f"law pack could not be opened: {e}"
            return
        if not self.pack_usable():
            self.pack_error = f"law pack is not trusted ({self.pack_trust.state}: {self.pack_trust.detail})"
        self.calcs = CalculatorService(self.pack)
        self.engine = RetrievalEngine(self.pack, self.settings, self.embedder, self.reranker)

    def pack_age_days(self) -> int | None:
        if not self.pack or not self.pack.built_at:
            return None
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(self.pack.built_at)).days
        except ValueError:
            return None

    # ---- providers by mode -----------------------------------------------------------------------------------------
    def _key(self, name: str):
        return lambda: self.keys.get_secret(name)

    def embedder(self) -> Embedder | None:
        if self.embedder_override is not None:
            return self.embedder_override
        s = self.settings
        if self.mode == "cloud_assisted" and s.embedder_cloud_url and s.embedder_cloud_model:
            return CloudEmbedder(s.embedder_id, s.embedder_cloud_model, s.embedder_cloud_url, self.gateway, self._key(s.embedder_cloud_secret))
        if self._local_embedder is None:
            auto = self._embedder_of_pack()
            if auto is not None:
                self._local_embedder = auto
            elif s.embedder_local_kind == "hash":
                self._local_embedder = HashingEmbedder(s.embedder_id)
            elif s.embedder_local_kind == "ollama":
                self._local_embedder = OllamaEmbedder(s.embedder_id, s.embedder_local_model, s.embedder_local_url)
            else:
                self._local_embedder = SentenceTransformerEmbedder(s.embedder_id, s.embedder_local_model)
        return self._local_embedder

    def _embedder_of_pack(self) -> Embedder | None:
        """Nothing configured and the pack holds real (non-hash) vectors: embed questions with the pack's own model, no settings needed."""
        s = self.settings
        if s.embedder_local_kind != "hash" or s.embedder_id != "hash-ngram-v1" or not self.pack:
            return None
        try:
            real = [e for e in self.pack.embedders().values() if not str(e["embedder_id"]).startswith("hash")]
        except Exception:  # noqa: BLE001
            return None
        if len(real) != 1:
            return None
        e = real[0]
        d = s.resolved_embed_model_dir(e["model"])
        return SentenceTransformerEmbedder(e["embedder_id"], str(d) if (d / "config.json").exists() else e["model"])

    def reranker(self) -> Reranker | None:
        s = self.settings
        if self.mode == "cloud_assisted" and s.reranker_cloud_url and s.reranker_cloud_model:
            return CloudReranker(s.reranker_cloud_model, s.reranker_cloud_url, self.gateway, self._key(s.reranker_cloud_secret))
        if self._local_reranker is None:
            if s.reranker_local_kind == "cross_encoder":
                try:
                    self._local_reranker = CrossEncoderReranker(s.resolved_reranker_model(), s.reranker_max_length, s.reranker_trust_remote_code, s.reranker_batch_size)
                    self.reranker_error = None
                except Exception as e:  # not installed / no internet for the first download / out of memory: keep working with the lexical one
                    self.reranker_error = f"{e.__class__.__name__}: {str(e)[:200]}"
                    self._local_reranker = LexicalReranker()
            else:
                self._local_reranker = LexicalReranker()
        return self._local_reranker

    # ---- providers chosen in the app (Settings > API keys) -------------------------------------------------------------
    PRESET_BASE = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com"}
    LOCAL_BASE = "http://127.0.0.1:11434/v1"   # Ollama; LM Studio is http://127.0.0.1:1234/v1

    def provider_secret_name(self, pid: str) -> str:
        return f"llm_p_{pid}"

    def _provider_from_settings(self, pid: str | None) -> LLMProvider | None:
        if not pid:
            return None
        cfg = (self.user_settings().get("llm_providers") or {}).get(pid)
        if not cfg or not cfg.get("model"):
            return None
        key = self._key(self.provider_secret_name(pid))
        kind, base = cfg.get("kind"), (cfg.get("base_url") or self.PRESET_BASE.get(cfg.get("kind", ""), "")).rstrip("/")
        if kind == "anthropic":
            return AnthropicProvider(self.gateway, cfg["model"], key, base or None, self.settings.cloud_timeout_s)
        if kind == "local":
            base = base or self.LOCAL_BASE
        if not base:
            return None
        # a model on this computer can take minutes for a long answer on an ordinary CPU
        prov = OpenAICompatProvider(self.gateway, cfg["model"], key, base, 900.0 if kind == "local" else self.settings.cloud_timeout_s)
        prov.name = {"openai": "openai", "local": "local"}.get(kind, "openai_compat")
        return prov

    def is_local_provider(self, pid: str | None) -> bool:
        cfg = (self.user_settings().get("llm_providers") or {}).get(pid or "")
        return bool(cfg) and cfg.get("kind") == "local"

    def offline_provider_id(self) -> str | None:
        """The local model used in Offline mode: the one chosen for it, else the active provider if it is local."""
        st = self.user_settings()
        for pid in (st.get("llm_offline"), st.get("llm_active")):
            if pid and self.is_local_provider(pid):
                return pid
        return None

    def llm(self) -> LLMProvider | None:
        if self.llm_override is not None:
            return self.llm_override if self.mode != "offline" else None
        if self.mode == "offline":   # only a model on this computer, never a cloud one
            return self._provider_from_settings(self.offline_provider_id())
        chosen = self._provider_from_settings(self.user_settings().get("llm_active"))
        if chosen is not None:
            return chosen
        s = self.settings
        if self.mode == "offline" or s.llm_provider == "none" or not s.llm_model:
            return None
        if s.llm_provider == "anthropic":
            return AnthropicProvider(self.gateway, s.llm_model, self._key(s.llm_secret), s.llm_base_url, s.cloud_timeout_s)
        if not s.llm_base_url:
            return None
        return OpenAICompatProvider(self.gateway, s.llm_model, self._key(s.llm_secret), s.llm_base_url, s.cloud_timeout_s)

    def claim_checker(self) -> ClaimChecker:
        if self.checker_override is not None:
            return self.checker_override
        s = self.settings
        second = self._provider_from_settings(self.user_settings().get("llm_checker"))
        if second is not None and self.mode != "offline":
            return LLMClaimChecker(second)
        if self.mode == "offline" or s.claim_check_provider == "local" or not s.claim_check_model:
            return LexicalChecker()
        prov: LLMProvider | None = None
        if s.claim_check_provider == "anthropic":
            prov = AnthropicProvider(self.gateway, s.claim_check_model, self._key(s.claim_check_secret), s.claim_check_base_url, s.cloud_timeout_s)
        elif s.claim_check_base_url:
            prov = OpenAICompatProvider(self.gateway, s.claim_check_model, self._key(s.claim_check_secret), s.claim_check_base_url, s.cloud_timeout_s)
        return LLMClaimChecker(prov) if prov else LexicalChecker()

    def close(self) -> None:
        if self.pack:
            self.pack.close()
        self.db.close()


def build_context(settings: Settings, transport: httpx.BaseTransport | None = None) -> AppContext:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    keys = KeyStore(settings.data_dir)
    db = UserDB(settings.data_dir / "user.db", keys)
    token = settings.api_token
    token_file = settings.data_dir / "api_token"
    if not token:
        if token_file.exists():
            token = token_file.read_text().strip()
        else:
            token = secrets.token_urlsafe(32)
            token_file.write_text(token)
            token_file.chmod(0o600)
    ctx_ref: dict[str, AppContext] = {}
    guard = OutboundGuard(db)
    gateway = Gateway(db, guard, lambda: ctx_ref["ctx"].mode, settings.cloud_timeout_s, transport)
    ctx = AppContext(settings, keys, db, gateway, Pseudonymiser(db, ner=NerDetector(settings.ner_model, settings.ner_enabled, settings.ner_min_score, tuple(settings.ner_kinds))), token)
    ctx_ref["ctx"] = ctx
    ctx.load_pack()
    db.purge_expired()
    db.purge_old_traces(settings.trace_retention_days)
    return ctx


def install_pack(ctx: AppContext, new_db: Path, new_sig: Path | None) -> dict[str, Any]:
    """Verify a downloaded / imported pack, swap it in atomically, keep the previous one for rollback + change notes."""
    dest = ctx.settings.resolved_lawpack_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    trust = verify_pack(new_db, effective_public_key(ctx.settings), new_sig)
    if not trust.ok and not (ctx.settings.allow_unsigned_pack and trust.state in ("unsigned", "no_public_key")):
        raise PackError(f"pack rejected: {trust.state} {trust.detail}")
    LawPack(new_db).close()  # opens and reads meta: catches corruption
    prev = dest.with_name("previous.db")
    if dest.exists():
        shutil.copy2(dest, prev)
        sig = dest.with_suffix(dest.suffix + ".sig")
        if sig.exists():
            shutil.copy2(sig, prev.with_suffix(".db.sig"))
    shutil.copy2(new_db, dest)
    if new_sig and new_sig.exists():
        shutil.copy2(new_sig, dest.with_suffix(dest.suffix + ".sig"))
    ctx.load_pack(dest)
    return {"installed": True, "pack_version": ctx.pack.version if ctx.pack else None, "trust": trust.state}
