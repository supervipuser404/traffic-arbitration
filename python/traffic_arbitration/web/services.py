from traffic_arbitration.models import ArticlePreview
from .cache import NewsCache
from typing import Dict, List


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


class TeaserService:
    """
    Сервисный слой для получения тизеров (рекламы, новостей и т.п.)
    для виджетов.

    На данном этапе является заглушкой и использует NewsRanker
    для получения контента.
    """

    def __init__(self, news_ranker: NewsRanker):
        # Временно используем NewsRanker как источник данных
        self.news_ranker = news_ranker

    def get_teasers_for_widgets(
            self,
            widgets: Dict[str, int]
            # Примечание: в будущем метод будет принимать всю схему
            # TeaserRequestSchema, чтобы использовать uid, ip, ua и т.д.
    ) -> Dict[str, List[ArticlePreview]]:
        """
        Формирует ответ для эндпоинта /etc.

        Args:
            widgets: Словарь {widget_name: quantity}

        Returns:
            Словарь {widget_name: [список ArticlePreview]}
        """
        # В будущем здесь будет сложная логика:
        # 1. Анализ `request_data` (uid, ip, loc...)
        # 2. Обращение к RTB-системам
        # 3. Обращение к ML-моделям ранжирования
        # 4. Формирование ответа из *разных* источников (новости, реклама)

        # --- Временная реализация (заглушка) ---
        # Просто запрашиваем N самых свежих новостей для каждого виджета.
        response_widgets: Dict[str, List[ArticlePreview]] = {}
        for widget_name, quantity in widgets.items():
            previews = self.news_ranker.get_ranked_previews(
                limit=quantity,
                offset=0
            )
            response_widgets[widget_name] = previews
        # --- Конец временной реализации ---

        return response_widgets
