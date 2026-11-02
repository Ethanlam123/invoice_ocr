import { describe, expect, it } from "vitest";

import type { Block } from "./types";
import { pageLabel, resultFilename, stepBlockId, toRect } from "./blocks";

const blocks: Block[] = [
  { id: 3, order: 0, label: "text", bbox: [10, 20, 110, 60], content: "a", content_html: null, page: 0, page_end: 0 },
  { id: 7, order: 1, label: "text", bbox: [10, 80, 110, 120], content: "Hong Kong", content_html: null, page: 0, page_end: 0 },
  { id: 11, order: 2, label: "text", bbox: [10, 140, 110, 180], content: "Hong Kong", content_html: null, page: 0, page_end: 0 },
];

describe("toRect", () => {
  it("converts bbox to rect geometry", () => {
    expect(toRect([10, 20, 110, 60])).toEqual({ x: 10, y: 20, width: 100, height: 40 });
  });

  it("is defensive against reversed coordinates", () => {
    expect(toRect([110, 60, 10, 20])).toEqual({ x: 10, y: 20, width: 100, height: 40 });
  });
});

describe("stepBlockId", () => {
  it("steps through reading order by stable id, not text", () => {
    expect(stepBlockId(blocks, 3, 1)).toBe(7);
    expect(stepBlockId(blocks, 7, 1)).toBe(11); // duplicate "Hong Kong" still distinct
    expect(stepBlockId(blocks, 11, -1)).toBe(7);
  });

  it("clamps at both ends", () => {
    expect(stepBlockId(blocks, 3, -1)).toBe(3);
    expect(stepBlockId(blocks, 11, 1)).toBe(11);
  });

  it("enters from the correct end when nothing is selected", () => {
    expect(stepBlockId(blocks, null, 1)).toBe(3);
    expect(stepBlockId(blocks, null, -1)).toBe(11);
  });
});

describe("resultFilename", () => {
  it("produces a sortable json filename", () => {
    expect(resultFilename()).toMatch(/^ocr-result-\d{4}-\d{2}-\d{2}T.*\.json$/);
  });
});

describe("pageLabel", () => {
  it("labels a single-page block", () => {
    expect(pageLabel({ page: 0, page_end: 0 })).toBe("p.1");
    expect(pageLabel({ page: 2, page_end: 2 })).toBe("p.3");
  });

  it("labels a cross-page span (merged table)", () => {
    expect(pageLabel({ page: 0, page_end: 1 })).toBe("p.1-2");
  });
});
