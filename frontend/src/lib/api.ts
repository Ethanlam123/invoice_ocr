import type { Envelope } from "./types";

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
