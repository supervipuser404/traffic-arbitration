from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sshtunnel import SSHTunnelForwarder
from contextlib import asynccontextmanager
from traffic_arbitration.common.config import config
from traffic_arbitration.db.queries import get_article_by_slug
from .utils import inject_in_article_teasers
from .cache import news_cache
from .services import NewsRanker, TeaserService
from .schemas import (
    TeaserRequestSchema,
    TeaserResponseSchema
)

BASE_DIR = Path(__file__).resolve().parent

web_config = dict(
    company_name=config.get("company_name", "WhatTheFuck"),
    company_short_name=config.get("company_short_name", "WTF"),
    static=config.get("static", BASE_DIR / "static"),
    show_preview_text=config.get("show_preview_text", False)
)


def template_context(request: Request) -> dict:
    return {
        "request": request,
        "config": web_config,
    }


# --- Управление состоянием приложения ---
class AppState:
    ssh_server: SSHTunnelForwarder | None = None
    db_engine: any = None
    SessionLocal: sessionmaker | None = None


app_state = AppState()


# --- Lifespan Manager ---
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

    # Добавлен pool_pre_ping=True
    # Это предотвратит зависание при "мертвых" соединениях в пуле
    # (например, если SSH-туннель "отвалился" по таймауту).
    engine = create_engine(sqlalchemy_url, pool_pre_ping=True)

    app_state.db_engine = engine
    app_state.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # 3. Внедряем session_maker в кэш и запускаем *первое* обновление
    print("INFO:     Внедрение сессии в кэш...")
    news_cache.set_session_maker(app_state.SessionLocal)

    print("INFO:     Запуск *первого* (синхронного) обновления кэша...")
    try:
        news_cache.force_update()
        print("INFO:     Кэш успешно обновлен.")
    except Exception as e:
        print(f"ERROR:    Не удалось выполнить первое обновление кэша: {e}")
        # В зависимости от логики, здесь можно либо упасть,
        # либо продолжить с пустым кэшем.

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


# --- Маршруты ---

@app.get("/", response_class=HTMLResponse)
@app.get("/cat/{category}", response_class=HTMLResponse)
async def read_index(request: Request, category: Optional[str] = None):
    context = template_context(request)
    context.update({"category": category})
    return templates.TemplateResponse("index.html", context)


@app.get("/preview/{slug}", response_class=HTMLResponse)
async def read_preview(request: Request, slug: str, db: Session = Depends(get_db)):
    """
    Страница анонса материала.
    """
    db_article = get_article_by_slug(db, slug)
    if db_article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    context = template_context(request)
    category = db_article.categories[0].code if db_article.categories else None

    context.update({
        "article": db_article,
        "category": category,
        "image_obj": db_article.image
    })
    return templates.TemplateResponse("preview.html", context)


@app.get("/article/{slug}", response_class=HTMLResponse)
async def read_article_page(request: Request, slug: str, db: Session = Depends(get_db)):
    """
    Полная страница статьи.
    Текст статьи обрабатывается для вставки тизеров.
    """
    db_article = get_article_by_slug(db, slug)
    if db_article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    # Внедряем плейсхолдеры тизеров в текст
    processed_content = inject_in_article_teasers(db_article.text)

    # Создаем копию, чтобы не мутировать объект сессии (хотя мы только читаем)
    # Но лучше использовать поле context, чтобы не трогать объект БД

    context = template_context(request)
    category = db_article.categories[0].code if db_article.categories else None

    context.update({
        "article": db_article,
        "article_content_with_teasers": processed_content,  # Передаем обработанный текст отдельно
        "category": category,
        "image_obj": db_article.image
    })
    return templates.TemplateResponse("article.html", context)


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


@app.post("/etc", response_model=TeaserResponseSchema)
async def get_teasers(request_data: TeaserRequestSchema = Body(...)):
    """
    API-эндпоинт для запроса тизеров (новостных превью) для виджетов
    с учетом дедупликации.

    Принимает (в теле запроса):
    - TeaserRequestSchema (uid, ip, ua, widgets, ...)
    - seen_ids_page: ID, уже показанные на этой странице
    - seen_ids_long_term: ID из cookie (долгосрочная память)

    Возвращает (TeaserResponseSchema):
    - widgets: Словарь {widget_name: ArticlePreviewSchema}
    - newly_served_ids: Список ID, которые клиент должен добавить в cookie
    """
    # Вся логика инкапсулирована в TeaserService.
    # Передаем *весь* объект запроса в сервис.
    # print(f"{request_data=}")
    response_data = teaser_service.get_teasers_for_widgets(
        request_data=request_data
    )
    # print(f"{response_data=}")
    # Сервис уже возвращает словарь,
    # соответствующий TeaserResponseSchema ({"widgets": ..., "newly_served_ids": ...})
    return response_data


if __name__ == "__main__":
    import uvicorn

    # Обратите внимание: reload=True может вызывать
    # многократный запуск lifespan.
    # Для production используйте gunicorn (как у вас и настроено).
    uvicorn.run("traffic_arbitration.web.main:app", reload=True, host="0.0.0.0", port=8000)
