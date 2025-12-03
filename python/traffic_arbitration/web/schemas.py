from pydantic import BaseModel, computed_field, IPvAnyAddress, HttpUrl, Field, field_validator
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
    uid: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9\-_]+$", description="User ID")
    ip: IPvAnyAddress
    ua: str = Field(..., min_length=10, max_length=2048, description="User Agent")
    url: HttpUrl = Field(..., max_length=2083)
    loc: str = Field(default="ru", pattern=r"^[a-z]{2}$", examples=["ru", "en"], description="Locale code (e.g., 'ru', 'en')")
    w: int = Field(..., gt=0, le=10000, description="Viewport width")
    h: int = Field(..., gt=0, le=10000, description="Viewport height")
    d: float = Field(default=1.0, ge=0.25, le=4.0, description="Device pixel ratio")
    widgets: Dict[str, int] = Field(..., description="{ 'l': qty, 's': qty, 'r': qty, 'i': qty }")

    # --- НОВЫЕ ПОЛЯ ---
    # ID, которые *уже показаны* на *этой странице* (краткосрочная память)
    seen_ids_page: List[int] = Field(default_factory=list, description="Seen preview IDs on current page")
    # ID из cookie (долгосрочная память)
    seen_ids_long_term: List[int] = Field(default_factory=list, description="Long-term seen preview IDs")
    # Код категории (из URL)
    category: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9_-]+$", max_length=50, description="Category code")

    @field_validator('widgets')
    @classmethod
    def validate_widgets(cls, v: Dict[str, int]) -> Dict[str, int]:
        allowed_keys = {'l', 's', 'r', 'i'}
        if not all(k.lower() in allowed_keys for k in v):
            raise ValueError(f"Widget keys must be subset of {allowed_keys}")
        if sum(v.values()) == 0:
            raise ValueError("Must request at least one teaser")
        if any(val < 1 for val in v.values()):
            raise ValueError("All widget quantities must be positive integers")
        if sum(v.values()) > 20:
            raise ValueError("Total number of teasers requested cannot exceed 20")
        return v

    @field_validator('seen_ids_page', 'seen_ids_long_term')
    @classmethod
    def validate_seen_ids(cls, v: List[int]) -> List[int]:
        if len(v) > 200:
            raise ValueError("Maximum 200 seen IDs allowed")
        if not all(isinstance(x, int) and 1 <= x <= 10000000 for x in v):
            raise ValueError("All seen IDs must be integers between 1 and 10,000,000")
        if len(set(v)) != len(v):
            raise ValueError("Seen IDs must be unique")
        return v

    @model_validator(mode='after')
    def validate_full_request(self: 'TeaserRequestSchema') -> 'TeaserRequestSchema':
        page_ids = self.seen_ids_page
        long_ids = self.seen_ids_long_term
        all_seen = set(page_ids) | set(long_ids)
        if len(all_seen) > 500:
            raise ValueError("Total unique seen preview IDs across page and long-term cannot exceed 500")
        return self


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
