from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from traffic_arbitration.admin.routers import articles, settings, pipeline, media
from traffic_arbitration.admin.dependencies import get_db, verify_credentials
from traffic_arbitration.models import (Article, ContentSource, VisualContent, ExternalArticle,
                                        ExternalArticleLink, ExternalArticlePreview, Category, Tag)
from traffic_arbitration.common.logging import logger

app = FastAPI(title="Traffic Arbitration Admin")
app.mount("/static", StaticFiles(directory="traffic_arbitration/admin/static"), name="static")
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")

logger.info("Starting Admin Panel")

# Подключение роутеров
app.include_router(articles, prefix="/admin/articles", tags=["articles"])
app.include_router(settings, prefix="/admin/settings", tags=["settings"])
app.include_router(pipeline, prefix="/admin/pipeline", tags=["pipeline"])
app.include_router(media, prefix="/admin/media", tags=["media"])


def get_dashboard_stats(db: Session):
    """Получение статистики для дашборда"""

    # Основная статистика
    total_articles = db.query(func.count(Article.id)).scalar() or 0
    active_articles = db.query(func.count(Article.id)).filter(Article.is_active == True).scalar() or 0
    total_sources = db.query(func.count(ContentSource.id)).scalar() or 0
    active_sources = db.query(func.count(ContentSource.id)).filter(ContentSource.is_active == True).scalar() or 0
    total_visual = db.query(func.count(VisualContent.id)).scalar() or 0
    total_categories = db.query(func.count(Category.id)).scalar() or 0
    total_tags = db.query(func.count(Tag.id)).scalar() or 0

    # Внешние статьи и ссылки
    external_links = db.query(func.count(ExternalArticleLink.id)).scalar() or 0
    processed_links = db.query(func.count(ExternalArticleLink.id)).filter(
        ExternalArticleLink.is_processed == True).scalar() or 0
    pending_links = external_links - processed_links

    external_articles = db.query(func.count(ExternalArticle.id)).scalar() or 0
    processed_articles = db.query(func.count(ExternalArticle.id)).filter(
        ExternalArticle.is_processed == True).scalar() or 0
    unprocessed_articles = external_articles - processed_articles

    # Предварительные просмотры статей
    article_previews = db.query(func.count(ExternalArticlePreview.id)).scalar() or 0
    active_previews = db.query(func.count(ExternalArticlePreview.id)).filter(
        ExternalArticlePreview.is_processed == True).scalar() or 0

    return {
        'total_articles': total_articles,
        'active_articles': active_articles,
        'content_sources': total_sources,
        'active_sources': active_sources,
        'visual_content': total_visual,
        'media_categories': total_categories,
        'categories': total_categories,
        'tags': total_tags,
        'external_links': external_links,
        'processed_links': processed_links,
        'pending_links': pending_links,
        'external_articles': external_articles,
        'processed_articles': processed_articles,
        'unprocessed_articles': unprocessed_articles,
        'article_previews': article_previews,
        'active_previews': active_previews
    }


def get_recent_activity(db: Session):
    """Получение недавней активности"""
    # Это упрощенная версия - в реальности здесь будет более сложная логика
    activities = []

    # Добавляем последние статьи как активность
    recent_articles = db.query(Article).order_by(Article.created_at.desc()).limit(3).all()
    for article in recent_articles:
        activities.append({
            'type': 'Article',
            'type_color': 'primary',
            'description': f"Article created: {article.title[:50]}...",
            'status': 'completed',
            'time_ago': f"{article.created_at.strftime('%Y-%m-%d %H:%M')}"
        })

    # Добавляем последние источники
    recent_sources = db.query(ContentSource).order_by(ContentSource.created_at.desc()).limit(2).all()
    for source in recent_sources:
        activities.append({
            'type': 'Source',
            'type_color': 'info',
            'description': f"Source added: {source.name}",
            'status': 'completed',
            'time_ago': f"{source.created_at.strftime('%Y-%m-%d %H:%M')}"
        })

    return sorted(activities, key=lambda x: x['time_ago'], reverse=True)[:5]


# Дашборд (главная страница админки)
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Главная страница админки с дашбордом"""
    logger.info("Accessing admin dashboard")

    # Получаем статистику и активность
    stats = get_dashboard_stats(db)
    recent_activity = get_recent_activity(db)

    # Текущее время
    current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "stats": stats,
        "recent_activity": recent_activity,
        "current_time": current_time
    })


# Главная страница приложения
@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Traffic Arbitration Admin Panel"}
