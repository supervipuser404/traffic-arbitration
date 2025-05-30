from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from traffic_arbitration.admin.routes import router
from traffic_arbitration.common.logging import logger

app = FastAPI(title="Traffic Arbitration Admin")
app.mount("/static", StaticFiles(directory="traffic_arbitration/admin/static"), name="static")
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")

logger.info("Starting Admin Panel")

app.include_router(router, prefix="/admin", tags=["admin"])


@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Traffic Arbitration Admin Panel"}
