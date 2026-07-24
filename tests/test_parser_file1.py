from __future__ import annotations

import os
import re
import tempfile
import unittest
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import SupplierEntry
from app.services.identifier_utils import extract_identifier
from app.services.parser_file1 import (
    _build_header_map,
    _detect_file1_format,
    _find_brif_header_row,
    _parse_brif_registry_row,
    import_file1,
)


WITHOUT_INN_PATH = Path(
    os.environ.get(
        "TEST_FILE1_WITHOUT_INN",
        r"C:\Users\misha\Downloads\Файл выгрузки. (3).xlsx",
    )
)
WITH_INN_PATH = Path(
    os.environ.get(
        "TEST_FILE1_WITH_INN",
        r"C:\Users\misha\Downloads\Файл выгрузки. 300.xlsx",
    )
)


def make_session() -> tuple[Session, object]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine), engine


class RegistryHeaderTests(unittest.TestCase):
    def test_registry_detection_and_header_map_are_case_and_space_insensitive(self):
        for mtr_header in (
            "Классификатор МТРиО",
            "Классификатор МТРИО",
            "кЛаССиФиКаТоР мТрИо",
        ):
            with self.subTest(mtr_header=mtr_header):
                headers = [
                    "  СТАТУС   ПРОДУКЦИИ ",
                    "Наименование изготовителя",
                    mtr_header,
                    " наименование ПРОДУКЦИИ ",
                    "Цена EXW без НДС",
                    "НАИМЕНОВАНИЕ ПОСТАВЩИКА",
                    "Классификатор ОКПД2",
                    "Дата обновления",
                ]
                dataframe = pd.DataFrame(
                    [
                        ["служебная строка"],
                        ["ещё одна служебная строка"],
                        headers,
                        [
                            "Подтверждена 09.07.2026 (mail@example.ru)",
                            'ООО "Вальвида" (ИНН 7801679362)',
                            "Затворы запорные (18010105)",
                            "Затвор дисковый",
                            "670 000,00",
                            'АО "АСТИАГ"',
                            "28.14.13.132: Затворы дисковые",
                            "09.07.2026",
                        ],
                    ]
                )

                self.assertEqual(_find_brif_header_row(dataframe), 2)
                self.assertEqual(_detect_file1_format(dataframe), "brif_registry")
                columns = _build_header_map(dataframe, 2)
                parsed = _parse_brif_registry_row(dataframe.iloc[3], columns)

                self.assertEqual(parsed["nomenclature_name"], "Затвор дисковый")
                self.assertEqual(parsed["supplier_name"], 'АО "АСТИАГ"')
                self.assertIn("Вальвида", parsed["manufacturer_name"])
                self.assertEqual(parsed["manufacturer_inn"], "7801679362")
                self.assertEqual(parsed["manufacturer_identifier_type"], "INN")
                self.assertEqual(parsed["okpd2_code"], "28.14.13.132")
                self.assertEqual(parsed["mtr_class"], "18010105")
                self.assertEqual(parsed["price"], Decimal("670000.00"))
                self.assertEqual(parsed["contract_date"], date(2026, 7, 9))
                self.assertEqual(parsed["supplier_site"], "mail@example.ru")


class LegacyImportTests(unittest.TestCase):
    def test_real_legacy_import_branch_does_not_raise_name_error(self):
        session, engine = make_session()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "legacy.xlsx"
                workbook = Workbook()
                sheet = workbook.active
                sheet.append(["legacy metadata"])
                sheet.append(["legacy metadata"])
                sheet.append(["legacy headers"])
                sheet.append(
                    [
                        None,
                        "Legacy product",
                        None,
                        "28.14.13.110",
                        "18010107",
                        "09.02.2026 tender@example.ru",
                        "123,45",
                        "10.02.2026",
                        "RUB",
                        2,
                        'ООО "Изготовитель"',
                        "5321034434",
                        "7701234567",
                    ]
                )
                workbook.save(path)

                response = import_file1(session, path)

            self.assertEqual(response["errors"], [])
            self.assertEqual(response["imported"], 1)
            entry = session.scalar(select(SupplierEntry))
            self.assertEqual(entry.manufacturer_inn, "5321034434")
            self.assertEqual(entry.supplier_inn, "7701234567")
        finally:
            session.close()
            engine.dispose()


@unittest.skipUnless(WITHOUT_INN_PATH.exists(), "Тестовый XLSX без отдельного ИНН не найден")
class AttachedWorkbookWithoutInnTests(unittest.TestCase):
    def test_import_and_repeat_import(self):
        session, engine = make_session()
        try:
            response = import_file1(session, WITHOUT_INN_PATH)
            self.assertEqual(response["errors"], [])
            self.assertEqual(response["imported"], 356)
            self.assertEqual(response["skipped"], 1)
            self.assertEqual(len(response["skipped_rows"]), 1)

            first = session.scalar(select(SupplierEntry).order_by(SupplierEntry.id))
            self.assertEqual(first.manufacturer_inn, "7801679362")
            self.assertEqual(first.manufacturer_identifier_type, "INN")
            self.assertEqual(first.okpd2_code, "28.14.13.132")
            self.assertEqual(first.mtr_class, "18010105")
            self.assertEqual(first.price, Decimal("670000.00"))
            self.assertEqual(first.contract_date, date(2026, 7, 9))
            self.assertIn("taskaeva@astiag.ru", first.supplier_site)

            dembla = session.scalar(
                select(SupplierEntry)
                .where(SupplierEntry.nomenclature_name.like("Затвор поворот.%"))
                .order_by(SupplierEntry.id)
            )
            self.assertIn("Dembla Valves Ltd.", dembla.manufacturer_name)
            self.assertEqual(dembla.manufacturer_inn, "U29121MH1989PLC051650")
            self.assertEqual(dembla.manufacturer_identifier_type, "INIO")
            self.assertEqual(dembla.mtr_class, "18010105")

            empty_mtr = session.scalar(
                select(func.count()).select_from(SupplierEntry).where(SupplierEntry.mtr_class.is_(None))
            )
            self.assertEqual(empty_mtr, 0)

            repeated = import_file1(session, WITHOUT_INN_PATH)
            self.assertEqual(repeated["errors"], [])
            self.assertEqual(repeated["imported"], 0)
            self.assertEqual(repeated["skipped"], 357)
            self.assertEqual(len(repeated["skipped_rows"]), 357)
        finally:
            session.close()
            engine.dispose()

    def test_raw_identifier_distribution(self):
        dataframe = pd.read_excel(WITHOUT_INN_PATH, header=None, engine="openpyxl", dtype=object)
        identifiers = [
            extract_identifier(None, name_value=row.iloc[10])["type"]
            for _, row in dataframe.iloc[4:].iterrows()
        ]
        self.assertEqual(Counter(identifiers), Counter({"INIO": 269, "INN": 88}))


@unittest.skipUnless(WITH_INN_PATH.exists(), "Тестовый XLSX с отдельным ИНН не найден")
class AttachedWorkbookWithInnTests(unittest.TestCase):
    def test_import_and_repeat_import(self):
        session, engine = make_session()
        try:
            response = import_file1(session, WITH_INN_PATH)
            self.assertEqual(response["errors"], [])
            self.assertEqual(response["imported"], 297)
            self.assertEqual(response["skipped"], 3)
            self.assertEqual(len(response["skipped_rows"]), 3)

            first = session.scalar(select(SupplierEntry).order_by(SupplierEntry.id))
            self.assertEqual(first.manufacturer_inn, "5321034434")
            self.assertEqual(first.manufacturer_identifier_type, "INN")
            self.assertEqual(first.mtr_class, "18010107")
            self.assertEqual(first.contract_date, date(2026, 2, 9))
            self.assertIn("tender@mksplav.ru", first.supplier_site)

            empty_mtr = session.scalar(
                select(func.count()).select_from(SupplierEntry).where(SupplierEntry.mtr_class.is_(None))
            )
            self.assertEqual(empty_mtr, 0)

            repeated = import_file1(session, WITH_INN_PATH)
            self.assertEqual(repeated["errors"], [])
            self.assertEqual(repeated["imported"], 0)
            self.assertEqual(repeated["skipped"], 300)
            self.assertEqual(len(repeated["skipped_rows"]), 300)
        finally:
            session.close()
            engine.dispose()

    def test_raw_identifier_distribution(self):
        dataframe = pd.read_excel(WITH_INN_PATH, header=None, engine="openpyxl", dtype=object)
        identifiers = [
            extract_identifier(row.iloc[12], name_value=row.iloc[11])["type"]
            for _, row in dataframe.iloc[4:].iterrows()
        ]
        inio_markers = sum(
            bool(re.search(r"\(\s*ИНИО\b", str(row.iloc[11]), re.IGNORECASE))
            for _, row in dataframe.iloc[4:].iterrows()
        )
        self.assertEqual(inio_markers, 30)
        self.assertEqual(Counter(identifiers), Counter({"INN": 270, "INIO": 29, None: 1}))


if __name__ == "__main__":
    unittest.main()
