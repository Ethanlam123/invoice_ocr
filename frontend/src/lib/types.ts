export interface Block {
  id: number;
  order: number;
  label: string;
  bbox: number[];
  content: string;
  content_html: string | null;
}

export interface ImageInfo {
  width: number;
  height: number;
  mime: string;
  data_url: string;
}

export interface OcrData {
  image: ImageInfo;
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
  } | null;
}
