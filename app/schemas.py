from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SkippedRow(BaseModel):
    row: int
    reason: str
    preview: dict[str, str] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
    skipped_rows: list[SkippedRow] = Field(default_factory=list)


class SupplierEntryListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nomenclature_name: str
    manufacturer_inn: str | None = None
    supplier_site: str | None = None
    contract_date: date | None = None


class StatsResponse(BaseModel):
    supplier_entries_count: int
    mtr_cards_count: int
    characteristics_count: int


class SearchFilter(BaseModel):
    char_name: str
    operator: str
    value: str = Field(min_length=1)


class SearchRequest(BaseModel):
    filters: list[SearchFilter]


class SearchResultItem(BaseModel):
    card_guid: str
    card_nomenclature: str | None = None
    manufacturer_inn: str | None = None
    manufacturer_name: str | None = None
    supplier_name: str | None = None
    contract_date: date | None = None
    price: float | None = None
    currency: str | None = None
    matched_characteristics: dict[str, str]
    all_characteristics: dict[str, str]


class SearchResponse(BaseModel):
    total: int
    results: list[SearchResultItem]
