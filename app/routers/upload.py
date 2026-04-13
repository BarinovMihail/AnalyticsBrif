import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import UploadResponse
from app.services.parser_file1 import import_file1
from app.services.parser_file2 import import_file2


router = APIRouter(prefix="/api/upload", tags=["upload"])


def _save_temp_file(upload_file: UploadFile) -> Path:
    suffix = Path(upload_file.filename or "").suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        upload_file.file.seek(0)
        shutil.copyfileobj(upload_file.file, temp_file)
        return Path(temp_file.name)


def _validate_excel(upload_file: UploadFile):
    if not (upload_file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Поддерживаются только .xlsx файлы")


@router.post("/file1", response_model=UploadResponse)
def upload_file1(file: UploadFile = File(...), db: Session = Depends(get_db)):
    _validate_excel(file)
    temp_path = _save_temp_file(file)
    try:
        return import_file1(db, temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/file2", response_model=UploadResponse)
def upload_file2(file: UploadFile = File(...), db: Session = Depends(get_db)):
    _validate_excel(file)
    temp_path = _save_temp_file(file)
    try:
        return import_file2(db, temp_path)
    finally:
        temp_path.unlink(missing_ok=True)
