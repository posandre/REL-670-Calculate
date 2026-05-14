from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.entities import Base


def create_sqlite_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{database_path}", future=True)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
