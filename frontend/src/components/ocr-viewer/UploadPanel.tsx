"use client";

import { useRef, useState } from "react";

export type Phase = "idle" | "ready" | "processing" | "done" | "error";

interface UploadPanelProps {
  phase: Phase;
  disabled: boolean;
  onFile: (file: File) => void;
  onRun: () => void;
}

const ACCEPTED_TYPES = ["image/jpeg", "image/jpg", "image/png"];
const MAX_BYTES = 10 * 1024 * 1024;

export default function UploadPanel({ phase, disabled, onFile, onRun }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  function accept(file: File | undefined | null) {
    if (disabled) return;
    if (!file) return;
    // Quick client feedback only; the API re-validates by decoding the file.
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setLocalError("Only JPG and PNG files are supported.");
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
        <p className="dropzone-hint">JPG or PNG, up to 10 MB, single page</p>
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
          accept="image/jpeg,image/png"
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
