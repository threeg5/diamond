from contextlib import asynccontextmanager
from threading import Thread
import os
import time
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from diamond.config import DATA_DIR, DB_PATH, cors_origins, ingest_years
from diamond.db import connect
from diamond.routes import router


def _player_count() -> int:
    if not DB_PATH.exists():
        return 0
    conn = connect()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
    except Exception:
        return 0
    finally:
        conn.close()


def _ingest_if_empty() -> None:
    resume = DB_PATH.exists()
    if resume and _player_count():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = DATA_DIR / "ingest.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return
    try:
        if resume and _player_count():
            return
        from diamond.ingest import run_ingest

        years = ingest_years()
        print(f"Ingesting MLB Stats API data for {years} (resume={resume})")
        run_ingest(years, resume=resume)
    except Exception:
        traceback.print_exc()
    finally:
        lock.unlink(missing_ok=True)


def _boot_ingest() -> None:
    time.sleep(20)
    _ingest_if_empty()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Could not create data dir {DATA_DIR}: {exc}")
    if not DB_PATH.exists() or not _player_count():
        Thread(target=_boot_ingest, daemon=True).start()
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


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "diamond-api",
        "health": "/health",
        "meta": "/api/meta",
    }
