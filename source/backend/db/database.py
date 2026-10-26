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
    from models.auth_models import AuthControl, SchemaVersion
    from sqlalchemy import text
    if settings.AUTH_MODE=='standalone' and engine.dialect.name=='sqlite':
        from sqlalchemy import event
        if not event.contains(engine.sync_engine,'connect',_standalone_sqlite):
            event.listen(engine.sync_engine,'connect',_standalone_sqlite)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Explicit additive ingestion migrations; fail startup on actual migration errors.
        from sqlalchemy import inspect
        columns=await conn.run_sync(lambda connection: {c['name'] for c in inspect(connection).get_columns('ingestion_documents')})
        for name in ('evidence_date','review_due'):
            if name not in columns:
                await conn.execute(text(f'ALTER TABLE ingestion_documents ADD COLUMN {name} DATE'))
        # Add only reviewed legacy columns; never swallow actual migration failures.
        for table, name, kind in [('grants','meta','TEXT'),('users','identity_id','VARCHAR(64)')]:
            existing = await conn.run_sync(lambda connection: {c['name'] for c in inspect(connection).get_columns(table)})
            if name not in existing:
                await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {kind}'))
        await conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_identity_id ON users (identity_id)")
        )
        # Refuse to serve a partially migrated schema.
        for table in Base.metadata.sorted_tables:
            present = await conn.run_sync(lambda connection: {c['name'] for c in inspect(connection).get_columns(table.name)})
            if set(table.columns.keys()) - present:
                raise RuntimeError('Database schema requires a reviewed migration: ' + table.name)
        import time
        from sqlalchemy.dialects.sqlite import insert
        if engine.dialect.name == 'sqlite':
            await conn.execute(insert(SchemaVersion).values(version=2,applied_at=int(time.time())).on_conflict_do_nothing())
            if settings.AUTH_MODE == 'standalone':
                await conn.execute(insert(AuthControl).values(id=1,bootstrapped=False).on_conflict_do_nothing())


def _standalone_sqlite(connection,record):
    cursor=connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA busy_timeout=5000')
    cursor.close()
