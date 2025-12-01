from fastapi import APIRouter, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_, func
from typing import Optional, List
from PIL import Image
import io
import requests
from datetime import datetime
import os
import mimetypes
from traffic_arbitration.models import VisualContent, Category, Tag, VisualContentCategory, VisualContentTag
from traffic_arbitration.admin.schemas import VisualContentCreate, VisualContentUpdate, VisualContentResponse
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger
from traffic_arbitration.common.utils import transliterate
import re

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


@router.get("/gallery", response_class=HTMLResponse)
async def list_media(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
        extension: Optional[str] = None,
        category_id: Optional[int] = None,
        tag_id: Optional[int] = None
):
    """Галерея изображений с расширенной фильтрацией"""
    logger.info(f"Listing media: page={page}, per_page={per_page}")
    
    query = db.query(VisualContent)
    
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
    
    total = query.count()
    media_items = query.order_by(desc(VisualContent.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    # Получаем данные для фильтров
    categories = db.query(Category).all()
    tags = db.query(Tag).all()
    extensions = db.query(VisualContent.extension).distinct().filter(
        VisualContent.extension.isnot(None)
    ).all()
    extensions = [ext[0] for ext in extensions if ext[0]]
    
    # Рассчитываем статистику
    total_files = db.query(VisualContent).count()
    images_count = db.query(VisualContent).filter(
        VisualContent.extension.in_(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'])
    ).count()
    this_month = db.query(VisualContent).filter(
        VisualContent.created_at >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ).count()
    storage_used = sum(
        len(item.data) if item.data else 0
        for item in db.query(VisualContent).all()
    )
    
    # Конвертируем байты в MB
    storage_used_mb = round(storage_used / (1024 * 1024), 2)
    
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
            "total": total_files,
            "images": images_count,
            "this_month": this_month,
            "storage_used": f"{storage_used_mb} MB"
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
        media_type=mime_type
    )


@router.post("/bulk/delete", response_class=HTMLResponse)
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