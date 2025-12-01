
from .articles import router as articles_router
from .settings import router as settings_router
from .pipeline import router as pipeline_router
from .media import router as media_router

# Экспортируем роутеры для удобного импорта
articles = articles_router
settings = settings_router
pipeline = pipeline_router
media = media_router