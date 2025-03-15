# Инициализация модуля db
import psycopg2
from sshtunnel import SSHTunnelForwarder
from config import config


class TunnelPostgresConnection:
    """
    Контекстный менеджер для объединения psycopg2 connection + SSH-туннель.
    """

    def __init__(self, config):
        self._ssh_config = dict(config.get('ssh', {}))
        self._db_config = dict(config.get('database', {}))
        self._conn = None
        self._server = None

    def __enter__(self):
        """
        Создаём SSH-туннель, если надо, и connection.
        Возвращаем сам connection (psycopg2) для использования.
        """
        ssh, db = self._ssh_config, dict(self._db_config)
        if ssh.get('host'):
            self._server = SSHTunnelForwarder(
                (ssh.get('host'), ssh.get('port')),
                remote_bind_address=(db.get('host'), db.get('port')),
                ssh_username=ssh.get('user'),
                ssh_password=ssh.get('password'),
                allow_agent=ssh.get('allow_agent', False),
            )
            if not self._ssh_config.get('allow_agent'):
                # HACK!
                # noinspection SpellCheckingInspection
                self._server.ssh_pkeys = []

            self._server.start()
            db['host'], db['port'] = '127.0.0.1', self._server.local_bind_port

        self._conn = psycopg2.connect(**db)
        self._conn.autocommit = False

        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Закрываем соединение и туннель, если был создан.
        """
        if self._conn:
            self._conn.close()
        if self._server:
            self._server.stop()


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
