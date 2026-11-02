"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import "@/components/ocr-viewer/viewer.css";

import BlockList from "@/components/ocr-viewer/BlockList";
import ErrorBanner from "@/components/ocr-viewer/ErrorBanner";
import HistoryStrip from "@/components/ocr-viewer/HistoryStrip";
import ImagePane from "@/components/ocr-viewer/ImagePane";
import StatusBar from "@/components/ocr-viewer/StatusBar";
import UploadPanel, { type Phase } from "@/components/ocr-viewer/UploadPanel";
import { correctBlock, fetchDocument, fetchDocuments, runOcr } from "@/lib/api";
import { downloadJson, resultFilename, stepBlockId } from "@/lib/blocks";
import type { ApiError, DocumentSummary, Envelope, OcrData } from "@/lib/types";

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
  const [history, setHistory] = useState<DocumentSummary[] | null>(null); // null = persistence off
  const [activeDocId, setActiveDocId] = useState<number | null>(null);
  const [historyName, setHistoryName] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    },
    [],
  );

  useEffect(() => {
    // hidden entirely when the backend has no DATABASE_URL (503 -> null)
    fetchDocuments().then((env) => setHistory(env?.data?.documents ?? null));
  }, []);

  const refreshHistory = useCallback(() => {
    fetchDocuments().then((env) => setHistory(env?.data?.documents ?? null));
  }, []);

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
    setActiveDocId(null);
    setHistoryName(null);
    setPhase("ready");
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    setPreviewDims(null);
    const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
    if (isPdf) {
      // a PDF cannot render in <img>; its pages appear after OCR runs
      objectUrlRef.current = null;
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(f);
    objectUrlRef.current = url;
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
      setPhase("done");
      if (env.meta?.document_id) {
        setActiveDocId(env.meta.document_id);
        refreshHistory();
      }
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
    setActiveDocId(null);
    setHistoryName(null);
    setPhase("idle");
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = null;
    setPreviewUrl(null);
    setPreviewDims(null);
  }, []);

  const handleOpenDocument = useCallback(
    async (id: number) => {
      if (phase === "processing") return;
      if (timerRef.current) clearInterval(timerRef.current);
      setPhase("processing"); // brief: shows busy state while pages download
      const env = await fetchDocument(id);
      if (env?.success && env.data) {
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
        setFile(null);
        setPreviewUrl(null);
        setPreviewDims(null);
        setResult(env.data);
        setMeta(env.meta);
        setError(null);
        setSelectedId(null);
        setActiveDocId(id);
        setHistoryName(env.meta?.filename ?? `document ${id}`);
        setPhase("done");
      } else {
        setPhase("error");
        setError(
          env?.error ?? { code: "network_error", message: "Cannot load the stored document." },
        );
      }
    },
    [phase],
  );

  const handleCorrect = useCallback(
    async (blockId: number, content: string) => {
      if (!activeDocId) return false;
      const ok = await correctBlock(activeDocId, blockId, content);
      if (ok) {
        setResult((prev) =>
          prev
            ? {
                ...prev,
                blocks: prev.blocks.map((b) =>
                  b.id === blockId
                    ? { ...b, content, content_html: null, reviewed: true }
                    : b,
                ),
              }
            : prev,
        );
      }
      return ok;
    },
    [activeDocId],
  );

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

      {history && (
        <HistoryStrip
          documents={history}
          activeId={activeDocId}
          disabled={phase === "processing"}
          onOpen={handleOpenDocument}
        />
      )}

      {error && <ErrorBanner error={error} />}

      <main className="split">
        <section className="pane pane-image" aria-label="Document and detected regions">
          <StatusBar
            phase={phase}
            fileName={file?.name ?? historyName}
            elapsedMs={meta?.elapsed_ms ?? null}
            liveElapsedMs={liveElapsed}
            blockCount={blocks.length}
            pageCount={meta?.page_count ?? null}
            model={meta?.model ?? null}
            docType={meta?.doc_type ?? null}
            qualityFlags={meta?.quality_flags ?? null}
            onDownload={() => result && downloadJson(result.raw, resultFilename())}
            onReset={handleReset}
          />
          <ImagePane
            pages={result?.pages ?? []}
            previewUrl={previewUrl}
            previewDims={previewDims}
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
              showPages={(result?.pages.length ?? 0) > 1}
              canCorrect={activeDocId != null}
              onCorrect={handleCorrect}
            />
          )}
        </aside>
      </main>
    </div>
  );
}
