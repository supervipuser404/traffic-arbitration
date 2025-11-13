from traffic_arbitration.models import ArticlePreview
from .cache import NewsCache
from typing import Dict, List, Set
from .schemas import TeaserRequestSchema
import logging

logger = logging.getLogger(__name__)


class NewsRanker:
    """
    Сервисный слой для получения и ранжирования новостей.
    Работает с данными из кэша, а не напрямую с БД.
    """

    def __init__(self, cache: NewsCache):
        self.cache = cache

    def get_ranked_previews(
            self,
            limit: int | None = 20,  # --- ИЗМЕНЕНИЕ: limit=None, чтобы получить ВСЕ ---
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
        # Мы предполагаем, что `all_previews` из кэша *уже* отсортированы
        # по `publication_date` (как мы это делали в cache.py)
        ranked_previews = filtered_previews

        # --- Этап 3: Пагинация ---
        if limit is None:
            return ranked_previews[offset:]
        return ranked_previews[offset: offset + limit]


class TeaserService:
    """
    Сервисный слой для получения тизеров (рекламы, новостей и т.п.)
    для виджетов.
    """

    def __init__(self, news_ranker: NewsRanker):
        self.news_ranker = news_ranker
        # Можно добавить кэш для (uid, url) -> seen_ids,
        # но пока, по вашей просьбе, делаем stateless.

    def get_teasers_for_widgets(
            self,
            request_data: TeaserRequestSchema
    ) -> Dict:  # Возвращает словарь, который Pydantic превратит в TeaserResponseSchema
        """
        Формирует ответ для эндпоинта /etc с учетом дедупликации.

        Args:
            request_data: Pydantic-схема TeaserRequestSchema

        Returns:
            Словарь { "widgets": {...}, "newly_served_ids": [...] }
        """

        # --- Шаг 1: Определяем, кого исключить ---

        # ID, которые *уже есть* на этой странице (из JS Set)
        seen_on_page_set = set(request_data.seen_ids_page)
        # ID, которые *давно видели* (из Cookie)
        seen_long_term_set = set(request_data.seen_ids_long_term)

        # Общий список "забаненных" ID
        excluded_ids = seen_on_page_set.union(seen_long_term_set)

        # --- Шаг 2: Получаем всех кандидатов ---
        # `get_ranked_previews(limit=None)` вернет *все* тизеры из кэша,
        # уже отсортированные по свежести (по `publication_date`).
        all_teasers = self.news_ranker.get_ranked_previews(limit=None)

        # --- Шаг 3: Формируем пулы ---

        # Пул 1: "Свежие", которых пользователь еще не видел
        available_teasers = []

        # Пул 2: "Повторные", которые можно показать, если свежие кончились
        # (Важно: они должны быть в том же порядке, что и в `all_teasers`)
        reusable_teasers = []

        for teaser in all_teasers:
            if teaser.id not in excluded_ids:
                available_teasers.append(teaser)

            # Мы можем повторно использовать только "долгосрочно" просмотренные.
            # Те, что *уже на этой странице* (seen_on_page_set),
            # нельзя использовать ни в коем случае (для дедупликации в моменте).
            elif teaser.id in seen_long_term_set and teaser.id not in seen_on_page_set:
                reusable_teasers.append(teaser)

        # Превращаем в итераторы, чтобы удобно "вынимать" по одному
        available_iter = iter(available_teasers)
        reusable_iter = iter(reusable_teasers)

        logger.info(
            f"UID: {request_data.uid}. "
            f"Доступно: {len(available_teasers)}, "
            f"Повторно: {len(reusable_teasers)}, "
            f"Исключено: {len(excluded_ids)}"
        )

        # --- Шаг 4: Сборка ответа ---
        response_widgets: Dict[str, ArticlePreview] = {}
        response_newly_served_ids: List[int] = []

        # Мы используем `served_on_this_request` для дедупликации *внутри*
        # одного запроса (если вдруг `available_iter` вернет один и тот же
        # ID дважды, хотя он не должен)
        served_on_this_request: Set[int] = set()

        # `request_data.widgets` - это {"l00": 1, "l10": 1, ...}
        for widget_name, quantity in request_data.widgets.items():

            # (На будущее) Если `quantity > 1`, этот цикл сработает
            for _ in range(quantity):
                teaser = None
                try:
                    # Сначала пытаемся взять "свежий"
                    teaser = next(available_iter)
                    while teaser.id in served_on_this_request:
                        teaser = next(available_iter)

                except StopIteration:
                    try:
                        # "Свежие" кончились. Берем "повторный"
                        teaser = next(reusable_iter)
                        while teaser.id in served_on_this_request:
                            teaser = next(reusable_iter)

                    except StopIteration:
                        # Тизеры кончились ВООБЩЕ.
                        logger.warning(f"Тизеры закончились! (UID: {request_data.uid})")
                        break  # Прерываем цикл `for _ in range(quantity)`

                if teaser:
                    # (Мы поддерживаем только quantity=1, поэтому просто перезаписываем)
                    response_widgets[widget_name] = teaser
                    served_on_this_request.add(teaser.id)

                    # Если тизер не был в "повторных",
                    # значит, он "новый" для пользователя.
                    if teaser.id not in seen_long_term_set:
                        response_newly_served_ids.append(teaser.id)

        return {
            "widgets": response_widgets,
            "newly_served_ids": list(set(response_newly_served_ids))  # Убираем дубли на всякий случай
        }
