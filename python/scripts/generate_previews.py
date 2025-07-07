# /home/andrey/Projects/Work/traffic-arbitration/python/scripts/generate_previews.py

import sys
from pathlib import Path
import logging

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, scoped_session, joinedload

# --- 1. Настройка системных путей и логирования ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Импорт моделей и конфигурации проекта ---
from traffic_arbitration.models import Article, ArticlePreview
from traffic_arbitration.common.config import config as project_config
from traffic_arbitration.db import get_database_url

# --- 3. Конфигурация ---
PREVIEW_TEXT_MAX_LENGTH = 300
STATIC_IMAGE_PATH_PREFIX = "/static/img/content/"


def create_excerpt(full_text: str, max_length: int) -> str:
    """
    Создает "умный" отрывок из полного текста.
    Обрезает текст, не разрывая слова, и добавляет многоточие.
    """
    if not full_text or len(full_text) <= max_length:
        return full_text

    # Ищем последний пробел в пределах максимальной длины
    last_space_index = full_text.rfind(' ', 0, max_length)

    if last_space_index != -1:
        # Обрезаем по последнему пробелу
        return full_text[:last_space_index].strip() + "..."
    else:
        # Если пробелов не нашлось (очень длинное слово), просто обрезаем
        return full_text[:max_length] + "..."


def generate_previews_for_articles():
    """Основная функция, которая находит статьи без превью и создает их."""
    logging.info("Запуск скрипта для генерации превью...")

    database_url = get_database_url()
    engine = create_engine(database_url)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Session = scoped_session(session_factory)
    db = Session()
    created_count = 0

    try:
        logging.info("1. Поиск статей, у которых нет превью...")

        # Шаг 1: Безопасно получаем и блокируем ID статей, у которых нет превью.
        # Этот запрос не содержит JOIN, поэтому FOR UPDATE работает корректно.
        article_ids_to_process = db.execute(
            select(Article.id)
            .filter(~Article.previews.any())
            .with_for_update()
        ).scalars().all()

        if not article_ids_to_process:
            logging.info("Отлично! Все статьи уже имеют превью.")
            return

        # Шаг 2: Загружаем полные объекты по этим ID с эффективной подгрузкой изображений.
        # Этот запрос уже не содержит FOR UPDATE, поэтому LEFT JOIN безопасен.
        articles_without_previews = (
            db.query(Article)
            .options(joinedload(Article.image))
            .filter(Article.id.in_(article_ids_to_process))
            .all()
        )

        if not articles_without_previews:
            logging.info("Отлично! Все статьи уже имеют превью.")
            return

        logging.info(f"Найдено {len(articles_without_previews)} статей для обработки.")
        logging.info("2. Создание превью...")

        for article in articles_without_previews:
            logging.info(f"  - Обработка статьи ID: {article.id}, Заголовок: '{article.title[:50]}...'")

            excerpt_text = create_excerpt(article.text, PREVIEW_TEXT_MAX_LENGTH)

            # --- ИЗМЕНЕННАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ ИЗОБРАЖЕНИЯ ---
            image_path = None
            if article.image:
                if article.image.name:
                    # Если есть имя файла, это локальный статический ресурс
                    # Формируем путь с подпапкой по первым двум символам
                    filename = article.image.name
                    subdir = filename[:2]
                    image_path = f"{STATIC_IMAGE_PATH_PREFIX}{subdir}/{filename}"  # <-- ИЗМЕНЕНО
                    logging.info(f"    > Найдено локальное изображение: {image_path}")
                elif article.image.link:
                    # Иначе, если есть ссылка, это внешний ресурс
                    image_path = article.image.link
                    logging.info(f"    > Найдено внешнее изображение: {image_path}")
            # ----------------------------------------------------

            new_preview = ArticlePreview(
                article_id=article.id,
                title=article.title,
                text=excerpt_text,
                image=image_path,
                is_active=article.is_active  # <-- Устанавливаем статус как у родительской статьи
            )

            db.add(new_preview)
            created_count += 1

        logging.info("3. Сохранение изменений в базе данных...")
        db.commit()
        logging.info(f"Успешно создано и сохранено {created_count} новых превью!")

    except Exception as e:
        logging.error(f"Произошла ошибка: {e}", exc_info=True)
        logging.warning("Откатываем изменения...")
        db.rollback()
    finally:
        logging.info("Закрытие сессии.")
        db.close()


if __name__ == "__main__":
    generate_previews_for_articles()
