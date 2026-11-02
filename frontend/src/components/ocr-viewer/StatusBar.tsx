"use client";

import type { Phase } from "./UploadPanel";

interface StatusBarProps {
  phase: Phase;
  fileName: string | null;
  elapsedMs: number | null;
  liveElapsedMs: number;
  blockCount: number;
  pageCount: number | null;
  model: string | null;
  docType: string | null;
  qualityFlags: string[] | null;
  canSave: boolean; // unsaved result + persistence on
  saving: boolean;
  onSave: () => void;
  onDownload: () => void;
  onReset: () => void;
}

function fmt(ms: number): string {
  return ms >= 10_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export default function StatusBar({
  phase,
  fileName,
  elapsedMs,
  liveElapsedMs,
  blockCount,
  pageCount,
  model,
  docType,
  qualityFlags,
  canSave,
  saving,
  onSave,
  onDownload,
  onReset,
}: StatusBarProps) {
  return (
    <div className="status-bar">
      {phase === "processing" && (
        <span className="status-status">
          <span className="spinner" aria-hidden="true" />
          Running PaddleOCR-VL locally - {fmt(liveElapsedMs)}
        </span>
      )}
      {phase === "done" && (
        <>
          <span className="status-status status-ok">
            {blockCount} blocks in {fmt(elapsedMs ?? 0)}
          </span>
          {docType && <span className="status-model">{docType}</span>}
          {qualityFlags && qualityFlags.length > 0 && (
            <span
              className="status-model status-flags"
              title={qualityFlags.join("\n")}
            >
              {qualityFlags.length} quality flag{qualityFlags.length > 1 ? "s" : ""}
            </span>
          )}
          {pageCount != null && pageCount > 1 && (
            <span className="status-model">{pageCount} pages</span>
          )}
          {model && <span className="status-model">{model}</span>}
        </>
      )}
      {(phase === "done" || phase === "error") && (
        <>
          <button type="button" className="btn" onClick={onReset}>
            New document
          </button>
          {phase === "done" && canSave && (
            <button type="button" className="btn" onClick={onSave} disabled={saving}>
              {saving ? "Saving..." : "Save to history"}
            </button>
          )}
          {phase === "done" && (
            <button type="button" className="btn btn-primary" onClick={onDownload}>
              Download JSON
            </button>
          )}
        </>
      )}
      {(phase === "idle" || phase === "ready") && fileName && (
        <span className="status-status">{fileName}</span>
      )}
    </div>
  );
}
