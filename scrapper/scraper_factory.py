from typing import Dict, Any
from .base_scraper import BaseScraperHandler
from .iadvert_scraper import IAdvertScraper


class ScraperHandlerFactory:
    """
    Фабрика. По значению source_handler создаём нужного потомка BaseScraperHandler.
    """

    @staticmethod
    def create(source_info: Dict[str, Any]) -> BaseScraperHandler:
        handler = source_info.get("source_handler")
        if handler == "iadvert":
            return IAdvertScraper(source_info)
        # elif handler == 'some_other':
        #     return SomeOtherScraper(source_info)
        else:
            raise ValueError(f"Неизвестный source_handler: {handler}")
