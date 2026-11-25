"""API 오류 형식. 모든 오류 응답은 {"error": {"code", "message", ...}} 형태다."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "E_INTERNAL"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details

    def to_body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


class NotFoundError(AppError):
    status_code = 404
    code = "E_NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "E_CONFLICT"


class UnprocessableError(AppError):
    status_code = 422
    code = "E_UNPROCESSABLE"


class UnsupportedFileError(AppError):
    status_code = 415
    code = "E_UNSUPPORTED_FILE"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "E_BODY_TOO_LARGE"
