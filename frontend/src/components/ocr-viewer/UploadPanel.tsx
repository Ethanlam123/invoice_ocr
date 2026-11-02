"use client";

import { useRef, useState } from "react";

export type Phase = "idle" | "ready" | "processing" | "done" | "error";

interface UploadPanelProps {
  phase: Phase;
  disabled: boolean;
  onFile: (file: File) => void;
  onRun: () => void;
}

const ACCEPTED_TYPES = ["image/jpeg", "image/jpg", "image/png", "application/pdf"];
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_PDF_PAGES = 8;

export default function UploadPanel({ phase, disabled, onFile, onRun }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  function accept(file: File | undefined | null) {
    if (disabled) return;
    if (!file) return;
    // Quick client feedback only; the API re-validates by decoding the file.
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!ACCEPTED_TYPES.includes(file.type) && !isPdf) {
      setLocalError("Only JPG, PNG and PDF files are supported.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setLocalError("File exceeds the 10 MB limit.");
      return;
    }
    setLocalError(null);
    onFile(file);
  }

  return (
    <div className="upload-panel">
      <div
        className={`dropzone ${dragOver ? "dropzone-active" : ""} ${disabled ? "dropzone-disabled" : ""}`}
        aria-disabled={disabled}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          accept(e.dataTransfer.files?.[0]);
        }}
      >
        <p className="dropzone-title">Drop an invoice or receipt</p>
        <p className="dropzone-hint">
          JPG, PNG or PDF (up to {MAX_PDF_PAGES} pages), max 10 MB
        </p>
        <button
          type="button"
          className="btn"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          Choose file
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,application/pdf"
          hidden
          disabled={disabled}
          onChange={(e) => {
            accept(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {localError && <p className="field-error">{localError}</p>}
      {phase === "ready" && (
        <button type="button" className="btn btn-primary" onClick={onRun}>
          Run OCR
        </button>
      )}
    </div>
  );
}
