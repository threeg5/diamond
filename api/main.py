from contextlib import asynccontextmanager
from threading import Thread
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from diamond.config import DATA_DIR, DB_PATH, cors_origins
from diamond.routes import router


def _ingest_if_empty() -> None:
    if DB_PATH.exists():
        return
    lock = DATA_DIR / "ingest.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return
    try:
        if DB_PATH.exists():
            return
        from diamond.ingest import run_ingest

        print(f"No database at {DB_PATH}; ingesting MLB Stats API data")
        run_ingest()
    finally:
        lock.unlink(missing_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        Thread(target=_ingest_if_empty, daemon=True).start()
    yield


app = FastAPI(title="Diamond", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
