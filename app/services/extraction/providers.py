"""선택형 추출 provider 구성.

실제 모델 호출은 아직 지원하지 않는다. ``llm-contract-stub``은 네트워크·키 없이
LLM 어댑터가 지켜야 할 결과 계약과 evidence 게이트만 검증하는 오프라인 하네스다.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.extraction.base import ExtractionProvider, ExtractionResult
from app.services.extraction.deterministic import DeterministicExtractor

DETERMINISTIC_PROVIDER = "deterministic"
LLM_CONTRACT_STUB_PROVIDER = "llm-contract-stub"
SUPPORTED_PROVIDERS = frozenset({DETERMINISTIC_PROVIDER, LLM_CONTRACT_STUB_PROVIDER})


class ExtractionProviderError(Exception):
    """선택형 provider가 결과 계약을 만들지 못했을 때의 명시적 실패."""


class OfflineLLMContractStub:
    """외부 호출 없이 ExtractionProvider 경계만 재현하는 LLM 어댑터 스텁.

    생산 LLM으로 오해되지 않도록 기본 provider가 아니며, 모델명·키·네트워크는 없다.
    결과는 기존 결정론적 추출기를 통해 만들어지고 이후에도 evidence 검증을 반드시 거친다.
    """

    version = "llm-contract-stub-0.1.0"

    def __init__(self, responder: Callable[[str], ExtractionResult] | None = None) -> None:
        self._responder = responder or DeterministicExtractor().extract

    def extract(self, raw_text: str) -> ExtractionResult:
        try:
            result = self._responder(raw_text)
        except Exception as exc:
            raise ExtractionProviderError("오프라인 LLM 계약 스텁이 추출에 실패했습니다.") from exc
        if not isinstance(result, ExtractionResult):
            raise ExtractionProviderError("provider 결과가 ExtractionResult 계약을 지키지 않습니다.")
        return result


def build_extractor(name: str) -> ExtractionProvider:
    """명시적으로 선택된 provider만 구성한다. 기본값은 deterministic이다."""
    if name == DETERMINISTIC_PROVIDER:
        return DeterministicExtractor()
    if name == LLM_CONTRACT_STUB_PROVIDER:
        return OfflineLLMContractStub()
    supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
    raise ValueError(f"지원하지 않는 EXTRACTION_PROVIDER입니다: {name!r} (허용: {supported})")
