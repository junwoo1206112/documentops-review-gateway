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
from app.domain.fields import FIELD_KEYS, FIELD_LABELS, MONEY_FIELDS
from app.domain.models import FieldCorrection
from app.domain.statuses import (
    DECISIONS,
    STATUSES,
    TERMINAL_STATUSES,
    InvalidTransition,
    assert_transition,
)
from app.errors import ConflictError, NotFoundError, UnprocessableError
from app.services.evidence import normalized_matches
from app.services.ingestion import ingest_bytes
from app.services.pipeline import process_document
from app.services.textnorm import (
    is_valid_doc_no,
    normalize_doc_no,
    normalize_vendor,
    parse_iso_date,
    parse_money,
)
from app.services.vendors import VendorRegistry
from app.version import EXTRACTOR_VERSION, RULESET_VERSION

EVENT_INGESTED = "DOCUMENT_INGESTED"
EVENT_VALIDATED = "VALIDATION_COMPLETED"
EVENT_REVALIDATED = "REVALIDATED"
EVENT_DECISION = "DECISION_RECORDED"
EVENT_CORRECTION = "CORRECTION_RECORDED"

DECISION_TARGETS = {"APPROVE": "APPROVED", "REJECT": "REJECTED"}
CORRECTABLE_FIELDS = frozenset(FIELD_KEYS)
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

        corrections = self._effective_corrections(document_id)
        result = self._process(document, corrections)
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
                    "corrections_applied": len(corrections),
                },
                now,
            )
        return self.get(document_id)

    # --------------------------------------------------------------- correction
    def record_correction(
        self,
        document_id: str,
        *,
        path: str,
        value: str | int,
        reviewer_alias: str,
        reason: str,
        excerpt: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
    ) -> dict[str, Any]:
        """원문 재인용으로 검증되는 필드 수정. 수정 후 항상 재검증하며 승인하지 않는다."""
        alias, cleaned_reason = self._validate_actor(reviewer_alias, reason)
        if path not in CORRECTABLE_FIELDS:
            raise UnprocessableError(
                f"수정할 수 없는 필드입니다: {path}. 허용: {', '.join(sorted(CORRECTABLE_FIELDS))}"
            )

        document = self._require_document(document_id)
        current = document["status"]
        if current in TERMINAL_STATUSES:
            raise ConflictError(f"{current} 문서는 수정할 수 없습니다.")

        raw_text = document["raw_text"]
        span_start, span_end, evidence_text = self._resolve_excerpt(
            raw_text, excerpt=excerpt, char_start=char_start, char_end=char_end
        )
        corrected_value = self._normalize_corrected_value(path, value)
        if not normalized_matches(path, evidence_text, corrected_value):
            raise UnprocessableError(
                "재인용 문구가 수정값과 일치하지 않습니다. 원문에 있는 값을 그대로 인용하세요."
            )

        corrections = self._effective_corrections(document_id)
        before = self._process(document, corrections)
        before_field = before.by_path().get(path)
        from_value = before_field.value if before_field is not None else None

        new_correction = FieldCorrection(
            path=path,
            value=corrected_value,
            excerpt=evidence_text,
            page=1,
            char_start=span_start,
            char_end=span_end,
        )
        merged = [item for item in corrections if item.path != path] + [new_correction]
        result = self._process(document, merged)
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
                """
                INSERT INTO field_corrections (
                    document_id, path, from_value_json, to_value_json, evidence_excerpt,
                    page, char_start, char_end, reviewer_alias, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    path,
                    json.dumps(from_value, ensure_ascii=False),
                    json.dumps(corrected_value, ensure_ascii=False),
                    evidence_text,
                    1,
                    span_start,
                    span_end,
                    alias,
                    cleaned_reason,
                    now,
                ),
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
                EVENT_CORRECTION,
                current,
                current,
                alias,
                {
                    "path": path,
                    "from_value": from_value,
                    "to_value": corrected_value,
                    "evidence_excerpt": evidence_text,
                    "char_start": span_start,
                    "char_end": span_end,
                    "reason": cleaned_reason,
                },
                now,
            )
            self._insert_audit(
                connection,
                document_id,
                EVENT_REVALIDATED,
                current,
                target,
                alias,
                {
                    "issue_count": len(result.issues),
                    "rule_ids": [issue.rule_id for issue in result.issues],
                    "correction_path": path,
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
        alias, cleaned_reason = self._validate_actor(reviewer_alias, reason)

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
            correction_rows = connection.execute(
                "SELECT * FROM field_corrections WHERE document_id = ? ORDER BY id",
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
            "fields": self._field_payload(field_rows),
            "effective_fields": self._effective_field_payload(field_rows, correction_rows),
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
            "corrections": [
                {
                    "path": row["path"],
                    "from_value": json.loads(row["from_value_json"])
                    if row["from_value_json"] is not None
                    else None,
                    "to_value": json.loads(row["to_value_json"]),
                    "evidence_excerpt": row["evidence_excerpt"],
                    "page": row["page"],
                    "char_start": row["char_start"],
                    "char_end": row["char_end"],
                    "reviewer_alias": row["reviewer_alias"],
                    "reason": row["reason"],
                    "created_at": row["created_at"],
                }
                for row in correction_rows
            ],
            "raw_text": document["raw_text"],
        }

    @staticmethod
    def _field_payload(field_rows: Sequence[Any]) -> list[dict[str, Any]]:
        return [
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
                "corrected": False,
            }
            for row in field_rows
        ]

    @staticmethod
    def _effective_field_payload(
        field_rows: Sequence[Any], correction_rows: Sequence[Any]
    ) -> list[dict[str, Any]]:
        """추출값은 보존하고, 수정이 반영된 유효 필드를 별도로 만든다."""
        base = {
            row["path"]: {
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
                "corrected": False,
            }
            for row in field_rows
        }
        original = {path: dict(payload) for path, payload in base.items()}
        for row in correction_rows:
            path = row["path"]
            payload = base.get(path)
            base[path] = {
                "path": path,
                "label": payload["label"] if payload else FIELD_LABELS.get(path, path),
                "value": json.loads(row["to_value_json"]),
                "value_text": row["evidence_excerpt"],
                "page": row["page"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "evidence_excerpt": row["evidence_excerpt"],
                "evidence_status": "verified",
                "confidence": 1.0,
                "corrected": True,
                "original_value": original.get(path, {}).get("value") if path in original else None,
            }
        order = [key for key in FIELD_KEYS if key in base]
        order.extend(path for path in base if path.startswith("items["))
        return [base[path] for path in order]

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
    def _validate_actor(self, reviewer_alias: str, reason: str) -> tuple[str, str]:
        alias = (reviewer_alias or "").strip()
        cleaned_reason = (reason or "").strip()
        if not alias:
            raise UnprocessableError("검토자 별칭은 필수입니다.")
        if not cleaned_reason:
            raise UnprocessableError("검토 사유는 필수입니다.")
        if len(alias) > ALIAS_MAX:
            raise UnprocessableError(f"검토자 별칭은 {ALIAS_MAX}자 이하여야 합니다.")
        if len(cleaned_reason) > REASON_MAX:
            raise UnprocessableError(f"사유는 {REASON_MAX}자 이하여야 합니다.")
        return alias, cleaned_reason

    def _process(self, document: Any, corrections: Sequence[FieldCorrection]):
        existing = tuple(
            item for item in self.db.existing_documents() if item.document_id != document["id"]
        )
        return process_document(
            document["raw_text"],
            sha256=document["sha256"],
            registry=self.registry,
            existing=existing,
            corrections=corrections,
        )

    def _effective_corrections(self, document_id: str) -> list[FieldCorrection]:
        with self.db.read() as connection:
            rows = connection.execute(
                "SELECT * FROM field_corrections WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
        latest: dict[str, Any] = {}
        for row in rows:
            latest[row["path"]] = row
        return [
            FieldCorrection(
                path=row["path"],
                value=json.loads(row["to_value_json"]),
                excerpt=row["evidence_excerpt"],
                page=row["page"],
                char_start=row["char_start"],
                char_end=row["char_end"],
            )
            for row in latest.values()
        ]

    def _resolve_excerpt(
        self,
        raw_text: str,
        *,
        excerpt: str | None,
        char_start: int | None,
        char_end: int | None,
    ) -> tuple[int, int, str]:
        if (char_start is None) != (char_end is None):
            raise UnprocessableError("char_start와 char_end는 함께 지정해야 합니다.")

        if char_start is not None and char_end is not None:
            if not 0 <= char_start < char_end <= len(raw_text):
                raise UnprocessableError("char_start/char_end가 원문 범위를 벗어났습니다.")
            text = raw_text[char_start:char_end]
            if excerpt and excerpt != text:
                raise UnprocessableError("지정한 span과 excerpt가 일치하지 않습니다.")
            if not text.strip():
                raise UnprocessableError("빈 구간은 근거로 쓸 수 없습니다.")
            return char_start, char_end, text

        text = excerpt or ""
        if not text.strip():
            raise UnprocessableError("원문에서 재인용할 문구(excerpt)가 필요합니다.")
        first = raw_text.find(text)
        if first < 0:
            raise UnprocessableError("재인용 문구를 원문에서 찾을 수 없습니다.")
        if raw_text.find(text, first + 1) >= 0:
            raise UnprocessableError(
                "재인용 문구가 원문에 여러 번 나타납니다. API에서 char_start/char_end를 지정하세요."
            )
        return first, first + len(text), text

    def _normalize_corrected_value(self, path: str, value: str | int) -> str | int:
        if path in MONEY_FIELDS:
            number: int | None
            if isinstance(value, bool):
                number = None
            elif isinstance(value, int):
                number = value
            elif isinstance(value, str):
                number = parse_money(value)
            else:
                number = None
            if number is None or number < 0:
                raise UnprocessableError("금액은 0 이상의 원 단위 정수여야 합니다.")
            return number

        if path == "doc_date":
            parsed = parse_iso_date(value if isinstance(value, str) else None)
            if parsed is None:
                raise UnprocessableError("날짜는 YYYY-MM-DD 형식의 실제 날짜여야 합니다.")
            return parsed

        if path == "doc_no":
            normalized = normalize_doc_no(value if isinstance(value, str) else None)
            if not is_valid_doc_no(normalized):
                raise UnprocessableError("문서번호는 ^[A-Z]{2,4}-\\d{4}-\\d{4}$ 형식이어야 합니다.")
            return normalized

        if path == "vendor":
            normalized = normalize_vendor(value if isinstance(value, str) else None)
            if not normalized:
                raise UnprocessableError("거래처는 비어 있을 수 없습니다.")
            return normalized

        raise UnprocessableError(f"수정할 수 없는 필드입니다: {path}")

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
