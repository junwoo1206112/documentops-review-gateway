"""합성 한국어 업무 문서 36건 + 정답 + manifest 생성기.

원칙
- 같은 입력(코드)에서 항상 같은 바이트가 나온다. 난수는 고정 시드만 쓴다.
- 파일 SHA-256은 manifest에 기록하고, 테스트가 재생성 결과와 비교한다.
- 실제 개인정보·실제 회사 문서를 쓰지 않는다. 모든 값은 이 파일에서 만든 가상 값이다.

사용
    python tools/generate_dataset.py            # 생성/갱신
    python tools/generate_dataset.py --check    # 커밋된 산출물과 일치하는지 검사
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import DATASET_VERSION, VENDOR_REGISTRY_VERSION  # noqa: E402

EVAL_DIR = ROOT / "fixtures" / "evaluation"
DEMO_DIR = ROOT / "fixtures" / "demo"
VENDOR_PATH = ROOT / "fixtures" / "vendors.json"

SEED = 20261126

VENDORS: tuple[str, ...] = (
    "가온상사",
    "누리기계",
    "도담전자",
    "라온산업",
    "마루테크",
    "바른정밀",
    "새솔유통",
    "온빛전자",
    "하람산업",
    "한결기계",
    "다움상사",
    "여울테크",
)
UNKNOWN_VENDORS: tuple[str, ...] = ("미등록물산", "없는상사", "가짜상회")

ITEM_NAMES: tuple[str, ...] = (
    "산업용 볼트 M8",
    "철제 브래킷",
    "알루미늄 프로파일",
    "모터 커플링",
    "베어링 6204",
    "센서 하우징",
    "케이블 타이",
    "스테인리스 와셔",
    "공압 실린더",
    "컨베이어 벨트",
    "제어반 스위치",
    "방열판",
    "리니어 가이드",
    "포장 박스",
    "라벨 롤",
    "에어 필터",
)
UNIT_PRICE_POOL: tuple[int, ...] = (1500, 6250, 3200, 18000, 4700, 8900, 1200, 25000, 3400, 5600)

ITEM_HEADER = "품목명                수량        단가          금액"
DERIVED_TOTAL_NOTE = "※ 총액은 공급가액과 부가세의 합으로 확인함."

CATEGORY_COUNTS: dict[str, int] = {
    "normal": 16,
    "missing_required": 5,
    "invalid_date": 2,
    "invalid_money": 1,
    "line_total_mismatch": 6,
    "duplicate": 2,
    "unknown_vendor": 2,
    "missing_evidence": 2,
}


def round_half_up_vat(supply: int) -> int:
    return (supply + 5) // 10


def money(value: int) -> str:
    return f"{value:,}"


class TextBuilder:
    """세그먼트를 이어 붙이면서 값의 문자 span을 기록한다."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._length = 0
        self.spans: dict[str, dict[str, object]] = {}

    def line(self, *segments: str | tuple[str, str]) -> None:
        for segment in segments:
            if isinstance(segment, tuple):
                key, text = segment
                start = self._length
                self._parts.append(text)
                self._length += len(text)
                self.spans[key] = {
                    "page": 1,
                    "char_start": start,
                    "char_end": self._length,
                    "excerpt": text,
                }
            else:
                self._parts.append(segment)
                self._length += len(segment)
        self._parts.append("\n")
        self._length += 1

    def blank(self) -> None:
        self.line()

    def text(self) -> str:
        return "".join(self._parts)


@dataclass
class Item:
    name: str
    qty: int
    unit_price: int
    amount: int


@dataclass
class Spec:
    doc_id: str
    category: str
    vendor: str | None
    doc_no: str | None
    date_raw: str | None
    items: list[Item]
    supply_raw: str | None
    vat_raw: str | None
    total_raw: str | None
    derive_total: bool = False
    expected_rules: tuple[str, ...] = field(default=())

    @property
    def expected_status(self) -> str:
        return "HOLD" if self.expected_rules else "PENDING_REVIEW"


def normalize_money(raw: str | None) -> int | None:
    if raw is None:
        return None
    cleaned = raw.replace(",", "").replace("원", "").replace("₩", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def parse_date(raw: str | None) -> str | None:
    if raw is None:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.isoformat() if len(raw) == 10 else None


def build_spec(spec: Spec) -> tuple[str, dict[str, object]]:
    builder = TextBuilder()
    builder.line("[거래명세서]")
    if spec.vendor is not None:
        builder.line("거래처: ", ("vendor", spec.vendor))
    if spec.doc_no is not None:
        builder.line("문서번호: ", ("doc_no", spec.doc_no))
    if spec.date_raw is not None:
        builder.line("작성일자: ", ("doc_date", spec.date_raw))
    builder.blank()
    builder.line(ITEM_HEADER)
    for index, item in enumerate(spec.items):
        builder.line(
            (f"items[{index}].name", item.name),
            "  ",
            (f"items[{index}].qty", str(item.qty)),
            "  ",
            (f"items[{index}].unit_price", money(item.unit_price)),
            "  ",
            (f"items[{index}].amount", money(item.amount)),
        )
    builder.blank()
    if spec.supply_raw is not None:
        builder.line("공급가액: ", ("supply_amount", spec.supply_raw))
    if spec.vat_raw is not None:
        builder.line("부가세: ", ("vat", spec.vat_raw))
    if spec.total_raw is not None:
        builder.line("총액: ", ("total", spec.total_raw))
    if spec.derive_total:
        builder.blank()
        builder.line(DERIVED_TOTAL_NOTE)
    return builder.text(), builder.spans


def expected_payload(spec: Spec, spans: dict[str, dict[str, object]]) -> dict[str, object]:
    supply = normalize_money(spec.supply_raw)
    vat = normalize_money(spec.vat_raw)
    total = normalize_money(spec.total_raw)
    if spec.derive_total and supply is not None and vat is not None:
        total = supply + vat

    fields = {
        "vendor": spec.vendor,
        "doc_no": spec.doc_no,
        "doc_date": parse_date(spec.date_raw),
        "supply_amount": supply,
        "vat": vat,
        "total": total,
    }
    expected_items = [
        {
            "name": item.name,
            "qty": item.qty,
            "unit_price": item.unit_price,
            "amount": item.amount,
        }
        for item in spec.items
    ]

    evidence: dict[str, dict[str, object]] = {}
    for path, span in spans.items():
        if path.startswith("items["):
            index = int(path.split("[")[1].split("]")[0])
            key = path.rsplit(".", 1)[1]
            value: object = expected_items[index][key]
        else:
            value = fields[path]  # type: ignore[index]
        if value is None:
            continue
        evidence[path] = span

    return {
        "document_id": spec.doc_id,
        "dataset_version": DATASET_VERSION,
        "expected_status": spec.expected_status,
        "expected_rule_ids": list(spec.expected_rules),
        "fields": fields,
        "items": expected_items,
        "evidence": evidence,
    }


def make_normal(doc_id: str, index: int, rng: random.Random) -> Spec:
    vendor = VENDORS[index % len(VENDORS)]
    doc_no = f"TX-2026-{1001 + index:04d}"
    doc_date = (date(2026, 1, 5) + timedelta(days=17 * index)).isoformat()
    item_count = 1 + (index % 3)
    items: list[Item] = []
    for offset in range(item_count):
        name = ITEM_NAMES[(index * 3 + offset) % len(ITEM_NAMES)]
        qty = rng.choice((12, 20, 35, 40, 60, 120, 7, 9))
        unit_price = UNIT_PRICE_POOL[(index + offset) % len(UNIT_PRICE_POOL)]
        items.append(Item(name, qty, unit_price, qty * unit_price))
    supply = sum(item.amount for item in items)
    vat = round_half_up_vat(supply)
    return Spec(
        doc_id=doc_id,
        category="normal",
        vendor=vendor,
        doc_no=doc_no,
        date_raw=doc_date,
        items=items,
        supply_raw=money(supply),
        vat_raw=money(vat),
        total_raw=money(supply + vat),
    )


def make_rounding_normal(doc_id: str) -> Spec:
    """부가세 반올림 경로를 실제로 지나가는 정상 문서."""
    items = [Item("정밀 샤프트", 3, 1234, 3702)]
    supply = 3702
    vat = round_half_up_vat(supply)  # 370.2 -> 370
    return Spec(
        doc_id=doc_id,
        category="normal",
        vendor=VENDORS[3],
        doc_no="TX-2026-1017",
        date_raw="2026-09-18",
        items=items,
        supply_raw=money(supply),
        vat_raw=money(vat),
        total_raw=money(supply + vat),
    )


def make_error_specs(start: int, rng: random.Random) -> list[Spec]:
    specs: list[Spec] = []
    counter = start

    def next_id() -> str:
        nonlocal counter
        doc_id = f"DOC-{counter:04d}"
        counter += 1
        return doc_id

    def base(doc_id: str) -> Spec:
        item = Item(
            ITEM_NAMES[counter % len(ITEM_NAMES)],
            rng.choice((10, 24, 30, 45)),
            UNIT_PRICE_POOL[counter % len(UNIT_PRICE_POOL)],
            0,
        )
        item.amount = item.qty * item.unit_price
        supply = item.amount
        vat = round_half_up_vat(supply)
        return Spec(
            doc_id=doc_id,
            category="normal",
            vendor=VENDORS[counter % len(VENDORS)],
            doc_no=f"TX-2026-{3000 + counter:04d}",
            date_raw=(date(2026, 2, 2) + timedelta(days=7 * counter)).isoformat(),
            items=[item],
            supply_raw=money(supply),
            vat_raw=money(vat),
            total_raw=money(supply + vat),
        )

    # 필수값 누락 5건
    for missing, count in (("vendor", 2), ("doc_no", 2), ("doc_date", 1)):
        for _ in range(count):
            doc_id = next_id()
            spec = base(doc_id)
            setattr(spec, missing, None)
            spec.category = "missing_required"
            spec.expected_rules = ("MISSING_REQUIRED",)
            specs.append(spec)

    # 날짜 형식 2건
    for raw in ("2026-13-05", "2026.03.04"):
        doc_id = next_id()
        spec = base(doc_id)
        spec.date_raw = raw
        spec.category = "invalid_date"
        spec.expected_rules = ("INVALID_DATE",)
        specs.append(spec)

    # 금액 형식 1건
    doc_id = next_id()
    spec = base(doc_id)
    spec.supply_raw = "사십삼만원"
    spec.category = "invalid_money"
    spec.expected_rules = ("INVALID_MONEY",)
    specs.append(spec)

    # 금액 불일치 6건
    doc_id = next_id()
    spec = base(doc_id)
    item = spec.items[0]
    item.amount = item.qty * item.unit_price + 1000
    supply = item.amount
    vat = round_half_up_vat(supply)
    spec.supply_raw, spec.vat_raw, spec.total_raw = money(supply), money(vat), money(supply + vat)
    spec.category = "line_total_mismatch"
    spec.expected_rules = ("LINE_TOTAL_MISMATCH",)
    specs.append(spec)

    doc_id = next_id()
    spec = base(doc_id)
    actual_supply = spec.items[0].amount
    spec.supply_raw = money(actual_supply + 5000)
    vat = round_half_up_vat(actual_supply + 5000)
    spec.vat_raw = money(vat)
    spec.total_raw = money(actual_supply + 5000 + vat)
    spec.category = "line_total_mismatch"
    spec.expected_rules = ("LINE_TOTAL_MISMATCH",)
    specs.append(spec)

    doc_id = next_id()
    spec = base(doc_id)
    supply = spec.items[0].amount
    vat = round_half_up_vat(supply)
    spec.supply_raw = money(supply)
    spec.vat_raw = money(vat + 100)
    spec.total_raw = money(supply + vat + 100)
    spec.category = "line_total_mismatch"
    spec.expected_rules = ("LINE_TOTAL_MISMATCH",)
    specs.append(spec)

    doc_id = next_id()
    spec = base(doc_id)
    supply = spec.items[0].amount
    vat = round_half_up_vat(supply)
    spec.supply_raw = money(supply)
    spec.vat_raw = money(vat)
    spec.total_raw = money(supply + vat + 1)
    spec.category = "line_total_mismatch"
    spec.expected_rules = ("LINE_TOTAL_MISMATCH",)
    specs.append(spec)

    doc_id = next_id()
    spec = base(doc_id)
    item = spec.items[0]
    item.amount = item.qty * item.unit_price + 300
    supply = item.amount
    vat = round_half_up_vat(supply)
    spec.supply_raw = money(supply)
    spec.vat_raw = money(vat)
    spec.total_raw = money(supply + vat + 30)
    spec.category = "line_total_mismatch"
    spec.expected_rules = ("LINE_TOTAL_MISMATCH",)
    specs.append(spec)

    doc_id = next_id()
    spec = base(doc_id)
    supply = spec.items[0].amount
    vat = round_half_up_vat(supply)
    spec.supply_raw = money(supply)
    spec.vat_raw = money(vat)
    spec.total_raw = money(supply + vat + 10)
    spec.category = "line_total_mismatch"
    spec.expected_rules = ("LINE_TOTAL_MISMATCH",)
    specs.append(spec)

    # 중복 2건 (첫 건 정상, 둘째 중복)
    doc_id = next_id()
    first = base(doc_id)
    first.doc_no = "TX-2026-9001"
    first.category = "duplicate"
    first.expected_rules = ()
    specs.append(first)

    doc_id = next_id()
    second = base(doc_id)
    second.doc_no = first.doc_no
    second.category = "duplicate"
    second.expected_rules = ("DUPLICATE_DOCUMENT",)
    specs.append(second)

    # 알 수 없는 거래처 2건
    for vendor in UNKNOWN_VENDORS[:2]:
        doc_id = next_id()
        spec = base(doc_id)
        spec.vendor = vendor
        spec.category = "unknown_vendor"
        spec.expected_rules = ("UNKNOWN_VENDOR",)
        specs.append(spec)

    # 근거 없음 2건: 총액 생략 + 파생 주석
    for _ in range(2):
        doc_id = next_id()
        spec = base(doc_id)
        spec.total_raw = None
        spec.derive_total = True
        spec.category = "missing_evidence"
        spec.expected_rules = ("MISSING_EVIDENCE",)
        specs.append(spec)

    return specs


def build_documents() -> tuple[list[Spec], list[Spec]]:
    rng = random.Random(SEED)
    evaluation: list[Spec] = []
    for index in range(15):
        evaluation.append(make_normal(f"DOC-{len(evaluation) + 1:04d}", index, rng))
    evaluation.append(make_rounding_normal(f"DOC-{len(evaluation) + 1:04d}"))
    evaluation.extend(make_error_specs(len(evaluation) + 1, rng))

    demo: list[Spec] = []
    demo_normal = make_normal("DEMO-0001", 1, rng)
    demo_normal.doc_no = "TX-2026-2001"
    demo.append(demo_normal)

    demo_mismatch = make_normal("DEMO-0002", 2, rng)
    demo_mismatch.doc_no = "TX-2026-2002"
    supply = sum(item.amount for item in demo_mismatch.items)
    demo_mismatch.total_raw = money(supply + round_half_up_vat(supply) + 1000)
    demo.append(demo_mismatch)

    demo_dupe_first = make_normal("DEMO-0003", 3, rng)
    demo_dupe_first.doc_no = "TX-2026-2003"
    demo.append(demo_dupe_first)

    demo_dupe_second = make_normal("DEMO-0004", 4, rng)
    demo_dupe_second.doc_no = demo_dupe_first.doc_no
    demo.append(demo_dupe_second)
    return evaluation, demo


def render_set(specs: list[Spec]) -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    manifest_lines: list[str] = []
    for sequence, spec in enumerate(specs, start=1):
        text, spans = build_spec(spec)
        payload = expected_payload(spec, spans)
        data = text.encode("utf-8")
        files[EVAL_DIR / f"{spec.doc_id}.txt"] = data
        files[EVAL_DIR / "expected" / f"{spec.doc_id}.json"] = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        manifest_lines.append(
            json.dumps(
                {
                    "sequence": sequence,
                    "document_id": spec.doc_id,
                    "filename": f"{spec.doc_id}.txt",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                    "category": spec.category,
                    "expected_status": spec.expected_status,
                    "expected_rule_ids": list(spec.expected_rules),
                    "dataset_version": DATASET_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    files[EVAL_DIR / "manifest.jsonl"] = ("\n".join(manifest_lines) + "\n").encode("utf-8")
    return files


def render_demo(specs: list[Spec]) -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    for spec in specs:
        text, _ = build_spec(spec)
        files[DEMO_DIR / f"{spec.doc_id}.txt"] = text.encode("utf-8")
    return files


def render_registry() -> dict[Path, bytes]:
    payload = {
        "registry_version": VENDOR_REGISTRY_VERSION,
        "note": "모두 가상의 거래처 이름입니다. 실제 회사와 무관합니다.",
        "vendors": list(VENDORS),
    }
    return {
        VENDOR_PATH: (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    }


def all_files() -> dict[Path, bytes]:
    evaluation, demo = build_documents()
    files = render_set(evaluation)
    files.update(render_demo(demo))
    files.update(render_registry())
    return files


def write_files(files: dict[Path, bytes]) -> None:
    for path, data in sorted(files.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def check_files(files: dict[Path, bytes]) -> list[str]:
    problems: list[str] = []
    for path, data in sorted(files.items()):
        if not path.exists():
            problems.append(f"missing: {path.relative_to(ROOT)}")
        elif path.read_bytes() != data:
            problems.append(f"stale: {path.relative_to(ROOT)}")
    return problems


def summarize(files: dict[Path, bytes]) -> str:
    evaluation, demo = build_documents()
    counts: dict[str, int] = {}
    for spec in evaluation:
        counts[spec.category] = counts.get(spec.category, 0) + 1
    lines = [
        f"dataset_version={DATASET_VERSION}",
        f"evaluation_docs={len(evaluation)} demo_docs={len(demo)}",
        "categories=" + ", ".join(f"{key}:{value}" for key, value in sorted(counts.items())),
        f"files={len(files)}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="합성 문서 데이터셋 생성기")
    parser.add_argument("--check", action="store_true", help="생성 결과와 커밋된 파일 비교")
    args = parser.parse_args(argv)

    files = all_files()
    if args.check:
        problems = check_files(files)
        if problems:
            print("데이터셋이 코드와 일치하지 않습니다:")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print("데이터셋 일치:", summarize(files))
        return 0

    write_files(files)
    print("데이터셋 생성 완료")
    print(summarize(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
