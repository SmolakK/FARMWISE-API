from fastapi import FastAPI
from farmwise_api.server.routers.data_call import api_router
from farmwise_api.server.routers.auth import auth_router
from farmwise_api.server.routers.frontpage import frontpage_router
from farmwise_api.server.security import setup_security
from farmwise_api.server.scheduler import start_scheduler, shutdown_scheduler
from farmwise_api.server.logging_config import logger
from farmwise_api.server.user_database import engine, Base
import shutil
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import os
import asyncio
from pathlib import Path

from farmwise_api.core.utils.paths import CACHE_ROOT, prefetch_all

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMP_DIR = Path(
    os.getenv("FARMWISE_TEMP_DIR", CACHE_ROOT / "temp_files")
).resolve()

# Create the database tables
Base.metadata.create_all(bind=engine)

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup logic
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        app.state.temp_dir = str(TEMP_DIR)
        if os.getenv("FARMWISE_PREFETCH_DATA", "").lower() in {"1", "true", "yes"}:
            await asyncio.to_thread(prefetch_all)
        start_scheduler(app.state.temp_dir)
        yield
    finally:
        # Shutdown logic
        shutdown_scheduler()
        shutil.rmtree(app.state.temp_dir, ignore_errors=True)
        logger.info(f"Temporary directory {app.state.temp_dir} removed")
        logger.info("Application shutdown completed.")


# Create the FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Include API routers
app.include_router(api_router)
app.include_router(auth_router)
app.include_router(frontpage_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Setup security configurations
setup_security(app)

# Run the application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "farmwise_api.server.main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,  # Number of worker processes
        proxy_headers=True
    )
