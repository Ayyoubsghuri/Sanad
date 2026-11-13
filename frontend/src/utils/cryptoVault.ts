/**
 * Client-side encrypted vault (Web Crypto: PBKDF2-SHA256 -> AES-GCM 256).
 *
 * Design (v2):
 *  - The user creates their OWN master passphrase on first use. There is no default or demo passphrase.
 *  - ONE vault key is derived at unlock (PBKDF2, 600k iterations, random vault salt) and kept in memory as a
 *    non-extractable CryptoKey. Items are encrypted with that key and a fresh random 12-byte IV each.
 *  - A small verification value ("check") is encrypted with the key so a wrong passphrase is detected even when the
 *    vault is empty, and it never depends on an item.
 *  - Changing the passphrase derives a new key (new salt) and re-encrypts every item.
 *  - Legacy v1 items (per-item salt, 100k iterations, demo passphrase) can only be read by decryptLegacy(), to migrate.
 */
import { VaultItem } from "../types/agent";

export const VAULT_ITERATIONS = 600_000;
export const MIN_PASSPHRASE_LENGTH = 10;
const LEGACY_ITERATIONS = 100_000;
const CHECK_PLAINTEXT = "sanad-vault-check-v2";
const META_KEY = "sanad_vault_meta_v2";
const AUTOLOCK_KEY = "sanad_vault_autolock_min";

export interface VaultMeta {
  v: 2;
  iter: number;
  salt: string; // base64, vault-wide
  check: { iv: string; ciphertext: string };
  createdAt: string;
  changedAt?: string;
}

interface ItemPackage {
  v: 2;
  iv: string;
  ciphertext: string;
}

// ---------------------------------------------------------------------------- helpers
const enc = new TextEncoder();
const dec = new TextDecoder();

function toB64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}
function fromB64(b64: string): Uint8Array<ArrayBuffer> {
  const s = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(s.length));
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

async function deriveKey(passphrase: string, salt: Uint8Array<ArrayBuffer>, iterations: number): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey("raw", enc.encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false, // non-extractable: the raw key bytes can never be read back by script
    ["encrypt", "decrypt"]
  );
}

async function sealWith(key: CryptoKey, plain: string): Promise<{ iv: string; ciphertext: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, enc.encode(plain));
  return { iv: toB64(iv), ciphertext: toB64(ct) };
}
async function openWith(key: CryptoKey, iv: string, ciphertext: string): Promise<string> {
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromB64(iv) }, key, fromB64(ciphertext));
  return dec.decode(pt);
}

// ---------------------------------------------------------------------------- passphrase quality
export function passphraseProblem(p: string): string | null {
  if (p.length < MIN_PASSPHRASE_LENGTH) return `Use at least ${MIN_PASSPHRASE_LENGTH} characters (a few random words works well).`;
  if (/^(.)\1+$/.test(p)) return "Do not repeat a single character.";
  if (["password123", "1234567890", "azertyuiop", "qwertyuiop"].includes(p.toLowerCase())) return "This passphrase is too common.";
  return null;
}

// ---------------------------------------------------------------------------- vault lifecycle
export async function createVault(passphrase: string): Promise<{ meta: VaultMeta; key: CryptoKey }> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const key = await deriveKey(passphrase, salt, VAULT_ITERATIONS);
  const meta: VaultMeta = {
    v: 2,
    iter: VAULT_ITERATIONS,
    salt: toB64(salt),
    check: await sealWith(key, CHECK_PLAINTEXT),
    createdAt: new Date().toISOString(),
  };
  return { meta, key };
}

/** Derives the key and verifies it against the stored check value. Throws on a wrong passphrase. */
export async function unlockVault(passphrase: string, meta: VaultMeta): Promise<CryptoKey> {
  const key = await deriveKey(passphrase, fromB64(meta.salt), meta.iter);
  try {
    const ok = await openWith(key, meta.check.iv, meta.check.ciphertext);
    if (ok !== CHECK_PLAINTEXT) throw new Error("bad check");
  } catch {
    throw new Error("Wrong passphrase.");
  }
  return key;
}

export async function encryptItem(key: CryptoKey, plain: string): Promise<string> {
  const { iv, ciphertext } = await sealWith(key, plain);
  const pkg: ItemPackage = { v: 2, iv, ciphertext };
  return JSON.stringify(pkg);
}

export async function decryptItem(key: CryptoKey, packed: string): Promise<string> {
  try {
    const pkg = JSON.parse(packed) as ItemPackage;
    if (pkg.v !== 2) throw new Error("unsupported version");
    return await openWith(key, pkg.iv, pkg.ciphertext);
  } catch {
    throw new Error("Could not decrypt this item (wrong key or corrupted data).");
  }
}

/** New passphrase: new salt + key, every item decrypted with the old key and re-encrypted with the new one. All-or-nothing. */
export async function changePassphrase(
  oldKey: CryptoKey,
  items: VaultItem[],
  newPassphrase: string
): Promise<{ meta: VaultMeta; key: CryptoKey; items: VaultItem[] }> {
  const plain = await Promise.all(items.map((i) => decryptItem(oldKey, i.encryptedData))); // throws before anything changes
  const { meta, key } = await createVault(newPassphrase);
  const next = await Promise.all(
    items.map(async (i, idx) => ({ ...i, encryptedData: await encryptItem(key, plain[idx]), updatedAt: new Date().toISOString() }))
  );
  return { meta: { ...meta, createdAt: meta.createdAt, changedAt: new Date().toISOString() }, key, items: next };
}

// ---------------------------------------------------------------------------- legacy (v1) migration
interface LegacyPackage {
  salt: string;
  iv: string;
  ciphertext: string;
}
export function isLegacyItem(i: VaultItem): boolean {
  try {
    const p = JSON.parse(i.encryptedData) as Partial<LegacyPackage & ItemPackage>;
    return !!p.salt && !p.v;
  } catch {
    return false;
  }
}
export async function decryptLegacy(passphrase: string, packed: string): Promise<string> {
  const p = JSON.parse(packed) as LegacyPackage;
  const key = await deriveKey(passphrase, fromB64(p.salt), LEGACY_ITERATIONS);
  return openWith(key, p.iv, p.ciphertext);
}

// ---------------------------------------------------------------------------- local persistence of the (non-secret) meta
export function loadVaultMeta(): VaultMeta | null {
  try {
    const raw = localStorage.getItem(META_KEY);
    if (!raw) return null;
    const m = JSON.parse(raw) as VaultMeta;
    return m && m.v === 2 && m.salt && m.check ? m : null;
  } catch {
    return null;
  }
}
export function saveVaultMeta(meta: VaultMeta): void {
  try {
    localStorage.setItem(META_KEY, JSON.stringify(meta));
  } catch {
    /* storage unavailable */
  }
}
export function clearVaultMeta(): void {
  try {
    localStorage.removeItem(META_KEY);
  } catch {
    /* ignore */
  }
}
export function loadAutoLockMinutes(): number {
  try {
    const n = Number(localStorage.getItem(AUTOLOCK_KEY));
    return [1, 5, 15, 30].includes(n) ? n : 5;
  } catch {
    return 5;
  }
}
export function saveAutoLockMinutes(n: number): void {
  try {
    localStorage.setItem(AUTOLOCK_KEY, String(n));
  } catch {
    /* ignore */
  }
}
