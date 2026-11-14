import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    pass


def create_database(database_url: Optional[str] = None):
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./grocery_tracker.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
