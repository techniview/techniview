from contextlib import contextmanager

import psycopg2
import pymysql

from .config import settings


@contextmanager
def mysql_conn():
    # TODO: replace with SQLAlchemy session when models land
    conn = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB,
        connect_timeout=2,
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def postgres_conn():
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        connect_timeout=2,
    )
    try:
        yield conn
    finally:
        conn.close()
