"""DocumentOps UI를 실제로 조작해 포트폴리오용 데모 영상을 녹화한다.

요구 사항: Playwright Python과 Chromium이 설치된 Python.
예: C:\\Users\\junwo\\AppData\\Local\\Programs\\Python\\Python312\\python.exe
     tools\\record_demo.py --output artifacts\\documentops-demo.webm

녹화는 임시 SQLite DB와 로컬 uvicorn만 사용하며, 기존 data/ DB나 외부 서비스는 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover - local recording dependency
    raise SystemExit(
        "Playwright Python이 필요합니다. --help의 예시 Python으로 실행하세요."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "fixtures" / "demo"


def wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            details = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"uvicorn이 시작 전에 종료됐습니다.\n{details}")
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    process.terminate()
    details = process.stderr.read() if process.stderr else ""
    raise RuntimeError(f"20초 안에 로컬 서버가 준비되지 않았습니다.\n{details}")


def pause(page, seconds: float = 7.0) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def upload(page, base_url: str, filename: str) -> str:
    page.goto(f"{base_url}/")
    page.locator("#file").set_input_files(str(DEMO_DIR / filename))
    page.get_by_role("button", name="업로드하고 검증").click()
    page.wait_for_url("**/documents/*")
    pause(page)
    return page.url


def add_disclosure(page) -> None:
    page.evaluate(
        """() => {
          const notice = document.createElement('div');
          notice.id = 'recording-disclosure';
          notice.textContent = '합성 데이터 · 외부 시스템 실행 없음(mock) · 사람만 승인 가능';
          Object.assign(notice.style, {
            position: 'fixed', top: '18px', left: '18px', zIndex: '9999',
            background: '#111827', color: '#ffffff', padding: '12px 16px',
            borderRadius: '8px', fontSize: '18px', fontWeight: '700'
          });
          document.body.append(notice);
        }"""
    )


def remove_disclosure(page) -> None:
    page.evaluate("() => document.querySelector('#recording-disclosure')?.remove()")


def record(base_url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(output.parent),
            record_video_size={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.goto(f"{base_url}/")
        add_disclosure(page)
        pause(page, 7)
        remove_disclosure(page)

        normal_url = upload(page, base_url, "DEMO-0001.txt")
        hold_url = upload(page, base_url, "DEMO-0002.txt")
        duplicate_source_url = upload(page, base_url, "DEMO-0003.txt")
        upload(page, base_url, "DEMO-0004.txt")

        page.goto(normal_url)
        page.get_by_label("검토자 별칭").fill("reviewer-a")
        page.get_by_label("사유").fill("원문 대조 완료: 수량·단가·총액 확인")
        page.get_by_role("button", name="승인", exact=True).click()
        page.wait_for_url("**/documents/*")
        pause(page)

        # 브라우저 필수 입력 검증을 우회해 서버의 422 응답을 화면에 남긴다.
        page.goto(duplicate_source_url)
        page.get_by_label("검토자 별칭").fill("reviewer-a")
        page.locator("textarea[name='reason']").evaluate("node => node.removeAttribute('required')")
        page.get_by_role("button", name="승인", exact=True).click()
        pause(page)

        # HOLD 화면의 비활성화는 UI 안전장치다. 서버가 우회 요청도 409로 막는 장면을 녹화한다.
        page.goto(hold_url)
        page.get_by_label("검토자 별칭").fill("reviewer-a")
        page.get_by_label("사유").fill("영상용 서버 차단 확인")
        page.get_by_role("button", name="승인", exact=True).evaluate(
            "node => node.removeAttribute('disabled')"
        )
        page.get_by_role("button", name="승인", exact=True).click()
        pause(page)

        source = Path(page.video.path())
        context.close()
        browser.close()
    shutil.move(str(source), output)


def main() -> int:
    parser = argparse.ArgumentParser(description="DocumentOps 55초 UI 데모를 WebM으로 녹화")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "documentops-demo.webm")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    with tempfile.TemporaryDirectory(prefix="documentops-demo-") as temp_dir:
        environment = {
            **os.environ,
            "DOCUMENTS_DB_PATH": str(Path(temp_dir) / "recording.db"),
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
                str(args.port),
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            wait_for_server(base_url, server)
            record(base_url, args.output)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
    print(f"녹화 완료: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
