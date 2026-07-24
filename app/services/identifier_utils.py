from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

import pandas as pd


INN_FROM_NAME_RE = re.compile(
    r"(?<!\w)ИНН(?!\w)\s*(?:[:№#\-–—]\s*)?"
    r"((?:\d[\s./\-–—]*){10,12})(?!\d)",
    re.IGNORECASE,
)
INIO_FROM_NAME_RE = re.compile(
    r"(?<!\w)ИНИО(?!\w)\s*(?:[:№#\-–—]\s*)?([^)]+?)\s*\)",
    re.IGNORECASE,
)

# Допустимые длины ИНН: 10 — юрлицо, 12 — физлицо/ИП
_INN_LENGTHS = (10, 12)
_RECOVERABLE_INN_LENGTHS = {
    8: 10,
    9: 10,
    11: 12,
}


def normalize_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def _pad_inn(digits: str) -> str | None:
    """Дополняет цифровую строку ведущими нулями до стандартной длины ИНН.

    Excel хранит ИНН как число и теряет ведущие нули (0274173735 → 274173735).
    Если строка короче допустимой длины на 1-2 символа, дополняем нулями.
    Возвращает None, если длину восстановить невозможно.
    """
    if not digits.isdigit():
        return None
    length = len(digits)
    if length in _INN_LENGTHS:
        return digits
    target = _RECOVERABLE_INN_LENGTHS.get(length)
    return digits.zfill(target) if target else None


def normalize_inn(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        digits = str(value)
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value) or not value.is_integer():
            return None
        digits = str(int(value))
    elif isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            return None
        digits = str(int(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"\d+", text):
            digits = text
        elif re.fullmatch(r"\d+(?:[\s/\-–—]+\d+)+", text):
            digits = re.sub(r"\D", "", text)
        else:
            try:
                decimal_value = Decimal(text)
            except InvalidOperation:
                return None
            if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
                return None
            digits = str(int(decimal_value))

    return _pad_inn(digits)


def extract_identifier(inn_value, name_value=None, inio_value=None) -> dict[str, str | None]:
    inn = normalize_inn(inn_value)
    if inn:
        return {"value": inn, "type": "INN"}

    inio_text = normalize_text(inio_value)
    if inio_text:
        return {"value": inio_text, "type": "INIO"}

    name_text = normalize_text(name_value)
    if name_text:
        inn_match = INN_FROM_NAME_RE.search(name_text)
        if inn_match:
            marked_inn = normalize_inn(inn_match.group(1))
            if marked_inn:
                return {"value": marked_inn, "type": "INN"}

        inio_match = INIO_FROM_NAME_RE.search(name_text)
        if inio_match:
            marked_inio = normalize_text(inio_match.group(1))
            if marked_inio:
                return {"value": marked_inio, "type": "INIO"}

    return {"value": None, "type": None}
