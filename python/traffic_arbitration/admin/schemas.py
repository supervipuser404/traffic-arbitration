from pydantic import BaseModel, HttpUrl, Field, validator
from typing import Optional, List
from datetime import datetime
import re


class CategoryCreate(BaseModel):
    code: str
    description: Optional[str] = None


class CategoryResponse(BaseModel):
    id: int
    code: str
    description: Optional[str]

    class Config:
        from_attributes = True


class GeoCreate(BaseModel):
    code: str
    description: Optional[str] = None


class GeoResponse(BaseModel):
    id: int
    code: str
    description: Optional[str]

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    code: str


class TagResponse(BaseModel):
    id: int
    code: str

    class Config:
        from_attributes = True


# ContentSource схемы
class ContentSourceBase(BaseModel):
    name: str = Field(..., max_length=256)
    source_handler: Optional[str] = Field(None, max_length=128)
    domain: Optional[str] = Field(None, max_length=256)
    aliases: Optional[str] = None
    old_domains: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Имя источника не может быть пустым')
        return v.strip()

    @validator('source_handler')
    def validate_source_handler(cls, v):
        if v and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', v):
            raise ValueError('Имя обработчика должно быть корректным Python идентификатором')
        return v


class ContentSourceCreate(ContentSourceBase):
    pass


class ContentSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    source_handler: Optional[str] = Field(None, max_length=128)
    domain: Optional[str] = Field(None, max_length=256)
    aliases: Optional[str] = None
    old_domains: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Имя источника не может быть пустым')
        return v.strip() if v else v

    @validator('source_handler')
    def validate_source_handler(cls, v):
        if v and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', v):
            raise ValueError('Имя обработчика должно быть корректным Python идентификатором')
        return v


class ContentSourceResponse(ContentSourceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# VisualContent схемы
class VisualContentBase(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    extension: Optional[str] = Field(None, max_length=16)
    width: Optional[int] = Field(None, ge=0)
    height: Optional[int] = Field(None, ge=0)

    @validator('extension')
    def validate_extension(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9]{1,16}$', v):
            raise ValueError('Расширение файла должно содержать только буквы и цифры')
        return v.lower() if v else v


class VisualContentCreate(VisualContentBase):
    link: Optional[str] = None
    data: Optional[bytes] = None

    @validator('data')
    def validate_file_size(cls, v):
        if v and len(v) > 10 * 1024 * 1024:  # 10MB
            raise ValueError('Размер файла не должен превышать 10MB')
        return v


class VisualContentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    extension: Optional[str] = Field(None, max_length=16)
    width: Optional[int] = Field(None, ge=0)
    height: Optional[int] = Field(None, ge=0)
    categories: Optional[List[int]] = None
    tags: Optional[List[int]] = None

    @validator('extension')
    def validate_extension(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9]{1,16}$', v):
            raise ValueError('Расширение файла должно содержать только буквы и цифры')
        return v.lower() if v else v


class VisualContentResponse(VisualContentBase):
    id: int
    link: Optional[str]
    created_at: datetime
    updated_at: datetime
    categories: List[CategoryResponse] = []
    tags: List[TagResponse] = []

    class Config:
        from_attributes = True


# ExternalArticleLink схемы
class ExternalArticleLinkBase(BaseModel):
    link: str
    is_processed: bool = False

    @validator('link')
    def validate_url(cls, v):
        if not v or not v.strip():
            raise ValueError('Ссылка не может быть пустой')
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not url_pattern.match(v):
            raise ValueError('Некорректный URL')
        return v.strip()


class ExternalArticleLinkCreate(ExternalArticleLinkBase):
    source_id: int
    categories: List[int] = []


class ExternalArticleLinkUpdate(BaseModel):
    link: Optional[str] = None
    is_processed: Optional[bool] = None
    categories: Optional[List[int]] = None

    @validator('link')
    def validate_url(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Ссылка не может быть пустой')
            url_pattern = re.compile(
                r'^https?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            if not url_pattern.match(v):
                raise ValueError('Некорректный URL')
        return v.strip() if v else v


class ExternalArticleLinkResponse(ExternalArticleLinkBase):
    id: int
    source_id: int
    created_at: datetime
    updated_at: datetime
    content_source: ContentSourceResponse
    categories: List[CategoryResponse] = []

    class Config:
        from_attributes = True


# ExternalArticlePreview схемы
class ExternalArticlePreviewBase(BaseModel):
    title: Optional[str] = Field(None, max_length=512)
    text: Optional[str] = None
    image_link: Optional[str] = None
    is_processed: bool = False

    @validator('image_link')
    def validate_image_url(cls, v):
        if v:
            url_pattern = re.compile(
                r'^https?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            if not url_pattern.match(v):
                raise ValueError('Некорректный URL изображения')
        return v


class ExternalArticlePreviewCreate(ExternalArticlePreviewBase):
    link_id: int


class ExternalArticlePreviewUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=512)
    text: Optional[str] = None
    image_link: Optional[str] = None
    is_processed: Optional[bool] = None

    @validator('image_link')
    def validate_image_url(cls, v):
        if v is not None:
            if v:
                url_pattern = re.compile(
                    r'^https?://'  # http:// or https://
                    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                    r'localhost|'  # localhost...
                    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                    r'(?::\d+)?'  # optional port
                    r'(?:/?|[/?]\S+)$', re.IGNORECASE)
                if not url_pattern.match(v):
                    raise ValueError('Некорректный URL изображения')
        return v


class ExternalArticlePreviewResponse(ExternalArticlePreviewBase):
    id: int
    link_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ExternalArticle схемы
class ExternalArticleBase(BaseModel):
    title: str = Field(..., max_length=512)
    text: str
    is_processed: bool = False

    @validator('title')
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError('Заголовок не может быть пустым')
        return v.strip()


class ExternalArticleCreate(ExternalArticleBase):
    link_id: int


class ExternalArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=512)
    text: Optional[str] = None
    is_processed: Optional[bool] = None

    @validator('title')
    def validate_title(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Заголовок не может быть пустым')
        return v.strip() if v else v


class ExternalArticleResponse(ExternalArticleBase):
    id: int
    link_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Locale схемы
class LocaleBase(BaseModel):
    code: str = Field(..., max_length=5)
    name: Optional[str] = Field(None, max_length=50)

    @validator('code')
    def validate_code(cls, v):
        if not re.match(r'^[a-z]{2,5}$', v):
            raise ValueError('Код локали должен содержать только строчные буквы (2-5 символов)')
        return v


class LocaleCreate(LocaleBase):
    pass


class LocaleUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=5)
    name: Optional[str] = Field(None, max_length=50)

    @validator('code')
    def validate_code(cls, v):
        if v is not None and not re.match(r'^[a-z]{2,5}$', v):
            raise ValueError('Код локали должен содержать только строчные буквы (2-5 символов)')
        return v


class LocaleResponse(LocaleBase):
    id: int

    class Config:
        from_attributes = True


# Обновленные Article схемы
class ArticleCreate(BaseModel):
    title: str
    text: str
    slug: Optional[str] = Field(None, max_length=128)
    parent_id: Optional[int] = None
    external_article_id: Optional[int] = None
    locale_id: int
    image_id: Optional[int] = None
    is_active: bool = True
    source_datetime: Optional[datetime] = None
    categories: List[int] = []
    geo: List[int] = []
    tags: List[int] = []

    @validator('title')
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError('Заголовок не может быть пустым')
        return v.strip()

    @validator('slug')
    def validate_slug(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Slug не может быть пустым')
            if not re.match(r'^[a-z0-9-]+$', v):
                raise ValueError('Slug должен содержать только строчные буквы, цифры и дефисы')
            if len(v) > 128:
                raise ValueError('Slug не должен превышать 128 символов')
        return v


class ArticleUpdate(ArticleCreate):
    title: Optional[str] = None
    slug: Optional[str] = None


class ArticleResponse(BaseModel):
    id: int
    title: str
    text: str
    slug: str
    parent_id: Optional[int]
    external_article_id: Optional[int]
    locale_id: int
    image_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    source_datetime: Optional[datetime]
    categories: List[CategoryResponse]
    geo: List[GeoResponse]
    tags: List[TagResponse]

    class Config:
        from_attributes = True
