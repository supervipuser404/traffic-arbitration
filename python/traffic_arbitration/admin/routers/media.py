from fastapi import APIRouter, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from PIL import Image
import io
from datetime import datetime
from traffic_arbitration.models import VisualContent
from traffic_arbitration.admin.schemas import VisualContentCreate, VisualContentUpdate, VisualContentResponse
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


@router.get("/", response_class=HTMLResponse)
async def list_media(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50
):
    """Галерея изображений"""
    logger.info(f"Listing media: page={page}, per_page={per_page}")
    
    query = db.query(VisualContent).order_by(desc(VisualContent.created_at))
    total = query.count()
    media_items = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return templates.TemplateResponse("media/gallery.html", {
        "request": request,
        "media_items": media_items,
        "total": total,
        "page": page,
        "per_page": per_page
    })


@router.post("/upload", response_class=HTMLResponse)
async def upload_media(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        file: UploadFile = File(...)
):
    """Загрузка новых файлов"""
    logger.info(f"Uploading media file: {file.filename}")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    try:
        # Читаем файл
        file_data = await file.read()
        
        # Обрабатываем изображение если это изображение
        if file.content_type and file.content_type.startswith('image/'):
            image = Image.open(io.BytesIO(file_data))
            extension = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
            
            visual_content = VisualContent(
                data=file_data,
                name=file.filename,
                extension=extension,
                width=image.width,
                height=image.height,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        else:
            # Для не-изображений сохраняем как есть
            extension = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
            visual_content = VisualContent(
                data=file_data,
                name=file.filename,
                extension=extension,
                width=None,
                height=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        
        db.add(visual_content)
        db.commit()
        
        logger.info(f"Media uploaded successfully: id={visual_content.id}, name={file.filename}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Media upload failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to upload file: {str(e)}")
    
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
        db.delete(media_item)
        db.commit()
        logger.info(f"Media deleted successfully: id={media_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete media: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete media: {str(e)}")
    
    return RedirectResponse(url="/admin/media", status_code=303)