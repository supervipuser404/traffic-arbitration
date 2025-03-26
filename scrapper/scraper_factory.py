from typing import Dict, Any
from .base_scraper import BaseScraperHandler
from .iadvert_scraper import IAdvertScraper


class ScraperHandlerFactory:
    """
    Фабрика. По значению source_handler создаём нужного потомка BaseScraperHandler.
    """

    @staticmethod
    def create(source_info: Dict[str, Any], driver_pool) -> BaseScraperHandler:
        handler = source_info.get("source_handler")
        if handler == "iadvert":
            result = IAdvertScraper(source_info)
            result.configure(driver_pool)
            return result
        # elif handler == 'some_other':
        #     return SomeOtherScraper(source_info)
        else:
            raise ValueError(f"Неизвестный source_handler: {handler}")
