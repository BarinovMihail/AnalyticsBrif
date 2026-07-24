from __future__ import annotations

import unittest

from app.services.identifier_utils import extract_identifier, normalize_inn


class IdentifierUtilsTests(unittest.TestCase):
    def test_separate_valid_inn_is_used(self):
        self.assertEqual(
            extract_identifier("5321034434", name_value='ООО "Пример"'),
            {"value": "5321034434", "type": "INN"},
        )

    def test_missing_separate_inn_falls_back_to_marked_name(self):
        self.assertEqual(
            extract_identifier(None, name_value='ООО "Вальвида" (ИНН 7801679362)'),
            {"value": "7801679362", "type": "INN"},
        )

    def test_blank_separate_inn_falls_back_to_marked_name(self):
        self.assertEqual(
            extract_identifier("  ", name_value='ООО "Вальвида" (ИНН: 7801-679-362)'),
            {"value": "7801679362", "type": "INN"},
        )

    def test_twelve_digit_inn_is_preserved_as_text(self):
        self.assertEqual(normalize_inn("500100732259"), "500100732259")

    def test_leading_zero_inn_is_preserved_or_recovered(self):
        self.assertEqual(normalize_inn("0274173735"), "0274173735")
        self.assertEqual(normalize_inn(274173735), "0274173735")
        self.assertEqual(normalize_inn("000047152371"), "000047152371")

    def test_inio_is_extracted_from_marked_name(self):
        self.assertEqual(
            extract_identifier(
                None,
                name_value="Dembla Valves Ltd. (ИНИО U29121MH1989PLC051650)",
            ),
            {"value": "U29121MH1989PLC051650", "type": "INIO"},
        )

    def test_empty_inio_marker_is_not_an_identifier(self):
        self.assertEqual(
            extract_identifier(None, name_value='АО "Фирма" (ИНИО )'),
            {"value": None, "type": None},
        )

    def test_valid_separate_inn_has_priority_over_name_marker(self):
        self.assertEqual(
            extract_identifier(
                "5321034434",
                name_value='ООО "Пример" (ИНН 7801679362)',
            ),
            {"value": "5321034434", "type": "INN"},
        )

    def test_invalid_separate_inn_falls_back_to_name_marker(self):
        self.assertEqual(
            extract_identifier(
                "не ИНН",
                name_value="Dembla Valves Ltd. (ИНИО U29121MH1989PLC051650)",
            ),
            {"value": "U29121MH1989PLC051650", "type": "INIO"},
        )

    def test_unmarked_random_digits_in_name_are_not_an_identifier(self):
        self.assertEqual(
            extract_identifier(None, name_value='ООО "Завод 7801679362"'),
            {"value": None, "type": None},
        )

    def test_whole_organization_name_is_not_normalized_as_inn(self):
        self.assertIsNone(normalize_inn('ООО "Завод 7801679362"'))


if __name__ == "__main__":
    unittest.main()
