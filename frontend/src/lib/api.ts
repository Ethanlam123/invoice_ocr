import type { DocumentListEnvelope, Envelope, SaveDocumentBody } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 300_000; // real inference can take a while; 5 min cap

export async function runOcr(file: File): Promise<Envelope> {
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(`${API_BASE}/api/ocr`, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    return (await res.json()) as Envelope;
  } catch (error) {
    const isTimeout = error instanceof DOMException && error.name === "TimeoutError";
    return {
      success: false,
      data: null,
      error: {
        code: isTimeout ? "timeout" : "network_error",
        message: isTimeout
          ? `Request timed out after ${REQUEST_TIMEOUT_MS / 1000} s.`
          : `Cannot reach the API at ${API_BASE}. Is the backend running?`,
      },
      meta: null,
    };
  }
}

export async function fetchHealth(): Promise<Envelope | null> {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    return (await res.json()) as Envelope;
  } catch {
    return null;
  }
}

// null = persistence off (503) or unreachable: the history strip stays hidden
export async function fetchDocuments(): Promise<DocumentListEnvelope | null> {
  try {
    const res = await fetch(`${API_BASE}/api/documents`, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as DocumentListEnvelope;
  } catch {
    return null;
  }
}

export async function fetchDocument(id: number): Promise<Envelope | null> {
  try {
    const res = await fetch(`${API_BASE}/api/documents/${id}`, {
      signal: AbortSignal.timeout(30_000), // pages come back as base64 data URLs
    });
    return (await res.json()) as Envelope;
  } catch {
    return null;
  }
}

// store a completed run the reviewer chose to keep (the Save button);
// null = save failed (network or 4xx/5xx)
export async function saveDocument(body: SaveDocumentBody): Promise<number | null> {
  try {
    const res = await fetch(`${API_BASE}/api/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60_000),
    });
    const env = (await res.json()) as Envelope;
    return typeof env.meta?.document_id === "number" ? env.meta.document_id : null;
  } catch {
    return null;
  }
}

// remove a stored document (rows + page files); false = failed or not found
export async function deleteDocument(id: number): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/documents/${id}`, {
      method: "DELETE",
      signal: AbortSignal.timeout(10_000),
    });
    const env = (await res.json()) as Envelope;
    return env.success === true;
  } catch {
    return false;
  }
}

// store a human correction for one block of a stored document
export async function correctBlock(
  docId: number,
  blockId: number,
  content: string,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/documents/${docId}/blocks/${blockId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corrected_content: content }),
      signal: AbortSignal.timeout(10_000),
    });
    const env = (await res.json()) as Envelope;
    return env.success === true;
  } catch {
    return false;
  }
}
