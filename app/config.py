"""환경 변수 기반 설정. 비밀키·외부 API는 사용하지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_SUFFIXES: tuple[str, ...] = (".txt",)

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "documentops.db"
DEFAULT_VENDOR_REGISTRY_PATH = PROJECT_ROOT / "fixtures" / "vendors.json"
DEFAULT_EVALUATION_DIR = PROJECT_ROOT / "fixtures" / "evaluation"
DEFAULT_DEMO_DIR = PROJECT_ROOT / "fixtures" / "demo"
DEFAULT_ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

DEFAULT_MAX_UPLOAD_BYTES = 512 * 1024
DEFAULT_RATE_LIMIT_PER_MINUTE = 120


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    vendor_registry_path: Path = DEFAULT_VENDOR_REGISTRY_PATH
    evaluation_dir: Path = DEFAULT_EVALUATION_DIR
    demo_dir: Path = DEFAULT_DEMO_DIR
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    trust_proxy_headers: bool = False
    public_demo_read_only: bool = False
    extraction_provider: str = "deterministic"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=_env_path("DOCUMENTS_DB_PATH", DEFAULT_DB_PATH),
            vendor_registry_path=_env_path("VENDOR_REGISTRY_PATH", DEFAULT_VENDOR_REGISTRY_PATH),
            evaluation_dir=_env_path("EVALUATION_DIR", DEFAULT_EVALUATION_DIR),
            demo_dir=_env_path("DEMO_DIR", DEFAULT_DEMO_DIR),
            artifacts_dir=_env_path("ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR),
            max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
            rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE),
            trust_proxy_headers=_env_bool("TRUST_PROXY_HEADERS", False),
            public_demo_read_only=_env_bool("PUBLIC_DEMO_READ_ONLY", False),
            extraction_provider=os.getenv("EXTRACTION_PROVIDER", "deterministic").strip()
            or "deterministic",
        )

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
