import psycopg2
from traffic_arbitration.common.config import config
from traffic_arbitration.db import TunnelPostgresConnection, TunnelPostgresSession


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
    return TunnelPostgresConnection(conf or dict(config))


def get_session(conf=None):
    """
    Возвращает контекстный менеджер для SQLAlchemy сессии.

    Использовать так:
    with get_session() as session:
        sources = session.query(ContentSource).all()
        ...

    При выходе из блока with сессия и туннель закрываются.
    """
    return TunnelPostgresSession(conf or dict(config))
