from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CategoryCreate(BaseModel):
    code: str
    description: Optional[str] = None


class GeoCreate(BaseModel):
    code: str
    description: Optional[str] = None


class TagCreate(BaseModel):
    code: str


class ArticleCreate(BaseModel):
    title: str
    text: str
    parent_id: Optional[int] = None
    external_article_id: Optional[int] = None
    locale_id: int
    image_id: Optional[int] = None
    is_active: bool = True
    source_datetime: Optional[datetime] = None
    categories: List[int] = []
    geo: List[int] = []
    tags: List[int] = []


class ArticleUpdate(ArticleCreate):
    pass


class ArticleResponse(BaseModel):
    id: int
    title: str
    text: str
    parent_id: Optional[int]
    external_article_id: Optional[int]
    locale_id: int
    image_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    source_datetime: Optional[datetime]
    categories: List[CategoryCreate]
    geo: List[GeoCreate]
    tags: List[TagCreate]

    class Config:
        from_attributes = True
