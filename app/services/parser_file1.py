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


logger = logging.getLogger(__name__)


DATE_DDMMYYYY_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


def _normalize_text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


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


def import_file1(db: Session, file_path: str | Path) -> dict:
    dataframe = pd.read_excel(file_path, header=None, engine="openpyxl")
    rows = dataframe.iloc[3:]

    existing_keys = {
        (manufacturer_inn or "", nomenclature_name or "", contract_date)
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
            nomenclature_name = _normalize_text(row.iloc[1])
            okpd2_code = _normalize_text(row.iloc[3])
            mtr_class = _normalize_text(row.iloc[4])
            contract_date, supplier_site = _split_contract_and_site(row.iloc[5])
            price = _parse_decimal(row.iloc[6])
            delivery_date = _parse_date(row.iloc[7])
            currency = _normalize_text(row.iloc[8])
            quantity = _parse_int(row.iloc[9])
            manufacturer_name = _normalize_text(row.iloc[10])
            manufacturer_inn = _normalize_text(row.iloc[11])
            supplier_inn = _normalize_text(row.iloc[12])

            if not nomenclature_name or not manufacturer_inn:
                raise ValueError("Не удалось определить номенклатуру или ИНН изготовителя")

            duplicate_key = (manufacturer_inn, nomenclature_name, contract_date)
            if duplicate_key in existing_keys:
                skipped += 1
                continue

            db.add(
                SupplierEntry(
                    nomenclature_name=nomenclature_name,
                    okpd2_code=okpd2_code,
                    mtr_class=mtr_class,
                    supplier_site=supplier_site,
                    manufacturer_inn=manufacturer_inn,
                    supplier_inn=supplier_inn,
                    manufacturer_name=manufacturer_name,
                    price=price,
                    currency=currency,
                    quantity=quantity,
                    contract_date=contract_date,
                    delivery_date=delivery_date,
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
