# /home/andrey/Projects/Work/traffic-arbitration/python/traffic_arbitration/web/main.py

from pathlib import Path
import json
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, Form, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sshtunnel import SSHTunnelForwarder
from contextlib import asynccontextmanager
from traffic_arbitration.common.config import config
from traffic_arbitration.models import Article, ArticlePreview as ArticlePreviewDB
from traffic_arbitration.db.queries import get_article_by_slug_and_category
from .utils import insert_teasers
from .cache import news_cache
# Обновляем импорты сервисов
from .services import NewsRanker, TeaserService
from .schemas import (
    ArticlePreviewSchema,
    ArticleSchema,
    TeaserRequestSchema,
    TeaserResponseSchema
)

BASE_DIR = Path(__file__).resolve().parent

web_config = dict(
    company_name=config.get("company_name", "WhatTheFuck"),
    company_short_name=config.get("company_short_name", "WTF"),
    static=config.get("static", BASE_DIR / "static")
)


def template_context(request: Request) -> dict:
    return {
        "request": request,
        "config": web_config,
    }


# --- Управление состоянием приложения ---
# Создадим класс для хранения глобальных, но управляемых ресурсов,
# таких как SSH-туннель и движок БД.
class AppState:
    ssh_server: SSHTunnelForwarder | None = None
    db_engine: any = None
    SessionLocal: sessionmaker | None = None


app_state = AppState()


# --- Lifespan Manager: Управление ресурсами при старте и остановке ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляет жизненным циклом приложения.
    Код до yield выполняется при старте, после yield - при остановке.
    """
    print("INFO:     Запуск приложения...")
    ssh_config = config.get('ssh', {})
    db_config = config.get('database', {})
    host, port = db_config.get('host'), db_config.get('port')

    # 1. Запускаем SSH-туннель, если он настроен в конфиге
    if ssh_config.get('host'):
        print(f"INFO:     Запуск SSH-туннеля к {ssh_config.get('host')}...")
        server = SSHTunnelForwarder(
            (ssh_config.get('host'), ssh_config.get('port', 22)),
            remote_bind_address=(host, port),
            ssh_username=ssh_config.get('user'),
            ssh_password=ssh_config.get('password'),
            allow_agent=ssh_config.get('allow_agent', False),
        )
        if not ssh_config.get('allow_agent'):
            server.ssh_pkeys = []

        server.start()
        app_state.ssh_server = server
        host, port = '127.0.0.1', server.local_bind_port
        print(f"INFO:     SSH-туннель запущен. БД доступна по адресу {host}:{port}")

    # 2. Создаем ЕДИНЫЙ движок SQLAlchemy для всего приложения
    sqlalchemy_url = (
        f"postgresql://{db_config.get('user')}:{db_config.get('password')}"
        f"@{host}:{port}/{db_config.get('dbname')}"
    )

    engine = create_engine(sqlalchemy_url)
    app_state.db_engine = engine
    app_state.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Приложение готово к работе
    yield

    # --- Код для корректной остановки ---
    print("INFO:     Остановка приложения...")
    if app_state.db_engine:
        app_state.db_engine.dispose()
        print("INFO:     Движок БД остановлен.")
    if app_state.ssh_server:
        app_state.ssh_server.stop()
        print("INFO:     SSH-туннель остановлен.")


# --- Инициализация FastAPI с новым менеджером жизненного цикла ---
app = FastAPI(lifespan=lifespan)

# --- Инициализация сервисов ---
# Создаем единственный экземпляр ранжировщика, передавая ему кэш
news_ranker = NewsRanker(cache=news_cache)
# Создаем сервис тизеров, передавая ему ранжировщик как зависимость
teaser_service = TeaserService(news_ranker=news_ranker)

# Подключаем статику: здесь файлы CSS, JS, изображения и т.п.
app.mount("/static", StaticFiles(directory=web_config["static"]), name="static")

# Указываем директорию с шаблонами
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# --- Эффективная зависимость для получения сессии БД ---
def get_db():
    """
    Эта зависимость быстро создает сессию из единого, уже настроенного
    пула соединений, не создавая каждый раз туннель.
    """
    if not app_state.SessionLocal:
        raise RuntimeError("Фабрика сессий БД не инициализирована. Проверьте lifespan.")

    db = app_state.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- ОБНОВЛЕННЫЙ Маршрут для главной страницы ---
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    """
    Рендерит главную страницу (которая теперь = страница категории).
    """
    context = template_context(request)
    context.update({"category": None})  # Для главной страницы категория = None
    return templates.TemplateResponse("index.html", context)


# --- НОВЫЙ Маршрут для страниц категорий ---
@app.get("/cat/{category}", response_class=HTMLResponse)
async def read_category(request: Request, category: str):
    """
    Рендерит страницу категории. Использует тот же шаблон, что и главная.
    """
    # В будущем здесь может быть проверка, существует ли категория
    # if not category_exists(category):
    #     raise HTTPException(status_code=404, detail="Category not found")

    context = template_context(request)
    context.update({"category": category})
    return templates.TemplateResponse("index.html", context)


@app.get("/fcm.js")
async def fcm_script(request: Request):
    return templates.TemplateResponse(
        "fcm.js", {"request": request, "fcm_token": "ABC123"},
        media_type="application/javascript"
    )


@app.get("/manifest.json")
async def manifest(request: Request):
    return templates.TemplateResponse(
        "manifest.json", template_context(request),
        media_type="application/manifest+json"
    )


# API-эндпоинт, возвращающий данные новостей (оставляем для совместимости)
@app.post("/qaz.html", response_model=list[ArticlePreviewSchema])
async def get_news(
        request_str: str = Form(..., alias="request"),
        b: str = Form(...),
        after: int = Form(0),
        db: Session = Depends(get_db)
):
    """
    Возвращает список превью новостей на основе POST-запроса.
    """
    try:
        # Просто парсим JSON, но пока не используем его для фильтрации
        request_params = json.loads(request_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'request' parameter")

    # Устанавливаем лимит по умолчанию, так как он больше не передается
    limit = 20
    offset = after

    # Запрашиваем из БД объекты SQLAlchemy
    news_previews_db = (
        db.query(ArticlePreviewDB)
        .filter(ArticlePreviewDB.is_active == True)
        .order_by(ArticlePreviewDB.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # FastAPI автоматически преобразует список объектов SQLAlchemy
    # в JSON, соответствующий схеме ArticlePreviewSchema,
    # благодаря `from_attributes = True`.
    return news_previews_db


# --- ЭНДПОИНТ ДЛЯ ТИЗЕРОВ ---
@app.post("/etc", response_model=TeaserResponseSchema)
async def get_teasers(request_data: TeaserRequestSchema = Body(...)):
    """
    API-эндпоинт для запроса тизеров (новостных превью) для виджетов.

    Принимает (в теле запроса):
    - uid: Идентификатор пользователя
    - ip: IP-адрес
    - ua: User-Agent
    - url: URL страницы
    - loc: Локаль (по умолч. "ru")
    - w: Ширина
    - h: Высота
    - d: Плотность (опционально)
    - widgets: Словарь {widget_name: quantity}

    Возвращает:
    - Словарь {widgets: {widget_name: [список ArticlePreviewSchema]}}
    """
    # На данном этапе данные uid, ip, ua и т.д. используются только для
    # валидации, но не для логики. В будущем они понадобятся для ML.
    # Вся логика инкапсулирована в TeaserService.
    # В будущем мы будем расширять TeaserService, а не этот эндпоинт.

    # Передаем только те данные, которые сервису нужны *сейчас*
    response_widgets = teaser_service.get_teasers_for_widgets(
        widgets=request_data.widgets
    )

    # FastAPI/Pydantic автоматически преобразует List[ArticlePreview] (модель)
    # в List[ArticlePreviewSchema] (схему) для JSON-ответа.
    return {"widgets": response_widgets}


@app.get("/{category}/{article_slug}", response_class=HTMLResponse)
def read_article_preview(request: Request, category: str, article_slug: str, db: Session = Depends(get_db)):
    db_article = get_article_by_slug_and_category(db, article_slug, category)
    if db_article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    context = template_context(request)
    context.update({
        "article": db_article,
        "bg": "https://example.com/background.jpg"  # Заглушка для URL
    })
    return templates.TemplateResponse("article.html", context)


@app.get("/{category}/{article_slug}/full", response_class=HTMLResponse)
def read_article_full(request: Request, category: str, article_slug: str, db: Session = Depends(get_db)):
    db_article = get_article_by_slug_and_category(db, article_slug, category)
    if db_article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    # Обрабатываем контент статьи для вставки тизеров
    processed_content = insert_teasers(db_article.content)

    # Создаем копию объекта статьи, чтобы не изменять исходные данные из БД
    from copy import copy
    article_with_teasers = copy(db_article)
    article_with_teasers.content = processed_content

    context = template_context(request)
    context.update({
        "article": article_with_teasers,
        "bg": "https://example.com/background.jpg"  # Заглушка для URL
    })
    return templates.TemplateResponse("article_full.html", context)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
