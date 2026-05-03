from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SupplierEntry
from app.services.identifier_utils import extract_identifier, normalize_inn, normalize_text


logger = logging.getLogger(__name__)


DATE_DDMMYYYY_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")
EMAIL_RE = re.compile(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)
BRIF_HEADER_ROW_INDEX = 3

BRIF_PRODUCT_COLUMN = "Наименование продукции"
BRIF_SUPPLIER_COLUMN = "Наименование поставщика"
BRIF_OKPD2_COLUMN = "Классификатор ОКПД2"
BRIF_MTR_CLASS_COLUMN = "Классификатор МТРИО"
BRIF_STATUS_COLUMN = "Статус продукции"
BRIF_PRICE_COLUMN = "Цена EXW без НДС"
BRIF_DELIVERY_DATE_COLUMN = "Дата окончания действия цены"
BRIF_CONTRACT_DATE_COLUMN = "Дата начала действия цены"
BRIF_UPDATE_DATE_COLUMN = "Дата обновления"
BRIF_CURRENCY_COLUMN = "Валюта"
BRIF_MANUFACTURER_COLUMN = "Наименование изготовителя"
BRIF_MANUFACTURER_INN_COLUMN = "ИНН изготовителя"


def _normalize_text(value: object) -> str | None:
    return normalize_text(value)


def _parse_decimal(value: object) -> Decimal | None:
    text = _normalize_text(value)
    if not text:
        return None
    cleaned = text.replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_int(value: object) -> int | None:
    number = _parse_decimal(value)
    return int(number) if number is not None else None


def _parse_date(value: object, fmt: str = "%d.%m.%Y") -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        return None


def _extract_date(value: object) -> date | None:
    text = _normalize_text(value)
    if not text:
        return None
    match = DATE_DDMMYYYY_RE.search(text)
    return _parse_date(match.group(1)) if match else _parse_date(text)


def _split_contract_and_site(value: object) -> tuple[date | None, str | None]:
    text = _normalize_text(value)
    if not text:
        return None, None
    match = DATE_DDMMYYYY_RE.search(text)
    if not match:
        return None, text
    contract_date = _parse_date(match.group(1))
    site = text.replace(match.group(1), "", 1).strip() or None
    return contract_date, site


def _extract_email(value: object) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    match = EMAIL_RE.search(text)
    return match.group(1) if match else None


def _extract_okpd2(value: object) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.split(":", 1)[0].strip()


def _extract_mtr_class(value: object) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    match = re.search(r"\((\d+)\)", text)
    return match.group(1) if match else text


def _extract_currency(value: object) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.split("(", 1)[0].strip()


def _is_effectively_empty_row(row) -> bool:
    relevant_indexes = list(range(min(len(row), 26)))
    return all(_normalize_text(row.iloc[index]) is None for index in relevant_indexes)


def _detect_file1_format(dataframe: pd.DataFrame) -> str:
    if len(dataframe) > BRIF_HEADER_ROW_INDEX:
        header_row = dataframe.iloc[BRIF_HEADER_ROW_INDEX].tolist()
        normalized_header = [_normalize_text(cell) for cell in header_row]
        if BRIF_PRODUCT_COLUMN in normalized_header and BRIF_MANUFACTURER_INN_COLUMN in normalized_header:
            return "brif_registry"
    return "legacy"


def _build_header_map(dataframe: pd.DataFrame, header_row_index: int) -> dict[str, int]:
    if len(dataframe) <= header_row_index:
        return {}
    return {
        header: index
        for index, value in enumerate(dataframe.iloc[header_row_index].tolist())
        if (header := _normalize_text(value))
    }


def _row_value(row, columns: dict[str, int], column_name: str) -> object | None:
    index = columns.get(column_name)
    if index is None or index >= len(row):
        return None
    return row.iloc[index]


def _parse_legacy_row(row) -> dict:
    contract_date, supplier_site = _split_contract_and_site(row.iloc[5])
    identifier = extract_identifier(row.iloc[11], name_value=row.iloc[10])
    return {
        "nomenclature_name": _normalize_text(row.iloc[1]),
        "okpd2_code": _normalize_text(row.iloc[3]),
        "mtr_class": _normalize_text(row.iloc[4]),
        "supplier_name": None,
        "supplier_site": supplier_site,
        "manufacturer_inn": identifier["value"],
        "manufacturer_identifier_type": identifier["type"],
        "supplier_inn": _normalize_inn(row.iloc[12]),
        "manufacturer_name": _normalize_text(row.iloc[10]),
        "price": _parse_decimal(row.iloc[6]),
        "currency": _normalize_text(row.iloc[8]),
        "quantity": _parse_int(row.iloc[9]),
        "contract_date": contract_date,
        "delivery_date": _parse_date(row.iloc[7]),
    }


def _parse_brif_registry_row(row, columns: dict[str, int]) -> dict:
    manufacturer_name = _row_value(row, columns, BRIF_MANUFACTURER_COLUMN)
    status = _row_value(row, columns, BRIF_STATUS_COLUMN)
    supplier_name = _normalize_text(_row_value(row, columns, BRIF_SUPPLIER_COLUMN))
    contract_date = (
        _parse_date(_row_value(row, columns, BRIF_CONTRACT_DATE_COLUMN))
        or _extract_date(status)
        or _parse_date(_row_value(row, columns, BRIF_UPDATE_DATE_COLUMN))
    )
    identifier = extract_identifier(
        _row_value(row, columns, BRIF_MANUFACTURER_INN_COLUMN),
        name_value=manufacturer_name,
    )
    return {
        "nomenclature_name": _normalize_text(_row_value(row, columns, BRIF_PRODUCT_COLUMN)),
        "okpd2_code": _extract_okpd2(_row_value(row, columns, BRIF_OKPD2_COLUMN)),
        "mtr_class": _extract_mtr_class(_row_value(row, columns, BRIF_MTR_CLASS_COLUMN)),
        "supplier_name": supplier_name,
        "supplier_site": _extract_email(status) or supplier_name,
        "manufacturer_inn": identifier["value"],
        "manufacturer_identifier_type": identifier["type"],
        "supplier_inn": None,
        "manufacturer_name": _normalize_text(manufacturer_name),
        "price": _parse_decimal(_row_value(row, columns, BRIF_PRICE_COLUMN)),
        "currency": _extract_currency(_row_value(row, columns, BRIF_CURRENCY_COLUMN)),
        "quantity": None,
        "contract_date": contract_date,
        "delivery_date": _parse_date(_row_value(row, columns, BRIF_DELIVERY_DATE_COLUMN)),
    }


def import_file1(db: Session, file_path: str | Path) -> dict:
    dataframe = pd.read_excel(file_path, header=None, engine="openpyxl", dtype=object)
    file_format = _detect_file1_format(dataframe)
    brif_columns = _build_header_map(dataframe, BRIF_HEADER_ROW_INDEX) if file_format == "brif_registry" else {}
    rows = dataframe.iloc[4:] if file_format == "brif_registry" else dataframe.iloc[3:]

    existing_keys = {
        (manufacturer_inn, nomenclature_name, contract_date)
        for manufacturer_inn, nomenclature_name, contract_date in db.execute(
            select(
                SupplierEntry.manufacturer_inn,
                SupplierEntry.nomenclature_name,
                SupplierEntry.contract_date,
            )
        ).all()
    }

    imported = 0
    skipped = 0
    errors: list[str] = []

    for row_index, row in rows.iterrows():
        excel_row = row_index + 1
        try:
            if _is_effectively_empty_row(row):
                logger.info("Строка %s пропущена: пустая строка", excel_row)
                skipped += 1
                continue

            parsed_row = (
                _parse_brif_registry_row(row, brif_columns)
                if file_format == "brif_registry"
                else _parse_legacy_row(row)
            )

            nomenclature_name = parsed_row["nomenclature_name"]
            manufacturer_inn = parsed_row["manufacturer_inn"]
            manufacturer_inn = str(manufacturer_inn).strip()[:255] if manufacturer_inn else None

            if not nomenclature_name:
                logger.warning("Строка %s: отсутствует наименование номенклатуры, строка пропущена", excel_row)
                skipped += 1
                continue

            if not manufacturer_inn:
                logger.warning(
                    "Строка %s: идентификатор изготовителя не найден, запись будет сохранена без него",
                    excel_row,
                )

            duplicate_key = (
                manufacturer_inn,
                nomenclature_name,
                parsed_row["contract_date"],
            )
            if duplicate_key in existing_keys:
                logger.info(
                    "Строка %s пропущена: дубль по ключу ИНН изготовителя=%r, номенклатура=%r, дата контракта=%r",
                    excel_row,
                    manufacturer_inn,
                    nomenclature_name,
                    parsed_row["contract_date"],
                )
                skipped += 1
                continue

            db.add(
                SupplierEntry(
                    nomenclature_name=nomenclature_name,
                    okpd2_code=parsed_row["okpd2_code"],
                    mtr_class=parsed_row["mtr_class"],
                    supplier_name=parsed_row["supplier_name"],
                    supplier_site=parsed_row["supplier_site"],
                    manufacturer_inn=manufacturer_inn,
                    manufacturer_identifier_type=parsed_row["manufacturer_identifier_type"],
                    supplier_inn=parsed_row["supplier_inn"],
                    manufacturer_name=parsed_row["manufacturer_name"],
                    price=parsed_row["price"],
                    currency=parsed_row["currency"],
                    quantity=parsed_row["quantity"],
                    contract_date=parsed_row["contract_date"],
                    delivery_date=parsed_row["delivery_date"],
                )
            )
            existing_keys.add(duplicate_key)
            imported += 1
        except Exception as exc:
            message = f"Строка {excel_row}: {exc}"
            logger.exception(message)
            errors.append(message)

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
