from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CardCharacteristic, MTRCard, SupplierEntry
from app.schemas import SearchRequest, SearchResponse, StatsResponse, SupplierEntryListItem
from app.services.comparator import clear_file1_data, clear_file2_data, export_search_results, search_cards


router = APIRouter(tags=["search"])


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    return {
        "supplier_entries_count": db.scalar(select(func.count()).select_from(SupplierEntry)) or 0,
        "mtr_cards_count": db.scalar(select(func.count()).select_from(MTRCard)) or 0,
        "characteristics_count": db.scalar(select(func.count()).select_from(CardCharacteristic)) or 0,
    }


@router.get("/api/file1/entries", response_model=list[SupplierEntryListItem])
def get_file1_entries(db: Session = Depends(get_db)):
    return db.scalars(
        select(SupplierEntry).order_by(SupplierEntry.contract_date.desc(), SupplierEntry.id.desc())
    ).all()


@router.get("/api/file2/characteristics-names", response_model=list[str])
def get_characteristics_names(db: Session = Depends(get_db)):
    return db.scalars(
        select(CardCharacteristic.char_name)
        .distinct()
        .order_by(CardCharacteristic.char_name.asc())
    ).all()


@router.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest, db: Session = Depends(get_db)):
    results = search_cards(db, request.filters)
    return {"total": len(results), "results": results}


@router.post("/api/export")
def export_results(request: SearchRequest, db: Session = Depends(get_db)):
    results = search_cards(db, request.filters)
    stream = export_search_results(results, request.filters)
    headers = {"Content-Disposition": 'attachment; filename="search_results.xlsx"'}
    return StreamingResponse(
        stream,
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.delete("/api/data/file1")
def delete_file1_data(db: Session = Depends(get_db)):
    clear_file1_data(db)
    return {"status": "ok"}


@router.delete("/api/data/file2")
def delete_file2_data(db: Session = Depends(get_db)):
    clear_file2_data(db)
    return {"status": "ok"}
