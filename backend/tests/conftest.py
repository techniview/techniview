import pytest
from app.core.db import get_db
from app.models import Base
from app.seed import seed_demo
from httpx import ASGITransport, AsyncClient
from main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        seed_demo(session)
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
async def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def student_client(client):
    response = await client.post(
        "/api/auth/login",
        json={"email": "student@techniview.local", "password": "student-demo"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
async def teacher_client(client):
    response = await client.post(
        "/api/auth/login",
        json={"email": "teacher@techniview.local", "password": "teacher-demo"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
