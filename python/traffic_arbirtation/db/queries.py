# db/queries.py
import logging
from typing import List, Dict, Any
import psycopg2
from utils.main import unify_str_values  # универсальная функция
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import mimetypes
import os
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)


def get_active_content_sources(conn) -> List[Dict[str, Any]]:
    """
    Возвращает список источников (из content_sources), где is_active=1.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, source_handler, domain, categories, locale, geo
              FROM content_sources
             WHERE is_active = TRUE
        """)
        rows = cur.fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "name": r[1],
            "source_handler": r[2],
            "domain": r[3],
            "categories": r[4] or "",
            "locale": r[5] or "RU",
            "geo": r[6] or "RU"
        })
    return result


def load_existing_links_for_source(conn, source_id: int) -> Dict[str, Dict[str, Any]]:
    """
    Загружает (link-> {id, categories}) для external_articles_links по source_id.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, link, categories
              FROM external_articles_links
             WHERE source_id = %s
        """, (source_id,))
        rows = cur.fetchall()

    out = {}
    for (row_id, link, cats) in rows:
        out[link] = {
            "id": row_id,
            "categories": cats or ""
        }
    return out


def upsert_external_articles_links_batch(conn, source_id: int, previews: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Batch upsert в external_articles_links:
      - один SELECT всех ссылок для этого source_id
      - формируем списки на UPDATE (где есть) и INSERT (где нет)
      - одним SQL блоком делаем INSERT (и сохраняем id)
      - делаем UPDATE где нужно
    Возвращаем словарь link->id.
    """
    existing = load_existing_links_for_source(conn, source_id)
    update_list = []
    insert_list = []
    result_map = {}

    for p in previews:
        link = p["link"]
        new_cats = p["category_text"] or ""
        if not link:
            continue
        if link in existing:
            row_id = existing[link]["id"]
            old_cats = existing[link]["categories"]
            merged = unify_str_values(old_cats, new_cats, sep=";")
            if merged != old_cats:
                update_list.append((merged, row_id))
            result_map[link] = row_id
        else:
            insert_list.append((link, new_cats))

    with conn.cursor() as cur:
        # UPDATE
        for (merged_cats, row_id) in update_list:
            cur.execute("""
                UPDATE external_articles_links
                   SET categories = %s,
                       updated_at = NOW()
                 WHERE id = %s
            """, (merged_cats, row_id))

        # INSERT
        if insert_list:
            # формируем VALUES
            vals_sql = ",".join(
                cur.mogrify("(%s, %s, %s, NOW(), NOW(), FALSE)", (source_id, lk, ct)).decode()
                for (lk, ct) in insert_list
            )
            sql = f"""
                INSERT INTO external_articles_links 
                    (source_id, link, categories, created_at, updated_at, is_processed)
                VALUES {vals_sql}
                RETURNING id, link
            """
            cur.execute(sql)
            inserted_rows = cur.fetchall()
            for r in inserted_rows:
                new_id, new_link = r
                result_map[new_link] = new_id

    return result_map


def upsert_external_articles_previews_batch(conn, link_map: Dict[str, int], previews: List[Dict[str, Any]]):
    """
    Batch вставка/обновление в external_articles_previews.
    Предполагаем UNIQUE(link_id, title, image_link).
    Используем INSERT ... ON CONFLICT ... DO NOTHING.
    """
    rows_to_insert = []
    for p in previews:
        link = p["link"]
        if not link or link not in link_map:
            continue
        link_id = link_map[link]
        title = p["title"] or ""
        image_link = p["image_link"] or ""
        # text="" (анонс, если нужен)

        rows_to_insert.append((link_id, title, "", image_link))

    if not rows_to_insert:
        return

    with conn.cursor() as cur:
        vals = ",".join(
            cur.mogrify("(%s, %s, %s, %s, NOW(), NOW(), FALSE)", row).decode()
            for row in rows_to_insert
        )
        sql = f"""
            INSERT INTO external_articles_previews
              (link_id, title, text, image_link, created_at, updated_at, is_processed)
            VALUES {vals}
            ON CONFLICT (link_id, title, image_link) DO NOTHING;
        """
        cur.execute(sql)


def upsert_visual_content_batch(conn, previews: List[Dict[str, Any]]):
    """
    Batch вставка "заглушек" в visual_content (link, data=NULL),
    используя INSERT ... ON CONFLICT (link) DO NOTHING.
    """
    links = set()
    for p in previews:
        if p["image_link"]:
            links.add(p["image_link"])

    if not links:
        return

    with conn.cursor() as cur:
        vals = ",".join(
            cur.mogrify("(%s, NULL, NULL, NULL, NULL, NOW(), NOW())", (lk,)).decode()
            for lk in links
        )
        sql = f"""
            INSERT INTO visual_content 
              (link, data, extension, width, height, created_at, updated_at)
            VALUES {vals}
            ON CONFLICT (link) DO NOTHING;
        """
        cur.execute(sql)


def download_missing_images_in_batches(conn):
    """
    Скачивает изображения, которых нет в visual_content.data,
    сохраняя их мини-батчами (чтобы не делать update на каждую запись).
    1) Смотрим, где data IS NULL
    2) Пул потоков (N воркеров) качает
    3) Раз в BATCH_SIZE собранные результаты обновляем в БД
    """
    from config import config
    max_workers = config.get("images_download_workers", 5)
    batch_size = config.get("images_download_batch_size", 20)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, link
              FROM visual_content
             WHERE data IS NULL
               AND link IS NOT NULL
        """)
        rows = cur.fetchall()

    logger.info(f"Для скачивания найдено {len(rows)} изображений")

    # Функция-воркер: скачиваем картинку, возвращаем (id, content, extension, width, height)
    def worker(row_item):
        vc_id, link = row_item
        try:
            resp = requests.get(link, timeout=10)
            if resp.status_code == 200:
                content = resp.content
                # Пытаемся определить расширение
                ctype = resp.headers.get("Content-Type", "")
                guess_ext = mimetypes.guess_extension(ctype)
                if not guess_ext:
                    # из ссылки
                    _, ext_from_link = os.path.splitext(link)
                    if ext_from_link:
                        guess_ext = ext_from_link

                width, height = None, None
                try:
                    im = Image.open(BytesIO(content))
                    width, height = im.size
                except Exception as e:
                    logger.debug(f"Не удалось определить размер (id={vc_id}): {e}", exc_info=True)

                return (vc_id, content, guess_ext, width, height)
            else:
                logger.debug(f"Не скачалось link={link}, status={resp.status_code}")
        except Exception as e:
            logger.debug(f"Ошибка при скачивании link={link}: {e}", exc_info=True)
        return None

    # Запускаем пул
    results = []
    to_update = []  # буфер под обновления (id, data, ext, w, h)
    updated_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, r): r for r in rows}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                to_update.append(res)  # (vc_id, content, ext, w, h)
                if len(to_update) >= batch_size:
                    _update_visual_content_batch(conn, to_update)
                    updated_count += len(to_update)
                    to_update.clear()

    # Если остались «хвост» в to_update
    if to_update:
        _update_visual_content_batch(conn, to_update)
        updated_count += len(to_update)
        to_update.clear()

    logger.info(f"Скачивание изображений завершено. Обновлено записей: {updated_count}")


def _update_visual_content_batch(conn, items: List):
    """
    Вспомогательная функция: обновление поля data/extension/width/height батчем.
    items = [(vc_id, content_bytes, ext, width, height), ...]
    """
    if not items:
        return
    with conn.cursor() as cur:
        # Можно сделать UPDATE с CASE WHEN, но проще несколько UPDATE'ов в цикле
        # или аккуратный "unnest" cte. Покажем вариант cte + unnest:
        # Для упрощённого примера, сделаем так:
        # WARNING: psycopg2 не умеет natively батчить UPDATE, придётся либо несколько UPDATE, либо хитрую конструкцию.
        # Здесь сделаем в цикле, чтоб было понятнее.
        for (vc_id, content, ext, w, h) in items:
            cur.execute("""
                UPDATE visual_content
                   SET data = %s,
                       extension = %s,
                       width = %s,
                       height = %s,
                       updated_at = NOW()
                 WHERE id = %s
            """, (psycopg2.Binary(content), ext, w, h, vc_id))
    conn.commit()


def get_unprocessed_article_links_for_source(conn, source_id):
    """ Получает все необработанные ссылки (is_processed = FALSE) для конкретного источника """
    sql = """
    SELECT link
    FROM external_articles_links
    WHERE source_id = %s AND is_processed = FALSE;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source_id,))
        return [row[0] for row in cur.fetchall()]


def upsert_external_articles_batch(conn, source_id, articles, batch_size=100):
    """ Батчево вставляет записи в external_articles. При конфликте — DO NOTHING, логируем. """
    if not articles:
        return

    with conn.cursor() as cur:
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]

            for art in batch:
                try:
                    cur.execute(
                        """
                        INSERT INTO external_articles (link_id, title, text, sources, created_at, updated_at)
                        VALUES (
                            (SELECT id FROM external_articles_links WHERE link = %s AND source_id = %s),
                            %s, %s, %s, NOW(), NOW()
                        )
                        ON CONFLICT (link_id) DO NOTHING;
                        """,
                        (art["link"], source_id, art["title"], art["text"], art["sources"])
                    )
                except Exception as e:
                    logging.warning(f"⚠️ Ошибка при вставке статьи с link={art['link']}: {e}")


def mark_links_processed_batch(conn, source_id, links, batch_size=100):
    """ Батчево помечает ссылки как обработанные в external_articles_links. """
    if not links:
        return

    with conn.cursor() as cur:
        for i in range(0, len(links), batch_size):
            batch = links[i:i + batch_size]

            cur.execute(
                """
                UPDATE external_articles_links
                SET is_processed = TRUE, updated_at = NOW()
                WHERE source_id = %s AND link = ANY(%s);
                """,
                (source_id, batch)
            )
