import React from "react";
import { tr } from "../i18n";
import { useI18n } from "../i18n";
import { FileCode2 } from "lucide-react";
import { ArtifactItem, OperatingMode } from "../types/agent";

interface HeaderActionsBarProps {
  activeThreadArtifacts: ArtifactItem[];
  rightPanel: "none" | "artifact" | "appearance" | "pseudonymiser";
  onToggleArtifacts: () => void;
  onToggleAppearance?: () => void;
  onOpenVault?: () => void;
  onTogglePseudonymiser?: () => void;
  autoPseudonymise?: boolean;
  asOfDate?: string;
  operatingMode?: OperatingMode;
  audienceMode?: "citizen" | "professional";
  onOpenOperatingMode?: () => void;
  onOpenConcordance?: () => void;
  onOpenCalculators?: () => void;
  onOpenSituations?: () => void;
  onOpenStatutes?: () => void;
  onOpenAuditTrace?: () => void;
  onToggleAudienceMode?: () => void;
}

export const HeaderActionsBar: React.FC<HeaderActionsBarProps> = ({
  activeThreadArtifacts,
  rightPanel,
  onToggleArtifacts,
}) => {
  const { t } = useI18n();
  if (activeThreadArtifacts.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <button
        type="button"
        onClick={onToggleArtifacts}
        title={tr("Workbench ({0} artifacts)", [activeThreadArtifacts.length])}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors hover:opacity-85 cursor-pointer whitespace-nowrap shrink-0"
        style={{
          backgroundColor:
            rightPanel === "artifact"
              ? "var(--bg-card)"
              : "var(--bg-surface)",
          borderColor:
            rightPanel === "artifact"
              ? "var(--border-strong)"
              : "var(--border-subtle)",
          color: "var(--text-heading)",
        }}
      >
        <FileCode2 className="w-3.5 h-3.5" />
        <span>{t("header.workbench")}</span>
        <span
          className="font-code text-[10px] px-1.5 py-0.2 rounded-full font-semibold"
          style={{
            backgroundColor: "var(--bg-muted)",
            color: "var(--accent-primary)",
          }}
        >
          {activeThreadArtifacts.length}
        </span>
      </button>
    </div>
  );
};
