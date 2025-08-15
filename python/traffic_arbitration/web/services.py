# /home/andrey/Projects/Work/traffic_arbitration/python/traffic_arbitration/web/services.py

from traffic_arbitration.models import ArticlePreview
from .cache import NewsCache


class NewsRanker:
    """
    Сервисный слой для получения и ранжирования новостей.
    Работает с данными из кэша, а не напрямую с БД.
    """

    def __init__(self, cache: NewsCache):
        self.cache = cache

    def get_ranked_previews(
            self,
            limit: int = 20,
            offset: int = 0,
            # category: str | None = None # Параметр для будущего расширения
    ) -> list[ArticlePreview]:
        """
        Возвращает отфильтрованный и отсортированный список превью.
        """
        all_previews = self.cache.get_previews()

        # --- Этап 1: Фильтрация (пока не используется, но есть задел) ---
        # if category:
        #     filtered_previews = [p for p in all_previews if p.category == category]
        # else:
        #     filtered_previews = all_previews

        filtered_previews = all_previews  # Временно

        # --- Этап 2: Ранжирование (сортировка) ---
        # Сейчас - простая сортировка по дате.
        # В будущем здесь может быть вызов сложной ML-модели,
        # которая пересортирует `filtered_previews` на основе бизнес-логики.

        # Сортируем по дате публикации в обратном порядке (сначала новые)
        # Убедимся, что publication_date не None
        ranked_previews = sorted(
            filtered_previews,
            key=lambda p: p.publication_date,
            reverse=True
        )

        # --- Этап 3: Пагинация ---
        return ranked_previews[offset: offset + limit]
