from __future__ import annotations

import re
from io import BytesIO
from typing import Callable, Optional

from openpyxl import Workbook
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.models import CardCharacteristic, MTRCard, SupplierEntry
from app.schemas import SearchFilter


OPERATORS = {
    "eq",
    "eq_str",
    "gte",
    "lte",
    "range_max_gte",
    "range_max_lte",
    "contains_any_word",
    "contains_all_words",
}

# Слово — непрерывная последовательность букв и цифр (без подчёркивания).
# Любой прочий символ (пробел, запятая, точка с запятой, слэш и т.п.) считается разделителем
# и не входит в состав слова.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str | None) -> set[str]:
    """Разбивает текст на множество слов (в нижнем регистре)."""
    if not text:
        return set()
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}


def _parse_float(value: str) -> float:
    return float(value.replace(",", ".").strip())


def _build_condition(
    search_filter: SearchFilter,
) -> tuple[Optional[object], object, Optional[Callable[[str], bool]]]:
    """Возвращает (not_null_condition, sql_condition, post_filter).

    Для операторов `contains_any_word` / `contains_all_words` SQL-условие выбирает
    все строки по имени характеристики, а финальная проверка по словам выполняется
    в Python через `post_filter`.
    """
    operator = search_filter.operator
    if operator not in OPERATORS:
        raise ValueError(f"Неподдерживаемый оператор: {operator}")

    if operator == "eq":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.char_value_numeric.is_not(None), CardCharacteristic.char_value_numeric == numeric_value, None
    if operator == "eq_str":
        normalized_value = search_filter.value.strip().lower()
        return None, func.lower(CardCharacteristic.char_value) == normalized_value, None
    if operator == "gte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.char_value_numeric.is_not(None), CardCharacteristic.char_value_numeric >= numeric_value, None
    if operator == "lte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.char_value_numeric.is_not(None), CardCharacteristic.char_value_numeric <= numeric_value, None
    if operator == "range_max_gte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.range_max.is_not(None), CardCharacteristic.range_max >= numeric_value, None
    if operator == "range_max_lte":
        numeric_value = _parse_float(search_filter.value)
        return CardCharacteristic.range_max.is_not(None), CardCharacteristic.range_max <= numeric_value, None

    query_tokens = _tokenize(search_filter.value)
    if operator == "contains_any_word":
        # Совпадение, если хотя бы одно слово из запроса присутствует в значении карточки.
        def _post_filter_any(card_value: str) -> bool:
            if not query_tokens:
                return False
            return bool(query_tokens & _tokenize(card_value))

        # На уровне SQL дополнительно ограничиваем выборку: значение должно содержать
        # хотя бы одно из слов запроса (с учётом регистра через LOWER).
        like_clauses = [
            func.lower(CardCharacteristic.char_value).like(f"%{token}%") for token in sorted(query_tokens)
        ]
        if not like_clauses:
            return None, CardCharacteristic.char_value.is_(None), _post_filter_any
        sql_condition = like_clauses[0]
        for clause in like_clauses[1:]:
            sql_condition = sql_condition | clause
        return None, sql_condition, _post_filter_any

    # operator == "contains_all_words"
    # Совпадение, если каждое слово материала из карточки присутствует в запросе
    # (порядок слов не важен, лишние слова в запросе допустимы).
    def _post_filter_all(card_value: str) -> bool:
        card_tokens = _tokenize(card_value)
        if not card_tokens:
            return False
        return card_tokens.issubset(query_tokens)

    return None, CardCharacteristic.char_value.is_not(None), _post_filter_all


def search_cards(db: Session, filters: list[SearchFilter]) -> list[dict]:
    if not filters:
        return []

    matched_card_ids: set[int] | None = None

    for search_filter in filters:
        not_null_condition, condition, post_filter = _build_condition(search_filter)
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

        if post_filter is not None:
            current_card_ids = {row.card_id for row in rows if post_filter(row.char_value)}
        else:
            current_card_ids = {row.card_id for row in rows}
        if matched_card_ids is None:
            matched_card_ids = current_card_ids
        else:
            matched_card_ids &= current_card_ids

        if not matched_card_ids:
            return []

    if not matched_card_ids:
        return []

    filter_names = [search_filter.char_name for search_filter in filters]
    matched_characteristics_rows = db.execute(
        select(
            CardCharacteristic.card_id,
            CardCharacteristic.char_name,
            CardCharacteristic.char_value,
        ).where(
            CardCharacteristic.card_id.in_(matched_card_ids),
            CardCharacteristic.char_name.in_(filter_names),
        )
    ).all()
    matched_values_by_card: dict[int, dict[str, str]] = {}
    for row in matched_characteristics_rows:
        matched_values_by_card.setdefault(row.card_id, {})[row.char_name] = row.char_value

    card_supplier_rows = db.execute(
        select(MTRCard, SupplierEntry)
        .outerjoin(SupplierEntry, SupplierEntry.manufacturer_inn == MTRCard.manufacturer_inn)
        .where(MTRCard.id.in_(matched_card_ids))
        .order_by(MTRCard.id.asc(), SupplierEntry.contract_date.desc(), SupplierEntry.id.desc())
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

    cards_by_id: dict[int, MTRCard] = {}
    freshest_supplier_by_card_id: dict[int, SupplierEntry | None] = {}
    for card, supplier in card_supplier_rows:
        cards_by_id.setdefault(card.id, card)
        if card.id not in freshest_supplier_by_card_id:
            freshest_supplier_by_card_id[card.id] = supplier

    results = []
    for card_id in sorted(cards_by_id):
        card = cards_by_id[card_id]
        supplier = freshest_supplier_by_card_id.get(card_id)
        matched_characteristics = matched_values_by_card.get(card.id, {})
        results.append(
            {
                "card_guid": card.guid,
                "card_nomenclature": card.nomenclature_name,
                "manufacturer_inn": card.manufacturer_inn,
                "manufacturer_name": supplier.manufacturer_name if supplier else None,
                "supplier_name": supplier.supplier_name if supplier else None,
                "contract_date": supplier.contract_date if supplier else None,
                "price": float(supplier.price) if supplier and supplier.price is not None else None,
                "currency": supplier.currency if supplier else None,
                "matched_characteristics": matched_characteristics,
                "all_characteristics": all_characteristics_by_card.get(card.id, {}),
            }
        )
    return results


def export_search_results(results: list[dict], filters: list[SearchFilter]) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"

    filter_names = [search_filter.char_name for search_filter in filters]
    additional_characteristics = sorted(
        {
            char_name
            for result in results
            for char_name in result.get("all_characteristics", {})
            if char_name not in filter_names
        }
    )

    headers = [
        "Наименование карточки",
        "ИНН изготовителя",
        "Наименование изготовителя",
        "Наименование поставщика",
        "Дата контракта",
        "Цена",
        "Валюта",
    ] + filter_names + additional_characteristics
    sheet.append(headers)

    for result in results:
        row = [
            result["card_nomenclature"],
            result["manufacturer_inn"],
            result.get("manufacturer_name"),
            result.get("supplier_name"),
            result["contract_date"].isoformat() if result["contract_date"] else None,
            result["price"],
            result["currency"],
        ]
        for char_name in filter_names:
            row.append(result["matched_characteristics"].get(char_name))
        for char_name in additional_characteristics:
            row.append(result["all_characteristics"].get(char_name))
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
