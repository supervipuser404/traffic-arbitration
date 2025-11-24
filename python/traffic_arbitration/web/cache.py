import time
import logging
import threading
import random
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from traffic_arbitration.models import (
    ArticlePreview, Article, ArticleCategory, Category
)
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CachedPreviewItem:
    """
    Структура данных для хранения превью в памяти.
    Добавлен CTR для имитации ранжирования.
    """
    preview_obj: ArticlePreview
    publication_date: Optional[datetime]
    category: Optional[str]
    slug: Optional[str]
    ctr: float = 0.0  # Estimated Click-Through Rate (0.0 - 1.0)


class NewsCache:
    """
    Потокобезопасный кэш новостей с поддержкой метрик ранжирования.
    """

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        # Основной список, отсортированный по CTR (для RTB)
        self.previews: List[CachedPreviewItem] = []

        self.last_updated: float = 0
        self.update_lock = threading.Lock()
        self.session_maker: sessionmaker | None = None

        logger.info(f"NewsCache инициализирован с TTL = {self.ttl} сек.")

    def set_session_maker(self, session_maker: sessionmaker):
        self.session_maker = session_maker

    def get_previews(self) -> List[CachedPreviewItem]:
        """
        Основной метод для получения превью из кэша.
        Запускает обновление в фоне, если кэш устарел.
        """
        self._update_if_needed()
        return self.previews

    def _update_cache_from_db(self):
        """
        (Блокирующая) Внутренняя функция для обновления кэша из БД.
        Всегда должна вызываться внутри `update_lock`.
        """
        if not self.session_maker:
            logger.error("Кэш не может обновиться: session_maker не установлен.")
            return

        logger.info("Обновление кэша из БД...")

        with self.session_maker() as db_session:
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
                    Category.code.label("category"),
                    Article.slug.label("slug")
                )
                .join(Article, ArticlePreview.article_id == Article.id)
                .join(ArticleCategory, Article.id == ArticleCategory.article_id)
                .join(Category, ArticleCategory.category_id == Category.id)
                .where(ArticlePreview.is_active == True)
                # Сначала свежие, но сортировка будет переделана в Python
                .order_by(Article.source_datetime.desc())
            )

            all_previews_data = db_session.execute(stmt).mappings().all()
            new_previews = []
            model_keys = ArticlePreview.__table__.columns.keys()

            for preview_data_row in all_previews_data:
                preview_data = dict(preview_data_row)

                extra_data = {
                    "publication_date": preview_data.get("publication_date"),
                    "category": preview_data.get("category"),
                    "slug": preview_data.get("slug")
                }

                model_data = {k: preview_data[k] for k in model_keys if k in preview_data}

                try:
                    preview_obj = ArticlePreview(**model_data)

                    # Имитация ML: присваиваем случайный CTR.
                    # В реальной системе здесь был бы запрос к Redis/Feature Store.
                    # Даем буст свежим новостям
                    days_old = (datetime.now() - (extra_data["publication_date"] or datetime.now())).days
                    freshness_factor = max(0, 1.0 - (days_old * 0.1))  # Угасает за 10 дней

                    base_ctr = random.uniform(0.01, 0.15)
                    final_ctr = base_ctr * (1 + freshness_factor)

                    new_previews.append(CachedPreviewItem(
                        preview_obj=preview_obj,
                        publication_date=extra_data["publication_date"],
                        category=extra_data["category"],
                        slug=extra_data["slug"],
                        ctr=final_ctr
                    ))

                except Exception as e:
                    logger.error(f"Ошибка создания объекта кэша: {e}")

            # Сортировка по CTR (High -> Low) для RTB логики
            new_previews.sort(key=lambda x: x.ctr, reverse=True)

            self.previews = new_previews
            self.last_updated = time.time()
            logger.info(
                f"Кэш обновлен. Загружено {len(self.previews)} превью. Top CTR: {self.previews[0].ctr if self.previews else 0:.4f}")

    def force_update(self):
        with self.update_lock:
            self._update_cache_from_db()

    def _run_update_in_background(self):
        if self.update_lock.acquire(blocking=False):
            try:
                self._update_cache_from_db()
            except Exception as e:
                logger.error(f"Фоновое обновление кэша упало: {e}", exc_info=True)
            finally:
                self.update_lock.release()

    def _update_if_needed(self):
        if time.time() - self.last_updated > self.ttl and not self.update_lock.locked():
            threading.Thread(target=self._run_update_in_background, daemon=True).start()


news_cache = NewsCache(ttl_seconds=300)
