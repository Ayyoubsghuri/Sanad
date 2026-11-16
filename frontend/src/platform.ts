// Where the interface runs. In the Android app (mobile/android) the page is shown in a WebView and the "backend" is the
// app's own Java engine, reached through window.SanadNative (see mobile/android/.../Bridge.java). Desktop-only features
// (operating modes, Bulletin Officiel update, providers screen) are hidden there; "API keys" opens the phone's setup page.
interface SanadNative {
  openSetup?: () => void;
}

const native = (): SanadNative | undefined => (typeof window !== "undefined" ? (window as unknown as { SanadNative?: SanadNative }).SanadNative : undefined);

export const IS_ANDROID = !!native();

export function openAndroidSetup(): void {
  native()?.openSetup?.();
}

interface FileBridge {
  saveFile?: (name: string, mime: string, base64: string) => string;
  printHtml?: (title: string, html: string) => void;
}
const files = (): FileBridge | undefined =>
  typeof window !== "undefined" ? (window as unknown as { SanadNative?: FileBridge }).SanadNative : undefined;

const toBase64 = (blob: Blob) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).replace(/^data:[^,]*,/, ""));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });

const desktop = (): { save_file?: (name: string, b64: string) => Promise<string> } | undefined =>
  typeof window !== "undefined" ? (window as unknown as { pywebview?: { api?: { save_file?: (n: string, b: string) => Promise<string> } } }).pywebview?.api : undefined;

/** The Android app and the Windows window cannot download a file made in the page: it is handed to the app.
 *  Android: saved in Downloads/Sanad, then opened. Windows: the "Save as" dialog, then the folder is shown.
 *  Returns where it was saved, "" when the user cancelled, or null in a normal browser (the page downloads it itself). */
export async function saveFileNative(name: string, blob: Blob): Promise<string | null> {
  const n = files();
  if (n?.saveFile) {
    const res = n.saveFile(name, blob.type || "application/octet-stream", await toBase64(blob));
    if (res.startsWith("error:")) throw new Error(res.slice(6));
    return res.replace(/^ok:/, "");
  }
  const d = desktop();
  if (d?.save_file) {
    const res = await d.save_file(name, await toBase64(blob));
    if (res.startsWith("error:")) throw new Error(res.slice(6).trim());
    return res;
  }
  return null;
}

/** Kept for older callers. */
export const saveFileOnAndroid = saveFileNative;

/** Android: opens Android's print screen for an HTML page ("Save as PDF"). Returns false when not in the Android app. */
export function printOnAndroid(title: string, html: string): boolean {
  const n = files();
  if (!n?.printHtml) return false;
  n.printHtml(title, html);
  return true;
}
