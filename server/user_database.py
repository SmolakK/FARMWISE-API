import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from core.utils.paths import CACHE_ROOT

DEFAULT_DATABASE_PATH = CACHE_ROOT / "user_storage.db"
DEFAULT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
SQLALCHEMY_DATABASE_URL = os.getenv(
    "FARMWISE_DATABASE_URL",
    f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}",
)

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
