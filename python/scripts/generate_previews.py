# /home/andrey/Projects/Work/traffic-arbitration/python/scripts/generate_previews.py

import sys
from pathlib import Path
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# --- 1. Настройка системных путей и логирования ---
# Это позволяет скрипту, запущенному из любой директории,
# корректно импортировать модули вашего проекта.
# Добавляем корень 'python' в PYTHONPATH.
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Импорт моделей и конфигурации проекта ---
# Импорты должны идти после настройки sys.path
from traffic_arbitration.models import Article, ArticlePreview
from traffic_arbitration.common.config import config as project_config

# --- 3. Конфигурация ---
PREVIEW_TEXT_MAX_LENGTH = 300


def get_database_url() -> str:
    """
    Формирует SQLAlchemy URL из глобального объекта конфигурации.
    Логика полностью повторяет ту, что используется в alembic/env.py.
    """
    db_config = project_config['database']
    return (
        f"postgresql://{db_config['user']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
    )


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
    """
    Основная функция, которая находит статьи без превью и создает их.
    """
    logging.info("Запуск скрипта для генерации превью...")

    # --- 4. Настройка сессии SQLAlchemy ---
    database_url = get_database_url()
    engine = create_engine(database_url)
    # Используем scoped_session для потокобезопасности, что является хорошей практикой
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Session = scoped_session(session_factory)

    db = Session()
    created_count = 0

    try:
        # --- 5. Основная логика ---
        logging.info("1. Поиск статей, у которых нет превью...")

        # Находим все статьи, у которых нет связанных записей в ArticlePreview.
        # `~Article.previews.any()` - это эффективный способ сделать это через ORM.
        # `with_for_update()` блокирует строки на время транзакции, чтобы избежать гонки состояний,
        # если скрипт может быть запущен параллельно.
        articles_without_previews = db.query(Article).filter(~Article.previews.any()).with_for_update().all()

        if not articles_without_previews:
            logging.info("Отлично! Все статьи уже имеют превью.")
            return

        logging.info(f"Найдено {len(articles_without_previews)} статей для обработки.")
        logging.info("2. Создание превью...")

        for article in articles_without_previews:
            logging.info(f"  - Обработка статьи ID: {article.id}, Заголовок: '{article.title[:50]}...'")

            # Создаем короткий текст
            excerpt_text = create_excerpt(article.text, PREVIEW_TEXT_MAX_LENGTH)

            # Получаем ссылку на изображение, если оно есть
            image_url = article.image.link if article.image else None

            # Создаем новый объект превью
            new_preview = ArticlePreview(
                article_id=article.id,
                title=article.title,  # Заголовок превью совпадает с заголовком статьи
                text=excerpt_text,
                image=image_url
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
