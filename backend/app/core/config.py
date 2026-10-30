import os
from pathlib import Path

from sqlalchemy import URL


def _setting(name: str, default: str = "") -> str:
    secret_file = os.getenv(f"{name}_FILE")
    if secret_file:
        return Path(secret_file).read_text(encoding="utf-8").rstrip("\r\n")
    return os.getenv(name, default)


def build_database_url(
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
) -> str:
    return URL.create(
        drivername="mysql+pymysql",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


class Settings:
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_TIMEOUT_SECONDS = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))
    EMAIL_DELIVERY_MODE = os.getenv("EMAIL_DELIVERY_MODE", "disabled")
    EMAIL_CAPTURE_DIR = os.getenv("EMAIL_CAPTURE_DIR", "/tmp/techniview-mail")
    EMAIL_SIGNING_KEY = _setting("EMAIL_SIGNING_KEY")
    RESEND_API_KEY = _setting("RESEND_API_KEY")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:5173")
    PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
    EMAIL_VERIFICATION_MINUTES = int(os.getenv("EMAIL_VERIFICATION_MINUTES", "1440"))
    EMAIL_TOKEN_COOLDOWN_SECONDS = int(os.getenv("EMAIL_TOKEN_COOLDOWN_SECONDS", "60"))
    EMAIL_MAX_ATTEMPTS = int(os.getenv("EMAIL_MAX_ATTEMPTS", "5"))
    EMAIL_LEASE_SECONDS = int(os.getenv("EMAIL_LEASE_SECONDS", "60"))
    GO_JUDGE_URL = os.getenv("GO_JUDGE_URL", "http://go-judge:5050")
    GO_JUDGE_WALL_SECONDS = int(os.getenv("GO_JUDGE_WALL_SECONDS", "5"))
    WORKER_LEASE_SECONDS = int(os.getenv("WORKER_LEASE_SECONDS", "60"))
    if not (0 < GO_JUDGE_WALL_SECONDS < WORKER_LEASE_SECONDS - 20):
        raise ValueError("direct execution timeout must fit within the worker lease")
    BIG_O_OLLAMA_URL = os.getenv("BIG_O_OLLAMA_URL", "").rstrip("/")
    BIG_O_OLLAMA_MODEL = os.getenv("BIG_O_OLLAMA_MODEL", "qwen3.8:27b")
    BIG_O_OLLAMA_TIMEOUT_SECONDS = float(
        os.getenv("BIG_O_OLLAMA_TIMEOUT_SECONDS", "90")
    )
    BIG_O_ANALYSIS_MAX_ATTEMPTS = int(os.getenv("BIG_O_ANALYSIS_MAX_ATTEMPTS", "3"))
    # MySQL (platform DB)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "app_user")
    MYSQL_PASSWORD = _setting("MYSQL_PASSWORD", "app_password")
    MYSQL_DB = os.getenv("MYSQL_DB", "app_db")
    DEFAULT_DATABASE_URL = build_database_url(
        MYSQL_USER,
        MYSQL_PASSWORD,
        MYSQL_HOST,
        MYSQL_PORT,
        MYSQL_DB,
    )
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        DEFAULT_DATABASE_URL,
    )

    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "techniview_session")
    SESSION_DAYS = int(os.getenv("SESSION_DAYS", "7"))
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    CORS_ORIGINS = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    )


settings = Settings()
