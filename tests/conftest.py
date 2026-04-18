import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.db import Base, get_db  # noqa: E402
from app.main import app, worker as app_worker  # noqa: E402
from app.worker import OrderPlacementWorker  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def setup_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    original_start = app_worker.start
    original_stop = app_worker.stop
    app_worker.start = lambda: None
    app_worker.stop = lambda: None
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app_worker.start = original_start
    app_worker.stop = original_stop


@pytest.fixture
def worker() -> OrderPlacementWorker:
    return OrderPlacementWorker()
