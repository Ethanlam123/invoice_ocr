import type { Block } from "./types";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** bbox [x1,y1,x2,y2] -> SVG rect geometry (defensive against reversed coords). */
export function toRect(bbox: number[]): Rect {
  const [x1, y1, x2, y2] = bbox;
  return {
    x: Math.min(x1, x2),
    y: Math.min(y1, y2),
    width: Math.abs(x2 - x1),
    height: Math.abs(y2 - y1),
  };
}

/** Id of the block `delta` positions from `currentId` in reading order (null if none). */
export function stepBlockId(blocks: Block[], currentId: number | null, delta: 1 | -1): number | null {
  if (blocks.length === 0) return null;
  const index = blocks.findIndex((b) => b.id === currentId);
  if (index === -1) return delta > 0 ? blocks[0].id : blocks[blocks.length - 1].id;
  const next = index + delta;
  if (next < 0 || next >= blocks.length) return blocks[index].id;
  return blocks[next].id;
}

export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function resultFilename(): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `ocr-result-${stamp}.json`;
}
