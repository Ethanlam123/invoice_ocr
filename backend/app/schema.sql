-- Idempotent schema, applied automatically on first use when DATABASE_URL is set.
-- One wide documents row + page rows + block rows. Type-specific fields stay in
-- JSONB (extracted) so new document types need no DDL change.

CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    filename      TEXT        NOT NULL,
    mime          TEXT        NOT NULL,
    page_count    INT         NOT NULL,
    elapsed_ms    INT         NOT NULL,
    model         TEXT        NOT NULL,
    mode          TEXT        NOT NULL,
    doc_type      TEXT        NOT NULL DEFAULT 'unknown',
    quality_flags JSONB       NOT NULL DEFAULT '[]'::jsonb,
    extracted     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    markdown      TEXT        NOT NULL,
    raw           JSONB       NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_pages (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_index  INT    NOT NULL,
    width       INT    NOT NULL,
    height      INT    NOT NULL,
    image_path  TEXT   NOT NULL,
    UNIQUE (document_id, page_index)
);

-- corrected_content / reviewed_at exist for the (future) review UI so this
-- schema never needs a migration for it.
CREATE TABLE IF NOT EXISTS blocks (
    id                BIGSERIAL PRIMARY KEY,
    document_id       BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_id          INT    NOT NULL,
    block_order       INT    NOT NULL,
    page              INT    NOT NULL DEFAULT 0,
    page_end          INT    NOT NULL DEFAULT 0,
    page_bboxes       JSONB,
    label             TEXT   NOT NULL,
    bbox              DOUBLE PRECISION[4] NOT NULL,
    content           TEXT   NOT NULL,
    content_html      TEXT,
    corrected_content TEXT,
    reviewed_at       TIMESTAMPTZ,
    UNIQUE (document_id, block_id)
);
