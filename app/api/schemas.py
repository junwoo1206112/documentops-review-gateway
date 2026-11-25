"""API 요청/응답 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DecisionRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reviewer_alias: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reviewer_alias", "reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("공백만으로는 입력할 수 없습니다.")
        return value
