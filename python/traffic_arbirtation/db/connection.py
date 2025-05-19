import psycopg2
from config import config
from db import TunnelPostgresConnection


def get_connection(conf=None):
    """
    Возвращает контекстный менеджер.
    Использовать так:

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            ...

    При выходе из блока with — conn и туннель закроются.
    """
    return TunnelPostgresConnection(conf or config)
