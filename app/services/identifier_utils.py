from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

import pandas as pd


INIO_FROM_NAME_RE = re.compile(r"\(ИНИО\s*([^\)]+)\)", re.IGNORECASE)

# Допустимые длины ИНН: 10 — юрлицо, 12 — физлицо/ИП
_INN_LENGTHS = (10, 12)


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
    # Пробуем дополнить до ближайшей стандартной длины
    for target in _INN_LENGTHS:
        if length < target:
            padded = digits.zfill(target)
            # Убеждаемся, что не добавили слишком много нулей
            if len(padded) == target:
                return padded
    return None


def normalize_inn(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    if isinstance(value, int):
        digits = str(value)
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        digits = str(int(round(value)))
    elif isinstance(value, Decimal):
        digits = str(int(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            decimal_value = Decimal(text)
            if decimal_value == decimal_value.to_integral_value():
                digits = str(int(decimal_value))
            else:
                digits = re.sub(r"\D", "", text)
        except InvalidOperation:
            digits = re.sub(r"\D", "", text)

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
        match = INIO_FROM_NAME_RE.search(name_text)
        if match:
            return {"value": match.group(1).strip(), "type": "INIO"}

    return {"value": None, "type": None}
