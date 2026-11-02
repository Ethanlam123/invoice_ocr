"use client";

import { useEffect, useState } from "react";

import type { Block } from "@/lib/types";
import { pageLabel } from "@/lib/blocks";

interface BlockListProps {
  blocks: Block[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onKey: (event: React.KeyboardEvent<HTMLDivElement>) => void;
  showPages?: boolean;
  canCorrect?: boolean; // only for stored documents (needs a document id)
  onCorrect?: (blockId: number, content: string) => Promise<boolean>;
}

function BlockItem({
  block,
  index,
  selected,
  showPages,
  canCorrect,
  onSelect,
  onCorrect,
}: {
  block: Block;
  index: number;
  selected: boolean;
  showPages: boolean;
  canCorrect: boolean;
  onSelect: (id: number) => void;
  onCorrect: (blockId: number, content: string) => Promise<boolean>;
}) {
  const [showSource, setShowSource] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  // tables carry model HTML; editing raw HTML by hand is not a review flow
  const correctable = canCorrect && !block.content_html && !editing;

  function startEdit() {
    setDraft(block.content);
    setSaveFailed(false);
    setEditing(true);
  }

  async function save() {
    if (saving) return;
    if (!draft.trim()) return; // backend rejects it; do not even send
    setSaving(true);
    setSaveFailed(false);
    const ok = await onCorrect(block.id, draft);
    setSaving(false);
    if (ok) setEditing(false);
    else setSaveFailed(true);
  }

  return (
    <li className="block-item" id={`block-opt-${block.id}`}>
      <button
        type="button"
        role="option"
        aria-selected={selected}
        className={`block-button ${selected ? "block-button-selected" : ""}`}
        onClick={() => onSelect(block.id)}
      >
        <span className="block-meta">
          <span className="block-index">{String(index + 1).padStart(2, "0")}</span>
          <span className="block-label">{block.label}</span>
          {showPages && <span className="block-page">{pageLabel(block)}</span>}
          <span className="block-id">#{block.id}</span>
          {block.reviewed && <span className="block-reviewed">reviewed</span>}
          {block.content_html && (
            <span
              role="button"
              tabIndex={0}
              className="block-toggle"
              onClick={(e) => {
                e.stopPropagation();
                setShowSource((v) => !v);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation();
                  e.preventDefault();
                  setShowSource((v) => !v);
                }
              }}
            >
              {showSource ? "table" : "source"}
            </span>
          )}
          {selected && correctable && (
            <span
              role="button"
              tabIndex={0}
              className="block-toggle block-toggle-correct"
              onClick={(e) => {
                e.stopPropagation();
                startEdit();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation();
                  e.preventDefault();
                  startEdit();
                }
              }}
            >
              correct
            </span>
          )}
        </span>
        {block.content_html && !showSource ? (
          // Server-sanitized table HTML (nh3 allowlist); see backend/app/blocks.py
          <div className="block-table" dangerouslySetInnerHTML={{ __html: block.content_html }} />
        ) : (
          <pre className="block-text">{block.content}</pre>
        )}
      </button>
      {editing && (
        <div className="block-editor">
          <textarea
            aria-label={`Correct block ${block.id}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            onKeyDown={(e) => {
              if (e.key === "Escape") setEditing(false);
              e.stopPropagation();
            }}
          />
          <div className="block-editor-actions">
            <button type="button" className="btn" onClick={save} disabled={saving}>
              {saving ? "Saving..." : "Save correction"}
            </button>
            <button type="button" className="btn" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </button>
          </div>
          {saveFailed && (
            <p className="field-error" role="alert">
              Could not save the correction. Is the backend running?
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export default function BlockList({
  blocks,
  selectedId,
  onSelect,
  onKey,
  showPages = false,
  canCorrect = false,
  onCorrect = async () => false,
}: BlockListProps) {
  useEffect(() => {
    if (selectedId == null) return;
    document.getElementById(`block-opt-${selectedId}`)?.scrollIntoView({
      block: "nearest",
      behavior: "smooth",
    });
  }, [selectedId]);

  return (
    <div
      className="block-list"
      role="listbox"
      aria-label="OCR blocks in reading order"
      aria-activedescendant={selectedId != null ? `block-opt-${selectedId}` : undefined}
      tabIndex={0}
      onKeyDown={onKey}
    >
      {blocks.length === 0 ? (
        <p className="dropzone-hint">No blocks yet. Upload a document and run OCR.</p>
      ) : (
        <ol>
          {blocks.map((b, i) => (
            <BlockItem
              key={b.id}
              block={b}
              index={i}
              selected={b.id === selectedId}
              showPages={showPages}
              canCorrect={canCorrect}
              onSelect={onSelect}
              onCorrect={onCorrect}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
