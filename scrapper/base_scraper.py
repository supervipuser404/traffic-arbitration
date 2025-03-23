import threading
from typing import Dict, Any, List
import abc
import concurrent.futures
import logging


class BaseScraperHandler(metaclass=abc.ABCMeta):
    """
    Базовый абстрактный класс для скраппера.
    Содержит обязательные методы:
      - scrape_category_previews
      - scrape_all_categories
    """

    def __init__(self, source_info: Dict[str, Any]):
        """
        :param source_info: Данные источника (из content_sources).
        """
        self.source_info = source_info
        self.source_id = source_info['id']
        self.driver_pool = None

    """ Базовый скраппер, поддерживающий переиспользование Selenium-драйверов. """

    def configure(self, driver_pool):
        """ Настраивает скраппер: передаёт пул драйверов и id источника. """
        self.driver_pool = driver_pool

    @abc.abstractmethod
    def scrape_category_previews(self, category_slug: str) -> List[Dict[str, Any]]:
        """
        Парсит одну категорию, возвращает список превью:
        [
          {
            "link": str,
            "image_link": str,
            "categories": str,
            "title": str
          },
          ...
        ]
        """
        pass

    def scrape_all_categories(self, categories: List[str]) -> List[Dict[str, Any]]:
        """
        Дефолтная (синхронная) реализация парсинга всех категорий по очереди.
        Если нужно параллельно, наследник может переопределить этот метод.
        """
        all_data = []
        for cat in categories:
            cat_data = self.scrape_category_previews(cat)
            all_data.extend(cat_data)
        return all_data

    def scrape_articles(self, links: list[str]) -> list[dict]:
        """
        Параллельно обрабатывает список ссылок на статьи.
        Возвращает список словарей с распарсенными данными.
        """
        if not links:
            logging.info("📭 Список ссылок на статьи пуст — нечего обрабатывать.")
            return []

        logging.info(f"📄 Начинаем обработку {len(links)} статей.")

        results = []
        lock = threading.Lock()

        def task(link: str):
            article = self.scrape_article(link)
            if article:
                with lock:
                    results.append(article)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.driver_pool.max_drivers) as executor:
            executor.map(task, links)

        logging.info(f"✅ Завершена обработка {len(results)} статей.")
        return results

    @abc.abstractmethod
    def scrape_article(self, link: str) -> dict | None:
        """
        Обрабатывает одну статью и возвращает словарь с результатами:
        {link, title, text, sources}
        """
        pass
