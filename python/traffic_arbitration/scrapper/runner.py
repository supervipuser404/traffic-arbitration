import logging
from typing import Dict

from .commons import CATEGORIES
from .driver_pool import DriverPool
from .scraper_factory import ScraperHandlerFactory
from traffic_arbitration.db.connection import get_connection
from traffic_arbitration.db.queries import (
    upsert_external_articles_links_batch,
    upsert_external_articles_previews_batch,
    upsert_visual_content_batch, get_unprocessed_article_links_for_source, upsert_external_articles_batch,
    mark_links_processed_batch
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

    with DriverPool() as driver_pool:
        # 1) Создаём скрапер
        scraper = ScraperHandlerFactory.create(source_info, driver_pool)

        # 2) Парсим
        all_previews = scraper.scrape_all_categories()
        logger.info(f"Источник={source_info['name']}: всего получено превью: {len(all_previews)}")

        # 3) Batch upsert
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

            links = get_unprocessed_article_links_for_source(conn, source_info["id"])

        # 4) Парсим статьи
        if links:
            parsed_articles = scraper.scrape_articles(links)

            with get_connection() as conn:
                try:
                    upsert_external_articles_batch(conn, source_info["id"], parsed_articles)
                    mark_links_processed_batch(conn, source_info["id"], [a["link"] for a in parsed_articles])

                    conn.commit()
                    logger.info(f"Источник={source_info['name']}: статьи успешно сохранены")
                except Exception as e:
                    logger.exception(f"Ошибка в process_source({source_info['name']}): {e}")
                    conn.rollback()
