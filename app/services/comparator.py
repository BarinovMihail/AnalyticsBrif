from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.models import CardCharacteristic, MTRCard, SupplierEntry
from app.schemas import SearchFilter


OPERATORS = {"eq", "eq_str", "gte", "lte", "range_max_gte", "range_max_lte"}


def _parse_float(value: str) -> float:
    return float(value.replace(",", ".").strip())


def _build_condition(search_filter: SearchFilter):
    operator = search_filter.operator
    if operator not in OPERATORS:
        raise ValueError(f"Неподдерживаемый оператор: {operator}")

    if operator == "eq":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.char_value_numeric.is_not(None), CardCharacteristic.char_value_numeric == numeric_value
    if operator == "eq_str":
        normalized_value = search_filter.value.strip().lower()
        return None, func.lower(CardCharacteristic.char_value) == normalized_value
    if operator == "gte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.char_value_numeric.is_not(None), CardCharacteristic.char_value_numeric >= numeric_value
    if operator == "lte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.char_value_numeric.is_not(None), CardCharacteristic.char_value_numeric <= numeric_value
    if operator == "range_max_gte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.range_max.is_not(None), CardCharacteristic.range_max >= numeric_value
    numeric_value = _parse_float(search_filter.value)
    return CardCharacteristic.range_max.is_not(None), CardCharacteristic.range_max <= numeric_value


def search_cards(db: Session, filters: list[SearchFilter]) -> list[dict]:
    if not filters:
        return []

    matched_card_ids: set[int] | None = None
    matched_values_by_card: dict[int, dict[str, str]] = {}

    for search_filter in filters:
        not_null_condition, condition = _build_condition(search_filter)
        conditions = [CardCharacteristic.char_name == search_filter.char_name, condition]
        if not_null_condition is not None:
            conditions.insert(1, not_null_condition)

        rows = db.execute(
            select(
                CardCharacteristic.card_id,
                CardCharacteristic.char_name,
                CardCharacteristic.char_value,
            ).where(and_(*conditions))
        ).all()

        current_card_ids = {row.card_id for row in rows}
        if matched_card_ids is None:
            matched_card_ids = current_card_ids
        else:
            matched_card_ids &= current_card_ids

        if not matched_card_ids:
            return []

        for row in rows:
            matched_values_by_card.setdefault(row.card_id, {})[row.char_name] = row.char_value

    if not matched_card_ids:
        return []

    cards = db.execute(
        select(MTRCard, SupplierEntry)
        .join(SupplierEntry, SupplierEntry.manufacturer_inn == MTRCard.manufacturer_inn)
        .where(MTRCard.id.in_(matched_card_ids))
        .order_by(SupplierEntry.contract_date.desc())
    ).all()

    all_characteristics_rows = db.execute(
        select(
            CardCharacteristic.card_id,
            CardCharacteristic.char_name,
            CardCharacteristic.char_value,
        ).where(CardCharacteristic.card_id.in_(matched_card_ids))
    ).all()
    all_characteristics_by_card: dict[int, dict[str, str]] = {}
    for row in all_characteristics_rows:
        all_characteristics_by_card.setdefault(row.card_id, {})[row.char_name] = row.char_value

    results = []
    for card, supplier in cards:
        matched_characteristics = matched_values_by_card.get(card.id, {})
        if len(matched_characteristics) != len(filters):
            continue
        results.append(
            {
                "card_guid": card.guid,
                "card_nomenclature": card.nomenclature_name,
                "manufacturer_inn": card.manufacturer_inn,
                "supplier_inn": supplier.supplier_inn,
                "supplier_site": supplier.supplier_site,
                "contract_date": supplier.contract_date,
                "price": float(supplier.price) if supplier.price is not None else None,
                "currency": supplier.currency,
                "matched_characteristics": matched_characteristics,
                "all_characteristics": all_characteristics_by_card.get(card.id, {}),
            }
        )
    return results


def export_search_results(results: list[dict], filters: list[SearchFilter]) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"

    headers = [
        "Наименование карточки",
        "ИНН изготовителя",
        "Поставщик (сайт)",
        "ИНН поставщика",
        "Дата контракта",
        "Цена",
        "Валюта",
    ] + [search_filter.char_name for search_filter in filters]
    sheet.append(headers)

    for result in results:
        row = [
            result["card_nomenclature"],
            result["manufacturer_inn"],
            result["supplier_site"],
            result["supplier_inn"],
            result["contract_date"].isoformat() if result["contract_date"] else None,
            result["price"],
            result["currency"],
        ]
        for search_filter in filters:
            row.append(result["matched_characteristics"].get(search_filter.char_name))
        sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def clear_file1_data(db: Session) -> None:
    db.execute(delete(SupplierEntry))
    db.commit()


def clear_file2_data(db: Session) -> None:
    db.execute(delete(CardCharacteristic))
    db.execute(delete(MTRCard))
    db.commit()
