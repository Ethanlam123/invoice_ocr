"use client";

import type { DocumentSummary } from "@/lib/types";

interface HistoryStripProps {
  documents: DocumentSummary[];
  activeId: number | null;
  disabled: boolean;
  onOpen: (id: number) => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function HistoryStrip({ documents, activeId, disabled, onOpen }: HistoryStripProps) {
  if (documents.length === 0) return null;
  return (
    <nav className="history-strip" aria-label="Recently processed documents">
      <span className="history-label">Recent</span>
      <ul className="history-items">
        {documents.map((doc) => (
          <li key={doc.id}>
            <button
              type="button"
              className={`history-item ${doc.id === activeId ? "history-item-active" : ""}`}
              disabled={disabled}
              onClick={() => onOpen(doc.id)}
            >
              <span className="history-filename">{doc.filename}</span>
              <span className="history-meta">
                <span className="history-doc-type">{doc.doc_type}</span>
                {doc.page_count > 1 && <span>{doc.page_count} pages</span>}
                {doc.quality_flags.length > 0 && (
                  <span className="history-flags" title={doc.quality_flags.join("\n")}>
                    {doc.quality_flags.length} flag{doc.quality_flags.length > 1 ? "s" : ""}
                  </span>
                )}
                <span>{formatTime(doc.created_at)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
