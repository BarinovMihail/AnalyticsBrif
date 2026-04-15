from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

import pandas as pd


INIO_FROM_NAME_RE = re.compile(r"\(ИНИО\s*([^\)]+)\)", re.IGNORECASE)


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

    if digits.isdigit() and len(digits) in (10, 12):
        return digits
    return None


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
