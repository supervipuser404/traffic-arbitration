from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from traffic_arbitration.models import ExternalArticle, ExternalArticlePreview, ContentSource, ExternalArticleLink
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


# Источники контента
@router.get("/sources", response_class=HTMLResponse)
async def list_sources(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Список источников контента"""
    logger.info("Listing content sources")
    sources = db.query(ContentSource).all()
    return templates.TemplateResponse("pipeline/sources_list.html", {
        "request": request,
        "sources": sources
    })


# Превью статей
@router.get("/previews", response_class=HTMLResponse)
async def list_previews(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Список превью статей"""
    logger.info("Listing article previews")
    previews = db.query(ExternalArticlePreview).all()
    return templates.TemplateResponse("pipeline/previews_list.html", {
        "request": request,
        "previews": previews
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
    logger.info(f"Article fetch initiated for preview: id={preview_id}")
    
    return RedirectResponse(url="/admin/pipeline/previews", status_code=303)


# Внешние статьи
@router.get("/external", response_class=HTMLResponse)
async def list_external_articles(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Список внешних статей"""
    logger.info("Listing external articles")
    external_articles = db.query(ExternalArticle).all()
    return templates.TemplateResponse("pipeline/external_list.html", {
        "request": request,
        "external_articles": external_articles
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