"""반응형 화면 캡처와 WCAG 대비 측정을 로컬에서 재현한다.

Playwright Python이 필요하다. 이 도구는 임시 DB와 로컬 uvicorn만 사용한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from record_demo import ROOT, wait_for_server

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover - local audit dependency
    raise SystemExit("Playwright Python이 필요합니다.") from exc


COLORS = {
    "body_text": ("#e6e9ef", "#0f1115"),
    "muted_text": ("#9aa3b2", "#0f1115"),
    "accent_link": ("#6ea8fe", "#0f1115"),
    "warning_text": ("#f0b429", "#171a21"),
    "danger_text": ("#ff6b6b", "#171a21"),
    "button_text": ("#0b1020", "#6ea8fe"),
}


def luminance(value: str) -> float:
    channels = tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))
    linear = tuple(
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return round((high + 0.05) / (low + 0.05), 2)


def main() -> int:
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    report = {"contrast": {}, "screenshots": [], "semantic_checks": {}}
    for name, (foreground, background) in COLORS.items():
        ratio = contrast(foreground, background)
        report["contrast"][name] = {"ratio": ratio, "aa_normal_text": ratio >= 4.5}

    with tempfile.TemporaryDirectory(prefix="documentops-a11y-") as temp_dir:
        environment = {
            **os.environ,
            "DOCUMENTS_DB_PATH": str(Path(temp_dir) / "audit.db"),
            "RATE_LIMIT_PER_MINUTE": "0",
            "PYTHONIOENCODING": "utf-8",
        }
        server = subprocess.Popen(
            [
                str(ROOT / ".venv" / "Scripts" / "python.exe"),
                "-m",
                "uvicorn",
                "app.asgi:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8766",
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            base_url = "http://127.0.0.1:8766"
            wait_for_server(base_url, server)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                for width in (768, 1024):
                    page = browser.new_page(viewport={"width": width, "height": 720})
                    page.goto(base_url)
                    destination = output / f"accessibility-{width}.png"
                    page.screenshot(path=str(destination), full_page=True)
                    report["screenshots"].append(str(destination.relative_to(ROOT)))
                    if width == 768:
                        html = page.content()
                        report["semantic_checks"] = {
                            "skip_link": 'href="#main"' in html,
                            "main_landmark": 'id="main"' in html,
                            "filter_current": 'aria-current="page"' in html,
                            "table_caption": 'class="sr-only"' in html,
                        }
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=5)

    report["all_aa_normal_text"] = all(
        entry["aa_normal_text"] for entry in report["contrast"].values()
    )
    report_path = output / "accessibility_audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
