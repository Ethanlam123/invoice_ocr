export interface PageBBox {
  page: number;
  bbox: number[];
}

export interface Block {
  id: number;
  order: number;
  label: string;
  bbox: number[];
  content: string;
  content_html: string | null;
  page: number;
  page_end: number; // > page when the block spans pages (merged cross-page table)
  page_bboxes?: PageBBox[] | null; // one bbox per page on spanning blocks
}

export interface PageInfo {
  index: number;
  width: number;
  height: number;
  mime: string;
  data_url: string;
}

export interface OcrData {
  pages: PageInfo[];
  blocks: Block[];
  markdown: string;
  raw: Record<string, unknown>;
}

export interface ApiError {
  code: string;
  message: string;
}

export interface Envelope {
  success: boolean;
  data: OcrData | null;
  error: ApiError | null;
  meta: {
    elapsed_ms: number;
    model: string;
    mode: string;
    page_count?: number;
  } | null;
}
