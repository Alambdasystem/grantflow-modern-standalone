from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings
import os
from fastapi import Depends
from auth.jwt_handler import get_current_user_token

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.SCREENSHOT_DIR, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_public_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db(identity: dict = Depends(get_current_user_token)):
    from auth.ownership import bind_identity
    async with AsyncSessionLocal() as session:
        try:
            await bind_identity(session, identity)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    from models import models  # noqa — ensures tables are registered
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Explicit additive ingestion migrations; fail startup on actual migration errors.
        from sqlalchemy import inspect
        columns=await conn.run_sync(lambda connection: {c['name'] for c in inspect(connection).get_columns('ingestion_documents')})
        for name in ('evidence_date','review_due'):
            if name not in columns:
                await conn.execute(text(f'ALTER TABLE ingestion_documents ADD COLUMN {name} DATE'))
        # Column migrations for existing tables (SQLite doesn't support IF NOT EXISTS in ALTER TABLE)
        for stmt in [
            "ALTER TABLE grants ADD COLUMN meta TEXT",
            "ALTER TABLE users ADD COLUMN identity_id VARCHAR(64)",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists
        await conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_identity_id ON users (identity_id)")
        )
