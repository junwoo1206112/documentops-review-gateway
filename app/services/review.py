"""검토 서비스: 업로드·재검증·사람 판정·감사 이력.

규칙 3가지를 코드로 강제한다.
1. blocking 이슈가 있으면 HOLD.
2. HOLD에서 승인으로 바로 갈 수 없다.
3. 승인/반려에는 별칭과 사유가 필요하고, 모든 변경은 append-only 감사에 남는다.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.db import Database
from app.domain.statuses import (
    DECISIONS,
    STATUSES,
    TERMINAL_STATUSES,
    InvalidTransition,
    assert_transition,
)
from app.errors import ConflictError, NotFoundError, UnprocessableError
from app.services.ingestion import ingest_bytes
from app.services.pipeline import process_document
from app.services.vendors import VendorRegistry
from app.version import EXTRACTOR_VERSION, RULESET_VERSION

EVENT_INGESTED = "DOCUMENT_INGESTED"
EVENT_VALIDATED = "VALIDATION_COMPLETED"
EVENT_REVALIDATED = "REVALIDATED"
EVENT_DECISION = "DECISION_RECORDED"

DECISION_TARGETS = {"APPROVE": "APPROVED", "REJECT": "REJECTED"}
ALIAS_MAX = 40
REASON_MAX = 500


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class ReviewService:
    def __init__(self, settings: Settings, registry: VendorRegistry, db: Database) -> None:
        self.settings = settings
        self.registry = registry
        self.db = db

    # ------------------------------------------------------------------ ingest
    def ingest(self, filename: str, data: bytes) -> dict[str, Any]:
        document = ingest_bytes(filename, data, max_bytes=self.settings.max_upload_bytes)
        existing = tuple(self.db.existing_documents())
        result = process_document(
            document.raw_text,
            sha256=document.sha256,
            registry=self.registry,
            existing=existing,
        )
        document_id = uuid.uuid4().hex
        now = utcnow()
        doc_no_field = result.by_path().get("doc_no")
        doc_no = (
            doc_no_field.value if doc_no_field and isinstance(doc_no_field.value, str) else None
        )

        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, filename, sha256, raw_text, size_bytes, source_kind, status,
                    doc_no, duplicate_of, extractor_version, ruleset_version, received_at
                ) VALUES (?, ?, ?, ?, ?, 'text', ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    document.filename,
                    document.sha256,
                    document.raw_text,
                    document.size_bytes,
                    result.status,
                    doc_no,
                    result.duplicate_of,
                    EXTRACTOR_VERSION,
                    RULESET_VERSION,
                    now,
                ),
            )
            self._insert_fields(connection, document_id, result)
            self._insert_issues(connection, document_id, result.issues, now)
            self._insert_audit(
                connection,
                document_id,
                EVENT_INGESTED,
                None,
                "INGESTED",
                "system",
                {"filename": document.filename, "sha256": document.sha256},
                now,
            )
            self._insert_audit(
                connection,
                document_id,
                EVENT_VALIDATED,
                "INGESTED",
                result.status,
                "system",
                {
                    "issue_count": len(result.issues),
                    "rule_ids": [issue.rule_id for issue in result.issues],
                    "extractor_version": EXTRACTOR_VERSION,
                    "ruleset_version": RULESET_VERSION,
                },
                now,
            )
        return self.get(document_id)

    # --------------------------------------------------------------- revalidate
    def revalidate(self, document_id: str) -> dict[str, Any]:
        document = self._require_document(document_id)
        current = document["status"]
        if current in TERMINAL_STATUSES:
            raise ConflictError(f"{current} 문서는 재검증할 수 없습니다.")

        existing = tuple(
            item for item in self.db.existing_documents() if item.document_id != document_id
        )
        result = process_document(
            document["raw_text"],
            sha256=document["sha256"],
            registry=self.registry,
            existing=existing,
        )
        target = result.status
        if target != current:
            try:
                assert_transition(current, target)
            except InvalidTransition as exc:
                raise ConflictError(str(exc)) from exc

        now = utcnow()
        with self.db.transaction() as connection:
            updated = connection.execute(
                "UPDATE documents SET status = ?, duplicate_of = ? WHERE id = ? AND status = ?",
                (target, result.duplicate_of, document_id, current),
            )
            if updated.rowcount != 1:
                raise ConflictError(
                    "다른 요청이 먼저 상태를 바꿨습니다. 새로고침 후 다시 시도하세요."
                )
            connection.execute(
                "UPDATE validation_issues SET status = 'resolved' "
                "WHERE document_id = ? AND status = 'open'",
                (document_id,),
            )
            self._insert_issues(connection, document_id, result.issues, now)
            self._insert_audit(
                connection,
                document_id,
                EVENT_REVALIDATED,
                current,
                target,
                "system",
                {
                    "issue_count": len(result.issues),
                    "rule_ids": [issue.rule_id for issue in result.issues],
                },
                now,
            )
        return self.get(document_id)

    # ----------------------------------------------------------------- decision
    def decide(
        self,
        document_id: str,
        *,
        decision: str,
        reviewer_alias: str,
        reason: str,
    ) -> dict[str, Any]:
        if decision not in DECISIONS:
            raise UnprocessableError(f"decision은 {', '.join(DECISIONS)} 중 하나여야 합니다.")
        alias = (reviewer_alias or "").strip()
        cleaned_reason = (reason or "").strip()
        if not alias:
            raise UnprocessableError("검토자 별칭은 필수입니다.")
        if not cleaned_reason:
            raise UnprocessableError("승인·반려 사유는 필수입니다.")
        if len(alias) > ALIAS_MAX:
            raise UnprocessableError(f"검토자 별칭은 {ALIAS_MAX}자 이하여야 합니다.")
        if len(cleaned_reason) > REASON_MAX:
            raise UnprocessableError(f"사유는 {REASON_MAX}자 이하여야 합니다.")

        document = self._require_document(document_id)
        current = document["status"]
        target = DECISION_TARGETS[decision]
        try:
            assert_transition(current, target)
        except InvalidTransition as exc:
            raise ConflictError(
                f"{current} 문서를 {target}로 바꿀 수 없습니다. 보류 문서는 재검증으로 "
                "검토 대기 상태를 거쳐야 합니다."
            ) from exc

        now = utcnow()
        with self.db.transaction() as connection:
            updated = connection.execute(
                "UPDATE documents SET status = ? WHERE id = ? AND status = ?",
                (target, document_id, current),
            )
            if updated.rowcount != 1:
                raise ConflictError("다른 판정이 먼저 기록되었습니다. 새로고침 후 다시 시도하세요.")
            connection.execute(
                """
                INSERT INTO review_decisions (
                    document_id, decision, reviewer_alias, reason, from_status, to_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, decision, alias, cleaned_reason, current, target, now),
            )
            self._insert_audit(
                connection,
                document_id,
                EVENT_DECISION,
                current,
                target,
                alias,
                {"decision": decision, "reason": cleaned_reason},
                now,
            )
        return self.get(document_id)

    # ------------------------------------------------------------------- reads
    def list_documents(
        self, *, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        if status is not None and status not in STATUSES:
            raise UnprocessableError(f"알 수 없는 상태입니다: {status}")
        where = " WHERE d.status = ?" if status else ""
        params: list[Any] = [status] if status else []
        with self.db.read() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS count FROM documents d{where}", params
            ).fetchone()["count"]
            rows = connection.execute(
                f"""
                SELECT d.id, d.filename, d.status, d.received_at, d.doc_no, d.duplicate_of,
                       (SELECT COUNT(*) FROM validation_issues i
                         WHERE i.document_id = d.id AND i.status = 'open'
                           AND i.severity = 'blocking') AS blocking_count,
                       (SELECT f.value_text FROM extracted_fields f
                         WHERE f.document_id = d.id AND f.path = 'vendor') AS vendor,
                       (SELECT f.value_text FROM extracted_fields f
                         WHERE f.document_id = d.id AND f.path = 'total') AS total
                FROM documents d{where}
                ORDER BY d.received_at DESC, d.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], total

    def get(self, document_id: str) -> dict[str, Any]:
        document = self._require_document(document_id)
        with self.db.read() as connection:
            field_rows = connection.execute(
                "SELECT * FROM extracted_fields WHERE document_id = ? ORDER BY ordinal",
                (document_id,),
            ).fetchall()
            item_rows = connection.execute(
                "SELECT * FROM document_items WHERE document_id = ? ORDER BY ordinal",
                (document_id,),
            ).fetchall()
            issue_rows = connection.execute(
                "SELECT * FROM validation_issues WHERE document_id = ? AND status = 'open' "
                "ORDER BY rule_id, path, id",
                (document_id,),
            ).fetchall()
            decision_rows = connection.execute(
                "SELECT * FROM review_decisions WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
            audit_rows = connection.execute(
                "SELECT * FROM audit_events WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()

        return {
            "document": {
                "id": document["id"],
                "filename": document["filename"],
                "sha256": document["sha256"],
                "size_bytes": document["size_bytes"],
                "source_kind": document["source_kind"],
                "status": document["status"],
                "doc_no": document["doc_no"],
                "duplicate_of": document["duplicate_of"],
                "extractor_version": document["extractor_version"],
                "ruleset_version": document["ruleset_version"],
                "received_at": document["received_at"],
            },
            "fields": [
                {
                    "path": row["path"],
                    "label": row["label"],
                    "value": json.loads(row["value_json"]),
                    "value_text": row["value_text"],
                    "page": row["page"],
                    "char_start": row["char_start"],
                    "char_end": row["char_end"],
                    "evidence_excerpt": row["evidence_excerpt"],
                    "evidence_status": row["evidence_status"],
                    "confidence": row["confidence"],
                }
                for row in field_rows
            ],
            "items": [
                {
                    "ordinal": row["ordinal"],
                    "name": row["name"],
                    "qty": row["qty"],
                    "unit_price": row["unit_price"],
                    "amount": row["amount"],
                }
                for row in item_rows
            ],
            "issues": [
                {
                    "rule_id": row["rule_id"],
                    "severity": row["severity"],
                    "path": row["path"],
                    "message": row["message"],
                    "status": row["status"],
                }
                for row in issue_rows
            ],
            "decisions": [
                {
                    "decision": row["decision"],
                    "reviewer_alias": row["reviewer_alias"],
                    "reason": row["reason"],
                    "from_status": row["from_status"],
                    "to_status": row["to_status"],
                    "created_at": row["created_at"],
                }
                for row in decision_rows
            ],
            "audit": [
                {
                    "event_id": row["id"],
                    "event_type": row["event_type"],
                    "from_status": row["from_status"],
                    "to_status": row["to_status"],
                    "actor": row["actor"],
                    "metadata": json.loads(row["metadata_json"]),
                    "created_at": row["created_at"],
                }
                for row in audit_rows
            ],
            "raw_text": document["raw_text"],
        }

    def audit(self, document_id: str) -> list[dict[str, Any]]:
        self._require_document(document_id)
        with self.db.read() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
        return [
            {
                "event_id": row["id"],
                "event_type": row["event_type"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "actor": row["actor"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ helpers
    def _require_document(self, document_id: str) -> Any:
        with self.db.read() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("문서를 찾을 수 없습니다.")
        return row

    def _insert_fields(self, connection, document_id: str, result) -> None:
        connection.executemany(
            """
            INSERT INTO extracted_fields (
                document_id, ordinal, path, label, value_text, value_json, page,
                char_start, char_end, evidence_excerpt, evidence_status, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    document_id,
                    ordinal,
                    field.path,
                    field.label,
                    field.value_text,
                    json.dumps(field.value, ensure_ascii=False),
                    field.page,
                    field.char_start,
                    field.char_end,
                    field.evidence_excerpt,
                    field.evidence_status,
                    field.confidence,
                )
                for ordinal, field in enumerate(result.fields)
            ],
        )
        connection.executemany(
            """
            INSERT INTO document_items (document_id, ordinal, name, qty, unit_price, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (document_id, item.ordinal, item.name, item.qty, item.unit_price, item.amount)
                for item in result.items
            ],
        )

    def _insert_issues(self, connection, document_id: str, issues: Sequence, now: str) -> None:
        connection.executemany(
            """
            INSERT INTO validation_issues (
                document_id, rule_id, severity, path, message, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?)
            """,
            [
                (document_id, issue.rule_id, issue.severity, issue.path, issue.message, now)
                for issue in issues
            ],
        )

    def _insert_audit(
        self,
        connection,
        document_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor: str,
        metadata: dict[str, Any],
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (
                document_id, event_type, from_status, to_status, actor, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                event_type,
                from_status,
                to_status,
                actor,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
