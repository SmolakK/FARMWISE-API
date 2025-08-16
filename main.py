from fastapi import FastAPI
from routers.data_call import api_router
from routers.auth import auth_router
from routers.frontpage import frontpage_router
from security import setup_security
from scheduler import start_scheduler, shutdown_scheduler
from logging_config import logger
from user_database import engine, Base
import tempfile
import shutil
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import os

# Create the database tables
Base.metadata.create_all(bind=engine)

# Create a temporary directory for the application
temp_dir = tempfile.mkdtemp()
logger.info(f"Temporary directory created at {temp_dir}")


# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup logic
        static_temp_dir = os.path.abspath("temp_files")
        os.makedirs(static_temp_dir, exist_ok=True)
        app.state.temp_dir = static_temp_dir
        start_scheduler(temp_dir)
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

app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup security configurations
setup_security(app)

# Run the application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",  # Specify the module and app
        host="0.0.0.0",
        port=8000,
        workers=4  # Number of worker processes
    )