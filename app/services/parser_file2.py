from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CardCharacteristic, MTRCard


logger = logging.getLogger(__name__)


GUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
INN_RE = re.compile(r"\b\d{10,12}\b")
DATE_RE = re.compile(r"\b\d{4}\.\d{2}\.\d{2}\b")
RANGE_RE = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s*(?:\.\.\.|/)\s*([+-]?\d+(?:[.,]\d+)?)")


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(" ", "").replace(",", "."))
    except (AttributeError, ValueError):
        return None


def _to_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y.%m.%d").date()
    except ValueError:
        return None


def _row_values(row) -> list[str]:
    return [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]


def _extract_header(row_values: list[str]) -> dict | None:
    combined = " | ".join(row_values)
    guid_match = GUID_RE.search(combined)
    if not guid_match:
        return None

    guid = guid_match.group(0)
    manufacturer_inn = next((value for value in row_values if INN_RE.fullmatch(value)), None)
    delivery_date = next((value for value in row_values if DATE_RE.fullmatch(value)), None)
    price = None

    candidate_numbers = []
    for value in row_values:
        normalized = value.replace(" ", "").replace(",", ".")
        if normalized == manufacturer_inn or normalized == delivery_date:
            continue
        try:
            float(normalized)
            candidate_numbers.append(value)
        except ValueError:
            continue
    if candidate_numbers:
        price = candidate_numbers[-1]

    filtered = [value for value in row_values if value != "TITLE"]
    guid_index = next((i for i, value in enumerate(filtered) if guid in value), 0)
    name = filtered[guid_index + 1] if len(filtered) > guid_index + 1 else None
    if not name:
        non_meta = [
            value
            for value in filtered
            if value != guid
            and value != manufacturer_inn
            and value != delivery_date
            and value != price
        ]
        name = non_meta[0] if non_meta else None

    mtr_class = None
    if manufacturer_inn:
        try:
            manufacturer_index = filtered.index(manufacturer_inn)
            if manufacturer_index + 1 < len(filtered):
                mtr_class = filtered[manufacturer_index + 1]
        except ValueError:
            mtr_class = None

    currency_code = None
    for value in filtered:
        if re.fullmatch(r"\d{3}", value):
            currency_code = value
            break

    return {
        "guid": guid,
        "nomenclature_name": name,
        "manufacturer_inn": manufacturer_inn,
        "mtr_class": mtr_class,
        "price": _to_decimal(price),
        "currency_code": currency_code,
        "delivery_date": _parse_date(delivery_date),
    }


def _parse_characteristic_value(raw_value: str | None) -> tuple[str, float | None, float | None, float | None]:
    value = raw_value or ""
    numeric_value = _to_float(value)
    range_min = None
    range_max = None

    match = RANGE_RE.search(value)
    if match:
        range_min = _to_float(match.group(1))
        range_max = _to_float(match.group(2))

    return value, numeric_value, range_min, range_max


def import_file2(db: Session, file_path: str | Path) -> dict:
    workbook = load_workbook(filename=file_path, data_only=True)
    sheet = workbook.active

    existing_guids = set(db.scalars(select(MTRCard.guid)).all())
    imported = 0
    skipped = 0
    errors: list[str] = []

    current_card: MTRCard | None = None

    def flush_card(card: MTRCard | None):
        nonlocal imported
        if card is None:
            return
        db.add(card)
        imported += 1

    for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        values = _row_values(row)
        if not values:
            continue

        try:
            is_header = "TITLE" in values or any(GUID_RE.search(value) for value in values)
            if is_header:
                header = _extract_header(values)
                if header is None:
                    raise ValueError("Не удалось определить GUID заголовка блока")

                guid = header["guid"]
                if guid in existing_guids:
                    skipped += 1
                    current_card = None
                    continue

                flush_card(current_card)
                current_card = MTRCard(**header)
                existing_guids.add(guid)
                continue

            if current_card is None:
                continue

            if len(values) < 2:
                raise ValueError("Строка характеристики должна содержать char_name и char_value")

            char_name = values[0]
            char_value, numeric_value, range_min, range_max = _parse_characteristic_value(values[1])
            current_card.characteristics.append(
                CardCharacteristic(
                    char_name=char_name,
                    char_value=char_value,
                    char_value_numeric=numeric_value,
                    range_min=range_min,
                    range_max=range_max,
                )
            )
        except Exception as exc:
            message = f"Строка {row_index}: {exc}"
            logger.exception(message)
            errors.append(message)

    flush_card(current_card)
    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
