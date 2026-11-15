// "Law as of" date in the top bar: the answers use the texts in force on this date (empty = today).
import React, { useRef } from "react";
import { CalendarDays, X } from "lucide-react";
import { tr } from "../i18n";

export function AsOfDateChip({ value, onChange }: { value: string; onChange: (date: string) => void }) {
  const input = useRef<HTMLInputElement | null>(null);
  const today = new Date().toISOString().slice(0, 10);
  const set = !!value && value !== today;
  const open = () => {
    const el = input.current;
    if (!el) return;
    try {
      (el as HTMLInputElement & { showPicker?: () => void }).showPicker?.();
    } catch {
      el.focus();
      el.click();
    }
  };
  return (
    <div
      className="relative inline-flex items-center h-8 rounded-full border text-xs font-medium shrink-0"
      style={{
        backgroundColor: set ? "var(--bg-card)" : "var(--bg-surface)",
        borderColor: set ? "var(--border-strong)" : "var(--border-subtle)",
        color: "var(--text-heading)",
      }}
      title={tr("The answers use the law in force on this date")}
    >
      <button type="button" onClick={open} className="inline-flex items-center gap-1.5 h-full pl-2.5 pr-2.5 cursor-pointer">
        <CalendarDays className="w-3.5 h-3.5 opacity-75" />
        <span className="whitespace-nowrap">{set ? value : tr("Law today")}</span>
      </button>
      {set && (
        <button
          type="button"
          onClick={() => onChange("")}
          title={tr("Back to today")}
          className="inline-flex items-center justify-center h-full pr-2 -ml-1 opacity-60 hover:opacity-100 cursor-pointer"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
      <input
        ref={input}
        type="date"
        value={value || today}
        max="2100-12-31"
        onChange={(e) => onChange(e.target.value === today ? "" : e.target.value)}
        className="absolute inset-0 opacity-0 pointer-events-none"
        tabIndex={-1}
        aria-label={tr("Law in force on")}
      />
    </div>
  );
}
