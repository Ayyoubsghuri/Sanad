import React from "react";
import { tr } from "../i18n";
import { useI18n, LANGS } from "../i18n";
import { GripHorizontal, RotateCcw, X } from "lucide-react";
import { THEME_DEFINITIONS } from "../themes/palettes";
import { LayoutDensity, ThemeId, WorkspaceSettings } from "../types/agent";

interface AppearanceDrawerProps {
  settings: WorkspaceSettings;
  onChange: (patch: Partial<WorkspaceSettings>) => void;
  onReset: () => void;
  onClose: () => void;
}

interface ToggleSwitchProps {
  checked: boolean;
  onToggle: () => void;
  label: string;
}

const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  checked,
  onToggle,
  label,
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    onClick={onToggle}
    className="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-150 cursor-pointer"
    style={{
      backgroundColor: checked ? "var(--accent-warm)" : "var(--bg-card)",
    }}
  >
    <span
      className="inline-block h-5 w-5 rounded-full transition-transform duration-150 shadow-xs"
      style={{
        backgroundColor: "var(--bg-surface)",
        transform: checked ? "translateX(22px)" : "translateX(2px)",
      }}
    />
  </button>
);

export const AppearanceDrawer: React.FC<AppearanceDrawerProps> = ({
  settings,
  onChange,
  onReset,
  onClose,
}) => {
  const { t, lang, setLang } = useI18n();
  const headingPctFill = ((settings.headingScale - 85) / (120 - 85)) * 100;
  const bodyPctFill = ((settings.bodyScale - 85) / (115 - 85)) * 100;

  return (
    <aside
      className="sanad-liquid-side w-full sm:w-[340px] h-full shrink-0 border-l flex flex-col overflow-y-auto"
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <div
        className="flex items-center justify-between px-6 py-4 border-b"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <h2
          className="text-sm font-semibold tracking-wide"
          style={{ color: "var(--text-muted)" }}
        >
          {t("app.appearance")}
        </h2>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onReset}
            title={t("app.reset")}
            className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            title={t("app.close")}
            className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-6 space-y-6 flex-1">
        {/* Language */}
        <div className="space-y-2.5 pb-5 border-b" style={{ borderColor: "var(--border-subtle)" }}>
          <span className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
            {t("lang.title")}
          </span>
          <div className="grid grid-cols-3 gap-1.5">
            {LANGS.map((l) => (
              <button
                key={l.id}
                type="button"
                onClick={() => setLang(l.id)}
                className="py-2 rounded-xl border text-xs transition-colors cursor-pointer"
                style={{
                  backgroundColor: lang === l.id ? "var(--bg-card)" : "transparent",
                  borderColor: lang === l.id ? "var(--accent-primary)" : "var(--border-subtle)",
                  color: lang === l.id ? "var(--text-heading)" : "var(--text-muted)",
                  fontWeight: lang === l.id ? 600 : 400,
                }}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        {/* Dark Mode Row */}
        <div
          className="flex items-center justify-between pb-5 border-b"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <span
            className="text-sm font-medium"
            style={{ color: "var(--text-heading)" }}
          >
            {t("app.dark")}
          </span>
          <ToggleSwitch
            checked={settings.darkMode}
            onToggle={() => onChange({ darkMode: !settings.darkMode })}
            label={tr("Toggle dark mode")}
          />
        </div>

        {/* 7 Organic Theme Swatches */}
        <div
          className="pb-5 border-b"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center justify-between mb-3">
            <span
              className="text-xs font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              {t("app.palette")}
            </span>
            {settings.theme === ThemeId.Ember && (
              <span
                className="text-[11px] font-medium flex items-center gap-1"
                style={{ color: "var(--accent-primary)" }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-[#9E3223]" />
                {tr("Ember • Parchment, Navy & Red")}
              </span>
            )}
            {settings.theme === ThemeId.Mono && (
              <span
                className="text-[11px] font-medium"
                style={{ color: "var(--accent-warm)" }}
              >
                {tr("Mono • Black, White & Gray")}
              </span>
            )}
            {settings.theme === ThemeId.Emerald && (
              <span
                className="text-[11px] font-editorial italic"
                style={{ color: "var(--accent-warm)" }}
              >
                {tr("Emerald & Warm Gold")}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2.5">
            {THEME_DEFINITIONS.map((theme) => {
              const isSelected = settings.theme === theme.id;
              return (
                <button
                  key={theme.id}
                  type="button"
                  onClick={() => {
                    onChange({ theme: theme.id as ThemeId });
                  }}
                  className="flex flex-col items-center gap-1.5 p-2 rounded-xl border transition-all duration-150 hover:opacity-90 cursor-pointer group"
                  style={{
                    backgroundColor: isSelected ? "var(--bg-card)" : "transparent",
                    borderColor: isSelected ? "var(--accent-primary)" : "var(--border-subtle)",
                  }}
                >
                  <span
                    className="w-8 h-8 rounded-lg transition-all duration-150 group-hover:scale-105 shadow-xs flex items-center justify-center"
                    style={{
                      backgroundColor: theme.swatchHex,
                      ...(theme.id === ThemeId.Mono
                        ? { backgroundImage: "linear-gradient(135deg, #FFFFFF 0 33%, #8C8C8C 33% 66%, #111111 66% 100%)" }
                        : {}),
                      border: isSelected
                        ? `2px solid ${
                            settings.darkMode
                              ? "var(--ring-active)"
                              : theme.swatchRingHex
                          }`
                        : "1px solid var(--border-subtle)",
                    }}
                  >
                    {theme.id === ThemeId.Ember && (
                      <span className="text-[10px] font-bold text-[#141D2B]">
                        EM
                      </span>
                    )}
                  </span>
                  <span
                    className={`text-[11px] leading-tight text-center ${
                      isSelected ? "font-semibold" : "font-normal"
                    }`}
                    style={{
                      color: isSelected
                        ? "var(--text-heading)"
                        : "var(--text-muted)",
                    }}
                  >
                    {theme.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Typography Sliders */}
        <div
          className="space-y-4 pb-5 border-b"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              {t("app.typography")}
            </span>
          </div>

          <div>
            <div className="flex items-center justify-between text-xs mb-2">
              <span
                className="font-medium"
                style={{ color: "var(--text-heading)" }}
              >
                {t("app.heading")}
              </span>
              <span
                className="font-code"
                style={{ color: "var(--text-muted)" }}
              >
                {settings.headingScale}%
              </span>
            </div>
            <input
              type="range"
              min={85}
              max={120}
              step={5}
              value={settings.headingScale}
              onChange={(e) =>
                onChange({ headingScale: Number(e.target.value) })
              }
              className="atelier-slider"
              style={{
                background: `linear-gradient(to right, var(--accent-warm) 0%, var(--accent-warm) ${headingPctFill}%, var(--bg-card) ${headingPctFill}%, var(--bg-card) 100%)`,
              }}
            />
          </div>

          <div>
            <div className="flex items-center justify-between text-xs mb-2">
              <span
                className="font-medium"
                style={{ color: "var(--text-heading)" }}
              >
                {t("app.body")}
              </span>
              <span
                className="font-code"
                style={{ color: "var(--text-muted)" }}
              >
                {settings.bodyScale}%
              </span>
            </div>
            <input
              type="range"
              min={85}
              max={115}
              step={5}
              value={settings.bodyScale}
              onChange={(e) => onChange({ bodyScale: Number(e.target.value) })}
              className="atelier-slider"
              style={{
                background: `linear-gradient(to right, var(--accent-warm) 0%, var(--accent-warm) ${bodyPctFill}%, var(--bg-card) ${bodyPctFill}%, var(--bg-card) 100%)`,
              }}
            />
          </div>
        </div>

        {/* Workspace Sections */}
        <div
          className="space-y-3.5 pb-5 border-b"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div
            className="text-xs font-semibold"
            style={{ color: "var(--text-muted)" }}
          >
            {t("app.sections")}
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5 text-sm">
              <GripHorizontal
                className="w-4 h-4 opacity-50"
                style={{ color: "var(--text-muted)" }}
              />
              <span style={{ color: "var(--text-primary)" }}>{t("app.continue")}</span>
            </div>
            <ToggleSwitch
              checked={settings.showContinueCard}
              onToggle={() =>
                onChange({ showContinueCard: !settings.showContinueCard })
              }
              label={tr("Toggle Continue card on home screen")}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5 text-sm">
              <GripHorizontal
                className="w-4 h-4 opacity-50"
                style={{ color: "var(--text-muted)" }}
              />
              <span style={{ color: "var(--text-primary)" }}>{t("app.explore")}</span>
            </div>
            <ToggleSwitch
              checked={settings.showExplorePrompts}
              onToggle={() =>
                onChange({ showExplorePrompts: !settings.showExplorePrompts })
              }
              label={tr("Toggle Explore starter prompts")}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5 text-sm">
              <GripHorizontal
                className="w-4 h-4 opacity-50"
                style={{ color: "var(--text-muted)" }}
              />
              <span style={{ color: "var(--text-primary)" }}>{t("app.recent")}</span>
            </div>
            <ToggleSwitch
              checked={settings.showRecentSidebar}
              onToggle={() =>
                onChange({ showRecentSidebar: !settings.showRecentSidebar })
              }
              label={tr("Toggle Recent threads in sidebar")}
            />
          </div>
        </div>

        {/* Layout Density */}
        <div>
          <div
            className="text-xs font-semibold mb-3"
            style={{ color: "var(--text-muted)" }}
          >
            {t("app.density")}
          </div>
          <div
            className="grid grid-cols-2 p-1 rounded-full border"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border-subtle)",
            }}
          >
            <button
              type="button"
              onClick={() => onChange({ density: LayoutDensity.Comfy })}
              className="py-1.5 text-xs font-semibold rounded-full transition-colors cursor-pointer whitespace-nowrap"
              style={{
                backgroundColor:
                  settings.density === LayoutDensity.Comfy
                    ? "var(--bg-surface)"
                    : "transparent",
                color:
                  settings.density === LayoutDensity.Comfy
                    ? "var(--text-heading)"
                    : "var(--text-muted)",
              }}
            >
              {t("app.comfy")}
            </button>
            <button
              type="button"
              onClick={() => onChange({ density: LayoutDensity.Compact })}
              className="py-1.5 text-xs font-semibold rounded-full transition-colors cursor-pointer whitespace-nowrap"
              style={{
                backgroundColor:
                  settings.density === LayoutDensity.Compact
                    ? "var(--bg-surface)"
                    : "transparent",
                color:
                  settings.density === LayoutDensity.Compact
                    ? "var(--text-heading)"
                    : "var(--text-muted)",
              }}
            >
              {t("app.compact")}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};
