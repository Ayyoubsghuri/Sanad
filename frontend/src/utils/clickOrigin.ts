/** Remembers where the user last clicked, as an offset from the viewport centre, so centred modals can grow out of that spot (see .sanad-liquid-modal). */
export function installClickOrigin(): void {
  if (typeof window === "undefined") return;
  window.addEventListener(
    "pointerdown",
    (e) => {
      const root = document.documentElement.style;
      root.setProperty("--pop-dx", `${Math.round(e.clientX - window.innerWidth / 2)}px`);
      root.setProperty("--pop-y", `${Math.round(e.clientY)}px`);
      root.setProperty("--pop-dy", `${Math.round(e.clientY - window.innerHeight / 2)}px`);
    },
    { capture: true, passive: true }
  );
}
