from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from config import config

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


app = FastAPI()

# Подключаем статику: здесь файлы CSS, JS, изображения и т.п.
app.mount("/static", StaticFiles(directory=web_config["static"]), name="static")

# Указываем директорию с шаблонами
templates = Jinja2Templates(directory=BASE_DIR / "templates")


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
@app.get("/news", response_class=JSONResponse)
async def get_news():
    # Пример данных новостей; в реальном проекте можно получать данные из БД
    news = [
        {
            "title": "Первая новость",
            "date": "2025-04-01",
            "category": "Новости и анонсы",
            "content": "Содержание первой новости."
        },
        {
            "title": "Вторая новость",
            "date": "2025-04-01",
            "category": "Спорт",
            "content": "Содержание второй новости."
        }
    ]
    return {"news": news}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
