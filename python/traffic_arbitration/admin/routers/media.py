from fastapi import APIRouter, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, load_only
from sqlalchemy import desc, or_, and_, func
from typing import Optional, List
from PIL import Image
import io
import requests
from datetime import datetime
import os
import mimetypes
import urllib.parse
import hashlib
import json
from traffic_arbitration.models import VisualContent, Category, Tag, VisualContentCategory, VisualContentTag
from traffic_arbitration.admin.schemas import VisualContentCreate, VisualContentUpdate, VisualContentResponse
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger
from traffic_arbitration.common.utils import transliterate
import re

# Система конфигурации для админ-панели
ADMIN_CONFIG_FILE = "admin_config.json"

# Стандартная конфигурация галереи
DEFAULT_GALLERY_CONFIG = {
    "use_thumbnails": False,  # По умолчанию - полноразмерные изображения
    "thumbnail_width": 150,
    "thumbnail_height": 100,
    "enable_lazy_loading": True,
    "cache_timeout": 300,  # 5 минут для кэша фильтров
}

# Глобальная переменная для кэширования конфигурации
_gallery_config = None
_config_lock = False

def load_gallery_config():
    """Загружает конфигурацию галереи из файла"""
    global _gallery_config, _config_lock
    
    if _config_lock:
        return _gallery_config or DEFAULT_GALLERY_CONFIG
    
    try:
        if os.path.exists(ADMIN_CONFIG_FILE):
            with open(ADMIN_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'gallery' in data:
                    config = {**DEFAULT_GALLERY_CONFIG, **data['gallery']}
                else:
                    config = DEFAULT_GALLERY_CONFIG.copy()
        else:
            config = DEFAULT_GALLERY_CONFIG.copy()
            
        _gallery_config = config
        logger.info(f"Gallery config loaded: thumbnails={config['use_thumbnails']}")
        
    except Exception as e:
        logger.error(f"Failed to load gallery config: {e}")
        _gallery_config = DEFAULT_GALLERY_CONFIG
    
    return _gallery_config

def save_gallery_config(config):
    """Сохраняет конфигурацию галереи в файл"""
    global _config_lock
    
    _config_lock = True
    try:
        os.makedirs(os.path.dirname(ADMIN_CONFIG_FILE) if os.path.dirname(ADMIN_CONFIG_FILE) else ".", exist_ok=True)
        
        # Загружаем существующий файл если есть
        if os.path.exists(ADMIN_CONFIG_FILE):
            with open(ADMIN_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
        
        # Обновляем секцию gallery
        data['gallery'] = config
        
        with open(ADMIN_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info("Gallery configuration saved")
        
    except Exception as e:
        logger.error(f"Failed to save gallery config: {e}")
    finally:
        _config_lock = False

def get_gallery_config():
    """Получает текущую конфигурацию галереи"""
    return load_gallery_config()

def update_gallery_config(key, value):
    """Обновляет конкретную настройку галереи"""
    config = get_gallery_config()
    config[key] = value
    save_gallery_config(config)
    return config

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


# Кэш для фильтров и статистики (обновляется каждые 5 минут)
_filter_cache = {
    'categories': [],
    'tags': [],
    'extensions': [],
    'stats': {'total': 0, 'images': 0, 'this_month': 0, 'storage_used_mb': 0},
    'last_update': None
}

_cache_lock = False


async def get_cached_filters(db: Session):
    """Получает кэшированные данные для фильтров"""
    global _filter_cache, _cache_lock
    
    if _cache_lock:
        # Если кэш обновляется, возвращаем старые данные
        return _filter_cache['categories'], _filter_cache['tags'], _filter_cache['extensions']
    
    # Проверяем, нужно ли обновить кэш
    config = get_gallery_config()
    cache_timeout = config.get('cache_timeout', 300)
    
    now = datetime.utcnow()
    if (_filter_cache['last_update'] and
        (now - _filter_cache['last_update']).total_seconds() < cache_timeout):
        return _filter_cache['categories'], _filter_cache['tags'], _filter_cache['extensions']
    
    # Обновляем кэш
    _cache_lock = True
    try:
        logger.info("Updating filter cache...")
        
        # Категории и теги
        categories = db.query(Category).order_by(Category.code).all()
        tags = db.query(Tag).order_by(Tag.code).all()
        
        # Расширения файлов (только непустые)
        extensions_query = db.query(VisualContent.extension).distinct().filter(
            VisualContent.extension.isnot(None),
            VisualContent.extension != ""
        ).order_by(VisualContent.extension)
        extensions = [ext[0] for ext in extensions_query.all() if ext[0]]
        
        # Статистика (без загрузки всех данных)
        total_files = db.query(func.count(VisualContent.id)).scalar() or 0
        images_count = db.query(func.count(VisualContent.id)).filter(
            VisualContent.extension.in_(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'])
        ).scalar() or 0
        this_month = db.query(func.count(VisualContent.id)).filter(
            VisualContent.created_at >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ).scalar() or 0
        
        # Размер хранилища (только приблизительный расчет)
        # Используем средний размер файла для ускорения
        avg_size_result = db.query(func.avg(func.length(VisualContent.data))).filter(
            VisualContent.data.isnot(None)
        ).scalar()
        avg_size = int(avg_size_result) if avg_size_result else 1024 * 1024  # 1MB по умолчанию
        storage_used_mb = round((total_files * avg_size) / (1024 * 1024), 2)
        
        # Обновляем кэш
        _filter_cache = {
            'categories': categories,
            'tags': tags,
            'extensions': extensions,
            'stats': {
                'total': total_files,
                'images': images_count,
                'this_month': this_month,
                'storage_used_mb': storage_used_mb
            },
            'last_update': now,
            'cache_timeout': cache_timeout
        }
        
        logger.info(f"Filter cache updated: {len(categories)} categories, {len(tags)} tags, {len(extensions)} extensions")
        
    finally:
        _cache_lock = False
    
    return _filter_cache['categories'], _filter_cache['tags'], _filter_cache['extensions']


@router.post("/config/gallery", response_class=HTMLResponse)
async def update_gallery_config(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        use_thumbnails: Optional[bool] = Form(None),
        thumbnail_width: Optional[int] = Form(None),
        thumbnail_height: Optional[int] = Form(None),
        enable_lazy_loading: Optional[bool] = Form(None),
        cache_timeout: Optional[int] = Form(None)
):
    """Обновление конфигурации галереи"""
    logger.info("Updating gallery configuration")
    
    try:
        current_config = get_gallery_config()
        
        # Обновляем только переданные параметры
        if use_thumbnails is not None:
            current_config['use_thumbnails'] = use_thumbnails
            logger.info(f"Setting use_thumbnails to {use_thumbnails}")
        
        if thumbnail_width is not None and 50 <= thumbnail_width <= 800:
            current_config['thumbnail_width'] = thumbnail_width
            logger.info(f"Setting thumbnail_width to {thumbnail_width}")
        
        if thumbnail_height is not None and 50 <= thumbnail_height <= 600:
            current_config['thumbnail_height'] = thumbnail_height
            logger.info(f"Setting thumbnail_height to {thumbnail_height}")
        
        if enable_lazy_loading is not None:
            current_config['enable_lazy_loading'] = enable_lazy_loading
            logger.info(f"Setting enable_lazy_loading to {enable_lazy_loading}")
        
        if cache_timeout is not None and 60 <= cache_timeout <= 3600:
            current_config['cache_timeout'] = cache_timeout
            logger.info(f"Setting cache_timeout to {cache_timeout}")
        
        # Сохраняем конфигурацию
        save_gallery_config(current_config)
        
        logger.info("Gallery configuration updated successfully")
        
    except Exception as e:
        logger.error(f"Failed to update gallery configuration: {str(e)}")
    
    # Возвращаемся на страницу галереи
    return RedirectResponse(url="/admin/media/gallery", status_code=303)


@router.get("/gallery-config", response_class=HTMLResponse)
async def gallery_config_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма настройки конфигурации галереи"""
    logger.info("Accessing gallery configuration form")
    
    config = get_gallery_config()
    
    return templates.TemplateResponse("media/gallery_config.html", {
        "request": request,
        "config": config
    })


@router.get("/gallery", response_class=HTMLResponse)
async def list_media(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        extension: Optional[str] = None,
        category_id: Optional[int] = None,
        tag_id: Optional[int] = None
):
    """Галерея изображений с оптимизированными запросами"""
    logger.info(f"Listing media: page={page}, per_page={per_page}, filters: search={search}, ext={extension}")
    
    # Получаем конфигурацию галереи
    config = get_gallery_config()
    use_thumbnails = config.get('use_thumbnails', False)
    thumbnail_width = config.get('thumbnail_width', 150)
    thumbnail_height = config.get('thumbnail_height', 100)
    enable_lazy_loading = config.get('enable_lazy_loading', True)
    
    # Базовая оптимизация - используем only() для загрузки только нужных полей
    query = db.query(VisualContent).options(
        load_only(VisualContent.id, VisualContent.name, VisualContent.extension,
                 VisualContent.width, VisualContent.height, VisualContent.created_at)
    )
    
    # Поиск по имени
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(VisualContent.name.ilike(search_pattern))
    
    # Фильтрация по расширению
    if extension:
        query = query.filter(VisualContent.extension == extension.lower())
    
    # Фильтрация по категориям
    if category_id:
        query = query.join(VisualContentCategory).filter(
            VisualContentCategory.category_id == category_id
        )
    
    # Фильтрация по тегам
    if tag_id:
        query = query.join(VisualContentTag).filter(
            VisualContentTag.tag_id == tag_id
        )
    
    # Подсчет общего количества
    total = query.count()
    
    # Получаем данные для текущей страницы
    media_items = query.order_by(desc(VisualContent.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    # Получаем кэшированные данные для фильтров
    categories, tags, extensions = await get_cached_filters(db)
    stats = _filter_cache['stats']
    
    return templates.TemplateResponse("media/gallery.html", {
        "request": request,
        "media_items": media_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "categories": categories,
        "tags": tags,
        "extensions": extensions,
        "filters": {
            "search": search,
            "extension": extension,
            "category_id": category_id,
            "tag_id": tag_id
        },
        "stats": {
            "total": stats['total'],
            "images": stats['images'],
            "this_month": stats['this_month'],
            "storage_used": f"{stats['storage_used_mb']} MB"
        },
        "gallery_config": {
            "use_thumbnails": use_thumbnails,
            "thumbnail_width": thumbnail_width,
            "thumbnail_height": thumbnail_height,
            "enable_lazy_loading": enable_lazy_loading
        }
    })


@router.get("/upload", response_class=HTMLResponse)
async def upload_media_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма загрузки медиа-файлов"""
    logger.info("Accessing media upload form")
    
    categories = db.query(Category).all()
    tags = db.query(Tag).all()
    
    # Рассчитываем статистику для upload формы
    storage_used = sum(
        len(item.data) if item.data else 0
        for item in db.query(VisualContent).all()
    )
    storage_used_mb = round(storage_used / (1024 * 1024), 2)
    max_file_size_mb = 10  # Максимальный размер файла 10MB
    
    allowed_types = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'pdf', 'doc', 'docx', 'txt', 'zip', 'rar']
    
    return templates.TemplateResponse("media/upload.html", {
        "request": request,
        "categories": categories,
        "tags": tags,
        "media_item": None,
        "is_edit": False,
        "stats": {
            "storage_used": f"{storage_used_mb} MB",
            "max_file_size": f"{max_file_size_mb} MB",
            "allowed_types": allowed_types
        }
    })


@router.post("/upload", response_class=HTMLResponse)
async def upload_media(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        file: UploadFile = File(...),
        category_ids: Optional[str] = Form(None),
        tag_ids: Optional[str] = Form(None)
):
    """Загрузка новых файлов"""
    logger.info(f"Uploading media file: {file.filename}")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    errors = []
    category_ids_list = [int(x) for x in category_ids.split(",") if x] if category_ids else []
    tag_ids_list = [int(x) for x in tag_ids.split(",") if x] if tag_ids else []
    
    try:
        # Читаем файл
        file_data = await file.read()
        
        # Проверяем размер файла (максимум 10MB)
        if len(file_data) > 10 * 1024 * 1024:
            errors.append("Размер файла не должен превышать 10MB")
            return templates.TemplateResponse("media/upload.html", {
                "request": request,
                "errors": errors,
                "categories": db.query(Category).all(),
                "tags": db.query(Tag).all(),
                "media_item": None,
                "is_edit": False
            })
        
        # Определяем расширение файла
        extension = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
        name = file.filename
        
        visual_content = None
        
        # Обрабатываем изображение если это изображение
        if file.content_type and file.content_type.startswith('image/'):
            try:
                image = Image.open(io.BytesIO(file_data))
                
                visual_content = VisualContent(
                    data=file_data,
                    name=name,
                    extension=extension,
                    width=image.width,
                    height=image.height,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            except Exception as e:
                errors.append(f"Некорректный формат изображения: {str(e)}")
                logger.error(f"Invalid image format: {str(e)}")
        else:
            # Для не-изображений сохраняем как есть
            visual_content = VisualContent(
                data=file_data,
                name=name,
                extension=extension,
                width=None,
                height=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        
        if errors:
            return templates.TemplateResponse("media/upload.html", {
                "request": request,
                "errors": errors,
                "categories": db.query(Category).all(),
                "tags": db.query(Tag).all(),
                "media_item": None,
                "is_edit": False
            })
        
        db.add(visual_content)
        db.flush()  # Получаем ID
        
        # Добавляем связи с категориями
        for cat_id in category_ids_list:
            db.add(VisualContentCategory(
                visual_content_id=visual_content.id,
                category_id=cat_id
            ))
        
        # Добавляем связи с тегами
        for tag_id in tag_ids_list:
            db.add(VisualContentTag(
                visual_content_id=visual_content.id,
                tag_id=tag_id
            ))
        
        db.commit()
        logger.info(f"Media uploaded successfully: id={visual_content.id}, name={file.filename}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Media upload failed: {str(e)}")
        errors.append(f"Ошибка при загрузке файла: {str(e)}")
        
        return templates.TemplateResponse("media/upload.html", {
            "request": request,
            "errors": errors,
            "categories": db.query(Category).all(),
            "tags": db.query(Tag).all(),
            "media_item": None,
            "is_edit": False
        })
    
    return RedirectResponse(url="/admin/media", status_code=303)


@router.get("/{media_id}/edit", response_class=HTMLResponse)
async def edit_media_form(
        request: Request,
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма редактирования медиа-файла"""
    logger.info(f"Accessing edit form for media: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item:
        logger.warning(f"Media item not found: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Получаем связанные категории и теги
    category_ids = [rel.category_id for rel in media_item.categories] if hasattr(media_item, 'categories') else []
    tag_ids = [rel.tag_id for rel in media_item.tags] if hasattr(media_item, 'tags') else []
    
    categories = db.query(Category).all()
    tags = db.query(Tag).all()
    
    return templates.TemplateResponse("media/upload.html", {
        "request": request,
        "media_item": media_item,
        "selected_category_ids": category_ids,
        "selected_tag_ids": tag_ids,
        "categories": categories,
        "tags": tags,
        "is_edit": True
    })


@router.post("/{media_id}/edit", response_class=HTMLResponse)
async def update_media(
        request: Request,
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        name: Optional[str] = Form(None),
        category_ids: Optional[str] = Form(None),
        tag_ids: Optional[str] = Form(None)
):
    """Обновление метаданных медиа-файла"""
    logger.info(f"Updating media: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item:
        logger.warning(f"Media item not found: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    errors = []
    category_ids_list = [int(x) for x in category_ids.split(",") if x] if category_ids else []
    tag_ids_list = [int(x) for x in tag_ids.split(",") if x] if tag_ids else []
    
    try:
        # Обновляем имя файла
        if name and name.strip():
            media_item.name = name.strip()
        
        media_item.updated_at = datetime.utcnow()
        
        # Удаляем старые связи
        db.query(VisualContentCategory).filter(
            VisualContentCategory.visual_content_id == media_id
        ).delete()
        
        db.query(VisualContentTag).filter(
            VisualContentTag.visual_content_id == media_id
        ).delete()
        
        # Добавляем новые связи с категориями
        for cat_id in category_ids_list:
            db.add(VisualContentCategory(
                visual_content_id=media_id,
                category_id=cat_id
            ))
        
        # Добавляем новые связи с тегами
        for tag_id in tag_ids_list:
            db.add(VisualContentTag(
                visual_content_id=media_id,
                tag_id=tag_id
            ))
        
        db.commit()
        logger.info(f"Media updated successfully: id={media_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update media: {str(e)}")
        errors.append(f"Ошибка при обновлении медиа: {str(e)}")
        
        categories = db.query(Category).all()
        tags = db.query(Tag).all()
        
        return templates.TemplateResponse("media/upload.html", {
            "request": request,
            "errors": errors,
            "media_item": media_item,
            "categories": categories,
            "tags": tags,
            "is_edit": True
        })
    
    return RedirectResponse(url="/admin/media", status_code=303)


@router.post("/{media_id}/delete", response_class=HTMLResponse)
async def delete_media(
        request: Request,
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление медиа-файла"""
    logger.info(f"Deleting media: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item:
        logger.warning(f"Media item not found: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    try:
        # Удаляем связи с категориями и тегами
        db.query(VisualContentCategory).filter(
            VisualContentCategory.visual_content_id == media_id
        ).delete()
        
        db.query(VisualContentTag).filter(
            VisualContentTag.visual_content_id == media_id
        ).delete()
        
        # Удаляем сам файл
        db.delete(media_item)
        db.commit()
        
        logger.info(f"Media deleted successfully: id={media_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete media: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete media: {str(e)}")
    
    return RedirectResponse(url="/admin/media", status_code=303)


@router.post("/{media_id}/duplicate", response_class=HTMLResponse)
async def duplicate_media(
        request: Request,
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Дублирование медиа-файла"""
    logger.info(f"Duplicating media: id={media_id}")
    
    original = db.query(VisualContent).get(media_id)
    if not original:
        logger.warning(f"Media item not found: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    try:
        # Создаем копию
        duplicated = VisualContent(
            data=original.data,
            name=f"{original.name}_copy" if original.name else None,
            extension=original.extension,
            width=original.width,
            height=original.height,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(duplicated)
        db.flush()  # Получаем ID
        
        # Копируем связи с категориями
        original_categories = db.query(VisualContentCategory).filter(
            VisualContentCategory.visual_content_id == media_id
        ).all()
        
        for rel in original_categories:
            db.add(VisualContentCategory(
                visual_content_id=duplicated.id,
                category_id=rel.category_id
            ))
        
        # Копируем связи с тегами
        original_tags = db.query(VisualContentTag).filter(
            VisualContentTag.visual_content_id == media_id
        ).all()
        
        for rel in original_tags:
            db.add(VisualContentTag(
                visual_content_id=duplicated.id,
                tag_id=rel.tag_id
            ))
        
        db.commit()
        logger.info(f"Media duplicated successfully: original_id={media_id}, new_id={duplicated.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to duplicate media: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to duplicate media: {str(e)}")
    
    return RedirectResponse(url="/admin/media", status_code=303)


@router.get("/{media_id}/download")
async def download_media(
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Скачивание медиа-файла"""
    logger.info(f"Downloading media: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item or not media_item.data:
        logger.warning(f"Media item not found or no data: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Определяем MIME тип
    mime_type, _ = mimetypes.guess_type(media_item.name or f"file.{media_item.extension}")
    if not mime_type:
        mime_type = "application/octet-stream"
    
    # Создаем поток для скачивания
    media_stream = io.BytesIO(media_item.data)
    
    return StreamingResponse(
        media_stream,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename={media_item.name or f'file.{media_item.extension}'}"
        }
    )


@router.get("/{media_id}/thumbnail")
async def get_media_thumbnail(
        media_id: int,
        width: int = 300,
        height: int = 200,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Получение thumbnail изображения"""
    logger.info(f"Getting thumbnail for media: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item or not media_item.data:
        logger.warning(f"Media item not found or no data: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Проверяем, что это изображение
    if not media_item.extension or media_item.extension.lower() not in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff']:
        raise HTTPException(status_code=400, detail="Not an image")
    
    try:
        # Генерируем thumbnail
        image = Image.open(io.BytesIO(media_item.data))
        
        # Создаем thumbnail с сохранением пропорций
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        # Создаем новое изображение нужного размера с белым фоном
        thumb = Image.new('RGB', (width, height), (255, 255, 255))
        
        # Вставляем thumbnail в центр
        x = (width - image.width) // 2
        y = (height - image.height) // 2
        thumb.paste(image, (x, y))
        
        # Конвертируем в JPEG
        output = io.BytesIO()
        thumb.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000",  # Кэширование на год
                "Content-Length": str(len(output.getvalue()))
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to generate thumbnail for {media_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate thumbnail")


@router.get("/{media_id}/view")
async def view_media(
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Просмотр медиа-файла в браузере"""
    logger.info(f"Viewing media: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item or not media_item.data:
        logger.warning(f"Media item not found or no data: id={media_id}")
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Определяем MIME тип
    mime_type, _ = mimetypes.guess_type(media_item.name or f"file.{media_item.extension}")
    if not mime_type:
        mime_type = "application/octet-stream"
    
    # Создаем поток
    media_stream = io.BytesIO(media_item.data)
    
    return StreamingResponse(
        media_stream,
        media_type=mime_type,
        headers={
            "Cache-Control": "public, max-age=3600"  # Кэширование на час
        }
    )


@router.get("/{media_id}")
async def get_media_info(
        media_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Получение информации о медиа-файле в JSON формате"""
    logger.info(f"Getting media info: id={media_id}")
    
    media_item = db.query(VisualContent).get(media_id)
    if not media_item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Получаем связанные категории и теги
    categories = []
    if hasattr(media_item, 'categories') and media_item.categories:
        for cat_rel in media_item.categories:
            categories.append({
                'id': cat_rel.category_id,
                'code': db.query(Category).get(cat_rel.category_id).code if db.query(Category).get(cat_rel.category_id) else 'Unknown'
            })
    
    tags = []
    if hasattr(media_item, 'tags') and media_item.tags:
        for tag_rel in media_item.tags:
            tags.append({
                'id': tag_rel.tag_id,
                'code': db.query(Tag).get(tag_rel.tag_id).code if db.query(Tag).get(tag_rel.tag_id) else 'Unknown'
            })
    
    return {
        'id': media_item.id,
        'name': media_item.name,
        'extension': media_item.extension,
        'size': len(media_item.data) if media_item.data else 0,
        'width': media_item.width,
        'height': media_item.height,
        'created_at': media_item.created_at.strftime('%Y-%m-%d %H:%M') if media_item.created_at else 'Unknown',
        'categories': categories,
        'tags': tags
    }


def extract_extension_from_url(url: str) -> str:
    """Извлекает расширение файла из URL"""
    try:
        # Разбираем URL
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path
        
        # Извлекаем расширение из пути
        if '.' in path:
            extension = path.split('.')[-1].lower()
            
            # Проверяем, что это действительно расширение файла
            if extension in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'tiff', 'ico']:
                return extension
        
        return ""
    except Exception as e:
        logger.warning(f"Failed to extract extension from URL {url}: {str(e)}")
        return ""


def get_image_dimensions_from_data(image_data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Получает размеры изображения из бинарных данных"""
    try:
        # Проверяем размер данных (ограничение в 10MB)
        if len(image_data) > 10 * 1024 * 1024:
            logger.warning(f"Image data too large: {len(image_data)} bytes")
            return None, None
        
        # Определяем размеры изображения из данных
        image = Image.open(io.BytesIO(image_data))
        return image.width, image.height
        
    except Exception as e:
        logger.warning(f"Failed to get dimensions from image data: {str(e)}")
        return None, None


@router.post("/update-metadata")
async def update_media_metadata(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Обновляет метаданные всех медиафайлов"""
    logger.info("Starting metadata update for all media files")
    
    try:
        # Получаем все файлы без extension или без размеров
        media_files = db.query(VisualContent).filter(
            or_(
                VisualContent.extension.is_(None),
                VisualContent.extension == "",
                VisualContent.width.is_(None),
                VisualContent.height.is_(None)
            )
        ).all()
        
        updated_count = 0
        errors = []
        
        for media_file in media_files:
            try:
                updated = False
                
                # Если нет расширения, пытаемся извлечь из URL
                if not media_file.extension and media_file.link:
                    extension = extract_extension_from_url(media_file.link)
                    if extension:
                        media_file.extension = extension
                        updated = True
                        logger.info(f"Updated extension for file {media_file.id}: {extension}")
                
                # Если нет размеров и это изображение, пытаемся получить размеры из данных
                if (not media_file.width or not media_file.height) and media_file.data:
                    # Проверяем, что это изображение по расширению
                    if media_file.extension and media_file.extension.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff']:
                        width, height = get_image_dimensions_from_data(media_file.data)
                        if width and height:
                            media_file.width = width
                            media_file.height = height
                            updated = True
                            logger.info(f"Updated dimensions for file {media_file.id}: {width}x{height}")
                
                if updated:
                    media_file.updated_at = datetime.utcnow()
                    updated_count += 1
                    
            except Exception as e:
                error_msg = f"Error updating file {media_file.id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
            
            # Батчинг: коммитим каждые 100 обработанных файлов
            if updated_count % 100 == 0:
                db.commit()
                logger.info(f"Batch commit: processed {updated_count} files")
        
        # Финальный коммит
        db.commit()
        
        logger.info(f"Metadata update completed. Updated {updated_count} files")
        
        # Возвращаем результат
        result = {
            "success": True,
            "updated_count": updated_count,
            "total_files_processed": len(media_files),
            "errors": errors
        }
        
        if errors:
            logger.warning(f"Metadata update completed with {len(errors)} errors")
        
        return result
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update metadata: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update metadata: {str(e)}")


async def bulk_delete_media(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        media_ids: str = Form(...)
):
    """Массовое удаление медиа-файлов"""
    logger.info(f"Bulk deleting media: {media_ids}")
    
    try:
        media_ids_list = [int(x) for x in media_ids.split(",") if x]
        
        if not media_ids_list:
            raise HTTPException(status_code=400, detail="No media IDs provided")
        
        # Удаляем связи
        db.query(VisualContentCategory).filter(
            VisualContentCategory.visual_content_id.in_(media_ids_list)
        ).delete(synchronize_session=False)
        
        db.query(VisualContentTag).filter(
            VisualContentTag.visual_content_id.in_(media_ids_list)
        ).delete(synchronize_session=False)
        
        # Удаляем файлы
        db.query(VisualContent).filter(
            VisualContent.id.in_(media_ids_list)
        ).delete(synchronize_session=False)
        
        db.commit()
        logger.info(f"Bulk delete successful: {len(media_ids_list)} items")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk delete failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Bulk delete failed: {str(e)}")
    
    return RedirectResponse(url="/admin/media", status_code=303)