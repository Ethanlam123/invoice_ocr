"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import "@/components/ocr-viewer/viewer.css";

import { deleteDocument, fetchDocuments } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";
import "./history.css";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export default function HistoryPage() {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null); // null = off/unreachable
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchDocuments().then((env) => {
      setLoaded(true);
      setDocs(env?.data?.documents ?? null);
    });
  }, []);

  useEffect(load, [load]);

  const handleDelete = useCallback(
    async (doc: DocumentSummary) => {
      if (!window.confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
      setBusyId(doc.id);
      const ok = await deleteDocument(doc.id);
      setBusyId(null);
      if (!ok) {
        setError(`Could not delete "${doc.filename}". Try again.`);
        return;
      }
      setError(null);
      load();
    },
    [load],
  );

  const q = query.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      (docs ?? []).filter(
        (d) =>
          !q || d.filename.toLowerCase().includes(q) || d.doc_type.toLowerCase().includes(q),
      ),
    [docs, q],
  );

  return (
    <div className="history-page">
      <header className="history-head">
        <div>
          <h1>Stored documents</h1>
          <p className="history-sub">
            Everything saved to the database. Click a filename to reopen it in the viewer.
          </p>
        </div>
        <div className="history-actions">
          <input
            type="search"
            className="history-search"
            placeholder="Search filename or type"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search documents"
          />
          <Link href="/" className="btn">
            Back to viewer
          </Link>
        </div>
      </header>

      {error && (
        <p className="history-error" role="alert">
          {error}
        </p>
      )}

      {!loaded ? (
        <p className="history-note">Loading...</p>
      ) : docs == null ? (
        <p className="history-note">
          History is unavailable - persistence is off (no DATABASE_URL) or the backend is
          unreachable.
        </p>
      ) : (
        <table className="history-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Filename</th>
              <th>Type</th>
              <th>Pages</th>
              <th>Blocks</th>
              <th>Reviewed</th>
              <th>Flags</th>
              <th>Saved</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((doc) => (
              <tr key={doc.id} className={busyId === doc.id ? "history-row-busy" : ""}>
                <td className="history-num">{doc.id}</td>
                <td>
                  <Link href={`/?doc=${doc.id}`} className="history-open">
                    {doc.filename}
                  </Link>
                </td>
                <td className="history-type">{doc.doc_type}</td>
                <td className="history-num">{doc.page_count}</td>
                <td className="history-num">{doc.block_count ?? "-"}</td>
                <td className="history-num">
                  {doc.block_count == null
                    ? "-"
                    : `${doc.reviewed_count ?? 0}/${doc.block_count}`}
                </td>
                <td className="history-flags" title={doc.quality_flags.join("\n")}>
                  {doc.quality_flags.length > 0 ? doc.quality_flags.join(", ") : "-"}
                </td>
                <td className="history-time">{formatTime(doc.created_at)}</td>
                <td>
                  <button
                    type="button"
                    className="btn history-delete"
                    disabled={busyId === doc.id}
                    onClick={() => handleDelete(doc)}
                  >
                    {busyId === doc.id ? "Deleting..." : "Delete"}
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="history-note">
                  {docs.length === 0
                    ? "Nothing saved yet - run OCR and press Save to history."
                    : "No document matches the search."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
