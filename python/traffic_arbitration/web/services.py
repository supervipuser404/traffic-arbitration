from traffic_arbitration.models import ArticlePreview
from .cache import NewsCache, CachedPreviewItem
from typing import Dict, List, Set, Optional
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
            limit: int | None = 20,
            offset: int = 0,
            category: str | None = None
    ) -> list[CachedPreviewItem]:
        """
        Возвращает отфильтрованный и отсортированный список превью.
        """
        all_preview_items = self.cache.get_previews()

        # --- Этап 1: Фильтрация ---
        if category:
            # Пытаемся отфильтровать по категории
            filtered_items = [
                item for item in all_preview_items
                if item.category == category
            ]

            # --- Логика ФОЛБЭКА ---
            if not filtered_items:
                logger.warning(
                    f"Категория '{category}' не найдена или для нее нет тизеров. "
                    f"Выполняется фолбэк: показываем все тизеры."
                )
                filtered_items = all_preview_items
        else:
            # Категория не задана (главная страница)
            filtered_items = all_preview_items

        # --- Этап 2: Ранжирование (сортировка) ---
        # (уже отсортировано в кэше)
        ranked_items = filtered_items

        # --- Этап 3: Пагинация ---
        if limit is None:
            return ranked_items[offset:]
        return ranked_items[offset: offset + limit]


class TeaserService:
    """
    Сервисный слой для получения тизеров (рекламы, новостей и т.п.)
    для виджетов.
    """

    def __init__(self, news_ranker: NewsRanker):
        self.news_ranker = news_ranker

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

        excluded_ids = seen_on_page_set.union(seen_long_term_set)

        # --- Шаг 2: Получаем всех кандидатов (УЖЕ С ФИЛЬТРОМ) ---

        all_teaser_items = self.news_ranker.get_ranked_previews(
            limit=None,
            category=request_data.category
        )

        # --- Шаг 3: Формируем пулы ---

        # Пул 1: "Свежие", которых пользователь еще не видел
        available_teasers: List[CachedPreviewItem] = []

        # Пул 2: "Повторные", которые можно показать, если свежие кончились
        # (Важно: они должны быть в том же порядке, что и в `all_teasers`)
        reusable_teasers: List[CachedPreviewItem] = []

        for item in all_teaser_items:
            # Сравниваем по ID из объекта
            if item.preview_obj.id not in excluded_ids:
                available_teasers.append(item)

            # Мы можем повторно использовать только "долгосрочно" просмотренные.
            # Те, что *уже на этой странице* (seen_on_page_set),
            # нельзя использовать ни в коем случае (для дедупликации в моменте).
            elif item.preview_obj.id in seen_long_term_set and item.preview_obj.id not in seen_on_page_set:
                reusable_teasers.append(item)

        # Превращаем в итераторы, чтобы удобно "вынимать" по одному
        available_iter = iter(available_teasers)
        reusable_iter = iter(reusable_teasers)

        logger.info(
            f"UID: {request_data.uid}, Категория: {request_data.category}. "
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
                teaser_item: Optional[CachedPreviewItem] = None
                try:
                    # Сначала пытаемся взять "свежий"
                    teaser_item = next(available_iter)
                    while teaser_item.preview_obj.id in served_on_this_request:
                        teaser_item = next(available_iter)

                except StopIteration:
                    try:
                        # "Свежие" кончились. Берем "повторный"
                        teaser_item = next(reusable_iter)
                        while teaser_item.preview_obj.id in served_on_this_request:
                            teaser_item = next(reusable_iter)

                    except StopIteration:
                        # Тизеры кончились ВООБЩЕ.
                        logger.warning(f"Тизеры закончились! (UID: {request_data.uid})")
                        break  # Прерываем цикл `for _ in range(quantity)`

                if teaser_item:
                    # Pydantic (в `ArticlePreviewSchema`) увидит этот атрибут
                    preview_obj = teaser_item.preview_obj
                    preview_obj.slug = teaser_item.slug

                    response_widgets[widget_name] = preview_obj
                    served_on_this_request.add(preview_obj.id)

                    # Если тизер не был в "повторных",
                    # значит, он "новый" для пользователя.
                    if preview_obj.id not in seen_long_term_set:
                        response_newly_served_ids.append(preview_obj.id)

        return {
            "widgets": response_widgets,
            "newly_served_ids": list(set(response_newly_served_ids))  # Убираем дубли на всякий случай
        }
