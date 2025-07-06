# /home/andrey/Projects/Work/traffic-arbitration/python/scripts/download_missing_images.py

import sys
from pathlib import Path
import logging
import requests

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# --- 1. Настройка системных путей и логирования ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Импорт моделей и конфигурации проекта ---
from traffic_arbitration.models import VisualContent
from traffic_arbitration.db import get_database_url

# --- 3. Конфигурация для загрузчика ---
# Размер пакета для обработки записей из БД за один раз
BATCH_SIZE = 100
# Таймаут для сетевых запросов (в секундах)
REQUEST_TIMEOUT = 15
# Заголовки, имитирующие браузер, для предотвращения блокировок
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def download_missing_images_data():
    """
    Находит VisualContent без бинарных данных, но со ссылкой,
    и пытается загрузить эти данные.
    """
    logging.info("Запуск скрипта для загрузки недостающих данных изображений...")

    database_url = get_database_url()
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    db = Session()

    total_processed = 0
    total_success = 0
    total_failed = 0

    try:
        while True:
            # --- Обработка пакетами (батчами) ---
            logging.info(f"1. Поиск следующего пакета (размер: {BATCH_SIZE}) контента для загрузки...")

            # Находим пакет записей, где 'data' IS NULL, а 'link' НЕ NULL
            contents_to_download = (
                db.query(VisualContent)
                .filter(VisualContent.data.is_(None), VisualContent.link.is_not(None))
                .limit(BATCH_SIZE)
                .all()
            )

            if not contents_to_download:
                logging.info("Отлично! Не найдено записей для загрузки.")
                break

            logging.info(f"Найдено {len(contents_to_download)} записей в пакете. Начинаем загрузку...")

            for vc in contents_to_download:
                try:
                    logging.info(f"  -> Пытаемся загрузить VC ID: {vc.id} со ссылки: {vc.link}")

                    response = requests.get(
                        vc.link,
                        timeout=REQUEST_TIMEOUT,
                        headers=REQUEST_HEADERS,
                        stream=True  # Загружаем заголовки, а не все тело сразу
                    )

                    # Проверяем, что сервер ответил успешно
                    response.raise_for_status()

                    # Проверяем тип контента, чтобы не загружать HTML страницы и прочее
                    content_type = response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        raise ValueError(f"Неверный Content-Type: '{content_type}'")

                    # Загружаем бинарные данные
                    image_data = response.content
                    vc.data = image_data

                    logging.info(f"  -- Успешно! Загружено {len(image_data) // 1024} KB для VC ID: {vc.id}")
                    total_success += 1

                except requests.exceptions.RequestException as e:
                    logging.error(f"  -- Ошибка сети для VC ID: {vc.id}. Причина: {e}")
                    total_failed += 1
                except ValueError as e:
                    logging.error(f"  -- Ошибка данных для VC ID: {vc.id}. Причина: {e}")
                    total_failed += 1
                except Exception as e:
                    logging.error(f"  -- Неизвестная ошибка для VC ID: {vc.id}. Причина: {e}", exc_info=True)
                    total_failed += 1

            total_processed += len(contents_to_download)

            logging.info("Сохранение изменений для обработанного пакета в БД...")
            db.commit()
            logging.info("Пакет успешно обработан и сохранен.")

    except Exception as e:
        logging.error(f"Произошла критическая ошибка во время работы: {e}", exc_info=True)
        logging.warning("Откатываем последнюю транзакцию...")
        db.rollback()
    finally:
        logging.info("--- Итоги работы ---")
        logging.info(f"Всего обработано записей: {total_processed}")
        logging.info(f"Успешно загружено: {total_success}")
        logging.info(f"Не удалось загрузить: {total_failed}")
        logging.info("Закрытие сессии.")
        db.close()


if __name__ == "__main__":
    download_missing_images_data()
