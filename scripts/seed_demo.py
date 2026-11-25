"""데모 데이터를 실행 중인 서버에 순서대로 접수한다.

python scripts/seed_demo.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "fixtures" / "demo"
ORDER = ("DEMO-0001.txt", "DEMO-0002.txt", "DEMO-0003.txt", "DEMO-0004.txt")


def upload(base_url: str, path: Path) -> dict:
    boundary = "----documentops-demo"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode()
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = request.Request(
        f"{base_url.rstrip('/')}/api/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req) as response:  # noqa: S310 - 로컬 데모 전용
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="데모 문서 4건 접수")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)

    for name in ORDER:
        path = DEMO_DIR / name
        if not path.exists():
            print(f"없음: {path}", file=sys.stderr)
            return 1
        try:
            body = upload(args.base_url, path)
        except error.URLError as exc:
            print(f"서버에 연결할 수 없습니다: {exc}", file=sys.stderr)
            return 1
        document = body["document"]
        rules = ", ".join(issue["rule_id"] for issue in body["issues"]) or "없음"
        print(f"{name}: {document['status']} ({rules}) -> /documents/{document['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
