from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from traffic_arbitration.admin.routers import articles, settings, pipeline, media
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

# Дашборд (главная страница админки)
@app.get("/admin")
async def admin_dashboard():
    """Главная страница админки - перенаправляет на список статей"""
    return {"message": "Traffic Arbitration Admin Panel - Dashboard"}

# Главная страница приложения
@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Traffic Arbitration Admin Panel"}
