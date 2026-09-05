import os


class Settings:
    # MySQL (platform DB)
    MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "app_user")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "app_password")
    MYSQL_DB = os.getenv("MYSQL_DB", "app_db")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}",
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


settings = Settings()
