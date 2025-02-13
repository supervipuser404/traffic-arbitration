from typing import Dict, Any, List
import abc


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

    @abc.abstractmethod
    def scrape_category_previews(self, category_slug: str) -> List[Dict[str, Any]]:
        """
        Парсит одну категорию, возвращает список превью:
        [
          {
            "link": str,
            "image_link": str,
            "category_text": str,  # (может содержать несколько значений через ';')
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
