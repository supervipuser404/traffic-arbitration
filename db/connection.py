import psycopg2
from config import config


def get_connection():
    """
    Возвращает psycopg2 connection, опираясь на настройки в config
    """
    conn = psycopg2.connect(
        host=config["db_host"],
        port=config["db_port"],
        dbname=config["db_name"],
        user=config["db_user"],
        password=config["db_password"]
    )
    conn.autocommit = False
    return conn
