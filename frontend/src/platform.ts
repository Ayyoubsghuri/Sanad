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

/** Android: the web view cannot download a file made in the page, so it is handed to the app (Downloads/Sanad, then opened).
 *  Returns where it was saved, or null when not in the Android app. Throws on failure. */
export async function saveFileOnAndroid(name: string, blob: Blob): Promise<string | null> {
  const n = files();
  if (!n?.saveFile) return null;
  const b64 = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).replace(/^data:[^,]*,/, ""));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
  const res = n.saveFile(name, blob.type || "application/octet-stream", b64);
  if (res.startsWith("error:")) throw new Error(res.slice(6));
  return res.replace(/^ok:/, "");
}

/** Android: opens Android's print screen for an HTML page ("Save as PDF"). Returns false when not in the Android app. */
export function printOnAndroid(title: string, html: string): boolean {
  const n = files();
  if (!n?.printHtml) return false;
  n.printHtml(title, html);
  return true;
}
