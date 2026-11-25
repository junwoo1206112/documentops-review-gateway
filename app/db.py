"""SQLite 저장소. 감사 이벤트는 DB 트리거로 append-only를 강제한다."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.domain.models import ExistingDocument
from app.domain.statuses import STATUSES

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'text',
    status TEXT NOT NULL,
    doc_no TEXT,
    duplicate_of TEXT,
    extractor_version TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_sha ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_documents_doc_no ON documents(doc_no);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id),
    ordinal INTEGER NOT NULL,
    path TEXT NOT NULL,
    label TEXT NOT NULL,
    value_text TEXT,
    value_json TEXT NOT NULL,
    page INTEGER NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    evidence_excerpt TEXT,
    evidence_status TEXT NOT NULL,
    confidence REAL NOT NULL,
    UNIQUE(document_id, path)
);
CREATE INDEX IF NOT EXISTS idx_fields_document ON extracted_fields(document_id, ordinal);

CREATE TABLE IF NOT EXISTS document_items (
    document_id TEXT NOT NULL REFERENCES documents(id),
    ordinal INTEGER NOT NULL,
    name TEXT,
    qty INTEGER,
    unit_price INTEGER,
    amount INTEGER,
    PRIMARY KEY (document_id, ordinal)
);

CREATE TABLE IF NOT EXISTS validation_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id),
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    path TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_issues_document ON validation_issues(document_id, status);

CREATE TABLE IF NOT EXISTS review_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id),
    decision TEXT NOT NULL,
    reviewer_alias TEXT NOT NULL,
    reason TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_document ON review_decisions(document_id, id);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id),
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    actor TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_document ON audit_events(document_id, id);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def existing_documents(self) -> list[ExistingDocument]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT id, doc_no, sha256, status FROM documents ORDER BY received_at, id"
            ).fetchall()
        return [
            ExistingDocument(
                document_id=row["id"],
                doc_no=row["doc_no"],
                sha256=row["sha256"],
                status=row["status"],
            )
            for row in rows
        ]

    def count_by_status(self) -> dict[str, int]:
        counts = {status: 0 for status in STATUSES}
        with self.read() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM documents GROUP BY status"
            ).fetchall()
        for row in rows:
            counts[row["status"]] = row["count"]
        return counts


def parse_value(raw: str):
    return json.loads(raw)
