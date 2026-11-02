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
