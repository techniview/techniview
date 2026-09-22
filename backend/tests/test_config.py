from app.core.config import build_database_url
from sqlalchemy import make_url


def test_database_url_escapes_credentials():
    url = make_url(
        build_database_url(
            username="app@example.com",
            password="p@ss:/word",
            host="mysql",
            port=3306,
            database="app_db",
        )
    )
    assert url.username == "app@example.com"
    assert url.password == "p@ss:/word"
    assert url.host == "mysql"
