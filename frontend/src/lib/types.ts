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
  reviewed?: boolean; // a stored human correction overrides this block
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

export interface DocumentSummary {
  id: number;
  filename: string;
  doc_type: string;
  page_count: number;
  quality_flags: string[];
  created_at: string;
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
    document_id?: number;
    doc_type?: string;
    quality_flags?: string[];
    extracted?: Record<string, { value: unknown; block?: number; needs_review?: boolean }>;
    filename?: string;
  } | null;
}

export interface DocumentListEnvelope {
  success: boolean;
  data: { documents: DocumentSummary[] } | null;
  error: ApiError | null;
  meta: Record<string, unknown> | null;
}
