"""거래처 레지스트리. 외부 조회 없이 로컬 JSON만 사용한다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError
from app.services.textnorm import normalize_vendor


@dataclass(frozen=True)
class VendorRegistry:
    version: str
    vendors: frozenset[str]

    @classmethod
    def load(cls, path: Path) -> VendorRegistry:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AppError(
                f"거래처 레지스트리를 찾을 수 없습니다: {path}",
                code="E_VENDOR_REGISTRY",
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError(
                f"거래처 레지스트리를 읽을 수 없습니다: {path}",
                code="E_VENDOR_REGISTRY",
            ) from exc
        try:
            version = str(payload["registry_version"])
            vendors = frozenset(normalize_vendor(item) for item in payload["vendors"])
        except (KeyError, TypeError) as exc:
            raise AppError(
                "거래처 레지스트리 형식이 올바르지 않습니다.",
                code="E_VENDOR_REGISTRY",
            ) from exc
        return cls(version=version, vendors=vendors)

    def contains(self, name: str | None) -> bool:
        if not name:
            return False
        return normalize_vendor(name) in self.vendors
