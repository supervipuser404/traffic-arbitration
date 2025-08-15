# /home/andrey/Projects/Work/traffic-arbitration/python/traffic_arbitration/web/main.py

from pathlib import Path
from fastapi import FastAPI, Request, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sshtunnel import SSHTunnelForwarder
from contextlib import asynccontextmanager
from traffic_arbitration.common.config import config
from traffic_arbitration.models import Article, ArticlePreview as ArticlePreviewDB
from .cache import news_cache
from .services import NewsRanker
from .schemas import ArticlePreviewSchema, ArticleSchema

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


# Основной маршрут для главной страницы
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", template_context(request))


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


# API-эндпоинт, возвращающий данные новостей
@app.get("/news", response_model=list[ArticlePreviewSchema])
async def get_news(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db)  # Получаем сессию через Depends
):
    """
    Возвращает список превью новостей.
    Данные берутся из кэша и ранжируются.
    """
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


# Пример для эндпоинта полной статьи
@app.get("/articles/{article_id}", response_model=ArticleSchema)
def read_article(article_id: int, db: Session = Depends(get_db)):
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if db_article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return db_article


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
