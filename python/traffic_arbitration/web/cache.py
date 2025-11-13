import time
import logging
import threading
from typing import List
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker, Session
from traffic_arbitration.models import (
    ArticlePreview, Article, ArticleCategory, Category
)

# Настройка логгера
logger = logging.getLogger(__name__)


class NewsCache:
    """
    Потокобезопасный кэш для хранения превью новостей.
    """

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds

        # --- ИЗМЕНЕНИЕ: Тип данных в кэше ---
        # Мы снова можем безопасно хранить List[ArticlePreview],
        # потому что теперь мы будем "отсоединять" их от сессии.
        self.previews: List[ArticlePreview] = []
        # --- Конец изменения ---

        self.last_updated: float = 0
        self.update_lock = threading.Lock()
        self.session_maker: sessionmaker | None = None

        logger.info(f"NewsCache инициализирован с TTL = {self.ttl} сек.")

    def set_session_maker(self, session_maker: sessionmaker):
        """
        Внедрение (DI) фабрики сессий из `main.py`
        """
        self.session_maker = session_maker
        logger.info("Фабрика сессий успешно внедрена в кэш.")

    def get_previews(self) -> List[ArticlePreview]:
        """
        Основной метод для получения превью из кэша.
        Запускает обновление в фоне, если кэш устарел.
        """
        self._update_if_needed()
        # *Немедленно* возвращаем то, что есть в кэше
        return self.previews

    def _update_cache_from_db(self):
        """
        (Блокирующая) Внутренняя функция для обновления кэша из БД.
        Всегда должна вызываться внутри `update_lock`.
        """
        if not self.session_maker:
            logger.error("Кэш не может обновиться: session_maker не установлен.")
            return

        logger.info("Кэш устарел. Обновление из базы данных...")

        with self.session_maker() as db_session:
            # Запрос для получения всех активных превью и
            # связанных данных (дата публикации статьи, категория)
            stmt = (
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
                .where(ArticlePreview.is_active == True)
                .order_by(Article.source_datetime.desc())
            )

            # Выполняем запрос
            all_previews_data = db_session.execute(stmt).mappings().all()

            new_previews = []
            model_keys = ArticlePreview.__table__.columns.keys()

            for preview_data_row in all_previews_data:
                preview_data = dict(preview_data_row)

                # 1. Отделяем "дополнительные" данные
                extra_data = {
                    "publication_date": preview_data.get("publication_date"),
                    "category": preview_data.get("category")
                }

                # 2. Формируем словарь только с теми данными,
                #    которые есть в модели ArticlePreview
                model_data = {
                    key: preview_data[key]
                    for key in model_keys
                    if key in preview_data
                }

                # 3. Создаем объект модели
                try:
                    preview_obj = ArticlePreview(**model_data)

                    # 4. "Прикрепляем" дополнительные данные к самому объекту
                    preview_obj.publication_date = extra_data["publication_date"]
                    preview_obj.category = extra_data["category"]

                    new_previews.append(preview_obj)

                except TypeError as e:
                    logger.error(f"Ошибка при создании ArticlePreview: {e}. Данные: {model_data}")

            # --- ИЗМЕНЕНИЕ: "Отсоединяем" объекты от сессии ---
            # Это ключевой шаг. Объекты становятся "Detached"
            # и могут безопасно храниться в кэше.
            for obj in new_previews:
                db_session.expunge(obj)
            # --- Конец изменения ---

            # Атомарно заменяем старые данные новыми
            self.previews = new_previews
            self.last_updated = time.time()
            logger.info(f"Кэш успешно обновлен. Загружено {len(self.previews)} превью.")

        # Сессия (db_session) здесь закрывается, но объекты в
        # self.previews теперь "отсоединены" и безопасны.

    def force_update(self):
        """
        Принудительное (синхронное) обновление кэша.
        Используется при старте приложения.
        """
        # Блокируем, чтобы избежать "гонки" с фоновыми обновлениями
        with self.update_lock:
            self._update_cache_from_db()

    def _run_update_in_background(self):
        """
        Обертка для запуска `_update_cache_from_db` в потоке.
        Обеспечивает, что только один поток обновления работает.
        """
        if self.update_lock.acquire(blocking=False):
            logger.info("Запуск фонового обновления кэша...")
            try:
                self._update_cache_from_db()
            except Exception as e:
                logger.error(f"Фоновое обновление кэша провалено: {e}", exc_info=True)
            finally:
                self.update_lock.release()
                logger.info("Фоновое обновление кэша завершено.")
        else:
            logger.info("Обновление кэша уже в процессе, пропускаем.")

    def _update_if_needed(self):
        """
        (Неблокирующий) Проверяет TTL и, если нужно,
        запускает обновление в фоновом потоке.
        """
        if time.time() - self.last_updated <= self.ttl:
            return

        if self.update_lock.locked():
            return

        threading.Thread(
            target=self._run_update_in_background,
            daemon=True
        ).start()


# --- Глобальный экземпляр кэша ---
# `main.py` будет импортировать этот экземпляр
news_cache = NewsCache(ttl_seconds=300)
