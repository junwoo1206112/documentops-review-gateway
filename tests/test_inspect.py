from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings
from app.inspect import render

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "fixtures" / "evaluation"


def test_render_shows_hold_reason() -> None:
    output = render(EVAL_DIR / "DOC-0020.txt", Settings())
    assert "HOLD" in output
    assert "INVALID_DOC_NO" in output


def test_cli_entrypoint_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.inspect", str(EVAL_DIR / "DOC-0001.txt")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
    assert "PENDING_REVIEW" in result.stdout
    assert "가온상사" in result.stdout
