# Инициализация модуля db
import psycopg2
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yaml

from traffic_arbitration.common.config import config as project_config


class TunnelPostgresConnection:
    """
    Контекстный менеджер для объединения psycopg2 connection + SSH-туннель.
    """

    def __init__(self, config=None):
        if not config:
            from ..common.config_loader import load_config
            config = load_config()
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
            if not ssh.get('allow_agent'):
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


class TunnelPostgresSession:
    """
    Контекстный менеджер для SQLAlchemy сессии с поддержкой SSH-туннеля.
    """

    def __init__(self, config=None):
        if not config:
            with open('config.yml', 'r') as file:
                config = yaml.safe_load(file)
        self._ssh_config = dict(config.get('ssh', {}))
        self._db_config = dict(config.get('database', {}))
        self._engine = None
        self._session = None
        self._server = None

    def __enter__(self):
        """
        Создаёт SSH-туннель (если нужно) и SQLAlchemy сессию.
        Возвращает сессию для использования.
        """
        ssh, db = self._ssh_config, self._db_config
        host, port = db.get('host'), db.get('port')

        if ssh.get('host'):
            self._server = SSHTunnelForwarder(
                (ssh.get('host'), ssh.get('port', 22)),
                remote_bind_address=(host, port),
                ssh_username=ssh.get('user'),
                ssh_password=ssh.get('password'),
                allow_agent=ssh.get('allow_agent', False),
            )
            if not ssh.get('allow_agent'):
                self._server.ssh_pkeys = []
            self._server.start()
            host, port = '127.0.0.1', self._server.local_bind_port

        # Формируем URL для SQLAlchemy
        sqlalchemy_url = (
            f"postgresql://{db.get('user')}:{db.get('password')}"
            f"@{host}:{port}/{db.get('dbname')}"
        )

        # Создаём движок и сессию
        self._engine = create_engine(sqlalchemy_url)
        Session = sessionmaker(bind=self._engine)
        self._session = Session()
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Закрывает сессию, движок и туннель (если был создан).
        """
        if self._session:
            self._session.close()
        if self._engine:
            self._engine.dispose()
        if self._server:
            self._server.stop()


def get_database_url() -> str:
    """Формирует SQLAlchemy URL из глобального объекта конфигурации."""
    db_config = project_config['database']
    return (
        f"postgresql://{db_config['user']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
    )
