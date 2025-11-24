from traffic_arbitration.models import ArticlePreview
from .cache import NewsCache, CachedPreviewItem
from typing import Dict, List, Set, Optional, Iterator
from .schemas import TeaserRequestSchema
import logging
import random

logger = logging.getLogger(__name__)


class NewsRanker:
    """
    Отвечает за выборку кандидатов из кэша.
    """

    def __init__(self, cache: NewsCache):
        self.cache = cache

    def get_candidates(self, category: str | None = None) -> list[CachedPreviewItem]:
        """
        Возвращает список кандидатов, отфильтрованных по категории,
        но уже отсортированных по CTR (так как они так лежат в кэше).
        """
        all_items = self.cache.get_previews()

        if category:
            filtered = [item for item in all_items if item.category == category]
            # Fallback: если в категории пусто, возвращаем всё (чтобы не показывать пустые блоки)
            if not filtered:
                logger.warning(f"Категория {category} пуста, отдаем общий микс.")
                return all_items
            return filtered

        return all_items


class TeaserService:
    """
    Распределяет тизеры по виджетам (l, s, r, i) с учетом дедупликации.
    """

    def __init__(self, news_ranker: NewsRanker):
        self.news_ranker = news_ranker

    def get_teasers_for_widgets(self, request_data: TeaserRequestSchema) -> Dict:
        """
        Единый метод для заполнения всех виджетов на странице.
        """

        # 1. Формируем множества исключений (seen IDs)
        seen_page = set(request_data.seen_ids_page)
        seen_long_term = set(request_data.seen_ids_long_term)

        # Полный бан-лист для "свежих" показов
        exclude_ids = seen_page.union(seen_long_term)

        # 2. Получаем кандидатов (уже отсортированы по CTR)
        candidates = self.news_ranker.get_candidates(category=request_data.category)

        # 3. Разделяем на потоки
        # Fresh: те, что пользователь не видел (High CTR -> Low CTR)
        fresh_pool = [x for x in candidates if x.preview_obj.id not in exclude_ids]

        # Reusable: те, что видел в long_term (но не на этой странице!), сохраняем порядок CTR
        # Используем их как fallback, если fresh закончатся
        reusable_pool = [x for x in candidates if
                         x.preview_obj.id in seen_long_term and x.preview_obj.id not in seen_page]

        # Итераторы для последовательной выдачи
        fresh_iter = iter(fresh_pool)
        reusable_iter = iter(reusable_pool)

        # 4. Сортируем виджеты по приоритету заполнения
        # Важно: Сначала заполняем 's' и 'r' (сайдбары - там лучшие тизеры),
        # потом 'i' (внутри статьи), потом 'l' (лента).
        # Сортировка по ключу виджета
        def widget_priority(w_name: str):
            if w_name.startswith('s'): return 0  # Sidebar Preview (самое видное)
            if w_name.startswith('r'): return 1  # Right Sidebar Article
            if w_name.startswith('i'): return 2  # In-Article
            return 3  # Feed (Lent)

        sorted_widgets = sorted(request_data.widgets.items(), key=lambda x: widget_priority(x[0]))

        response_widgets: Dict[str, ArticlePreview] = {}
        newly_served_ids: List[int] = []

        # Локальный сет для дедупликации внутри одного реквеста (чтобы не дать один тизер в 's' и 'l')
        served_in_this_request: Set[int] = set()

        for widget_name, quantity in sorted_widgets:
            # Обычно quantity=1 для поименных виджетов (l00, s01),
            # но поддерживаем логику bulk
            for _ in range(quantity):
                chosen_item = self._pick_next_teaser(fresh_iter, reusable_iter, served_in_this_request)

                if not chosen_item:
                    # Тизеры кончились совсем
                    break

                preview = chosen_item.preview_obj
                # Прокидываем slug для формирования URL
                preview.slug = chosen_item.slug

                response_widgets[widget_name] = preview
                served_in_this_request.add(preview.id)

                # Если это был свежий тизер (не из reusable), добавляем в newly_served
                if preview.id not in seen_long_term:
                    newly_served_ids.append(preview.id)

        return {
            "widgets": response_widgets,
            "newly_served_ids": newly_served_ids
        }

    def _pick_next_teaser(
            self,
            fresh_iter: Iterator[CachedPreviewItem],
            reusable_iter: Iterator[CachedPreviewItem],
            ignore_ids: Set[int]
    ) -> Optional[CachedPreviewItem]:
        """
        Берет следующий доступный тизер из fresh, если нет — из reusable.
        Пропускает те, что в ignore_ids.
        """
        # 1. Пробуем Fresh
        try:
            while True:
                item = next(fresh_iter)
                if item.preview_obj.id not in ignore_ids:
                    return item
        except StopIteration:
            pass

        # 2. Fallback: Reusable
        try:
            while True:
                item = next(reusable_iter)
                if item.preview_obj.id not in ignore_ids:
                    return item
        except StopIteration:
            return None
