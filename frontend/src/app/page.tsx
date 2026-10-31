"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import "@/components/ocr-viewer/viewer.css";

import BlockList from "@/components/ocr-viewer/BlockList";
import ErrorBanner from "@/components/ocr-viewer/ErrorBanner";
import ImagePane from "@/components/ocr-viewer/ImagePane";
import StatusBar from "@/components/ocr-viewer/StatusBar";
import UploadPanel, { type Phase } from "@/components/ocr-viewer/UploadPanel";
import { runOcr } from "@/lib/api";
import { downloadJson, resultFilename, stepBlockId } from "@/lib/blocks";
import type { ApiError, Envelope, OcrData } from "@/lib/types";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<OcrData | null>(null);
  const [meta, setMeta] = useState<Envelope["meta"]>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [liveElapsed, setLiveElapsed] = useState(0);
  const [previewDims, setPreviewDims] = useState<{ width: number; height: number } | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    },
    [],
  );

  const handleFile = useCallback((f: File) => {
    // stop any in-flight run's timer so it cannot leak into the next session
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setFile(f);
    setResult(null);
    setMeta(null);
    setError(null);
    setSelectedId(null);
    setPhase("ready");
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    const url = URL.createObjectURL(f);
    objectUrlRef.current = url;
    setPreviewDims(null);
    // read the preview's intrinsic size so the img can reserve space (no layout jump)
    const el = new Image();
    el.onload = () => setPreviewDims({ width: el.naturalWidth, height: el.naturalHeight });
    el.src = url;
    setPreviewUrl(url);
  }, []);

  const handleRun = useCallback(async () => {
    if (!file || phase === "processing") return;
    // Clear prior results first: a failed run must never show stale output.
    setResult(null);
    setMeta(null);
    setError(null);
    setSelectedId(null);
    setPhase("processing");
    setLiveElapsed(0);
    const started = performance.now();
    timerRef.current = setInterval(() => setLiveElapsed(performance.now() - started), 200);
    const env = await runOcr(file);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    if (env.success && env.data) {
      setResult(env.data);
      setMeta(env.meta);
      setPreviewUrl(env.data.image.data_url); // normalized image: boxes match these pixels
      setPhase("done");
    } else {
      setResult(null);
      setError(env.error ?? { code: "unknown_error", message: "Unexpected empty response." });
      setPhase("error");
    }
  }, [file, phase]);

  const handleReset = useCallback(() => {
    setFile(null);
    setResult(null);
    setMeta(null);
    setError(null);
    setSelectedId(null);
    setPhase("idle");
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = null;
    setPreviewUrl(null);
    setPreviewDims(null);
  }, []);

  const handleListKey = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (!result || result.blocks.length === 0) return;
      const target = event.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        setSelectedId(stepBlockId(result.blocks, selectedId, 1));
      } else if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        setSelectedId(stepBlockId(result.blocks, selectedId, -1));
      } else if (event.key === "Escape") {
        setSelectedId(null);
      }
    },
    [result, selectedId],
  );

  const blocks = result?.blocks ?? [];

  return (
    <div className="viewer">
      <header className="viewer-header">
        <div className="wordmark">
          <span className="wordmark-mark">IO</span>
          <span className="wordmark-text">
            Invoice OCR Viewer
            <span className="wordmark-sub">PaddleOCR-VL x MLX - local inference</span>
          </span>
        </div>
        <UploadPanel phase={phase} disabled={phase === "processing"} onFile={handleFile} onRun={handleRun} />
      </header>

      {error && <ErrorBanner error={error} />}

      <main className="split">
        <section className="pane pane-image" aria-label="Document and detected regions">
          <StatusBar
            phase={phase}
            fileName={file?.name ?? null}
            elapsedMs={meta?.elapsed_ms ?? null}
            liveElapsedMs={liveElapsed}
            blockCount={blocks.length}
            model={meta?.model ?? null}
            onDownload={() => result && downloadJson(result.raw, resultFilename())}
            onReset={handleReset}
          />
          <ImagePane
            imageUrl={previewUrl}
            imageWidth={result?.image.width ?? previewDims?.width ?? null}
            imageHeight={result?.image.height ?? previewDims?.height ?? null}
            blocks={blocks}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </section>
        <aside className="pane pane-blocks" aria-label="OCR results">
          {phase === "idle" && !file ? (
            <div className="pane-hint">
              <h2>Reading-order output</h2>
              <p>
                Upload a document, run the pipeline, and the recognized blocks appear here in
                reading order. Select a block to highlight its source region on the image.
              </p>
              <p className="kbd-hint">
                Keys: arrows or j / k to step through blocks, Esc to clear.
              </p>
            </div>
          ) : (
            <BlockList
              blocks={blocks}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onKey={handleListKey}
            />
          )}
        </aside>
      </main>
    </div>
  );
}
