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
