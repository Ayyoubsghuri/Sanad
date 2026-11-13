import React, { useState } from "react";
import { tr } from "../i18n";
import { Plus, Trash2, X } from "lucide-react";
import { ProjectDoc } from "../types/agent";

interface ProjectKnowledgeModalProps {
  systemInstruction: string;
  onChangeSystemInstruction: (val: string) => void;
  docs: ProjectDoc[];
  onAddDoc: (doc: ProjectDoc) => void;
  onRemoveDoc: (id: string) => void;
  onClose: () => void;
}

export const ProjectKnowledgeModal: React.FC<ProjectKnowledgeModalProps> = ({
  systemInstruction,
  onChangeSystemInstruction,
  docs,
  onAddDoc,
  onRemoveDoc,
  onClose,
}) => {
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) return;
    onAddDoc({
      id: `doc-${Date.now()}`,
      title: newTitle.trim(),
      content: newContent.trim(),
    });
    setNewTitle("");
    setNewContent("");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(27, 22, 20, 0.45)" }}
    >
      <div
        className="sanad-liquid-modal w-full max-w-2xl max-h-[86vh] rounded-2xl border flex flex-col overflow-hidden"
        style={{
          backgroundColor: "var(--bg-surface)",
          borderColor: "var(--border-strong)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4 border-b"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div>
            <h2
              className="font-editorial text-lg font-medium"
              style={{ color: "var(--text-heading)" }}
            >
              {tr("Project Knowledge & Guidance")}
            </h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              {tr("Context and custom instructions shared across every Sanad session.")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg hover:opacity-75 cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Custom Instructions */}
          <div>
            <label
              className="block text-xs font-semibold mb-2"
              style={{ color: "var(--text-heading)" }}
            >
              {tr("Custom Agent Instructions")}
            </label>
            <textarea
              rows={3}
              value={systemInstruction}
              onChange={(e) => onChangeSystemInstruction(e.target.value)}
              placeholder={tr("e.g., Favor concise architectural trade-offs, TypeScript examples, and clear executive tables.")}
              className="w-full rounded-xl border p-3 text-xs leading-relaxed outline-none"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            />
          </div>

          {/* Reference Notes List */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <span
                className="text-xs font-semibold"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Reference Notes (")}{docs.length})
              </span>
            </div>

            {docs.length === 0 ? (
              <div
                className="p-4 rounded-xl border text-xs text-center"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-muted)",
                }}
              >
                {tr("No reference notes saved yet. Add domain context below or ask the agent to save notes during a conversation.")}
              </div>
            ) : (
              <div className="space-y-2.5">
                {docs.map((doc) => (
                  <div
                    key={doc.id}
                    className="p-3.5 rounded-xl border flex items-start justify-between gap-3"
                    style={{
                      backgroundColor: "var(--bg-canvas)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div
                        className="text-xs font-semibold"
                        style={{ color: "var(--text-heading)" }}
                      >
                        {doc.title}
                      </div>
                      <p
                        className="text-xs mt-1 leading-relaxed whitespace-pre-wrap"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {doc.content}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onRemoveDoc(doc.id)}
                      title={tr("Remove note")}
                      className="p-1 rounded-md hover:opacity-75 cursor-pointer shrink-0"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Add Note Form */}
          <form
            onSubmit={handleAdd}
            className="p-4 rounded-xl border space-y-3"
            style={{
              backgroundColor: "var(--bg-muted)",
              borderColor: "var(--border-subtle)",
            }}
          >
            <div
              className="text-xs font-semibold"
              style={{ color: "var(--text-heading)" }}
            >
              {tr("Add Reference Note")}
            </div>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={tr("Note title (e.g., Q4 Product Roadmap Goals)")}
              className="w-full rounded-lg border px-3 py-2 text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            />
            <textarea
              rows={3}
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder={tr("Paste specifications, style rules, or domain facts...")}
              className="w-full rounded-lg border px-3 py-2 text-xs outline-none leading-relaxed"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!newTitle.trim() || !newContent.trim()}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition-opacity cursor-pointer disabled:opacity-40 whitespace-nowrap"
                style={{
                  backgroundColor: "var(--accent-primary)",
                  color: "var(--accent-primary-fg)",
                }}
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{tr("Add to Knowledge")}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
