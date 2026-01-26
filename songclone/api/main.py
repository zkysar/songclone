"""FastAPI application for SongClone."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from songclone.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    logger.info("SongClone API starting up...")

    sessions_dir = Path("sessions")
    sessions_dir.mkdir(exist_ok=True)

    yield

    logger.info("SongClone API shutting down...")


app = FastAPI(
    title="SongClone API",
    description="AI-powered song recreation system using REAPER DAW",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

static_dir = Path(__file__).parent.parent / "web" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def run() -> None:
    """Entry point for running the server."""
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(
        "songclone.api.main:app",
        host=host,
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    run()
