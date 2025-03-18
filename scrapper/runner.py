import logging
from typing import Dict

from .commons import CATEGORIES
from .scraper_factory import ScraperHandlerFactory
from db.connection import get_connection
from db.queries import (
    upsert_external_articles_links_batch,
    upsert_external_articles_previews_batch,
    upsert_visual_content_batch
)

logger = logging.getLogger(__name__)


def process_source(source_info: Dict):
    """
    Обрабатывает ОДИН источник:
    1) Создаём скрапер через фабрику
    2) Вызываем scrape_all_categories (базовый или переопределённый)
    3) Делаем batch upsert:
       - external_articles_links
       - external_articles_previews
       - visual_content (placeholder)
    """
    logger.info(f"=== Начинаем обработку источника: {source_info['name']} (ID={source_info['id']}) ===")

    # 1) Создаём скрапер
    scraper = ScraperHandlerFactory.create(source_info)

    # 2) Получаем список slugs (у нас в примере - ключи CATEGORIES).
    # Можно подхватить иные категории из source_info['categories'].
    cat_slugs = source_info['categories'] or list(CATEGORIES.keys())

    # 3) Парсим
    all_previews = scraper.scrape_all_categories(cat_slugs)
    logger.info(f"Источник={source_info['name']}: всего получено превью: {len(all_previews)}")

    # 4) Batch upsert
    with get_connection() as conn:
        try:
            link_map = upsert_external_articles_links_batch(conn, source_info["id"], all_previews)
            upsert_external_articles_previews_batch(conn, link_map, all_previews)
            upsert_visual_content_batch(conn, all_previews)

            conn.commit()
            logger.info(f"Источник={source_info['name']}: данные успешно сохранены")
        except Exception as e:
            logger.exception(f"Ошибка в process_source({source_info['name']}): {e}")
            conn.rollback()
