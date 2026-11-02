"use client";

import type { Block, PageInfo } from "@/lib/types";
import { toRect } from "@/lib/blocks";

interface ImagePaneProps {
  pages: PageInfo[]; // result pages (empty until a run succeeds)
  previewUrl: string | null; // upload preview; PDFs cannot be previewed as images
  previewDims: { width: number; height: number } | null;
  blocks: Block[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function Overlay({
  page,
  dims,
  blocks,
  selectedId,
  onSelect,
}: {
  page: number;
  dims: { width: number; height: number };
  blocks: Block[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const pageBlocks = blocks.filter(
    (b) => b.page === page || (b.page_bboxes ?? []).some((pb) => pb.page === page),
  );
  if (pageBlocks.length === 0) return null;
  return (
    <svg
      className="overlay"
      viewBox={`0 0 ${dims.width} ${dims.height}`}
      role="group"
      aria-label={`Page ${page + 1} detected regions (${pageBlocks.length})`}
    >
      {pageBlocks.map((b) => {
        // spanning blocks draw one rect per page from page_bboxes
        const bbox = b.page_bboxes?.find((pb) => pb.page === page)?.bbox ?? b.bbox;
        const r = toRect(bbox);
        const isSelected = b.id === selectedId;
        const isContinuation = b.page_end > b.page && page > b.page;
        return (
          <rect
            key={`${b.id}-${page}`}
            x={r.x}
            y={r.y}
            width={r.width}
            height={r.height}
            className={
              `overlay-rect ${isSelected ? "overlay-rect-selected" : ""} ` +
              `${isContinuation ? "overlay-rect-continuation" : ""}`
            }
            vectorEffect="non-scaling-stroke"
            tabIndex={-1}
            role="button"
            aria-label={`Region ${b.id}: ${b.label}${b.page_end > b.page ? " (spans pages)" : ""}`}
            onClick={() => onSelect(b.id)}
          />
        );
      })}
    </svg>
  );
}

export default function ImagePane({
  pages,
  previewUrl,
  previewDims,
  blocks,
  selectedId,
  onSelect,
}: ImagePaneProps) {
  if (pages.length > 0) {
    return (
      <div className="image-pane">
        <div className="page-stack">
          {pages.map((p) => (
            <figure key={p.index} className="image-frame">
              <div className="image-holder">
                {/* eslint-disable-next-line @next/next/no-img-element -- local blob/data URL, not a managed asset */}
                <img
                  src={p.data_url}
                  alt={`Document page ${p.index + 1}`}
                  width={p.width}
                  height={p.height}
                />
                <Overlay
                  page={p.index}
                  dims={{ width: p.width, height: p.height }}
                  blocks={blocks}
                  selectedId={selectedId}
                  onSelect={onSelect}
                />
              </div>
              {pages.length > 1 && (
                <figcaption className="page-caption">
                  Page {p.index + 1} / {pages.length}
                </figcaption>
              )}
            </figure>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="image-pane">
      {previewUrl ? (
        <figure className="image-frame">
          <div className="image-holder">
            {/* eslint-disable-next-line @next/next/no-img-element -- local blob/data URL, not a managed asset */}
            <img
              src={previewUrl}
              alt="Uploaded document"
              width={previewDims?.width ?? undefined}
              height={previewDims?.height ?? undefined}
            />
          </div>
        </figure>
      ) : (
        <div className="image-empty">
          <p className="dropzone-hint">
            The document preview and detected regions appear here. PDF pages render
            once OCR has run.
          </p>
        </div>
      )}
    </div>
  );
}
