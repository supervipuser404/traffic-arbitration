import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from db.connection import get_connection
from db.queries import get_active_content_sources, download_missing_images_in_batches
from scrapper.runner import process_source
from config import config, logger


def main():
    logger.info("=== START MAIN SCRAPPER ===")
    try:
        # 1) Получаем список источников
        with get_connection() as conn:
            sources = get_active_content_sources(conn)
        logger.info(f"Активных источников: {len(sources)}")

        # 2) Параллельная обработка источников (каждый внутри себя может параллелить категории)
        max_source_workers = config["parallel_sources_workers"]  # например, 3
        with ThreadPoolExecutor(max_workers=max_source_workers) as executor:
            fut_map = {}
            for src in sources:
                f = executor.submit(process_source, src)
                fut_map[f] = src["name"]

            for f in as_completed(fut_map):
                src_name = fut_map[f]
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"Ошибка при обработке источника {src_name}: {e}", exc_info=True)

        # 3) После обработки всех источников — скачиваем картинки
        with get_connection() as conn:
            download_missing_images_in_batches(conn)

    except KeyboardInterrupt:
        logger.warning("Остановка по Ctrl+C")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Глобальная ошибка main(): {e}")
    logger.info("=== END MAIN SCRAPPER ===")


if __name__ == "__main__":
    main()
