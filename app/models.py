from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SupplierEntry(Base):
    __tablename__ = "supplier_entries"
    __table_args__ = (
        UniqueConstraint(
            "manufacturer_inn",
            "nomenclature_name",
            "contract_date",
            name="uq_supplier_entry_key",
        ),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nomenclature_name: Mapped[str] = mapped_column(String(500), nullable=False)
    okpd2_code: Mapped[str | None] = mapped_column(String(50))
    mtr_class: Mapped[str | None] = mapped_column(String(50))
    supplier_site: Mapped[str | None] = mapped_column(String(255))
    manufacturer_inn: Mapped[str | None] = mapped_column(String(20), index=True)
    supplier_inn: Mapped[str | None] = mapped_column(String(20))
    manufacturer_name: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[float | None] = mapped_column(DECIMAL(15, 2))
    currency: Mapped[str | None] = mapped_column(String(10))
    quantity: Mapped[int | None] = mapped_column(Integer)
    contract_date: Mapped[datetime | None] = mapped_column(Date)
    delivery_date: Mapped[datetime | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class MTRCard(Base):
    __tablename__ = "mtr_cards"
    __table_args__ = (
        UniqueConstraint("guid", name="uq_mtr_card_guid"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    guid: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nomenclature_name: Mapped[str | None] = mapped_column(String(500))
    manufacturer_inn: Mapped[str | None] = mapped_column(String(20), index=True)
    mtr_class: Mapped[str | None] = mapped_column(String(50))
    price: Mapped[float | None] = mapped_column(DECIMAL(15, 2))
    currency_code: Mapped[str | None] = mapped_column(String(10))
    delivery_date: Mapped[datetime | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    characteristics: Mapped[list["CardCharacteristic"]] = relationship(
        "CardCharacteristic",
        back_populates="card",
        cascade="all, delete-orphan",
    )


class CardCharacteristic(Base):
    __tablename__ = "card_characteristics"
    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("mtr_cards.id", ondelete="CASCADE"), index=True)
    char_name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    char_value: Mapped[str] = mapped_column(Text, nullable=False)
    char_value_numeric: Mapped[float | None] = mapped_column(Float)
    range_min: Mapped[float | None] = mapped_column(Float)
    range_max: Mapped[float | None] = mapped_column(Float)

    card: Mapped[MTRCard] = relationship("MTRCard", back_populates="characteristics")
