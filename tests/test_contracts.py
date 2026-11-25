"""문서 계약과 코드 계약의 드리프트를 막는 테스트.

이 테스트가 실패하면 구현이 아니라 계약(문서 또는 코드)이 어긋난 것이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domain import fields, rules, statuses
from app.version import APP_VERSION, DATASET_VERSION, EXTRACTOR_VERSION, RULESET_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (PROJECT_ROOT / "docs" / "schema.md").read_text(encoding="utf-8")
RULES_DOC = (PROJECT_ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
EVAL_DOC = (PROJECT_ROOT / "docs" / "evaluation.md").read_text(encoding="utf-8")
README = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")


def test_every_status_is_in_schema_table() -> None:
    for status in statuses.STATUSES:
        assert f"| `{status}` |" in SCHEMA, f"{status} 상태가 docs/schema.md 표에 없습니다"


def test_every_transition_is_in_schema_table() -> None:
    for source, targets in statuses.TRANSITIONS.items():
        for target in targets:
            assert f"| `{source}` | `{target}` |" in SCHEMA, (
                f"{source} -> {target} 전이가 docs/schema.md 표에 없습니다"
            )


def test_forbidden_transition_is_documented_and_enforced() -> None:
    for source, target in statuses.FORBIDDEN_TRANSITIONS:
        assert f"| `{source}` | `{target}` |" in SCHEMA
        assert not statuses.can_transition(source, target)
        with pytest.raises(statuses.InvalidTransition):
            statuses.assert_transition(source, target)


def test_transition_targets_are_known_statuses() -> None:
    known = set(statuses.STATUSES)
    assert set(statuses.TRANSITIONS) == known
    for targets in statuses.TRANSITIONS.values():
        assert targets <= known


def test_every_status_has_label() -> None:
    assert set(statuses.STATUS_LABELS) == set(statuses.STATUSES)


def test_every_rule_is_in_rules_doc_with_severity() -> None:
    for rule in rules.RULES:
        assert f"| `{rule.rule_id}` | `{rule.severity}` |" in RULES_DOC, (
            f"{rule.rule_id} 규칙이 docs/rules.md 카탈로그와 다릅니다"
        )


def test_rule_ids_are_unique() -> None:
    assert len(rules.RULE_IDS) == len(set(rules.RULE_IDS))


def test_mvp_has_no_warning_rules() -> None:
    """엔진은 blocking만 집계한다. warning 규칙이 생기면 판정 로직도 함께 바뀌어야 한다."""
    assert rules.SEVERITIES == ("blocking", "warning")
    assert all(rule.severity == rules.SEVERITY_BLOCKING for rule in rules.RULES)


def test_every_field_is_in_schema_table() -> None:
    for key in fields.FIELD_KEYS:
        assert f"| `{key}` |" in SCHEMA, f"{key} 필드가 docs/schema.md 표에 없습니다"
    for key in fields.ITEM_FIELD_KEYS:
        assert f"| `items[].{key}` |" in SCHEMA, (
            f"items[].{key} 필드가 docs/schema.md 표에 없습니다"
        )
    for key, label in fields.FIELD_LABELS.items():
        assert key in fields.FIELD_KEYS + fields.ITEM_FIELD_KEYS + ("items",)
        assert label in SCHEMA


def test_required_fields_are_known() -> None:
    known = set(fields.FIELD_KEYS) | {"items"}
    assert set(fields.REQUIRED_FIELDS) <= known


def test_evaluation_metrics_are_documented() -> None:
    for metric in (
        "field_exact_match",
        "document_exact_match",
        "hold_recall",
        "false_hold_rate",
        "rule_match",
        "evidence_validity",
        "p50_ms",
        "p95_ms",
        "failures",
        "limitations",
    ):
        assert metric in EVAL_DOC, f"{metric} 지표가 docs/evaluation.md에 없습니다"


def test_readme_links_resolve() -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    broken: list[str] = []
    for raw_target in link_pattern.findall(README):
        target = raw_target.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        path = (PROJECT_ROOT / target).resolve()
        if not path.exists():
            broken.append(raw_target)
    assert not broken, f"README 링크가 깨졌습니다: {broken}"


def test_env_vars_are_documented_in_example() -> None:
    config_source = (PROJECT_ROOT / "app" / "config.py").read_text(encoding="utf-8")
    used = set(re.findall(r"_env_(?:int|bool|path)\(\s*\"([A-Z_]+)\"", config_source))
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    missing = sorted(name for name in used if name not in example)
    assert not missing, f".env.example에 없는 환경 변수: {missing}"


def test_versions_are_pinned_strings() -> None:
    for value in (APP_VERSION, EXTRACTOR_VERSION, RULESET_VERSION, DATASET_VERSION):
        assert isinstance(value, str) and value
    assert DATASET_VERSION.startswith("synth-")
    assert RULESET_VERSION.startswith("rules-")
    assert EXTRACTOR_VERSION.startswith("deterministic-")
