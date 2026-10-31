"use client";

import type { Block } from "@/lib/types";
import { toRect } from "@/lib/blocks";

interface ImagePaneProps {
  imageUrl: string | null;
  imageWidth: number | null;
  imageHeight: number | null;
  blocks: Block[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function ImagePane({
  imageUrl,
  imageWidth,
  imageHeight,
  blocks,
  selectedId,
  onSelect,
}: ImagePaneProps) {
  const hasOverlay = blocks.length > 0 && imageWidth != null && imageHeight != null;

  return (
    <div className="image-pane">
      {imageUrl ? (
        <figure className="image-frame">
          <div className="image-holder">
            {/* eslint-disable-next-line @next/next/no-img-element -- local blob/data URL, not a managed asset */}
            <img src={imageUrl} alt="Uploaded document" />
            {hasOverlay && (
              <svg
                className="overlay"
                viewBox={`0 0 ${imageWidth} ${imageHeight}`}
                role="group"
                aria-label={`Detected regions (${blocks.length})`}
              >
                {blocks.map((b) => {
                  const r = toRect(b.bbox);
                  const isSelected = b.id === selectedId;
                  return (
                    <rect
                      key={b.id}
                      x={r.x}
                      y={r.y}
                      width={r.width}
                      height={r.height}
                      className={`overlay-rect ${isSelected ? "overlay-rect-selected" : ""}`}
                      vectorEffect="non-scaling-stroke"
                      tabIndex={-1}
                      role="button"
                      aria-label={`Region ${b.id}: ${b.label}`}
                      onClick={() => onSelect(b.id)}
                    />
                  );
                })}
              </svg>
            )}
          </div>
        </figure>
      ) : (
        <div className="image-empty">
          <p className="dropzone-hint">The document preview and detected regions appear here.</p>
        </div>
      )}
    </div>
  );
}
