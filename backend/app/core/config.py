"""应用配置读取与启动前校验。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

APP_ENV = Literal["development", "test", "staging", "production"]

JWT_PLACEHOLDER_VALUES = {
    "change_me",
    "changeme",
    "change-me",
    "your-secret-key",
    "secret",
    "jwt_secret_key",
}

MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """从环境变量与 backend/.env 读取配置。"""

    app_env: APP_ENV = "development"
    log_level: str = "INFO"

    database_url: str
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=120, gt=0)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL 必须以 postgresql+psycopg:// 开头")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if len(secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY 至少需要 {MIN_JWT_SECRET_LENGTH} 个字符"
            )
        if secret.lower() in JWT_PLACEHOLDER_VALUES or "change_me" in secret.lower():
            raise ValueError("JWT_SECRET_KEY 不能使用占位值")
        return SecretStr(secret)

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("JWT_ALGORITHM 只允许 HS256")
        return value

    @property
    def access_token_expire_seconds(self) -> int:
        return self.access_token_expire_minutes * 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
