import os

from sqlalchemy import URL


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
    EMAIL_DELIVERY_MODE = os.getenv("EMAIL_DELIVERY_MODE", "disabled")
    EMAIL_CAPTURE_DIR = os.getenv("EMAIL_CAPTURE_DIR", "/tmp/techniview-mail")
    EMAIL_SIGNING_KEY = os.getenv("EMAIL_SIGNING_KEY", "")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:5173")
    PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
    EMAIL_VERIFICATION_MINUTES = int(os.getenv("EMAIL_VERIFICATION_MINUTES", "1440"))
    EMAIL_TOKEN_COOLDOWN_SECONDS = int(os.getenv("EMAIL_TOKEN_COOLDOWN_SECONDS", "60"))
    EMAIL_MAX_ATTEMPTS = int(os.getenv("EMAIL_MAX_ATTEMPTS", "5"))
    EMAIL_LEASE_SECONDS = int(os.getenv("EMAIL_LEASE_SECONDS", "60"))
    WORKER_LEASE_SECONDS = int(os.getenv("WORKER_LEASE_SECONDS", "60"))
    WORKER_POLL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "2"))
    WORKER_RECOVERY_SECONDS = int(os.getenv("WORKER_RECOVERY_SECONDS", "600"))
    # MySQL (platform DB)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "app_user")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "app_password")
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

    # Judge0 Postgres/Redis
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "test_password")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")

    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "test_password")

    JUDGE0_URL = os.getenv("JUDGE0_URL", "http://server:2358")
    JUDGE0_CALLBACK_BASE_URL = os.getenv(
        "JUDGE0_CALLBACK_BASE_URL",
        "http://backend:8000/api/internal/judge0/callbacks",
    ).rstrip("/")


settings = Settings()
