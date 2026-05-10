from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Sequence, Union


DEFAULT_DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d")
_DATE_INPUT_PATTERNS: dict[str, re.Pattern[str]] = {
    "%Y-%m-%d": re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"),
    "%Y/%m/%d": re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"),
    "%Y%m%d": re.compile(r"^\d{8}$"),
}
_MONTH_DAY_INPUT_PROBES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\d{1,2}-\d{1,2}$"), "%m-%d"),
    (re.compile(r"^\d{1,2}/\d{1,2}$"), "%m/%d"),
)


class DateInputError(ValueError):
    def __init__(self, value: object, reason: str) -> None:
        self.value_text = str(value).strip()
        self.reason = reason
        super().__init__(f"{reason}: {self.value_text}")


def _normalize_formats(formats: Optional[Sequence[str]]) -> tuple[str, ...]:
    return tuple(formats or DEFAULT_DATE_FORMATS)


def _looks_like_supported_date(text: str, formats: Sequence[str]) -> bool:
    return any(pattern.fullmatch(text) for fmt, pattern in _DATE_INPUT_PATTERNS.items() if fmt in formats)


def _classify_date_input_error(text: str, formats: Sequence[str]) -> str:
    if _looks_like_supported_date(text, formats):
        return "nonexistent"

    for pattern, _ in _MONTH_DAY_INPUT_PROBES:
        if not pattern.fullmatch(text):
            continue
        try:
            datetime.strptime(f"2000-{text.replace('/', '-')}", "%Y-%m-%d")
        except ValueError:
            return "nonexistent"
        return "format"

    return "format"


def parse_date_text(text: str, formats: Optional[Sequence[str]] = None) -> date:
    normalized = str(text).strip()
    allowed_formats = _normalize_formats(formats)

    for fmt in allowed_formats:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    raise DateInputError(normalized, _classify_date_input_error(normalized, allowed_formats))


def parse_date(value: Union[str, date, datetime], formats: Optional[Sequence[str]] = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    return parse_date_text(str(value), formats=formats)


def normalize_date_string(value: Optional[Union[str, date, datetime]]) -> Optional[str]:
    if value is None:
        return None
    return parse_date(value).isoformat()


def to_compact_date(value: Union[str, date, datetime]) -> str:
    return parse_date(value).strftime("%Y%m%d")


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_date_order(start_date: Union[str, date, datetime], end_date: Union[str, date, datetime]) -> tuple[str, str]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")
    return start.isoformat(), end.isoformat()
