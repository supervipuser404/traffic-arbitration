import sys
from pathlib import Path
import logging

from sqlalchemy import create_engine, select, or_
from sqlalchemy.orm import sessionmaker, scoped_session

# --- 1. Настройка системных путей и логирования ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Импорт моделей и конфигурации проекта ---
from traffic_arbitration.models import VisualContent, Article, ArticlePreview
from traffic_arbitration.common.config import config as project_config
from traffic_arbitration.db import get_database_url

# --- 3. Конфигурация ---
# Определяем путь к папке для контентных изображений
STATIC_CONTENT_DIR = project_root / "traffic_arbitration" / "web" / "static" / "img" / "content"


def export_images_to_static():
    """
    Находит изображения, связанные с активным контентом,
    и выгружает их бинарные данные в папку статики.
    """
    logging.info("Запуск скрипта для экспорта изображений в статику...")

    # Убедимся, что директория для сохранения существует
    STATIC_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    logging.info(f"Директория для сохранения: {STATIC_CONTENT_DIR}")

    database_url = get_database_url()
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    db = Session()

    exported_count = 0
    skipped_count = 0

    try:
        logging.info("1. Поиск изображений для экспорта...")

        # Находим ID всех изображений, которые связаны либо с активной статьей,
        # либо с активным превью.
        # Это более эффективно, чем делать два отдельных больших запроса.

        # Изображения из активных статей
        stmt_articles = (
            select(Article.image_id)
            .where(Article.is_active == True, Article.image_id.isnot(None))
        )

        # Изображения из активных превью (теоретически, они дублируют статьи, но для полноты)
        # Примечание: в ArticlePreview поле image - это Text, а не FK. Мы должны идти от Article.
        stmt_previews = (
            select(Article.image_id)
            .join(Article.previews)
            .where(ArticlePreview.is_active == True, Article.image_id.isnot(None))
        )

        # Объединяем ID и убираем дубликаты
        image_ids_to_export = set(db.execute(stmt_articles).scalars().all())
        image_ids_to_export.update(db.execute(stmt_previews).scalars().all())

        if not image_ids_to_export:
            logging.info("Не найдено активных изображений для экспорта.")
            return

        logging.info(f"Найдено {len(image_ids_to_export)} уникальных изображений, связанных с активным контентом.")
        logging.info("2. Проверка и выгрузка файлов...")

        # Теперь получаем сами объекты VisualContent по найденным ID
        visual_contents = db.query(VisualContent).filter(VisualContent.id.in_(image_ids_to_export)).all()

        for vc in visual_contents:
            # Проверяем ключевые условия для экспорта
            if not vc.name:
                logging.warning(f"  - Пропуск VC ID: {vc.id}. Отсутствует имя файла (vc.name).")
                continue
            if not vc.data:
                logging.warning(f"  - Пропуск VC ID: {vc.id}, Файл: {vc.name}. Отсутствуют бинарные данные (vc.data).")
                continue

            filename = vc.name
            subdir_name = filename[:2]
            destination_dir = STATIC_CONTENT_DIR / subdir_name

            # Убедимся, что подпапка существует
            destination_dir.mkdir(parents=True, exist_ok=True)  # <-- ДОБАВЛЕНО

            destination_path = destination_dir / filename  # <-- ИЗМЕНЕНО

            if destination_path.exists():
                # Файл уже существует, пропускаем
                skipped_count += 1
                continue

            try:
                destination_path.write_bytes(vc.data)
                logging.info(f"  - Экспортирован файл: {destination_path}")
                exported_count += 1
            except IOError as e:
                logging.error(f"  - Ошибка записи файла {destination_path}: {e}")

        logging.info("3. Завершение работы.")
        logging.info(f"Успешно экспортировано новых файлов: {exported_count}")
        logging.info(f"Пропущено (уже существуют): {skipped_count}")

    except Exception as e:
        logging.error(f"Произошла критическая ошибка: {e}", exc_info=True)
    finally:
        logging.info("Закрытие сессии.")
        db.close()


if __name__ == "__main__":
    export_images_to_static()
