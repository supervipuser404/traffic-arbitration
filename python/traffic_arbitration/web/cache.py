# /home/andrey/Projects/Work/traffic-arbitration/python/traffic_arbitration/web/cache.py

import logging
import time
from threading import Lock
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select
# Убираем сломанный импорт:
# from traffic_arbitration.db.connection import get_db_session
# Нам нужны модели, чтобы создать правильный запрос
from traffic_arbitration.models import ArticlePreview, Article, ArticleCategory, Category

logger = logging.getLogger(__name__)


class NewsCache:
    """
    Потокобезопасный кэш для хранения списка превью новостей в памяти.
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Инициализирует кэш.
        """
        self.previews: list[ArticlePreview] = []
        self.ttl_seconds = ttl_seconds
        self.last_updated: float = 0.0
        self.lock = Lock()

        # Фабрика сессий, будет установлена из main.py
        self.session_maker: sessionmaker | None = None

        # Убираем попытку обновления из __init__,
        # так как session_maker еще не установлен.

    def set_session_maker(self, session_maker: sessionmaker):
        """
        Метод для 'внедрения' (injection) фабрики сессий из main.py.
        """
        self.session_maker = session_maker
        logger.info("Фабрика сессий БД установлена для NewsCache.")

    def force_update(self):
        """
        Принудительно обновляет кэш из БД.
        Вызывается из main.py при старте приложения.
        """
        if not self.session_maker:
            logger.error("Невозможно обновить кэш: фабрика сессий не установлена.")
            return

        logger.info("Принудительное обновление кэша при старте...")
        try:
            with self.session_maker() as db:
                self._update_cache_from_db(db)
        except Exception as e:
            logger.error(f"Ошибка при принудительном обновлении кэша: {e}", exc_info=True)

    def _is_cache_stale(self) -> bool:
        """Проверяет, "устарел" ли кэш."""
        return (time.monotonic() - self.last_updated) > self.ttl_seconds

    def _update_if_needed(self):
        """
        Обновляет кэш, если он устарел и фабрика сессий установлена.
        Этот метод *не* потокобезопасный, он должен быть вызван
        внутри контекста `with self.lock:`.
        """
        # Проверяем, что у нас есть чем создавать сессию
        if self.session_maker and self._is_cache_stale():
            # Используем сессию из 'внедренной' фабрики
            try:
                with self.session_maker() as db:
                    self._update_cache_from_db(db)
            except Exception as e:
                logger.error(f"Ошибка при фоновом обновлении кэша: {e}", exc_info=True)
                # Сбрасываем last_updated, чтобы повторить попытку
                self.last_updated = 0.0
        elif not self.session_maker:
            logger.warning("NewsCache: _update_if_needed пропущен, session_maker не установлен.")
        else:
            logger.debug("Кэш актуален, обновление не требуется.")

    def _update_cache_from_db(self, db: Session):
        """
        Загружает *активные* превью из базы данных, обогащая их
        датой публикации и категорией из связанной статьи.
        (Этот код из предыдущего шага уже правильный)
        """
        try:
            logger.info("Кэш устарел. Обновление из базы данных...")

            query = (
                select(
                    ArticlePreview.id,
                    ArticlePreview.article_id,
                    ArticlePreview.title,
                    ArticlePreview.text,
                    ArticlePreview.image,
                    ArticlePreview.is_active,
                    ArticlePreview.created_at,
                    Article.source_datetime.label("publication_date"),
                    Category.code.label("category")
                )
                .join(Article, ArticlePreview.article_id == Article.id)
                .join(ArticleCategory, Article.id == ArticleCategory.article_id)
                .join(Category, ArticleCategory.category_id == Category.id)
                .filter(ArticlePreview.is_active == True, Article.is_active == True)
            )

            result = db.execute(query).mappings().all()

            new_previews = []
            for preview_data_row in result:
                preview_data = dict(preview_data_row)

                publication_date = preview_data.pop("publication_date", None)
                category = preview_data.pop("category", None)

                preview_obj = ArticlePreview(**preview_data)

                preview_obj.publication_date = publication_date
                preview_obj.category = category

                new_previews.append(preview_obj)

            with self.lock:
                self.previews = new_previews

            self.last_updated = time.monotonic()
            logger.info(f"Кэш успешно обновлен. Загружено {len(self.previews)} превью.")

        except Exception as e:
            logger.error(f"Ошибка при обновлении кэша: {e}", exc_info=True)
            # Не сбрасываем last_updated, чтобы не пытаться обновиться
            # снова немедленно.

    def get_previews(self) -> list[ArticlePreview]:
        """
        Возвращает список кэшированных превью.
        Автоматически обновляет кэш, если он устарел.
        Этот метод потокобезопасен.
        """
        with self.lock:
            try:
                self._update_if_needed()
            except Exception as e:
                logger.error(f"Не удалось обновить кэш. Возврат старых данных. Ошибка: {e}", exc_info=True)

            return list(self.previews)


# --- Глобальный экземпляр ---
news_cache = NewsCache(ttl_seconds=60)