from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.dependencies import uploader
from api.legacy import legacy_router
from api.v1.router import api_router
from core import GenerationError, StorageError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("Initializing application resources...")
    try:
        if uploader is not None:
            uploader.ensure_bucket()
        else:
            logger.warning("Uploader unavailable — skipping bucket check (demo mode).")
    except Exception as exc:
        # Never crash startup when MinIO is not running (local/demo dev).
        logger.warning("Storage bucket check skipped: %s", exc)
    try:
        from core.database import engine as _db_engine
        from models.source import Base as _Base

        if _db_engine is not None:
            async with _db_engine.begin() as conn:
                # create_all is non-destructive: only missing tables are created.
                await conn.run_sync(_Base.metadata.create_all)
            logger.info("Database tables verified.")
        else:
            logger.warning("Database engine unavailable — DB endpoints will return 503.")
    except Exception as exc:
        logger.warning("Database table check skipped: %s", exc)
    yield
    logger.info("Shutting down application resources...")


app = FastAPI(title="MarketSphere (MochaTrade) Policy Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _register_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @application.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    if StorageError is not None:

        @application.exception_handler(StorageError)
        async def storage_error_handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=502, content={"detail": str(exc)})

    if GenerationError is not None:

        @application.exception_handler(GenerationError)
        async def generation_error_handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=503, content={"detail": str(exc)})


_register_error_handlers(app)


# Mount Modern Versioned API & Health Check
app.include_router(api_router)

# Mount Legacy Compatibility Routes
app.include_router(legacy_router)


# Serve the static frontend (frontend/index.html, app.js, style.css) so the
# project runs as a single server: `uvicorn main:app` -> http://localhost:8000/
_FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/", include_in_schema=False)
async def serve_frontend_index():
    index_file = _FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    return JSONResponse(
        status_code=200,
        content={"service": "MarketSphere API", "docs": "/docs", "health": "/health"},
    )


if _FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(_FRONTEND_DIR), html=False),
        name="frontend",
    )

    # index.html references ./app.js and ./style.css relatively, so when the
    # UI is served from "/" the browser requests /app.js and /style.css.
    for _asset in ("app.js", "analyzer.js", "style.css", "favicon.ico"):
        _asset_path = _FRONTEND_DIR / _asset
        if _asset_path.exists():

            async def _serve_asset(request: Request, _p=_asset_path):
                media = "text/javascript" if _p.suffix == ".js" else None
                return FileResponse(_p, media_type=media)

            app.add_api_route(
                f"/{_asset}",
                _serve_asset,
                methods=["GET"],
                include_in_schema=False,
            )
