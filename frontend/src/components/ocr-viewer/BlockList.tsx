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
}

function BlockItem({
  block,
  index,
  selected,
  showPages,
  onSelect,
}: {
  block: Block;
  index: number;
  selected: boolean;
  showPages: boolean;
  onSelect: (id: number) => void;
}) {
  const [showSource, setShowSource] = useState(false);

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
        </span>
        {block.content_html && !showSource ? (
          // Server-sanitized table HTML (nh3 allowlist); see backend/app/blocks.py
          <div className="block-table" dangerouslySetInnerHTML={{ __html: block.content_html }} />
        ) : (
          <pre className="block-text">{block.content}</pre>
        )}
      </button>
    </li>
  );
}

export default function BlockList({ blocks, selectedId, onSelect, onKey, showPages = false }: BlockListProps) {
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
              onSelect={onSelect}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
