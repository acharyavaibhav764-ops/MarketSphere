"""
core/database.py — SQLAlchemy database engine and session management.

Provides async engine and session factory for PostgreSQL/SQLite persistence of:
  - SourceRegistry (models/source.py)
  - ComplianceRule (models/rule.py)
"""
from collections.abc import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

logger = logging.getLogger(__name__)

# Convert standard postgresql:// to postgresql+asyncpg:// if needed
db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
