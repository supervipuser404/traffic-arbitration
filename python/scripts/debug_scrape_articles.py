import logging
import time
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from traffic_arbitration.db.queries import get_active_content_sources
from traffic_arbitration.db.connection import get_session
from traffic_arbitration.scrapper.base_scraper import BaseScraperHandler
from traffic_arbitration.scrapper.scraper_factory import ScraperHandlerFactory
from traffic_arbitration.scrapper.driver_pool import DriverPool
from traffic_arbitration.models import ExternalArticleLink

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def get_latest_link(session: Session, source_id: int) -> Optional[str]:
    """
    Получает наиболее новый линк для источника (любой, включая обработанные).

    Args:
        session: SQLAlchemy сессия.
        source_id: ID источника.

    Returns:
        Ссылка (строка) или None, если нет ссылок.
    """
    result = session.execute(
        select(ExternalArticleLink.link)
        .filter_by(source_id=source_id)
        .order_by(ExternalArticleLink.created_at.desc())
        .limit(1)
    ).scalar()
    return result


def scrape_article(handler: BaseScraperHandler, url: str) -> Dict[str, Any]:
    """
    Скраппит статью по URL с помощью обработчика.

    Args:
        handler: Обработчик источника (например, Handler24NewsRF).
        url: URL статьи.

    Returns:
        Словарь с данными статьи (title, text) или ошибкой.
    """
    try:
        article_data = handler.scrape_article(url)
        return {
            "success": True,
            "title": article_data.get("title", ""),
            "text": article_data.get("text", ""),
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "title": None,
            "text": None,
            "error": str(e)
        }


def debug_scrape_articles():
    """
    Линейный отладочный скрипт для скраппинга одной статьи с каждого источника.
    """
    logger.info("Запуск отладки скраппинга статей")
    pool = DriverPool(1)

    with get_session() as session:
        # Получаем активные источники
        sources = get_active_content_sources(session)
        logger.info(f"Найдено {len(sources)} активных источников")

        for source in sources:
            source_id = source["id"]
            source_name = source["name"]
            source_handler = source["source_handler"]

            logger.info(f"Обрабатываем источник: {source_name} (ID: {source_id})")

            # Получаем наиболее новый линк
            link = get_latest_link(session, source_id)
            if not link:
                logger.info("  Нет ссылок для этого источника")
                continue

            logger.info(f"  Ссылка: {link}")

            # Создаём обработчик
            try:
                handler = ScraperHandlerFactory.create(source, pool)
            except ValueError as e:
                logger.error(f"  Ошибка: Не удалось создать обработчик для {source_handler}: {e}")
                continue

            # Скраппим статью
            start_time = time.time()
            result = scrape_article(handler, link)
            elapsed_time = time.time() - start_time

            # Выводим диагностику
            if result["success"]:
                title = result["title"] or "<без заголовка>"
                text = result["text"] or ""
                logger.info(f"  Успешно: Заголовок: {title}")
                logger.info(f"  Текст: {text}")
                logger.info(f"  Время выполнения: {elapsed_time:.2f} сек")
            else:
                logger.error(f"  Ошибка скраппинга: {result['error']}")
                logger.info(f"  Время выполнения: {elapsed_time:.2f} сек")


def main():
    try:
        debug_scrape_articles()
    except Exception as e:
        logger.error(f"Глобальная ошибка: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
