from pydantic import BaseModel, computed_field
from datetime import datetime
from typing import Optional, List, Dict


# --- Базовая конфигурация ---

# Использование общего базового класса для схем помогает избежать
# дублирования и обеспечивает консистентность.
class BaseSchema(BaseModel):
    """Базовая схема, от которой будут наследоваться все остальные."""

    class Config:
        # Эта настройка позволяет Pydantic создавать схемы напрямую
        # из ваших ORM-моделей SQLAlchemy (e.g., Article, ArticlePreview).
        from_attributes = True


# --- Схемы для связанных данных ---
# Создание отдельных схем для связанных сущностей — лучшая практика.
# Это позволяет вам точно контролировать, какие данные отдавать по API.

class TagSchema(BaseModel):
    """Схема для тега."""
    id: int
    code: str


class CategorySchema(BaseModel):
    """Схема для категории."""
    id: int
    code: str
    # Примечание: Локализованное поле 'label' лучше формировать
    # в сервисном слое, так как оно зависит от языка запроса.


class GeoSchema(BaseSchema):
    """Схема для гео-локации."""
    id: int
    code: str


# --- Основные схемы для API ---

class ArticlePreviewSchema(BaseModel):
    """
    Pydantic-схема для превью статьи.
    Определяет поля, которые будут возвращены клиенту в JSON.
    Схема была расширена, чтобы предоставлять более полную информацию.
    """
    id: int  # ID самого превью
    article_id: int  # ID статьи, к которой относится превью
    title: Optional[str] = None
    text: Optional[str] = None  # Текст превью (отрывок)
    image: Optional[str] = None  # URL изображения для превью
    is_active: bool
    created_at: datetime  # Дата создания полезна для сортировки на клиенте
    slug: str

    @computed_field
    @property
    def url(self) -> str:
        """
        Генерирует URL для страницы анонса на основе slug.
        """
        # --- ИЗМЕНЕНИЕ: Используем self.slug ---
        return f"/preview/{self.slug}"

    @computed_field
    @property
    def publication_date(self) -> str:
        """Генерирует дату публикации"""
        return f"{self.created_at:%d-%m-%Y}"


class ArticleSchema(BaseModel):
    """
    Pydantic-схема для полной статьи.
    Расширена для включения связанных данных (теги, категории, гео)
    и полной мета-информации.
    """
    id: int
    title: str
    text: str
    is_active: bool
    source_datetime: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Вложенные схемы для связанных данных.
    # FastAPI автоматически преобразует `article.tags` в список объектов `TagSchema`.
    tags: List[TagSchema] = []
    categories: List[CategorySchema] = []
    geo: List[GeoSchema] = []

    # Примечание: поле для URL основного изображения статьи.
    # Его можно добавить, если оно будет формироваться в сервисном слое
    # на основе `article.image`.
    # image_url: Optional[str] = None


# --- Схемы для эндпоинта тизеров /etc ---

class TeaserRequestSchema(BaseModel):
    """
    Схема для валидации входящего запроса на /etc.
    """
    # TODO: ip -> pydantic.IPvAnyAddress; url -> pydantic.HttpUrl
    uid: str
    ip: str
    ua: str
    url: str
    loc: str = "ru"
    w: int
    h: int
    d: Optional[float] = None
    widgets: Dict[str, int]  # { "widget_name": quantity }

    # --- НОВЫЕ ПОЛЯ ---
    # ID, которые *уже показаны* на *этой странице* (краткосрочная память)
    seen_ids_page: List[int] = []
    # ID из cookie (долгосрочная память)
    seen_ids_long_term: List[int] = []
    # Код категории (из URL)
    category: Optional[str] = None


class TeaserResponseSchema(BaseModel):
    """
    Схема для ответа эндпоинта /etc.
    """
    widgets: Dict[str, ArticlePreviewSchema]

    # ID тизеров, которые сервер *только что выдал*.
    # Клиент использует их, чтобы пополнить свой краткосрочный кеш (seen_ids_page).
    newly_served_ids: List[int] = []

    # Обновленный полный список ID для долгосрочного хранения в cookie.
    # Клиент должен **полностью заменить** старый список в cookie на этот.
    seen_ids_long_term: List[int] = []
