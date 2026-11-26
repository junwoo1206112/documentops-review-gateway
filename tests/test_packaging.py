"""패키징·CI·Docker 계약이 실제로 존재하고 최소 요건을 갖췄는지 확인한다."""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_pyproject_declares_runtime_and_dev_dependencies() -> None:
    data = tomllib.loads(read("pyproject.toml"))
    project = data["project"]
    assert project["requires-python"] == ">=3.12"
    runtime = " ".join(project["dependencies"])
    for package in ("fastapi", "uvicorn", "jinja2", "pydantic", "python-multipart"):
        assert package in runtime
    dev = " ".join(project["optional-dependencies"]["dev"])
    for package in ("pytest", "httpx", "ruff"):
        assert package in dev
    assert data["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_package_data_includes_templates_and_static() -> None:
    data = tomllib.loads(read("pyproject.toml"))
    package_data = data["tool"]["setuptools"]["package-data"]["app"]
    assert any("templates" in pattern for pattern in package_data)
    assert any("static" in pattern for pattern in package_data)


def test_dockerfile_is_non_root_and_healthchecked() -> None:
    dockerfile = read("Dockerfile")
    assert "python:3.12-slim" in dockerfile
    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "app.asgi:app" in dockerfile
    assert "0.0.0.0" in dockerfile


def test_compose_uses_volume_and_healthcheck() -> None:
    compose = read("docker-compose.yml")
    assert "build: ." in compose
    assert "documentops-data:/app/data" in compose
    assert "healthcheck:" in compose
    assert "8000:8000" in compose


def test_ci_runs_tests_dataset_and_evaluation_without_secrets() -> None:
    workflow = read(".github/workflows/ci.yml")
    assert "python -m pytest" in workflow
    assert "tools/generate_dataset.py --check" in workflow
    assert "app.evaluate" in workflow
    assert "upload-artifact" in workflow
    lowered = workflow.lower()
    for forbidden in ("api_key", "secrets.", "openai", "anthropic"):
        assert forbidden not in lowered


def test_env_example_has_no_real_looking_secret() -> None:
    example = read(".env.example")
    assert "sk-" not in example
    assert "API_KEY" not in example


def test_security_policy_states_synthetic_data_and_limits() -> None:
    security = read("docs/security.md")
    assert "합성" in security
    assert "append-only" in security
    assert "자동 승인" in security
    assert "비목표" in security


def test_decision_log_lists_deferred_scope() -> None:
    pending = read("docs/decisions/pending.md")
    for item in ("P-001", "P-002", "P-003", "P-004", "P-005", "P-006"):
        assert item in pending
    assert "OCR" in pending


def test_readme_documents_runbook_and_limits() -> None:
    readme = read("README.md")
    for command in (
        "pip install -e",
        "pytest",
        "uvicorn app.asgi:app",
        "python -m app.evaluate",
        "docker compose up --build",
    ):
        assert command in readme
    assert "합성" in readme
    assert "자동 승인" in readme


def test_artifacts_and_db_are_not_tracked_candidates() -> None:
    gitignore = read(".gitignore")
    assert "artifacts/" in gitignore
    assert "data/*.db" in gitignore
    assert ".env" in gitignore


def test_phase_reviews_exist_for_every_phase() -> None:
    reviews = sorted(
        (PROJECT_ROOT / "docs" / "reviews").glob("phase-*.md"),
        key=lambda path: int(path.stem.removeprefix("phase-")),
    )
    assert [path.name for path in reviews] == [
        "phase-0.md",
        "phase-1.md",
        "phase-2.md",
        "phase-3.md",
        "phase-4.md",
        "phase-5.md",
        "phase-6.md",
        "phase-7.md",
        "phase-8.md",
        "phase-9.md",
        "phase-10.md",
        "phase-11.md",
        "phase-12.md",
        "phase-14.md",
    ]


def test_handoff_document_covers_resume_and_backlog() -> None:
    handoff = read("HANDOFF.md")
    for token in (
        "30초 요약",
        "절대 바뀌면 안 되는 계약",
        "실행·검증 런북",
        "남은 작업 백로그",
        "알려진 함정",
        "재개 체크리스트",
        "Definition of Done",
        "R-001",
        "R-002",
    ):
        assert token in handoff, f"HANDOFF.md에 '{token}'이 없습니다"
    assert "docs/ROADMAP_PHASES.md" in handoff


def test_phase_roadmap_preserves_decision_gates() -> None:
    roadmap = read("docs/ROADMAP_PHASES.md")
    for token in (
        "Phase 13",
        "Gate A",
        "P-001",
        "P-002",
        "P-003",
        "P-004",
        "P-005",
        "P-006",
        "Gate D",
        "Phase 14-I",
        "자동 승인 없음",
    ):
        assert token in roadmap


def test_handoff_seed_is_valid_and_tracks_state() -> None:
    import yaml

    data = yaml.safe_load(read("handoff.seed.yaml"))
    assert data["schema"] == "handoff-seed-1"
    assert data["status"] == "phase-14-complete"
    assert data["versions"]["dataset"] == "synth-2026-11-26.2"
    assert data["verified"]["tests_passed"] >= 155
    assert data["verified"]["corrections"]["model"] == "original_quote_only"
    assert data["verified"]["tests_collected_after_phase_6"] == 133
    assert data["verified"]["evaluation_exit_code"] == 0
    assert data["verified"]["ci_remote"]["status"] == "success"
    assert data["verified"]["ci_remote"]["run_url"].endswith("/45697512065")

    task_ids = {task["id"] for task in data["remaining"]}
    assert {"R-001", "R-002", "R-003", "R-004", "R-005", "R-008"} <= task_ids
    assert data["do_not"]
    assert data["resume"]["read_first"][0] == "HANDOFF.md"
    assert data["resume"]["phase_plan"] == "docs/ROADMAP_PHASES.md"
