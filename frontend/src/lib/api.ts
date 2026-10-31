import type { Envelope } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const NETWORK_ERROR: Envelope = {
  success: false,
  data: null,
  error: {
    code: "network_error",
    message: `Cannot reach the API at ${API_BASE}. Is the backend running?`,
  },
  meta: null,
};

export async function runOcr(file: File): Promise<Envelope> {
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(`${API_BASE}/api/ocr`, { method: "POST", body: form });
    const body = (await res.json()) as Envelope;
    if (!res.ok && body?.error) return body;
    return body;
  } catch {
    return NETWORK_ERROR;
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
