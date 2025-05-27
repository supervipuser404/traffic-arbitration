import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func, update, delete, bindparam
from sqlalchemy.dialects.postgresql import insert
from traffic_arbitration.models import (
    ContentSource, ExternalArticleLink, ExternalArticlePreview, ExternalArticle,
    VisualContent, Category, ExternalArticleLinkCategory
)
from traffic_arbitration.common.utils import unify_str_values
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import mimetypes
import os
from io import BytesIO
from PIL import Image
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_active_content_sources(session: Session) -> List[Dict[str, Any]]:
    """
    Возвращает список источников (из content_sources), где is_active=True.

    Args:
        session: SQLAlchemy сессия.

    Returns:
        Список словарей с данными активных источников.
    """
    result = session.execute(
        select(
            ContentSource.id,
            ContentSource.name,
            ContentSource.source_handler,
            ContentSource.domain,
            ContentSource.aliases
        ).filter_by(is_active=True)
    ).all()

    return [
        {
            "id": row.id,
            "name": row.name,
            "source_handler": row.source_handler,
            "domain": row.domain,
            "categories": row.aliases or "",  # aliases как категории
            "locale": "RU",  # TODO: Добавить поле locale в content_sources
            "geo": "RU"  # TODO: Добавить поле geo в content_sources
        }
        for row in result
    ]


def load_existing_links_for_source(session: Session, source_id: int) -> Dict[str, Dict[str, Any]]:
    """
    Загружает (link -> {id, categories}) для external_articles_links по source_id.
    Категории извлекаются из external_article_link_categories за один запрос.

    Args:
        session: SQLAlchemy сессия.
        source_id: ID источника.

    Returns:
        Словарь, где ключ - строка ссылки, значение - словарь с id и списком категорий.
    """
    # Запрос с LEFT JOIN и агрегацией категорий
    stmt = (
        select(
            ExternalArticleLink.id,
            ExternalArticleLink.link,
            func.string_agg(Category.code, ';').label('categories')
        )
        .outerjoin(ExternalArticleLinkCategory, ExternalArticleLink.id == ExternalArticleLinkCategory.link_id)
        .outerjoin(Category, ExternalArticleLinkCategory.category_id == Category.id)
        .filter(ExternalArticleLink.source_id == source_id)
        .group_by(ExternalArticleLink.id, ExternalArticleLink.link)
    )

    result = session.execute(stmt).all()
    out: Dict[str, Dict[str, Any]] = {}
    for row in result:
        out[str(row.link)] = {
            "id": row.id,
            "categories": row.categories or ""
        }
    return out


def upsert_external_articles_links_batch(session: Session, source_id: int,
                                         previews: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Batch upsert в external_articles_links и обновление категорий в external_article_link_categories.
    Возвращает словарь link -> id.

    Args:
        session: SQLAlchemy сессия.
        source_id: ID источника.
        previews: Список словарей с данными превью.

    Returns:
        Словарь, где ключ - строка ссылки, значение - ID записи.
    """
    # Загружаем существующие ссылки
    existing = load_existing_links_for_source(session, source_id)
    result_map: Dict[str, Optional[int]] = {}

    # Кэшируем категории (code -> id)
    categories = session.execute(select(Category.code, Category.id)).all()
    category_map: Dict[str, int] = {row.code: row.id for row in categories if row.code}

    # Списки для пакетной обработки
    new_links = []
    links_to_update = []  # ID ссылок для обновления updated_at
    categories_to_insert = []  # Новые связи для external_article_link_categories
    link_ids_to_clear = []  # ID ссылок, у которых нужно удалить старые категории

    for preview in previews:
        link = preview.get("link")
        if not link:
            continue
        new_cats = preview.get("category_text", "") or ""

        if link in existing:
            link_id = existing[link]["id"]
            old_cats = existing[link]["categories"]
            merged_cats = unify_str_values(old_cats, new_cats, sep=";")
            if merged_cats != old_cats:
                links_to_update.append(link_id)
                link_ids_to_clear.append(link_id)
                # Добавляем категории
                for cat_code in merged_cats.split(";"):
                    if cat_code in category_map:  # Проверка наличия категории
                        categories_to_insert.append({
                            "link_id": link_id,
                            "category_id": category_map[cat_code]
                        })
            result_map[link] = link_id
        else:
            new_link = ExternalArticleLink(
                source_id=source_id,
                link=link,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_processed=False
            )
            new_links.append(new_link)
            # Сохраняем временное значение None
            result_map[link] = None
            # Добавляем категории для новой ссылки
            for cat_code in new_cats.split(";"):
                if cat_code in category_map:
                    categories_to_insert.append({
                        "link_id": None,  # Заполним после flush
                        "category_id": category_map[cat_code],
                        "_link": link  # Для маппинга после flush
                    })

    # Пакетная вставка новых ссылок
    if new_links:
        session.add_all(new_links)
        session.flush()  # Получаем ID новых ссылок
        for link_obj in new_links:
            result_map[link_obj.link] = link_obj.id
            # Обновляем link_id для категорий
            for cat in categories_to_insert:
                if cat.get("_link") == link_obj.link:
                    cat["link_id"] = link_obj.id
                    del cat["_link"]

    # Пакетное удаление старых категорий
    if link_ids_to_clear:
        session.execute(
            delete(ExternalArticleLinkCategory).where(
                ExternalArticleLinkCategory.link_id.in_(link_ids_to_clear)
            )
        )

    # Пакетная вставка новых категорий
    if categories_to_insert:
        session.bulk_save_objects([
            ExternalArticleLinkCategory(
                link_id=cat["link_id"],
                category_id=cat["category_id"]
            )
            for cat in categories_to_insert if cat["link_id"] is not None
        ])

    # Пакетное обновление updated_at
    if links_to_update:
        session.execute(
            update(ExternalArticleLink)
            .where(ExternalArticleLink.id.in_(links_to_update))
            .values(updated_at=datetime.now(timezone.utc))
        )

    # Проверяем, что все значения в result_map - int
    final_result_map: Dict[str, int] = {k: v for k, v in result_map.items() if v is not None}
    return final_result_map


def upsert_external_articles_previews_batch(session: Session, link_map: Dict[str, int], previews: List[Dict[str, Any]]):
    """
    Batch вставка/обновление в external_articles_previews.

    Args:
        session: SQLAlchemy сессия.
        link_map: Словарь link -> link_id.
        previews: Список словарей с данными превью.
    """
    # Получаем все link_id, для которых будем проверять существующие превью
    link_ids = list(link_map.values())
    if not link_ids:
        return

    # Загружаем существующие превью одним запросом
    existing_previews = session.execute(
        select(
            ExternalArticlePreview.link_id,
            ExternalArticlePreview.title,
            ExternalArticlePreview.image_link
        ).filter(ExternalArticlePreview.link_id.in_(link_ids))
    ).all()

    # Создаём множество для быстрого поиска существующих комбинаций
    existing_set = {(row.link_id, row.title or "", row.image_link or "") for row in existing_previews}

    # Собираем новые записи для вставки
    new_previews = []
    current_time = datetime.now(timezone.utc)

    for preview in previews:
        link = preview.get("link")
        if not link or link not in link_map:
            continue
        link_id = link_map[link]
        title = preview.get("title", "") or ""
        image_link = preview.get("image_link", "") or ""

        # Проверяем, существует ли запись
        if (link_id, title, image_link) not in existing_set:
            new_previews.append({
                "link_id": link_id,
                "title": title,
                "text": "",
                "image_link": image_link,
                "created_at": current_time,
                "updated_at": current_time,
                "is_processed": False
            })

    # Пакетная вставка новых превью
    if new_previews:
        session.execute(
            insert(ExternalArticlePreview)
            .values(new_previews)
            .on_conflict_do_nothing(
                index_elements=["link_id", "title", "image_link"]
            )
        )


def upsert_visual_content_batch(session: Session, previews: List[Dict[str, Any]]):
    """
    Batch вставка заглушек в visual_content (link, data=NULL).

    Args:
        session: SQLAlchemy сессия.
        previews: Список словарей с данными превью.
    """
    # Собираем уникальные image_link
    links = {preview.get("image_link") for preview in previews if preview.get("image_link")}
    if not links:
        return

    # Загружаем существующие записи одним запросом
    existing_links = session.execute(
        select(VisualContent.link).filter(VisualContent.link.in_(links))
    ).scalars().all()
    existing_set = set(existing_links)

    # Собираем новые записи
    current_time = datetime.now(timezone.utc)
    new_contents = [
        {
            "link": link,
            "data": None,
            "extension": None,
            "width": None,
            "height": None,
            "created_at": current_time,
            "updated_at": current_time
        }
        for link in links if link not in existing_set
    ]

    # Пакетная вставка
    if new_contents:
        session.execute(
            insert(VisualContent)
            .values(new_contents)
            .on_conflict_do_nothing(index_elements=["link"])
        )


def download_missing_images_in_batches(session: Session):
    """
    Скачивает изображения, где data IS NULL в visual_content.

    Args:
        session: SQLAlchemy сессия.
    """
    from traffic_arbitration.common.config import config
    max_workers = config.get("images_download_workers", 5)
    batch_size = config.get("images_download_batch_size", 20)

    # Загружаем только id и link
    contents = session.execute(
        select(VisualContent.id, VisualContent.link)
        .filter(VisualContent.data.is_(None), VisualContent.link.isnot(None))
    ).all()
    logger.info(f"Для скачивания найдено {len(contents)} изображений")

    def worker(content) -> Tuple[int, bytes, str | None, int | None, int | None] | None:
        try:
            resp = requests.get(content.link, timeout=10)
            if resp.status_code == 200:
                content_bytes = resp.content
                ctype = resp.headers.get("Content-Type", "")
                guess_ext = mimetypes.guess_extension(ctype)
                if not guess_ext:
                    _, ext_from_link = os.path.splitext(content.link)
                    guess_ext = ext_from_link or None
                width, height = None, None
                try:
                    im = Image.open(BytesIO(content_bytes))
                    width, height = im.size
                except Exception as e:
                    logger.debug(f"Не удалось определить размер (id={content.id}): {e}", exc_info=True)
                return content.id, content_bytes, guess_ext, width, height
            else:
                logger.debug(f"Не скачалось link={content.link}, status={resp.status_code}")
        except Exception as e:
            logger.debug(f"Ошибка при скачивании link={content.link}: {e}", exc_info=True)
        return None

    to_update: List[Tuple[int, bytes, str | None, int | None, int | None]] = []
    updated_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, content): content for content in contents}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                to_update.append(res)
                if len(to_update) >= batch_size:
                    _update_visual_content_batch(session, to_update)
                    updated_count += len(to_update)
                    to_update.clear()

    if to_update:
        _update_visual_content_batch(session, to_update)
        updated_count += len(to_update)

    logger.info(f"Скачивание изображений завершено. Обновлено записей: {updated_count}")


def _update_visual_content_batch(session: Session, items: List[Tuple[int, bytes, str | None, int | None, int | None]]):
    """
    Обновление visual_content батчем.

    Args:
        session: SQLAlchemy сессия.
        items: Список кортежей (vc_id, content_bytes, ext, width, height).
    """
    if not items:
        return

    # Собираем данные для обновления
    values = [
        {
            "id": vc_id,
            "data": content,
            "extension": ext,
            "width": width,
            "height": height,
            "updated_at": datetime.now(timezone.utc)
        }
        for vc_id, content, ext, width, height in items
    ]

    # Пакетное обновление с отключением синхронизации сессии
    session.execute(
        update(VisualContent)
        .where(VisualContent.id.in_([v["id"] for v in values]))
        .values(
            data=bindparam("data"),
            extension=bindparam("extension"),
            width=bindparam("width"),
            height=bindparam("height"),
            updated_at=bindparam("updated_at")
        ),
        values,
        execution_options={"synchronize_session": None}  # Отключаем синхронизацию
    )


def get_unprocessed_article_links_for_source(session: Session, source_id: int) -> List[str]:
    """
    Получает список необработанных ссылок (is_processed = False) для источника.

    Args:
        session: SQLAlchemy сессия.
        source_id: ID источника.

    Returns:
        Список строк ссылок.
    """
    result = session.execute(
        select(ExternalArticleLink.link)
        .filter_by(source_id=source_id, is_processed=False)
    ).scalars().all()

    # Приводим к list, если тип не соответствует, из-за аннотации Sequence[_R] в SQLAlchemy,
    # которая вызывает предупреждение в статическом анализаторе PyCharm/Pyright
    links = result if isinstance(result, list) else list(result)

    return links


def upsert_external_articles_batch(session: Session, source_id: int, articles: List[Dict[str, Any]],
                                   batch_size: int = 100):
    """
    Батчево вставляет записи в external_articles.

    Args:
        session: SQLAlchemy сессия.
        source_id: ID источника.
        articles: Список словарей с данными статей.
        batch_size: Размер пакета для вставки.
    """
    if not articles:
        return

    # Собираем все link
    links = [art.get("link") for art in articles if art.get("link")]
    if not links:
        return

    # Загружаем link_id для всех ссылок
    link_objs = session.execute(
        select(ExternalArticleLink.link, ExternalArticleLink.id)
        .filter_by(source_id=source_id)
        .filter(ExternalArticleLink.link.in_(links))
    ).all()
    link_id_map = {row.link: row.id for row in link_objs}

    # Загружаем существующие статьи
    link_ids = list(link_id_map.values())
    existing_articles = session.execute(
        select(ExternalArticle.link_id).filter(ExternalArticle.link_id.in_(link_ids))
    ).scalars().all()
    existing_set = set(existing_articles)

    # Собираем новые статьи
    current_time = datetime.now(timezone.utc)
    new_articles = []
    for art in articles:
        link = art.get("link")
        if not link or link not in link_id_map:
            logger.warning(f"⚠️ Ссылка не найдена: {link}")
            continue
        link_id = link_id_map[link]
        if link_id not in existing_set:
            new_articles.append({
                "link_id": link_id,
                "title": art.get("title", "") or "",
                "text": art.get("text", "") or "",
                "created_at": current_time,
                "updated_at": current_time,
                "is_processed": False
            })

    # Пакетная вставка
    for i in range(0, len(new_articles), batch_size):
        batch = new_articles[i:i + batch_size]
        session.execute(
            insert(ExternalArticle)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["link_id"])
        )


def mark_links_processed_batch(session: Session, source_id: int, links: List[str], batch_size: int = 100):
    """
    Помечает ссылки как обработанные.

    Args:
        session: SQLAlchemy сессия.
        source_id: ID источника.
        links: Список ссылок для пометки.
        batch_size: Размер пакета для обновления.
    """
    if not links:
        return

    for i in range(0, len(links), batch_size):
        batch = links[i:i + batch_size]
        session.execute(
            update(ExternalArticleLink)
            .where(
                ExternalArticleLink.source_id == source_id,
                ExternalArticleLink.link.in_(batch)
            )
            .values(
                is_processed=True,
                updated_at=datetime.now(timezone.utc)
            )
        )
