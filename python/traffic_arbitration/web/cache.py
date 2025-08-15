# /home/andrey/Projects/Work/traffic_arbitration/python/traffic_arbitration/web/cache.py

import logging
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Импортируем наши модели и функцию для создания URL
from traffic_arbitration.models import Article, ArticlePreview
from traffic_arbitration.db import get_database_url
from scripts.generate_previews import create_excerpt, STATIC_IMAGE_PATH_PREFIX

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class NewsCache:
    """
    Класс для кэширования превью новостей в памяти с TTL (Time-To-Live).
    Это позволяет избежать постоянных запросов к БД на каждый вызов API.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._cache: list[ArticlePreview] = []
        self._last_updated: datetime | None = None
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = Lock()  # Блокировка для потокобезопасного обновления

    def _is_cache_stale(self) -> bool:
        """Проверяет, не устарел ли кэш."""
        if not self._cache or not self._last_updated:
            return True
        return datetime.now() - self._last_updated > self._ttl

    def _update_cache_from_db(self):
        """
        Основная функция обновления кэша. Запрашивает все активные
        статьи из БД и генерирует для них превью.
        """
        logging.info("Кэш устарел. Обновление из базы данных...")
        database_url = get_database_url()
        engine = create_engine(database_url)
        session_factory = sessionmaker(bind=engine)
        Session = scoped_session(session_factory)
        db = Session()

        try:
            # Запрашиваем только активные статьи
            active_articles = db.query(Article).filter(Article.is_active == True).all()

            new_previews = []
            for article in active_articles:
                # Используем логику из наших скриптов для консистентности
                excerpt_text = create_excerpt(article.text, 300)
                image_path = None
                if article.image:
                    if article.image.name:
                        filename = article.image.name
                        subdir = filename[:2]
                        image_path = f"{STATIC_IMAGE_PATH_PREFIX}{subdir}/{filename}"
                    elif article.image.link:
                        image_path = article.image.link

                # Создаем Pydantic-совместимый объект (или используем существующий ArticlePreview)
                # Для простоты здесь создадим словарь, который соответствует модели
                preview_data = {
                    "id": article.id,
                    "title": article.title,
                    "excerpt": excerpt_text,
                    "author": "Редакция",  # Заглушка, можно добавить в модель Article
                    "publication_date": article.source_datetime or article.created_at,
                    "url": f"/news/{article.id}/some-slug",  # Заглушка для slug
                    "image": image_path
                }
                new_previews.append(ArticlePreview(**preview_data))

            self._cache = new_previews
            self._last_updated = datetime.now()
            logging.info(f"Кэш успешно обновлен. Загружено {len(self._cache)} превью.")

        except Exception as e:
            logging.error(f"Ошибка при обновлении кэша: {e}", exc_info=True)
        finally:
            db.close()

    def get_previews(self) -> list[ArticlePreview]:
        """
        Возвращает список превью. Если кэш устарел, обновляет его.
        Использует блокировку, чтобы избежать гонки состояний при обновлении.
        """
        if self._is_cache_stale():
            with self._lock:
                # Повторная проверка внутри блокировки на случай,
                # если другой поток уже обновил кэш, пока мы ждали.
                if self._is_cache_stale():
                    self._update_cache_from_db()

        return self._cache


# Создаем единственный экземпляр кэша для всего приложения
news_cache = NewsCache(ttl_seconds=60)  # Кэш живет 1 минуту для демонстрации
