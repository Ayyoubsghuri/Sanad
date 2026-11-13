import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { tr } from "../i18n";
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  FileLock2,
  FilePlus,
  KeyRound,
  Lock,
  LockOpen,
  Plus,
  Search,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { AttachmentItem, VaultItem } from "../types/agent";
import {
  changePassphrase,
  clearVaultMeta,
  createVault,
  decryptItem,
  decryptLegacy,
  encryptItem,
  isLegacyItem,
  loadAutoLockMinutes,
  loadVaultMeta,
  MIN_PASSPHRASE_LENGTH,
  passphraseProblem,
  saveAutoLockMinutes,
  saveVaultMeta,
  unlockVault,
  VAULT_ITERATIONS,
  type VaultMeta,
} from "../utils/cryptoVault";

interface EncryptedVaultModalProps {
  isOpen: boolean;
  onClose: () => void;
  vaultItems: VaultItem[];
  onUpdateVaultItems: (items: VaultItem[]) => void;
  onAttachVaultItemToPrompt: (attachment: AttachmentItem) => void;
}

type Category = VaultItem["category"];
const categories = (): { id: Category; label: string; hint: string }[] => [
  { id: "dossier", label: tr("Client dossier"), hint: tr("Facts, timeline, correspondence for a matter") },
  { id: "contract", label: tr("Contract"), hint: tr("Lease, employment contract, deed, agreement") },
  { id: "identity", label: tr("ID / identity document"), hint: tr("CIN, passport, family book, power of attorney") },
  { id: "notes", label: tr("Private notes"), hint: tr("Your own notes and strategy") },
];
const LEGACY_CATEGORY: Record<string, Category> = { dossier: "dossier", contract: "contract", identity: "identity", notes: "notes" };
const AUTOLOCK_CHOICES = [1, 5, 15, 30];

const inputStyle = (bad?: boolean): React.CSSProperties => ({
  backgroundColor: "var(--bg-canvas)",
  borderColor: bad ? "#EF4444" : "var(--border-strong)",
  color: "var(--text-primary)",
});
const primaryBtn: React.CSSProperties = { backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" };

export const EncryptedVaultModal: React.FC<EncryptedVaultModalProps> = ({
  isOpen,
  onClose,
  vaultItems,
  onUpdateVaultItems,
  onAttachVaultItemToPrompt,
}) => {
  const CATEGORIES = categories();
  const [meta, setMeta] = useState<VaultMeta | null>(() => loadVaultMeta());
  const [key, setKey] = useState<CryptoKey | null>(null); // in memory only; non-extractable
  const isUnlocked = key !== null;
  const hasLegacy = !meta && vaultItems.length > 0;
  const mode: "setup" | "legacy" | "locked" | "unlocked" = isUnlocked ? "unlocked" : meta ? "locked" : hasLegacy ? "legacy" : "setup";

  // forms
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [oldPass, setOldPass] = useState("");
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [confirmWipe, setConfirmWipe] = useState(false);

  // dashboard
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<"all" | Category>("all");
  const [decryptedContents, setDecryptedContents] = useState<Record<string, string>>({});
  const [revealedIds, setRevealedIds] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [attachedId, setAttachedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState<Category>("dossier");
  const [newContent, setNewContent] = useState("");
  const [newSnippet, setNewSnippet] = useState("");
  const [curPass, setCurPass] = useState("");

  // auto-lock
  const [autoLockMin, setAutoLockMin] = useState<number>(() => loadAutoLockMinutes());
  const lastActivity = useRef<number>(Date.now());
  const touch = useCallback(() => {
    lastActivity.current = Date.now();
  }, []);

  const lock = useCallback((message = "") => {
    setKey(null);
    setDecryptedContents({});
    setRevealedIds({});
    setShowAdd(false);
    setShowSettings(false);
    setPass("");
    setPass2("");
    setOldPass("");
    setCurPass("");
    setNotice(message);
  }, []);

  useEffect(() => {
    if (!isUnlocked) return;
    lastActivity.current = Date.now();
    const id = window.setInterval(() => {
      if (Date.now() - lastActivity.current > autoLockMin * 60_000) {
        lock(tr("Locked automatically after {0} minute{1} without activity.", [autoLockMin, autoLockMin > 1 ? "s" : ""]));
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [isUnlocked, autoLockMin, lock]);

  // ------------------------------------------------------------------------- create / unlock / upgrade
  const validateNew = (): string | null => {
    const problem = passphraseProblem(pass);
    if (problem) return problem;
    if (pass !== pass2) return tr("The two passphrases do not match.");
    return null;
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validateNew();
    if (err) return setFormError(err);
    setBusy(true);
    setFormError("");
    try {
      const { meta: m, key: k } = await createVault(pass);
      saveVaultMeta(m);
      setMeta(m);
      setKey(k);
      setPass("");
      setPass2("");
      setNotice("");
    } catch {
      setFormError(tr("Could not create the vault (Web Crypto is unavailable in this browser context)."));
    } finally {
      setBusy(false);
    }
  };

  const handleUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!meta) return;
    if (!pass) return setFormError(tr("Enter your passphrase."));
    setBusy(true);
    setFormError("");
    try {
      setKey(await unlockVault(pass, meta));
      setPass("");
      setNotice("");
    } catch {
      setFormError(tr("Wrong passphrase."));
    } finally {
      setBusy(false);
    }
  };

  const handleUpgradeLegacy = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validateNew();
    if (err) return setFormError(err);
    if (!oldPass) return setFormError(tr("Enter the passphrase the old vault was created with."));
    setBusy(true);
    setFormError("");
    try {
      const plains: string[] = [];
      for (const it of vaultItems) {
        if (!isLegacyItem(it)) throw new Error(tr("unexpected item format"));
        try {
          plains.push(await decryptLegacy(oldPass, it.encryptedData));
        } catch {
          throw new Error(tr("The old passphrase did not open every item."));
        }
      }
      const { meta: m, key: k } = await createVault(pass);
      const next: VaultItem[] = [];
      for (let i = 0; i < vaultItems.length; i++) {
        const it = vaultItems[i];
        next.push({
          ...it,
          category: LEGACY_CATEGORY[it.category as string] ?? "notes",
          encryptedData: await encryptItem(k, plains[i]),
        });
      }
      saveVaultMeta(m);
      onUpdateVaultItems(next);
      setMeta(m);
      setKey(k);
      setPass("");
      setPass2("");
      setOldPass("");
    } catch (ex) {
      setFormError((ex as Error).message || tr("Upgrade failed."));
    } finally {
      setBusy(false);
    }
  };

  const handleStartFresh = () => {
    if (!confirmWipe) return setConfirmWipe(true);
    onUpdateVaultItems([]);
    clearVaultMeta();
    setMeta(null);
    setConfirmWipe(false);
    setFormError("");
  };

  // ------------------------------------------------------------------------- items
  const decryptOne = async (item: VaultItem): Promise<string> => {
    if (!key) throw new Error("locked");
    const cached = decryptedContents[item.id];
    if (cached !== undefined) return cached;
    const plain = await decryptItem(key, item.encryptedData);
    setDecryptedContents((prev) => ({ ...prev, [item.id]: plain }));
    return plain;
  };

  const handleToggleReveal = async (item: VaultItem) => {
    touch();
    if (revealedIds[item.id]) return setRevealedIds((p) => ({ ...p, [item.id]: false }));
    try {
      await decryptOne(item);
      setRevealedIds((p) => ({ ...p, [item.id]: true }));
    } catch (ex) {
      setNotice((ex as Error).message);
    }
  };

  const handleCopy = async (item: VaultItem) => {
    touch();
    try {
      await navigator.clipboard.writeText(await decryptOne(item));
      setCopiedId(item.id);
      setTimeout(() => setCopiedId(null), 1800);
    } catch {
      /* clipboard blocked */
    }
  };

  const handleAttach = async (item: VaultItem) => {
    touch();
    try {
      const plain = await decryptOne(item);
      onAttachVaultItemToPrompt({
        id: `vault-att-${Date.now()}`,
        name: `[Vault] ${item.title}.txt`,
        mimeType: "text/plain",
        sizeBytes: new Blob([plain]).size,
        textContent: plain,
        source: "vault",
      });
      setAttachedId(item.id);
      setTimeout(() => setAttachedId(null), 2000);
    } catch (ex) {
      setNotice((ex as Error).message);
    }
  };

  const handleDelete = (id: string) => {
    touch();
    onUpdateVaultItems(vaultItems.filter((i) => i.id !== id));
    setDecryptedContents((p) => {
      const { [id]: _drop, ...rest } = p;
      return rest;
    });
  };

  const handleSaveNew = async (e: React.FormEvent) => {
    e.preventDefault();
    touch();
    if (!key || !newTitle.trim() || !newContent.trim()) return;
    setBusy(true);
    try {
      const item: VaultItem = {
        id: `vault-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        title: newTitle.trim(),
        category: newCategory,
        encryptedData: await encryptItem(key, newContent.trim()),
        previewSnippet: newSnippet.trim() || tr("(no preview: encrypted)"),
        updatedAt: new Date().toISOString(),
        isCustom: true,
      };
      onUpdateVaultItems([item, ...vaultItems]);
      setDecryptedContents((p) => ({ ...p, [item.id]: newContent.trim() }));
      setNewTitle("");
      setNewContent("");
      setNewSnippet("");
      setShowAdd(false);
    } finally {
      setBusy(false);
    }
  };

  const handleChangePassphrase = async (e: React.FormEvent) => {
    e.preventDefault();
    touch();
    if (!meta || !key) return;
    const err = validateNew();
    if (err) return setFormError(err);
    setBusy(true);
    setFormError("");
    try {
      await unlockVault(curPass, meta); // re-authenticate with the CURRENT passphrase
    } catch {
      setBusy(false);
      return setFormError(tr("Current passphrase is wrong."));
    }
    try {
      const res = await changePassphrase(key, vaultItems, pass);
      saveVaultMeta(res.meta);
      onUpdateVaultItems(res.items);
      setMeta(res.meta);
      setKey(res.key);
      setDecryptedContents({});
      setRevealedIds({});
      setCurPass("");
      setPass("");
      setPass2("");
      setShowSettings(false);
      setNotice(tr("Passphrase changed. {0} item(s) re-encrypted.", [res.items.length]));
    } catch (ex) {
      setFormError((ex as Error).message || tr("Could not change the passphrase. Nothing was modified."));
    } finally {
      setBusy(false);
    }
  };

  const filteredItems = useMemo(
    () =>
      vaultItems.filter((item) => {
        if (selectedCategory !== "all" && item.category !== selectedCategory) return false;
        if (!searchQuery.trim()) return true;
        const q = searchQuery.toLowerCase();
        return item.title.toLowerCase().includes(q) || item.previewSnippet.toLowerCase().includes(q);
      }),
    [vaultItems, selectedCategory, searchQuery]
  );

  if (!isOpen) return null;

  const labelOf = (c: string) => CATEGORIES.find((x) => x.id === c)?.label ?? c;
  const newPassFields = (
    <>
      <input
        type="password"
        value={pass}
        onChange={(e) => setPass(e.target.value)}
        placeholder={tr("New passphrase (min {0} characters)", [MIN_PASSPHRASE_LENGTH])}
        autoComplete="new-password"
        className="w-full px-4 py-2.5 rounded-xl border text-sm outline-none text-center font-code"
        style={inputStyle(!!formError)}
      />
      <input
        type="password"
        value={pass2}
        onChange={(e) => setPass2(e.target.value)}
        placeholder={tr("Repeat the passphrase")}
        autoComplete="new-password"
        className="w-full px-4 py-2.5 rounded-xl border text-sm outline-none text-center font-code"
        style={inputStyle(!!formError)}
      />
    </>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5" onMouseMove={touch} onKeyDown={touch} onClick={touch}>
      <div className="fixed inset-0 bg-black/65 backdrop-blur-xs transition-opacity" onClick={onClose} />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="vault-title"
        className="relative w-full max-w-3xl rounded-3xl border shadow-2xl overflow-hidden flex flex-col max-h-[90vh] z-10 sanad-liquid-modal"
        style={{ backgroundColor: "var(--bg-surface)", borderColor: "var(--border-strong)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0" style={{ borderColor: "var(--border-subtle)" }}>
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{ backgroundColor: isUnlocked ? "rgba(16,185,129,0.12)" : "var(--bg-muted)", color: isUnlocked ? "#10B981" : "var(--accent-warm)" }}
            >
              {isUnlocked ? <LockOpen className="w-4 h-4" /> : <Lock className="w-4 h-4" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="vault-title" className="font-editorial text-base sm:text-lg font-semibold leading-tight" style={{ color: "var(--text-heading)" }}>
                  {tr("Encrypted Confidential Vault")}
                </h2>
                <span
                  className="px-2 py-0.5 rounded text-[10px] font-code font-bold tracking-wider uppercase"
                  style={{ backgroundColor: isUnlocked ? "rgba(16,185,129,0.15)" : "var(--bg-muted)", color: isUnlocked ? "#10B981" : "var(--text-muted)" }}
                >
                  {isUnlocked ? "Unlocked" : mode === "setup" ? tr("Not set up") : "Locked"}
                </span>
              </div>
              <div className="text-xs font-code mt-0.5" style={{ color: "var(--text-muted)" }}>
                {tr("Stored only in this browser, encrypted with your own passphrase")}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isUnlocked && (
              <>
                <button
                  type="button"
                  onClick={() => { setShowSettings((v) => !v); setFormError(""); }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:opacity-85 cursor-pointer"
                  style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                >
                  <Settings2 className="w-3.5 h-3.5" />
                  <span>{tr("Security")}</span>
                </button>
                <button
                  type="button"
                  onClick={() => lock("")}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:opacity-85 cursor-pointer"
                  style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
                >
                  <Lock className="w-3.5 h-3.5" />
                  <span>{tr("Lock now")}</span>
                </button>
              </>
            )}
            <button type="button" onClick={onClose} aria-label={tr("Close vault")} className="p-1.5 rounded-lg opacity-60 hover:opacity-100 cursor-pointer" style={{ color: "var(--text-muted)" }}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {notice && (
          <div className="px-6 py-2 text-xs border-b" style={{ borderColor: "var(--border-subtle)", color: "var(--accent-warm)", backgroundColor: "var(--bg-canvas)" }}>
            {notice}
          </div>
        )}

        {/* ------------------------------------------------------------ SETUP (first run) */}
        {mode === "setup" && (
          <div className="p-8 sm:p-10 flex flex-col items-center text-center max-w-md mx-auto space-y-5 overflow-y-auto">
            <div className="w-16 h-16 rounded-3xl flex items-center justify-center" style={{ backgroundColor: "var(--bg-muted)", color: "var(--accent-primary)" }}>
              <KeyRound className="w-8 h-8 stroke-[1.7]" />
            </div>
            <div className="space-y-1.5">
              <h3 className="font-editorial text-lg font-medium" style={{ color: "var(--text-heading)" }}>{tr("Create your vault passphrase")}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {tr("The vault keeps client dossiers, contracts, ID documents and private notes encrypted in this browser (AES-256-GCM). Your passphrase is never stored and cannot be recovered: if you forget it, the content is lost.")}
              </p>
            </div>
            <form onSubmit={handleCreate} className="w-full space-y-3">
              {newPassFields}
              {formError && <div className="text-xs text-red-500 font-medium">{formError}</div>}
              <button type="submit" disabled={busy} className="w-full py-2.5 rounded-xl font-semibold text-xs hover:opacity-90 shadow-sm cursor-pointer" style={primaryBtn}>
                {busy ? tr("Creating…") : tr("Create encrypted vault")}
              </button>
            </form>
            <div className="text-[11px] font-code" style={{ color: "var(--text-muted)" }}>
              {tr("PBKDF2-SHA256 (")}{VAULT_ITERATIONS.toLocaleString()} {tr("iterations) · no server involved")}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------ LEGACY (old demo vault) */}
        {mode === "legacy" && (
          <div className="p-8 sm:p-10 flex flex-col items-center text-center max-w-md mx-auto space-y-5 overflow-y-auto">
            <div className="space-y-1.5">
              <h3 className="font-editorial text-lg font-medium" style={{ color: "var(--text-heading)" }}>{tr("Upgrade your existing vault")}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {tr("This browser holds")} {vaultItems.length} {tr("item(s) from the old vault, which used a shared demo passphrase and weaker key derivation. Enter the old passphrase once and choose your own: every item is re-encrypted. Or delete them and start fresh.")}
              </p>
            </div>
            <form onSubmit={handleUpgradeLegacy} className="w-full space-y-3">
              <input
                type="password"
                value={oldPass}
                onChange={(e) => setOldPass(e.target.value)}
                placeholder={tr("Old vault passphrase")}
                className="w-full px-4 py-2.5 rounded-xl border text-sm outline-none text-center font-code"
                style={inputStyle(!!formError)}
              />
              {newPassFields}
              {formError && <div className="text-xs text-red-500 font-medium">{formError}</div>}
              <button type="submit" disabled={busy} className="w-full py-2.5 rounded-xl font-semibold text-xs hover:opacity-90 shadow-sm cursor-pointer" style={primaryBtn}>
                {busy ? tr("Re-encrypting…") : tr("Upgrade and re-encrypt")}
              </button>
            </form>
            <button type="button" onClick={handleStartFresh} className="text-xs underline cursor-pointer" style={{ color: confirmWipe ? "#EF4444" : "var(--text-muted)" }}>
              {confirmWipe ? tr("Click again to permanently delete the old items") : tr("Delete old items and start fresh")}
            </button>
          </div>
        )}

        {/* ------------------------------------------------------------ LOCKED */}
        {mode === "locked" && (
          <div className="p-8 sm:p-12 flex flex-col items-center text-center max-w-md mx-auto space-y-6 overflow-y-auto">
            <div className="w-16 h-16 rounded-3xl flex items-center justify-center shadow-inner" style={{ backgroundColor: "var(--bg-muted)", color: "var(--accent-primary)" }}>
              <KeyRound className="w-8 h-8 stroke-[1.7]" />
            </div>
            <div className="space-y-1.5">
              <h3 className="font-editorial text-lg font-medium" style={{ color: "var(--text-heading)" }}>{tr("Unlock your vault")}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {vaultItems.length} {tr("encrypted item(s). Enter your passphrase to read them.")}
              </p>
            </div>
            <form onSubmit={handleUnlock} className="w-full space-y-3">
              <input
                type="password"
                value={pass}
                onChange={(e) => setPass(e.target.value)}
                placeholder="Passphrase"
                autoComplete="current-password"
                autoFocus
                className="w-full px-4 py-2.5 rounded-xl border text-sm outline-none text-center font-code"
                style={inputStyle(!!formError)}
              />
              {formError && <div className="text-xs text-red-500 font-medium">{formError}</div>}
              <button type="submit" disabled={busy} className="w-full py-2.5 rounded-xl font-semibold text-xs hover:opacity-90 shadow-sm cursor-pointer" style={primaryBtn}>
                {busy ? tr("Deriving key…") : "Unlock"}
              </button>
            </form>
            <div className="text-[11px] font-code" style={{ color: "var(--text-muted)" }}>
              {tr("PBKDF2-SHA256 (")}{meta?.iter.toLocaleString()} {tr("iterations) · AES-GCM 256")}
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------ UNLOCKED */}
        {mode === "unlocked" && (
          <div className="flex-1 overflow-y-auto flex flex-col">
            <div className="p-4 border-b space-y-3" style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)" }}>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                <div className="relative flex-1 max-w-sm">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 opacity-50" style={{ color: "var(--text-muted)" }} />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={tr("Search titles and previews…")}
                    className="w-full pl-9 pr-3 py-1.5 rounded-xl border text-xs bg-transparent outline-none"
                    style={{ borderColor: "var(--border-subtle)" }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setShowAdd((v) => !v)}
                  className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold cursor-pointer shadow-xs hover:opacity-90 shrink-0"
                  style={primaryBtn}
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{tr("New confidential item")}</span>
                </button>
              </div>
              <div className="flex items-center gap-1.5 overflow-x-auto text-xs">
                {(["all", ...CATEGORIES.map((c) => c.id)] as const).map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3 py-1 rounded-lg whitespace-nowrap transition-colors cursor-pointer text-xs ${selectedCategory === cat ? "font-semibold border shadow-xs" : "opacity-70 hover:opacity-100"}`}
                    style={{
                      backgroundColor: selectedCategory === cat ? "var(--bg-surface)" : "transparent",
                      borderColor: selectedCategory === cat ? "var(--border-strong)" : "transparent",
                      color: selectedCategory === cat ? "var(--text-heading)" : "var(--text-muted)",
                    }}
                  >
                    {cat === "all" ? tr("All items") : labelOf(cat)}
                  </button>
                ))}
              </div>
            </div>

            {/* Security settings: change passphrase + auto-lock */}
            {showSettings && (
              <form onSubmit={handleChangePassphrase} className="p-5 border-b space-y-3" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-strong)" }}>
                <div className="font-semibold text-xs" style={{ color: "var(--text-heading)" }}>{tr("Security")}</div>
                <div className="flex items-center gap-2 text-xs">
                  <label htmlFor="autolock" style={{ color: "var(--text-muted)" }}>{tr("Lock automatically after")}</label>
                  <select
                    id="autolock"
                    value={autoLockMin}
                    onChange={(e) => { const n = Number(e.target.value); setAutoLockMin(n); saveAutoLockMinutes(n); }}
                    className="px-2 py-1 rounded-lg border bg-transparent text-xs"
                    style={{ borderColor: "var(--border-subtle)" }}
                  >
                    {AUTOLOCK_CHOICES.map((n) => <option key={n} value={n}>{n} {tr("min")}</option>)}
                  </select>
                  <span style={{ color: "var(--text-muted)" }}>{tr("without activity")}</span>
                </div>
                <div className="text-[11px] font-medium pt-1" style={{ color: "var(--text-heading)" }}>{tr("Change passphrase (re-encrypts all")} {vaultItems.length} {tr("item(s))")}</div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <input type="password" value={curPass} onChange={(e) => setCurPass(e.target.value)} placeholder={tr("Current passphrase")} autoComplete="current-password" className="px-3 py-2 rounded-xl border bg-transparent text-xs font-code" style={{ borderColor: "var(--border-subtle)" }} />
                  <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder={tr("New passphrase")} autoComplete="new-password" className="px-3 py-2 rounded-xl border bg-transparent text-xs font-code" style={{ borderColor: "var(--border-subtle)" }} />
                  <input type="password" value={pass2} onChange={(e) => setPass2(e.target.value)} placeholder={tr("Repeat new passphrase")} autoComplete="new-password" className="px-3 py-2 rounded-xl border bg-transparent text-xs font-code" style={{ borderColor: "var(--border-subtle)" }} />
                </div>
                {formError && <div className="text-xs text-red-500 font-medium">{formError}</div>}
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setShowSettings(false)} className="px-3 py-1.5 rounded-xl text-xs border cursor-pointer hover:opacity-80" style={{ borderColor: "var(--border-subtle)" }}>{tr("Close")}</button>
                  <button type="submit" disabled={busy} className="px-4 py-1.5 rounded-xl text-xs font-semibold cursor-pointer hover:opacity-90" style={primaryBtn}>{busy ? tr("Re-encrypting…") : tr("Change passphrase")}</button>
                </div>
              </form>
            )}

            {showAdd && (
              <form onSubmit={handleSaveNew} className="p-5 border-b space-y-3.5" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-strong)" }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileLock2 className="w-4 h-4 text-[var(--accent-warm)]" />
                    <span className="font-semibold text-xs" style={{ color: "var(--text-heading)" }}>{tr("Encrypt a new item")}</span>
                  </div>
                  <button type="button" onClick={() => setShowAdd(false)} className="p-1 rounded opacity-60 hover:opacity-100 cursor-pointer"><X className="w-4 h-4" /></button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="sm:col-span-2">
                    <label className="text-[11px] font-medium opacity-75 mb-1 block">{tr("Title")}</label>
                    <input type="text" required value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder={tr("e.g. Unpaid wages: client file, Oct 2026")} className="w-full px-3 py-2 rounded-xl border bg-transparent text-xs" style={{ borderColor: "var(--border-subtle)" }} />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium opacity-75 mb-1 block">{tr("Category")}</label>
                    <select value={newCategory} onChange={(e) => setNewCategory(e.target.value as Category)} className="w-full px-3 py-2 rounded-xl border bg-transparent text-xs" style={{ borderColor: "var(--border-subtle)" }}>
                      {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label className="text-[11px] font-medium opacity-75 mb-1 block">{tr("Content (encrypted before it is saved)")}</label>
                  <textarea rows={5} required value={newContent} onChange={(e) => setNewContent(e.target.value)} placeholder={CATEGORIES.find((c) => c.id === newCategory)?.hint} className="w-full p-3 rounded-xl border bg-transparent font-code text-xs resize-none" style={{ borderColor: "var(--border-subtle)" }} />
                </div>
                <div>
                  <label className="text-[11px] font-medium opacity-75 mb-1 block">{tr("Safe preview (shown while locked-down lists are visible: do not put names or numbers here)")}</label>
                  <input type="text" value={newSnippet} onChange={(e) => setNewSnippet(e.target.value)} placeholder={tr("e.g. Employment dispute, documents and timeline")} className="w-full px-3 py-2 rounded-xl border bg-transparent text-xs" style={{ borderColor: "var(--border-subtle)" }} />
                </div>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button type="button" onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded-xl text-xs border cursor-pointer hover:opacity-80" style={{ borderColor: "var(--border-subtle)" }}>{tr("Cancel")}</button>
                  <button type="submit" disabled={busy} className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-xs font-semibold cursor-pointer shadow-xs hover:opacity-90" style={primaryBtn}>
                    <Lock className="w-3.5 h-3.5" />
                    <span>{busy ? tr("Encrypting…") : tr("Encrypt & store")}</span>
                  </button>
                </div>
              </form>
            )}

            {/* Vault Items List */}
            <div className="flex-1 p-5 space-y-3">
              {filteredItems.length === 0 ? (
                <div
                  className="p-10 rounded-2xl border text-center text-xs space-y-2"
                  style={{
                    backgroundColor: "var(--bg-canvas)",
                    borderColor: "var(--border-subtle)",
                    color: "var(--text-muted)",
                  }}
                >
                  <Lock className="w-6 h-6 mx-auto opacity-40" />
                  <div>{tr("No items yet. Use “New confidential item” to add a dossier, contract or ID.")}</div>
                </div>
              ) : (
                filteredItems.map((item) => {
                  const isRevealed = revealedIds[item.id];
                  const decrypted = decryptedContents[item.id];

                  return (
                    <div
                      key={item.id}
                      className="p-4 rounded-2xl border space-y-3 transition-colors shadow-xs"
                      style={{
                        backgroundColor: "var(--bg-surface)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span
                              className="px-2 py-0.5 rounded text-[10px] font-code uppercase font-semibold tracking-wider"
                              style={{
                                backgroundColor: "var(--bg-muted)",
                                color: "var(--accent-warm)",
                              }}
                            >
                              {labelOf(item.category)}
                            </span>
                            <span
                              className="font-editorial text-sm font-semibold truncate"
                              style={{ color: "var(--text-heading)" }}
                            >
                              {item.title}
                            </span>
                          </div>

                          <p
                            className="text-xs leading-relaxed line-clamp-2"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {item.previewSnippet}
                          </p>
                        </div>

                        {/* Top card actions */}
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={() => handleToggleReveal(item)}
                            title={isRevealed ? tr("Hide Plaintext") : tr("Decrypt & Reveal")}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border text-xs font-medium cursor-pointer hover:opacity-85 transition-opacity"
                            style={{
                              backgroundColor: isRevealed
                                ? "var(--bg-card)"
                                : "var(--bg-canvas)",
                              borderColor: "var(--border-subtle)",
                              color: "var(--text-primary)",
                            }}
                          >
                            {isRevealed ? (
                              <>
                                <EyeOff className="w-3.5 h-3.5" />
                                <span>{tr("Hide")}</span>
                              </>
                            ) : (
                              <>
                                <Eye className="w-3.5 h-3.5" />
                                <span>{tr("Reveal")}</span>
                              </>
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleCopy(item)}
                            title={tr("Copy decrypted secret to clipboard")}
                            className="p-1.5 rounded-lg border hover:opacity-85 cursor-pointer"
                            style={{
                              backgroundColor: "var(--bg-canvas)",
                              borderColor: "var(--border-subtle)",
                              color: "var(--text-muted)",
                            }}
                          >
                            {copiedId === item.id ? (
                              <Check className="w-3.5 h-3.5 text-emerald-500" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleAttach(item)}
                            title={tr("Attach to the chat: the text is masked by the local backend before anything is sent")}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold cursor-pointer shadow-xs hover:opacity-90"
                            style={{
                              backgroundColor: "var(--accent-primary)",
                              color: "var(--accent-primary-fg)",
                            }}
                          >
                            {attachedId === item.id ? (
                              <>
                                <Check className="w-3.5 h-3.5" />
                                <span>{tr("Attached")}</span>
                              </>
                            ) : (
                              <>
                                <FilePlus className="w-3.5 h-3.5" />
                                <span>{tr("Attach to Chat")}</span>
                              </>
                            )}
                          </button>

                          {(
                            <button
                              type="button"
                              onClick={() => handleDelete(item.id)}
                              title={tr("Delete secret")}
                              className="p-1.5 rounded-lg opacity-40 hover:opacity-100 cursor-pointer"
                              style={{ color: "var(--text-muted)" }}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Decrypted Expanded Preview */}
                      {isRevealed && (
                        <div
                          className="p-3.5 rounded-xl border font-code text-xs leading-relaxed whitespace-pre-wrap select-text animate-in fade-in"
                          style={{
                            backgroundColor: "var(--bg-canvas)",
                            borderColor: "var(--border-subtle)",
                            color: "var(--text-primary)",
                          }}
                        >
                          {decrypted || tr("Decrypting payload...")}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-6 py-3 border-t flex items-center justify-between text-[11px] shrink-0 font-code" style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-muted)" }}>
          <span>{isUnlocked ? tr("Unlocked · auto-lock {0} min", [autoLockMin]) : tr("Encrypted at rest")}</span>
          <span>{tr("AES-GCM 256 · PBKDF2")} {(meta?.iter ?? VAULT_ITERATIONS).toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
};
