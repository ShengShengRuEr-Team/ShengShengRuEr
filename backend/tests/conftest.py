"""pytest 环境准备：独立测试库、迁移、种子数据。"""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_NAME = os.getenv("TEST_DATABASE_NAME", "shengshengruer_test")


def _base_database_url() -> str:
    env_value = os.getenv("DATABASE_URL")
    if env_value:
        return env_value
    file_value = dotenv_values(BACKEND_DIR / ".env").get("DATABASE_URL")
    if not file_value:
        raise RuntimeError("未找到 DATABASE_URL，请先配置 backend/.env")
    return str(file_value)


def _test_database_url(base_url: str) -> str:
    return make_url(base_url).set(database=TEST_DATABASE_NAME).render_as_string(
        hide_password=False
    )


def _ensure_database(base_url: str) -> None:
    base = make_url(base_url)
    if base.database == TEST_DATABASE_NAME:
        raise RuntimeError("测试库不能与 DATABASE_URL 指向的开发库同名")
    admin_url: URL = base.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE_NAME},
            ).scalar()
            if not exists:
                connection.execute(
                    text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
                )
    finally:
        engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> Generator[None]:
    base_url = _base_database_url()
    test_url = _test_database_url(base_url)
    _ensure_database(base_url)

    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = test_url
    os.environ["JWT_SECRET_KEY"] = "pytest-only-secret-key-0123456789abcdef"
    os.environ["JWT_ALGORITHM"] = "HS256"
    os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "120"

    from alembic import command
    from alembic.config import Config

    from app.db.base import engine
    from app.seed import seed

    # 测试库每次从空 schema 开始，保证迁移文件可独立建表。
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_config.set_main_option(
        "sqlalchemy.url", test_url.replace("%", "%%")
    )
    command.upgrade(alembic_config, "head")
    seed()

    yield

    engine.dispose()


@pytest.fixture(scope="session")
def client(prepared_database: None) -> Generator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


@pytest.fixture
def admin_token(client: TestClient) -> str:
    return login(client, "admin", "admin123")


@pytest.fixture
def student_token(client: TestClient) -> str:
    return login(client, "student", "student123")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
