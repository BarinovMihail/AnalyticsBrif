import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


# override=False: Docker env vars take priority over .env file
load_dotenv(override=False)


DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "brifdb")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Локальный запуск без MySQL/Docker: DB_ENGINE=sqlite uvicorn app.main:app ...
if os.getenv("DB_ENGINE", "mysql").lower() == "sqlite":
    DATABASE_URL = os.getenv("DB_URL", "sqlite:///./analyticsbrif_local.db")
else:
    DATABASE_URL = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        "?charset=utf8mb4"
    )

engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def ensure_optional_columns() -> None:
    # ALTER-миграции нужны только для существующей MySQL-схемы;
    # на SQLite таблицы создаются create_all сразу в полном виде.
    if engine.dialect.name != "mysql":
        return
    inspector = inspect(engine)
    table_columns = {
        "supplier_entries": {
            "manufacturer_identifier_type": "VARCHAR(10) NULL",
            "supplier_name": "VARCHAR(500) NULL",
        },
        "mtr_cards": {"manufacturer_identifier_type": "VARCHAR(10) NULL"},
    }

    with engine.begin() as connection:
        for table_name, columns in table_columns.items():
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def ensure_column_sizes() -> None:
    if engine.dialect.name != "mysql":
        return
    sized_columns = {
        "supplier_entries": {
            "okpd2_code": "VARCHAR(255) NULL",
            "mtr_class": "VARCHAR(255) NULL",
            "supplier_site": "VARCHAR(255) NULL",
            "manufacturer_inn": "VARCHAR(255) NULL",
            "supplier_inn": "VARCHAR(255) NULL",
            "currency": "VARCHAR(255) NULL",
        },
        "mtr_cards": {
            "manufacturer_inn": "VARCHAR(255) NULL",
            "mtr_class": "VARCHAR(255) NULL",
            "currency_code": "VARCHAR(255) NULL",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in sized_columns.items():
            for column_name, ddl in columns.items():
                connection.execute(text(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
