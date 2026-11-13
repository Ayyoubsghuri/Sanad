import React, { useEffect, useRef, useState } from "react";

export type AvatarMode = "idle" | "typing" | "thinking";
export type AvatarEmotion = "neutral" | "happy" | "angry";

interface SanadAvatarProps {
  /** idle = follows the mouse, typing = looks down at the composer, thinking = scanning + pulsing antenna. */
  mode?: AvatarMode;
  /** 0..1 – how far through the input the user is; the eyes sweep left -> right while typing. */
  typingProgress?: number;
  /** Pixel size of the avatar (width = height). */
  size?: number;
  /** Optional mono pill under the avatar, e.g. "idle" / "thinking". Use `autoLabel` to derive it from mode. */
  label?: string;
  autoLabel?: boolean;
  /** Soft halo behind the avatar. */
  glow?: boolean;
  /** false = no mouse tracking / blinking (cheap, for older messages in a long thread). */
  interactive?: boolean;
  className?: string;
}

const clamp = (v: number, min: number, max: number) =>
  Math.min(max, Math.max(min, v));

/**
 * Detects dark mode from the real background behind the avatar: walks up from the
 * avatar to the first ancestor with a visible background colour and checks its
 * luminance. Works with any theme mechanism (class, data-attr, CSS variables).
 */
function useIsDark(ref: React.RefObject<HTMLElement | null>): boolean {
  const read = (): boolean => {
    let el: HTMLElement | null = ref.current;
    while (el) {
      const m = getComputedStyle(el).backgroundColor.match(/[\d.]+/g);
      if (m && m.length >= 3) {
        const [r, g, b, a = 1] = m.map(Number);
        if (a > 0.05) return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
      }
      el = el.parentElement;
    }
    return false; // no background found -> assume light
  };

  const [dark, setDark] = useState<boolean>(false);

  useEffect(() => {
    const update = () => setDark(read());
    update();

    // Watch every ancestor for class/style/attribute changes (theme toggles)
    const mo = new MutationObserver(update);
    let el: HTMLElement | null = ref.current;
    while (el) {
      mo.observe(el, {
        attributes: true,
        attributeFilter: ["class", "style", "data-theme", "data-mode"],
      });
      el = el.parentElement;
    }
    // Re-check shortly after mount in case styles/themes apply late
    const t = window.setTimeout(update, 150);
    return () => {
      mo.disconnect();
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return dark;
}

export const SanadAvatar: React.FC<SanadAvatarProps> = ({
  mode = "idle",
  typingProgress = 0,
  size = 64,
  label,
  autoLabel = false,
  glow = true,
  interactive = true,
  className = "",
}) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<SVGGElement>(null);
  const eyesRef = useRef<SVGGElement>(null);
  const antennaRef = useRef<SVGGElement>(null);

  const target = useRef({ x: 0, y: 0 });
  const current = useRef({ x: 0, y: 0 });
  const mouse = useRef({ x: 0, y: 0 });
  const raf = useRef<number | null>(null);
  const kickRef = useRef<() => void>(() => {});

  const modeRef = useRef<AvatarMode>(mode);
  const progressRef = useRef(typingProgress);
  modeRef.current = mode;
  progressRef.current = typingProgress;

  const [emotion, setEmotion] = useState<AvatarEmotion>("neutral");
  const isDark = useIsDark(wrapRef);
  const bodyColor = isDark ? "#ffffff" : "#000000";
  const eyeColor = isDark ? "#000000" : "#ffffff";
  const rimColor = isDark ? "rgba(0,0,0,0.15)" : "rgba(255,255,255,0.12)";
  const haloColor = emotion === "angry" ? "#ef4444" : isDark ? "#fff" : "#000";
  const fillFade: React.CSSProperties = { transition: "fill 0.3s ease" };

  const [blink, setBlink] = useState(false);
  const [hover, setHover] = useState(false);
  const [boop, setBoop] = useState(false);
  const clicks = useRef({ n: 0, last: 0 });
  const emoTimer = useRef<number | null>(null);
  useEffect(() => () => { if (emoTimer.current) window.clearTimeout(emoTimer.current); }, []);

  /* ---------- Pop when the mode changes (e.g. user hits send -> thinking) ---------- */
  const prevMode = useRef<AvatarMode>(mode);
  useEffect(() => {
    if (prevMode.current !== mode) {
      if (mode === "thinking" || prevMode.current === "thinking") {
        setBoop(true);
        const t = window.setTimeout(() => setBoop(false), 450);
        prevMode.current = mode;
        kickRef.current();
        return () => window.clearTimeout(t);
      }
      prevMode.current = mode;
    }
    kickRef.current();
  }, [mode, typingProgress]);

  /* ---------- Animation loop + global mouse tracking ---------- */
  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !interactive) return;

    const apply = (t: number, m: AvatarMode) => {
      const c = current.current;
      const bob = m === "thinking" ? Math.sin(t / 200) * 1.8 : 0;
      const lean = m === "typing" ? 1.6 : 0; // nods forward while typing
      const perk = m === "typing" ? -1.5 : 0; // antenna perks up
      bodyRef.current?.setAttribute(
        "transform",
        `translate(${(c.x * 2.5).toFixed(2)} ${(c.y * 2 + lean).toFixed(2)}) rotate(${(c.x * 4).toFixed(2)} 50 90)`
      );
      eyesRef.current?.setAttribute(
        "transform",
        `translate(${(c.x * 6.5).toFixed(2)} ${(c.y * 5).toFixed(2)})`
      );
      antennaRef.current?.setAttribute(
        "transform",
        `translate(${(-c.x * 3.5).toFixed(2)} ${(-c.y * 2 + bob + perk).toFixed(2)})`
      );
    };

    const tick = (t: number) => {
      const m = modeRef.current;
      if (m === "thinking") {
        // Scan side to side, a bit faster than idle
        target.current.x = Math.sin(t / 420) * 0.95;
        target.current.y = Math.cos(t / 900) * 0.25 - 0.15;
      } else if (m === "typing") {
        // Look down at the composer; sweep along with the text like reading it
        const p = clamp(progressRef.current, 0, 1);
        target.current.x = (p * 2 - 1) * 0.65;
        target.current.y = 0.95;
      } else {
        target.current.x = mouse.current.x;
        target.current.y = mouse.current.y;
      }

      const c = current.current;
      const g = target.current;
      const ease = m === "typing" ? 0.2 : 0.13;
      c.x += (g.x - c.x) * ease;
      c.y += (g.y - c.y) * ease;
      apply(t, m);

      const settled =
        Math.abs(g.x - c.x) < 0.001 && Math.abs(g.y - c.y) < 0.001;
      if (settled && m === "idle") {
        raf.current = null;
        return;
      }
      raf.current = requestAnimationFrame(tick);
    };

    const kick = () => {
      if (raf.current === null) raf.current = requestAnimationFrame(tick);
    };
    kickRef.current = kick;

    const onMove = (e: PointerEvent) => {
      const el = wrapRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      const dist = Math.hypot(dx, dy) || 1;
      const strength = clamp(dist / 140, 0, 1);
      mouse.current.x = (dx / dist) * strength;
      mouse.current.y = (dy / dist) * strength;
      if (modeRef.current === "idle") kick();
    };

    const onLeave = () => {
      mouse.current.x = 0;
      mouse.current.y = 0;
      kick();
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onLeave);
    window.addEventListener("blur", onLeave);
    kick();

    return () => {
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("blur", onLeave);
      if (raf.current !== null) cancelAnimationFrame(raf.current);
      raf.current = null;
      kickRef.current = () => {};
    };
  }, [interactive]);

  /* ---------- Random blinking ---------- */
  useEffect(() => {
    if (!interactive) return;
    let timer: number;
    const schedule = () => {
      timer = window.setTimeout(
        () => {
          setBlink(true);
          window.setTimeout(() => setBlink(false), 120);
          schedule();
        },
        modeRef.current === "thinking"
          ? 1400 + Math.random() * 1400
          : 2200 + Math.random() * 3200
      );
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [interactive]);

  const handleClick = () => {
    setBoop(true);
    window.setTimeout(() => setBoop(false), 450);
    if (!interactive) return;
    // 1 click = happy. 3 quick clicks (each within 1.1s of the last) = angry.
    const now = Date.now();
    const c = clicks.current;
    c.n = now - c.last < 1100 ? c.n + 1 : 1;
    c.last = now;
    const angry = c.n >= 3;
    if (angry) c.n = 0;
    setEmotion(angry ? "angry" : "happy");
    if (emoTimer.current) window.clearTimeout(emoTimer.current);
    emoTimer.current = window.setTimeout(() => setEmotion("neutral"), angry ? 2600 : 1800);
  };

  // Typing = slightly narrowed, concentrating eyes. Hover = a bit bigger.
  const eyeStyle = (): React.CSSProperties => {
    const sx = hover && !blink && emotion === "neutral" ? 1.1 : 1;
    const baseY = mode === "typing" ? 0.82 : 1;
    return {
      transformBox: "fill-box",
      transformOrigin: "center",
      transform: `scale(${sx}, ${blink && emotion === "neutral" ? 0.08 : baseY})`,
      transition: "transform 0.09s ease-out",
    };
  };

  const pillText = label ?? (autoLabel ? mode : undefined);

  return (
    <div
      className={`inline-flex flex-col items-center gap-3 shrink-0 ${className}`}
    >
      <div
        ref={wrapRef}
        className="relative"
        style={{ width: size, height: size, cursor: interactive ? "pointer" : "default" }}
        onPointerEnter={() => setHover(true)}
        onPointerLeave={() => setHover(false)}
        onClick={handleClick}
        role="img"
        aria-label={`Sanad assistant avatar (${mode}, ${emotion})`}
      >
        <svg
          viewBox="0 0 100 100"
          width={size}
          height={size}
          style={{
            overflow: "visible",
            transformOrigin: "50% 90%",
            transform: boop ? "scale(1.1, 0.9)" : "scale(1)",
            transition: "transform 0.4s cubic-bezier(.34,1.56,.64,1)",
          }}
        >
          <defs>
            <radialGradient id="sanad-halo" cx="50%" cy="55%" r="50%">
              <stop offset="55%" stopColor="currentColor" stopOpacity="0.07" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </radialGradient>
          </defs>

          {glow && (
            <circle
              cx="50"
              cy="56"
              r="68"
              fill="url(#sanad-halo)"
              style={{ color: haloColor, transition: "color 0.3s ease" }}
            />
          )}

          <g className={emotion === "angry" ? "sanad-angry" : emotion === "happy" ? "sanad-happy" : undefined} style={{ transformBox: "fill-box", transformOrigin: "50% 90%" }}>
          <g ref={bodyRef}>
            {/* Antenna dot (+ pulsing ring while thinking) */}
            <g ref={antennaRef}>
              {mode === "thinking" && (
                <circle
                  cx="50"
                  cy="12"
                  r="5.5"
                  fill="none"
                  stroke={bodyColor}
                  strokeWidth="1.6"
                >
                  <animate attributeName="r" values="5.5;13" dur="1.1s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.6;0" dur="1.1s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx="50" cy="12" r="5.5" fill={bodyColor} style={fillFade} />
            </g>

            {/* Squircle body */}
            <path
              d="M12 58 C12 32 24 23 50 23 C76 23 88 32 88 58 C88 84 76 93 50 93 C24 93 12 84 12 58 Z"
              fill={bodyColor}
              stroke={rimColor}
              strokeWidth="0.8"
              style={fillFade}
            />

            {/* Eyes: neutral dots, happy arcs (^ ^), angry slanted lids */}
            <g ref={eyesRef}>
              {emotion === "happy" ? (
                <g fill="none" stroke={eyeColor} strokeWidth="5.5" strokeLinecap="round" style={fillFade}>
                  <path d="M26 63 Q36.5 47 47 63" />
                  <path d="M53 63 Q63.5 47 74 63" />
                  <ellipse cx="22" cy="72" rx="5" ry="3" fill="#fb7185" stroke="none" opacity="0.55" />
                  <ellipse cx="78" cy="72" rx="5" ry="3" fill="#fb7185" stroke="none" opacity="0.55" />
                </g>
              ) : (
                <>
                  <g style={eyeStyle()}>
                    <circle cx="36.5" cy="58" r="11" fill={eyeColor} style={fillFade} />
                  </g>
                  <g style={eyeStyle()}>
                    <circle cx="63.5" cy="58" r="11" fill={eyeColor} style={fillFade} />
                  </g>
                  {emotion === "angry" && (
                    <g>
                      {/* body-coloured lids cut the top inner part of each eye; brow lines sit on top */}
                      <polygon points="20,36 50,36 50,62 20,47" fill={bodyColor} />
                      <polygon points="80,36 50,36 50,62 80,47" fill={bodyColor} />
                      <line x1="22" y1="45" x2="49" y2="58" stroke={eyeColor} strokeWidth="5" strokeLinecap="round" />
                      <line x1="78" y1="45" x2="51" y2="58" stroke={eyeColor} strokeWidth="5" strokeLinecap="round" />
                    </g>
                  )}
                </>
              )}
            </g>
          </g>
          </g>
        </svg>
      </div>

      {pillText && (
        <span
          className="font-code text-[11px] px-3 py-0.5 rounded-full border"
          style={{
            backgroundColor: "var(--bg-surface, #fff)",
            borderColor: "var(--border-subtle)",
            color: "var(--text-muted)",
          }}
        >
          {pillText}
        </span>
      )}
    </div>
  );
};

export default SanadAvatar;
