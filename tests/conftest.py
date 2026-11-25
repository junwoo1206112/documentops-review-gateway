from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


def read_doc(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")
