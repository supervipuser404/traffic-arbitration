from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from typing import Optional, List
from datetime import datetime
from traffic_arbitration.models import (
    ExternalArticle, ExternalArticlePreview, ContentSource, ExternalArticleLink,
    Category, ArticleCategory
)
from traffic_arbitration.admin.schemas import (
    ContentSourceCreate, ContentSourceUpdate, ContentSourceResponse,
    ExternalArticleCreate, ExternalArticleUpdate, ExternalArticleResponse,
    ExternalArticlePreviewCreate, ExternalArticlePreviewUpdate, ExternalArticlePreviewResponse,
    ExternalArticleLinkCreate, ExternalArticleLinkUpdate, ExternalArticleLinkResponse
)
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger
import re

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


# ================================
# CONTENT SOURCE CRUD
# ================================

@router.get("/sources", response_class=HTMLResponse)
async def list_sources(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
        is_active: Optional[str] = "all"
):
    """Список источников контента с фильтрацией и поиском"""
    logger.info(f"Listing content sources: page={page}, per_page={per_page}")
    
    query = db.query(ContentSource)
    
    # Фильтрация по статусу
    if is_active != "all":
        query = query.filter(ContentSource.is_active == (is_active == "true"))
    
    # Поиск по имени и домену
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                ContentSource.name.ilike(search_pattern),
                ContentSource.domain.ilike(search_pattern),
                ContentSource.description.ilike(search_pattern)
            )
        )
    
    total = query.count()
    sources = query.order_by(desc(ContentSource.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    return templates.TemplateResponse("pipeline/sources.html", {
        "request": request,
        "sources": sources,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search,
        "is_active": is_active
    })


@router.get("/sources/create", response_class=HTMLResponse)
async def create_source_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания источника контента"""
    logger.info("Accessing create content source form")
    return templates.TemplateResponse("pipeline/sources_form.html", {
        "request": request,
        "source": None,
        "is_edit": False
    })


@router.post("/sources/create", response_class=HTMLResponse)
async def create_source(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        name: str = Form(...),
        source_handler: Optional[str] = Form(None),
        domain: Optional[str] = Form(None),
        aliases: Optional[str] = Form(None),
        old_domains: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        is_active: bool = Form(True)
):
    """Создание нового источника контента"""
    logger.info(f"Creating content source: name={name}")
    
    errors = []
    
    # Валидация
    if not name or not name.strip():
        errors.append("Название источника обязательно")
    
    if source_handler and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', source_handler):
        errors.append("Имя обработчика должно быть корректным Python идентификатором")
    
    if errors:
        return templates.TemplateResponse("pipeline/sources_form.html", {
            "request": request,
            "errors": errors,
            "source": None,
            "is_edit": False,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    try:
        source = ContentSource(
            name=name.strip(),
            source_handler=source_handler.strip() if source_handler else None,
            domain=domain.strip() if domain else None,
            aliases=aliases,
            old_domains=old_domains,
            description=description,
            is_active=is_active,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(source)
        db.commit()
        logger.info(f"Content source created successfully: id={source.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create content source: {str(e)}")
        errors.append(f"Ошибка при создании источника: {str(e)}")
        
        return templates.TemplateResponse("pipeline/sources_form.html", {
            "request": request,
            "errors": errors,
            "source": None,
            "is_edit": False,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    return RedirectResponse(url="/admin/pipeline/sources", status_code=303)


@router.get("/sources/{source_id}/edit", response_class=HTMLResponse)
async def edit_source_form(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма редактирования источника контента"""
    logger.info(f"Accessing edit form for source: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        logger.warning(f"Content source not found: id={source_id}")
        raise HTTPException(status_code=404, detail="Content source not found")
    
    return templates.TemplateResponse("pipeline/sources_form.html", {
        "request": request,
        "source": source,
        "is_edit": True
    })


@router.post("/sources/{source_id}/edit", response_class=HTMLResponse)
async def update_source(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        name: str = Form(...),
        source_handler: Optional[str] = Form(None),
        domain: Optional[str] = Form(None),
        aliases: Optional[str] = Form(None),
        old_domains: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        is_active: bool = Form(True)
):
    """Обновление источника контента"""
    logger.info(f"Updating content source: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        logger.warning(f"Content source not found: id={source_id}")
        raise HTTPException(status_code=404, detail="Content source not found")
    
    errors = []
    
    # Валидация
    if not name or not name.strip():
        errors.append("Название источника обязательно")
    
    if source_handler and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', source_handler):
        errors.append("Имя обработчика должно быть корректным Python идентификатором")
    
    if errors:
        return templates.TemplateResponse("pipeline/sources_form.html", {
            "request": request,
            "errors": errors,
            "source": source,
            "is_edit": True,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    try:
        source.name = name.strip()
        source.source_handler = source_handler.strip() if source_handler else None
        source.domain = domain.strip() if domain else None
        source.aliases = aliases
        source.old_domains = old_domains
        source.description = description
        source.is_active = is_active
        source.updated_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Content source updated successfully: id={source_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update content source: {str(e)}")
        errors.append(f"Ошибка при обновлении источника: {str(e)}")
        
        return templates.TemplateResponse("pipeline/sources_form.html", {
            "request": request,
            "errors": errors,
            "source": source,
            "is_edit": True,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    return RedirectResponse(url="/admin/pipeline/sources", status_code=303)


@router.post("/sources/{source_id}/delete", response_class=HTMLResponse)
async def delete_source(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление источника контента"""
    logger.info(f"Deleting content source: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        logger.warning(f"Content source not found: id={source_id}")
        raise HTTPException(status_code=404, detail="Content source not found")
    
    try:
        # Проверяем, есть ли связанные данные
        external_articles_count = db.query(ExternalArticleLink).filter(
            ExternalArticleLink.source_id == source_id
        ).count()
        
        if external_articles_count > 0:
            error_msg = f"Невозможно удалить источник: есть {external_articles_count} связанных ссылок"
            logger.warning(f"Cannot delete source with related data: {error_msg}")
            # Можно добавить flash message здесь
            return RedirectResponse(url="/admin/pipeline/sources", status_code=303)
        
        db.delete(source)
        db.commit()
        logger.info(f"Content source deleted successfully: id={source_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete content source: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete content source: {str(e)}")
    
    return RedirectResponse(url="/admin/pipeline/sources", status_code=303)


# ================================
# EXTERNAL ARTICLE LINK CRUD
# ================================

@router.get("/links", response_class=HTMLResponse)
async def list_links(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        source_id: Optional[int] = None,
        is_processed: Optional[str] = "all"
):
    """Список ссылок на внешние статьи"""
    logger.info(f"Listing external article links: page={page}")
    
    query = db.query(ExternalArticleLink).join(ContentSource)
    
    # Фильтрация
    if source_id:
        query = query.filter(ExternalArticleLink.source_id == source_id)
    
    if is_processed != "all":
        query = query.filter(ExternalArticleLink.is_processed == (is_processed == "true"))
    
    total = query.count()
    links = query.order_by(desc(ExternalArticleLink.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    sources = db.query(ContentSource).all()
    
    return templates.TemplateResponse("pipeline/links.html", {
        "request": request,
        "links": links,
        "sources": sources,
        "total": total,
        "page": page,
        "per_page": per_page,
        "filters": {
            "source_id": source_id,
            "is_processed": is_processed
        }
    })


@router.get("/links/create", response_class=HTMLResponse)
async def create_link_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания ссылки на внешнюю статью"""
    logger.info("Accessing create external article link form")
    
    sources = db.query(ContentSource).all()
    categories = db.query(Category).all()
    
    return templates.TemplateResponse("pipeline/links_form.html", {
        "request": request,
        "link": None,
        "sources": sources,
        "categories": categories,
        "is_edit": False
    })


@router.post("/links/create", response_class=HTMLResponse)
async def create_link(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        source_id: int = Form(...),
        link: str = Form(...),
        category_ids: Optional[str] = Form(None)
):
    """Создание ссылки на внешнюю статью"""
    logger.info(f"Creating external article link: source_id={source_id}")
    
    errors = []
    category_ids_list = [int(x) for x in category_ids.split(",") if x] if category_ids else []
    
    # Валидация URL
    if not link or not link.strip():
        errors.append("Ссылка обязательна")
    else:
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not url_pattern.match(link.strip()):
            errors.append("Некорректный URL")
    
    # Проверяем уникальность ссылки для источника
    if link.strip():
        existing = db.query(ExternalArticleLink).filter(
            and_(
                ExternalArticleLink.source_id == source_id,
                ExternalArticleLink.link == link.strip()
            )
        ).first()
        if existing:
            errors.append("Эта ссылка уже существует для выбранного источника")
    
    if errors:
        sources = db.query(ContentSource).all()
        categories = db.query(Category).all()
        return templates.TemplateResponse("pipeline/links_form.html", {
            "request": request,
            "errors": errors,
            "link": None,
            "sources": sources,
            "categories": categories,
            "is_edit": False,
            "form_data": {
                "source_id": source_id,
                "link": link,
                "category_ids": category_ids_list
            }
        })
    
    try:
        link_obj = ExternalArticleLink(
            source_id=source_id,
            link=link.strip(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(link_obj)
        db.flush()  # Получаем ID
        
        # Добавляем связи с категориями
        for cat_id in category_ids_list:
            db.execute(
                f"INSERT INTO external_article_link_categories (link_id, category_id) VALUES ({link_obj.id}, {cat_id})"
            )
        
        db.commit()
        logger.info(f"External article link created successfully: id={link_obj.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create external article link: {str(e)}")
        errors.append(f"Ошибка при создании ссылки: {str(e)}")
        
        sources = db.query(ContentSource).all()
        categories = db.query(Category).all()
        return templates.TemplateResponse("pipeline/links_form.html", {
            "request": request,
            "errors": errors,
            "link": None,
            "sources": sources,
            "categories": categories,
            "is_edit": False,
            "form_data": {
                "source_id": source_id,
                "link": link,
                "category_ids": category_ids_list
            }
        })
    
    return RedirectResponse(url="/admin/pipeline/links", status_code=303)


@router.post("/links/{link_id}/delete", response_class=HTMLResponse)
async def delete_link(
        request: Request,
        link_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление ссылки на внешнюю статью"""
    logger.info(f"Deleting external article link: id={link_id}")
    
    link = db.query(ExternalArticleLink).get(link_id)
    if not link:
        logger.warning(f"External article link not found: id={link_id}")
        raise HTTPException(status_code=404, detail="Link not found")
    
    try:
        db.delete(link)
        db.commit()
        logger.info(f"External article link deleted successfully: id={link_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete external article link: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete link: {str(e)}")
    
    return RedirectResponse(url="/admin/pipeline/links", status_code=303)


# ================================
# EXTERNAL ARTICLE PREVIEW CRUD
# ================================

@router.get("/previews", response_class=HTMLResponse)
async def list_previews(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        is_processed: Optional[str] = "all"
):
    """Список превью статей"""
    logger.info(f"Listing article previews: page={page}")
    
    query = db.query(ExternalArticlePreview).join(ExternalArticleLink)
    
    # Фильтрация
    if is_processed != "all":
        query = query.filter(ExternalArticlePreview.is_processed == (is_processed == "true"))
    
    total = query.count()
    previews = query.order_by(desc(ExternalArticlePreview.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    return templates.TemplateResponse("pipeline/previews.html", {
        "request": request,
        "previews": previews,
        "total": total,
        "page": page,
        "per_page": per_page,
        "is_processed": is_processed
    })


@router.post("/previews/{preview_id}/fetch", response_class=HTMLResponse)
async def fetch_full_article(
        request: Request,
        preview_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Загрузить полную статью из превью"""
    logger.info(f"Fetching full article for preview: id={preview_id}")
    
    preview = db.query(ExternalArticlePreview).get(preview_id)
    if not preview:
        logger.warning(f"Preview not found: id={preview_id}")
        raise HTTPException(status_code=404, detail="Preview not found")
    
    # TODO: Реализовать логику загрузки полной статьи
    # Это требует интеграции с scraper'ом
    
    # Временно просто отмечаем как обработанное
    preview.is_processed = True
    db.commit()
    
    logger.info(f"Article fetch initiated for preview: id={preview_id}")
    
    return RedirectResponse(url="/admin/pipeline/previews", status_code=303)


# ================================
# EXTERNAL ARTICLE CRUD
# ================================

@router.get("/external", response_class=HTMLResponse)
async def list_external_articles(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        is_processed: Optional[str] = "all"
):
    """Список внешних статей"""
    logger.info(f"Listing external articles: page={page}")
    
    query = db.query(ExternalArticle).join(ExternalArticleLink).join(ContentSource)
    
    # Фильтрация
    if is_processed != "all":
        query = query.filter(ExternalArticle.is_processed == (is_processed == "true"))
    
    total = query.count()
    external_articles = query.order_by(desc(ExternalArticle.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    
    return templates.TemplateResponse("pipeline/external_articles.html", {
        "request": request,
        "external_articles": external_articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "is_processed": is_processed
    })


@router.get("/external/{external_id}/convert", response_class=HTMLResponse)
async def convert_external_article(
        request: Request,
        external_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания чистовой статьи на основе внешней"""
    logger.info(f"Converting external article: id={external_id}")
    
    external_article = db.query(ExternalArticle).get(external_id)
    if not external_article:
        logger.warning(f"External article not found: id={external_id}")
        raise HTTPException(status_code=404, detail="External article not found")
    
    # Перенаправляем к форме создания статьи с предзаполненными данными
    return RedirectResponse(url=f"/admin/articles/create?external_article_id={external_id}", status_code=303)