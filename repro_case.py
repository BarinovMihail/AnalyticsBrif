# Воспроизведение кейса «Клапан сильфонный КЗА 0208-100М1-08»:
# импорт обоих файлов в чистую SQLite-БД и поиск по DN=100 + Класс безопасности=3.
import os
from pathlib import Path

os.environ["DB_ENGINE"] = "sqlite"
DB_PATH = Path(__file__).parent / "repro_case.db"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["DB_URL"] = f"sqlite:///{DB_PATH.as_posix()}"

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import MTRCard, SupplierEntry  # noqa: E402
from app.services.parser_file1 import import_file1  # noqa: E402
from app.services.parser_file2 import import_file2  # noqa: E402
from app.services.comparator import export_search_results, search_cards  # noqa: E402
from app.schemas import SearchFilter  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()

f1 = r"C:\Users\Barinov_MA\Downloads\Файл выгрузки. (13).xlsx"
f2 = r"C:\Users\Barinov_MA\Downloads\Клапаны запорные_18010107.XLSX"
print("import file1:", {k: v for k, v in import_file1(db, f1).items() if k != "skipped_rows"})
print("import file2:", {k: v for k, v in import_file2(db, f2).items() if k != "skipped_rows"})

# Что реально лежит в БД по целевой номенклатуре и по ИНН 5252012050
print("\n-- SupplierEntry с номенклатурой КЗА 0208-100М1-08:")
for e in db.query(SupplierEntry).filter(SupplierEntry.nomenclature_name.contains("0208-100М1-08")).all():
    print(f"  id={e.id} поставщик={e.supplier_name!r} ИНН изг.={e.manufacturer_inn!r} дата={e.contract_date} цена={e.price}")
print("-- SupplierEntry с manufacturer_inn=5252012050 (первые 6, сортировка как в поиске):")
for e in (
    db.query(SupplierEntry)
    .filter(SupplierEntry.manufacturer_inn == "5252012050")
    .order_by(SupplierEntry.contract_date.desc(), SupplierEntry.id.desc())
    .limit(6)
):
    print(f"  id={e.id} номенклатура={e.nomenclature_name[:45]!r} поставщик={e.supplier_name!r} дата={e.contract_date}")

filters = [
    SearchFilter(char_name="Диаметр номинальный DN", operator="eq", value="100"),
    SearchFilter(char_name="Класс безопасности", operator="eq_str", value="3"),
]
results = search_cards(db, filters)
print(f"\nПоиск DN=100 И КБ=3: всего строк {len(results)}")
for r in results:
    marker = "  <<< ЦЕЛЬ" if "0208-100М1-08" in (r["card_nomenclature"] or "") else ""
    print(
        f"  {r['card_nomenclature'][:45]!r} | изг={str(r['manufacturer_name'])[:25]!r} "
        f"| пост={r['supplier_name']!r} | дата={r['contract_date']} | цена={r['price']}{marker}"
    )

target = [r for r in results if "0208-100М1-08" in (r["card_nomenclature"] or "")]
ok_suppliers = {r["supplier_name"] for r in target}
expected = {'ООО "ПФ "ОКА"', 'ООО "АКСИОМА"'}
print(f"\nПроверка целевой карточки: поставщики в выдаче = {ok_suppliers}")
print("OK: найдены ровно ОКА и АКСИОМА" if ok_suppliers == expected else f"FAIL: ожидались {expected}")

out = export_search_results(results, filters)
Path("repro_search_results.xlsx").write_bytes(out.read())
print("\nЭкспорт: repro_search_results.xlsx")
db.close()
