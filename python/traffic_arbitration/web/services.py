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
    priority_map = {'s': 0, 'r': 1, 'i': 2, 'l': 3}

    def __init__(self, news_ranker: NewsRanker):
        self.news_ranker = news_ranker

    @classmethod
    def widget_priority(cls, w_name: str, priority_map: Dict[str, int] = None) -> int:
        priority_map = priority_map or cls.priority_map
        return priority_map.get(w_name[0], 99)

    @staticmethod
    def candidate_generator(candidates: List[CachedPreviewItem],
                            qualities: List[int] = None) -> Iterator[CachedPreviewItem]:
        if qualities is None:
            qualities = [2] * len(candidates)
        current_quality = 2  # Start with Fresh
        while True:
            for i in range(len(candidates)):
                if qualities[i] == current_quality:
                    yield candidates[i]
                    qualities[i] -= 1  # Ухудшаем качество, чтобы не выдавать один и тот же тизер снова
            current_quality -= 1

    def get_teasers_for_widgets(self, request_data: TeaserRequestSchema) -> Dict:
        """
        Единый метод для заполнения всех виджетов на странице.
        """
        # 1. Получаем кандидатов (уже отсортированы по CTR)
        candidates = self.news_ranker.get_candidates(category=request_data.category)

        # 2. Сколько всего нужно тизеров
        total_needed = sum(request_data.widgets.values())

        # 3. Формируем множества исключений (seen IDs)
        seen_page = set(request_data.seen_ids_page)
        seen_long_term = set(request_data.seen_ids_long_term)
        exclude_ids = seen_page.union(seen_long_term)

        # 4. Ограничиваем список кандидатов, чтобы избежать перебора слишком большого числа
        if len(candidates) > total_needed + len(exclude_ids):
            candidates = candidates[:total_needed + len(exclude_ids)]

        # 5. Рассчитываем качество кандидатов
        candidates_quality = []
        for item in candidates:
            if item.preview_obj.id not in exclude_ids:
                quality = 2  # Fresh
            elif item.preview_obj.id in seen_long_term:
                quality = 1
            else:
                quality = 0  # Seen on page
            candidates_quality.append(quality)

        # 6. Сортируем виджеты по приоритету заполнения
        sorted_widgets = sorted(request_data.widgets.items(), key=lambda x: self.widget_priority(x))

        response_widgets: Dict[str, ArticlePreview] = {}

        # 7. Выбираем тизеры для виджетов
        selected_candidates_ids: Set[int] = set()
        candidate_generator = self.candidate_generator(candidates, candidates_quality)
        for widget_name, quantity in sorted_widgets:
            # Сейчас quantity=1, подразумевалось, что может быть bulk, для чего в ответе мы должны отдавать списки.
            # Но пока не используется, поэтому оставляем логику простую.
            try:
                candidate = next(candidate_generator)
            except StopIteration:
                return {
                    "widgets": {},
                    "newly_served_ids": [],
                    "seen_ids_long_term": list(request_data.seen_ids_long_term),
                }
            # Прокидываем slug для формирования URL
            candidate.preview_obj.slug = candidate.slug
            response_widgets[widget_name] = candidate.preview_obj
            selected_candidates_ids.add(candidate.preview_obj.id)

        # 8. Формируем список newly_served_ids
        newly_served_ids = list(selected_candidates_ids)

        # 9. Обновляем seen_ids_long_term
        # Создаем копию списка, чтобы не изменять оригинальный объект запроса
        updated_seen_long_term = list(request_data.seen_ids_long_term)
        # Добавляем в конец новые показанные ID
        updated_seen_long_term.extend(newly_served_ids)
        # Обрезаем до последних 200 элементов, чтобы не разрастался бесконечно
        updated_seen_long_term = updated_seen_long_term[-200:]

        # 10. Возвращаем результат
        return {
            "widgets": response_widgets,
            "newly_served_ids": newly_served_ids,
            "seen_ids_long_term": updated_seen_long_term,
        }
