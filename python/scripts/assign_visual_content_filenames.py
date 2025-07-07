# /home/andrey/Projects/Work/traffic-arbitration/python/scripts/assign_filenames.py

import sys
import uuid
from pathlib import Path
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# --- 1. Настройка системных путей и логирования ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Импорт моделей и конфигурации проекта ---
from traffic_arbitration.models import VisualContent
from traffic_arbitration.common.config import config as project_config
from traffic_arbitration.db import get_database_url


def generate_unique_filename(extension: str | None) -> str:
    """
    Генерирует уникальное имя файла на основе UUID.
    Пример: 'f47ac10b58cc4372a5670e02b2c3d479.jpg'
    """
    base_name = uuid.uuid4().hex
    if extension:
        # Очищаем расширение от возможной точки в начале
        clean_extension = extension.lstrip('.')
        return f"{base_name}.{clean_extension}"
    return base_name


def assign_missing_filenames():
    """
    Находит VisualContent без имени файла и присваивает им уникальные имена.
    """
    logging.info("Запуск скрипта для присвоения имён файлам...")

    database_url = get_database_url()
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    db = Session()

    assigned_count = 0
    try:
        logging.info("1. Поиск контента без имён файлов...")
        # Находим все записи, где 'name' IS NULL, и блокируем их для обновления
        contents_to_update = db.query(VisualContent).filter(VisualContent.name.is_(None)).with_for_update().all()

        if not contents_to_update:
            logging.info("Отлично! Весь визуальный контент уже имеет имена файлов.")
            return

        logging.info(f"Найдено {len(contents_to_update)} записей для обработки.")
        logging.info("2. Генерация и присвоение новых имён...")

        for vc in contents_to_update:
            new_name = generate_unique_filename(vc.extension)
            vc.name = new_name
            logging.info(f"  - Присвоено имя '{new_name}' для VC ID: {vc.id}")
            assigned_count += 1

        logging.info("3. Сохранение изменений в базе данных...")
        db.commit()
        logging.info(f"Успешно присвоено {assigned_count} новых имён файлов!")

    except Exception as e:
        logging.error(f"Произошла ошибка: {e}", exc_info=True)
        logging.warning("Откатываем изменения...")
        db.rollback()
    finally:
        logging.info("Закрытие сессии.")
        db.close()


if __name__ == "__main__":
    assign_missing_filenames()
