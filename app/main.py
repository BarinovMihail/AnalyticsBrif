import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine, ensure_optional_columns
from app.routers.search import router as search_router
from app.routers.upload import router as upload_router


logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BRIF MTR Comparator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
ensure_optional_columns()

app.include_router(upload_router)
app.include_router(search_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(frontend_dir / "index.html")
