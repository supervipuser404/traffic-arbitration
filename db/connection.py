import psycopg2
from config import config


def get_connection():
    """
    Возвращает psycopg2 connection, опираясь на настройки в config
    """
    conn = psycopg2.connect(**config["database"])
    conn.autocommit = False
    return conn
