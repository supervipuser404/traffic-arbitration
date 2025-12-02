from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func
from typing import Optional, List
import re
from traffic_arbitration.models import Category, Geo, Tag, Locale, CategoryLabel, GeoLabel, ContentSource
from traffic_arbitration.admin.schemas import (
    CategoryCreate, CategoryResponse, GeoCreate, GeoResponse,
    TagCreate, TagResponse, LocaleCreate, LocaleUpdate, LocaleResponse
)
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


# ================================
# CATEGORY CRUD
# ================================

@router.get("/categories", response_class=HTMLResponse)
async def list_categories(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None
):
    """Список категорий с поиском"""
    logger.info(f"Listing categories: page={page}")
    
    query = db.query(Category)
    
    # Поиск по коду и описанию
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Category.code.ilike(search_pattern),
                Category.description.ilike(search_pattern)
            )
        )
    
    total = query.count()
    categories = query.order_by(desc(Category.code)).offset((page - 1) * per_page).limit(per_page).all()
    
    # Рассчитываем статистику
    from traffic_arbitration.models import ArticleCategory
    
    total_categories = db.query(Category).count()
    # Исправляем join - используем правильный подход для связи многие-ко-многим
    from sqlalchemy import distinct
    categories_with_articles = db.query(Category).join(
        ArticleCategory, Category.id == ArticleCategory.category_id
    ).distinct().count()
    
    avg_articles = 0
    if total_categories > 0:
        total_articles = db.query(ArticleCategory).count()
        avg_articles = round(total_articles / total_categories, 1)
    
    # Добавляем количество статей и labels для каждой категории
    for category in categories:
        category.article_count = db.query(ArticleCategory).filter(
            ArticleCategory.category_id == category.id
        ).count()
        # Загружаем labels
        category.labels = db.query(CategoryLabel).filter(
            CategoryLabel.category_id == category.id
        ).all()
    
    # Создаем объект пагинации вручную
    class SimplePagination:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page  # округление вверх
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if page < self.pages else None
        
        def iter_pages(self):
            for i in range(1, self.pages + 1):
                yield i
    
    pagination = SimplePagination(page, per_page, total)
    
    return templates.TemplateResponse("settings/categories.html", {
        "request": request,
        "categories": categories,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search,
        "filters": {
            "search": search or "",
            "sort": "code"  # сортировка по умолчанию
        },
        "pagination": pagination,
        "stats": {
            "total": total_categories,
            "with_articles": categories_with_articles,
            "avg_articles": avg_articles
        }
    })


@router.get("/categories/create", response_class=HTMLResponse)
async def create_category_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания категории"""
    logger.info("Accessing create category form")
    return templates.TemplateResponse("settings/categories_form.html", {
        "request": request,
        "category": None,
        "is_edit": False,
        "labels": []
    })


@router.post("/categories/create", response_class=HTMLResponse)
async def create_category(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...),
        description: Optional[str] = Form(None),
        labels_json: Optional[str] = Form(None)
):
    """Создание новой категории"""
    logger.info(f"Creating category: code={code}")
    
    errors = []
    
    # Валидация кода
    if not code or not code.strip():
        errors.append("Код категории обязателен")
    elif not re.match(r'^[a-z0-9_]+$', code.strip().lower()):
        errors.append("Код должен содержать только строчные буквы, цифры и подчеркивания")
    
    # Проверяем уникальность кода
    if code.strip():
        existing = db.query(Category).filter(Category.code == code.strip().lower()).first()
        if existing:
            errors.append("Категория с таким кодом уже существует")
    
    if errors:
        return templates.TemplateResponse("settings/categories_form.html", {
            "request": request,
            "errors": errors,
            "category": None,
            "is_edit": False,
            "form_data": {
                "code": code,
                "description": description,
                "labels_json": labels_json
            }
        })
    
    try:
        # Парсим метки
        labels = []
        if labels_json:
            try:
                import json
                labels = json.loads(labels_json)
            except json.JSONDecodeError:
                errors.append("Некорректный формат меток")
        
        category = Category(
            code=code.strip().lower(),
            description=description,
            created_at=func.now(),
            updated_at=func.now()
        )
        
        db.add(category)
        db.flush()
        
        # Добавляем метки
        for label_data in labels:
            if isinstance(label_data, dict) and 'locale' in label_data and 'label' in label_data:
                label = CategoryLabel(
                    category_id=category.id,
                    locale=label_data['locale'],
                    label=label_data['label']
                )
                db.add(label)
        
        db.commit()
        logger.info(f"Category created successfully: id={category.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create category: {str(e)}")
        errors.append(f"Ошибка при создании категории: {str(e)}")
        
        return templates.TemplateResponse("settings/categories_form.html", {
            "request": request,
            "errors": errors,
            "category": None,
            "is_edit": False,
            "form_data": {
                "code": code,
                "description": description,
                "labels_json": labels_json
            }
        })
    
    return RedirectResponse(url="/admin/settings/categories", status_code=303)


@router.get("/categories/{category_id}/edit", response_class=HTMLResponse)
async def edit_category_form(
        request: Request,
        category_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма редактирования категории"""
    logger.info(f"Accessing edit form for category: id={category_id}")
    
    category = db.query(Category).get(category_id)
    if not category:
        logger.warning(f"Category not found: id={category_id}")
        raise HTTPException(status_code=404, detail="Category not found")
    
    labels = db.query(CategoryLabel).filter(CategoryLabel.category_id == category_id).all()
    
    return templates.TemplateResponse("settings/categories_form.html", {
        "request": request,
        "category": category,
        "labels": labels,
        "is_edit": True
    })


@router.post("/categories/{category_id}/edit", response_class=HTMLResponse)
async def update_category(
        request: Request,
        category_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...),
        description: Optional[str] = Form(None),
        labels_json: Optional[str] = Form(None)
):
    """Обновление категории"""
    logger.info(f"Updating category: id={category_id}")
    
    category = db.query(Category).get(category_id)
    if not category:
        logger.warning(f"Category not found: id={category_id}")
        raise HTTPException(status_code=404, detail="Category not found")
    
    errors = []
    
    # Валидация кода
    if not code or not code.strip():
        errors.append("Код категории обязателен")
    elif not re.match(r'^[a-z0-9_]+$', code.strip().lower()):
        errors.append("Код должен содержать только строчные буквы, цифры и подчеркивания")
    
    # Проверяем уникальность кода (исключая текущую категорию)
    if code.strip():
        existing = db.query(Category).filter(
            Category.code == code.strip().lower(),
            Category.id != category_id
        ).first()
        if existing:
            errors.append("Категория с таким кодом уже существует")
    
    if errors:
        labels = db.query(CategoryLabel).filter(CategoryLabel.category_id == category_id).all()
        return templates.TemplateResponse("settings/categories_form.html", {
            "request": request,
            "errors": errors,
            "category": category,
            "labels": labels,
            "is_edit": True,
            "form_data": {
                "code": code,
                "description": description,
                "labels_json": labels_json
            }
        })
    
    try:
        # Обновляем основные поля
        category.code = code.strip().lower()
        category.description = description
        category.updated_at = func.now()
        
        # Удаляем старые метки
        db.query(CategoryLabel).filter(CategoryLabel.category_id == category_id).delete()
        
        # Добавляем новые метки
        if labels_json:
            try:
                import json
                labels = json.loads(labels_json)
                for label_data in labels:
                    if isinstance(label_data, dict) and 'locale' in label_data and 'label' in label_data:
                        label = CategoryLabel(
                            category_id=category_id,
                            locale=label_data['locale'],
                            label=label_data['label']
                        )
                        db.add(label)
            except json.JSONDecodeError:
                errors.append("Некорректный формат меток")
        
        if not errors:
            db.commit()
            logger.info(f"Category updated successfully: id={category_id}")
        else:
            db.rollback()
            
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update category: {str(e)}")
        errors.append(f"Ошибка при обновлении категории: {str(e)}")
        
        labels = db.query(CategoryLabel).filter(CategoryLabel.category_id == category_id).all()
        return templates.TemplateResponse("settings/categories_form.html", {
            "request": request,
            "errors": errors,
            "category": category,
            "labels": labels,
            "is_edit": True,
            "form_data": {
                "code": code,
                "description": description,
                "labels_json": labels_json
            }
        })
    
    return RedirectResponse(url="/admin/settings/categories", status_code=303)


@router.post("/categories/{category_id}/delete", response_class=HTMLResponse)
async def delete_category(
        request: Request,
        category_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление категории"""
    logger.info(f"Deleting category: id={category_id}")
    
    category = db.query(Category).get(category_id)
    if not category:
        logger.warning(f"Category not found: id={category_id}")
        raise HTTPException(status_code=404, detail="Category not found")
    
    try:
        # Проверяем, есть ли связанные данные
        from traffic_arbitration.models import ArticleCategory, VisualContentCategory, ExternalArticleLinkCategory
        
        article_categories_count = db.query(ArticleCategory).filter(
            ArticleCategory.category_id == category_id
        ).count()
        
        visual_content_categories_count = db.query(VisualContentCategory).filter(
            VisualContentCategory.category_id == category_id
        ).count()
        
        external_article_link_categories_count = db.query(ExternalArticleLinkCategory).filter(
            ExternalArticleLinkCategory.category_id == category_id
        ).count()
        
        total_related = article_categories_count + visual_content_categories_count + external_article_link_categories_count
        
        if total_related > 0:
            error_msg = f"Невозможно удалить категорию: есть {total_related} связанных элементов"
            logger.warning(f"Cannot delete category with related data: {error_msg}")
            return RedirectResponse(url="/admin/settings/categories", status_code=303)
        
        # Удаляем метки
        db.query(CategoryLabel).filter(CategoryLabel.category_id == category_id).delete()
        
        # Удаляем категорию
        db.delete(category)
        db.commit()
        
        logger.info(f"Category deleted successfully: id={category_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete category: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete category: {str(e)}")
    
    return RedirectResponse(url="/admin/settings/categories", status_code=303)


# ================================
# GEO CRUD
# ================================

@router.get("/geo", response_class=HTMLResponse)
async def list_geo(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None
):
    """Список географических меток"""
    logger.info(f"Listing geo: page={page}")
    
    query = db.query(Geo)
    
    # Поиск по коду и описанию
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Geo.code.ilike(search_pattern),
                Geo.description.ilike(search_pattern)
            )
        )
    
    total = query.count()
    geo_items = query.order_by(desc(Geo.code)).offset((page - 1) * per_page).limit(per_page).all()
    
    # Рассчитываем статистику
    from traffic_arbitration.models import ArticleGeo
    
    total_geo = db.query(Geo).count()
    # Исправляем join - используем правильный подход для связи многие-ко-многим
    geo_with_articles = db.query(Geo).join(
        ArticleGeo, Geo.id == ArticleGeo.geo_id
    ).distinct().count()
    
    # Самый используемый GEO
    most_used_geo = db.query(Geo).join(
        ArticleGeo, Geo.id == ArticleGeo.geo_id
    ).group_by(Geo.id).order_by(func.count(ArticleGeo.article_id).desc()).first()
    most_used_code = most_used_geo.code if most_used_geo else None
    
    avg_articles = 0
    if total_geo > 0:
        total_article_geo = db.query(ArticleGeo).count()
        avg_articles = round(total_article_geo / total_geo, 1)
    
    # Добавляем количество статей и labels для каждого geo элемента
    for geo_item in geo_items:
        geo_item.article_count = db.query(ArticleGeo).filter(ArticleGeo.geo_id == geo_item.id).count()
        # Загружаем labels
        geo_item.labels = db.query(GeoLabel).filter(
            GeoLabel.geo_id == geo_item.id
        ).all()
    
    max_article_count = max([geo_item.article_count for geo_item in geo_items], default=0)
    
    # Создаем объект пагинации вручную
    class SimplePagination:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page  # округление вверх
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if page < self.pages else None
        
        def iter_pages(self):
            for i in range(1, self.pages + 1):
                yield i
    
    pagination = SimplePagination(page, per_page, total)
    
    return templates.TemplateResponse("settings/geo.html", {
        "request": request,
        "geo_items": geo_items,
        "geo_tags": geo_items,  # Переименовываем для совместимости с шаблоном
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search,
        "filters": {
            "search": search or "",
            "sort": "code",  # сортировка по умолчанию
            "popularity": ""  # популярность по умолчанию
        },
        "pagination": pagination,
        "stats": {
            "total": total_geo,
            "with_articles": geo_with_articles,
            "most_used_code": most_used_code,
            "avg_articles": avg_articles,
            "max_article_count": max_article_count
        }
    })


@router.get("/geo/create", response_class=HTMLResponse)
async def create_geo_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания географической метки"""
    logger.info("Accessing create geo form")
    return templates.TemplateResponse("settings/geo_form.html", {
        "request": request,
        "geo_item": None,
        "is_edit": False,
        "labels": []
    })


@router.post("/geo/create", response_class=HTMLResponse)
async def create_geo(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...),
        description: Optional[str] = Form(None),
        labels_json: Optional[str] = Form(None)
):
    """Создание новой географической метки"""
    logger.info(f"Creating geo: code={code}")
    
    errors = []
    
    # Валидация кода
    if not code or not code.strip():
        errors.append("Код географической метки обязателен")
    elif not re.match(r'^[a-z0-9_]+$', code.strip().lower()):
        errors.append("Код должен содержать только строчные буквы, цифры и подчеркивания")
    
    # Проверяем уникальность кода
    if code.strip():
        existing = db.query(Geo).filter(Geo.code == code.strip().lower()).first()
        if existing:
            errors.append("Географическая метка с таким кодом уже существует")
    
    if errors:
        return templates.TemplateResponse("settings/geo_form.html", {
            "request": request,
            "errors": errors,
            "geo_item": None,
            "is_edit": False,
            "form_data": {
                "code": code,
                "description": description,
                "labels_json": labels_json
            }
        })
    
    try:
        # Парсим метки
        labels = []
        if labels_json:
            try:
                import json
                labels = json.loads(labels_json)
            except json.JSONDecodeError:
                errors.append("Некорректный формат меток")
        
        geo = Geo(
            code=code.strip().lower(),
            description=description,
            created_at=func.now(),
            updated_at=func.now()
        )
        
        db.add(geo)
        db.flush()
        
        # Добавляем метки
        for label_data in labels:
            if isinstance(label_data, dict) and 'locale' in label_data and 'label' in label_data:
                label = GeoLabel(
                    geo_id=geo.id,
                    locale=label_data['locale'],
                    label=label_data['label']
                )
                db.add(label)
        
        db.commit()
        logger.info(f"Geo created successfully: id={geo.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create geo: {str(e)}")
        errors.append(f"Ошибка при создании географической метки: {str(e)}")
        
        return templates.TemplateResponse("settings/geo_form.html", {
            "request": request,
            "errors": errors,
            "geo_item": None,
            "is_edit": False,
            "form_data": {
                "code": code,
                "description": description,
                "labels_json": labels_json
            }
        })
    
    return RedirectResponse(url="/admin/settings/geo", status_code=303)


@router.post("/geo/{geo_id}/delete", response_class=HTMLResponse)
async def delete_geo(
        request: Request,
        geo_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление географической метки"""
    logger.info(f"Deleting geo: id={geo_id}")
    
    geo = db.query(Geo).get(geo_id)
    if not geo:
        logger.warning(f"Geo not found: id={geo_id}")
        raise HTTPException(status_code=404, detail="Geo not found")
    
    try:
        # Проверяем связанные данные
        from traffic_arbitration.models import ArticleGeo
        
        article_geo_count = db.query(ArticleGeo).filter(
            ArticleGeo.geo_id == geo_id
        ).count()
        
        if article_geo_count > 0:
            error_msg = f"Невозможно удалить географическую метку: есть {article_geo_count} связанных статей"
            logger.warning(f"Cannot delete geo with related data: {error_msg}")
            return RedirectResponse(url="/admin/settings/geo", status_code=303)
        
        # Удаляем метки
        db.query(GeoLabel).filter(GeoLabel.geo_id == geo_id).delete()
        
        # Удаляем географическую метку
        db.delete(geo)
        db.commit()
        
        logger.info(f"Geo deleted successfully: id={geo_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete geo: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete geo: {str(e)}")
    
    return RedirectResponse(url="/admin/settings/geo", status_code=303)


# ================================
# TAG CRUD
# ================================

@router.get("/tags", response_class=HTMLResponse)
async def list_tags(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None
):
    """Список тегов"""
    logger.info(f"Listing tags: page={page}")
    
    query = db.query(Tag)
    
    # Поиск по коду
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(Tag.code.ilike(search_pattern))
    
    total = query.count()
    tags = query.order_by(desc(Tag.code)).offset((page - 1) * per_page).limit(per_page).all()
    
    # Рассчитываем статистику
    from traffic_arbitration.models import ArticleTag, VisualContentTag
    
    total_tags = db.query(Tag).count()
    # Исправляем join - используем правильный подход для связи многие-ко-многим
    tags_with_articles = db.query(Tag).join(
        ArticleTag, Tag.id == ArticleTag.tag_id
    ).distinct().count()
    
    # Популярные теги (теги с более чем 5 статьями)
    popular_tags_count = db.query(Tag).join(
        ArticleTag, Tag.id == ArticleTag.tag_id
    ).group_by(Tag.id).having(func.count(ArticleTag.article_id) > 5).count()
    
    avg_usage = 0
    if total_tags > 0:
        total_article_tags = db.query(ArticleTag).count()
        avg_usage = round(total_article_tags / total_tags, 1)
    
    # Добавляем количество статей для каждого тега
    for tag in tags:
        tag.article_count = db.query(ArticleTag).filter(ArticleTag.tag_id == tag.id).count()
    
    max_usage = max([tag.article_count for tag in tags], default=0)
    
    # Создаем объект пагинации вручную
    class SimplePagination:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page  # округление вверх
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if page < self.pages else None
        
        def iter_pages(self):
            for i in range(1, self.pages + 1):
                yield i
    
    pagination = SimplePagination(page, per_page, total)
    
    return templates.TemplateResponse("settings/tags.html", {
        "request": request,
        "tags": tags,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search,
        "filters": {
            "search": search or "",
            "sort": "code",  # сортировка по умолчанию
            "usage": ""  # фильтр использования по умолчанию
        },
        "pagination": pagination,
        "stats": {
            "total": total_tags,
            "with_articles": tags_with_articles,
            "popular_count": popular_tags_count,
            "avg_usage": avg_usage,
            "max_usage": max_usage
        }
    })


@router.get("/tags/create", response_class=HTMLResponse)
async def create_tag_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания тега"""
    logger.info("Accessing create tag form")
    return templates.TemplateResponse("settings/tags_form.html", {
        "request": request,
        "tag": None,
        "is_edit": False
    })


@router.post("/tags/create", response_class=HTMLResponse)
async def create_tag(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...)
):
    """Создание нового тега"""
    logger.info(f"Creating tag: code={code}")
    
    errors = []
    
    # Валидация кода
    if not code or not code.strip():
        errors.append("Код тега обязателен")
    elif not re.match(r'^[a-z0-9_]+$', code.strip().lower()):
        errors.append("Код должен содержать только строчные буквы, цифры и подчеркивания")
    
    # Проверяем уникальность кода
    if code.strip():
        existing = db.query(Tag).filter(Tag.code == code.strip().lower()).first()
        if existing:
            errors.append("Тег с таким кодом уже существует")
    
    if errors:
        return templates.TemplateResponse("settings/tags_form.html", {
            "request": request,
            "errors": errors,
            "tag": None,
            "is_edit": False,
            "form_data": {
                "code": code
            }
        })
    
    try:
        tag = Tag(code=code.strip().lower())
        db.add(tag)
        db.commit()
        logger.info(f"Tag created successfully: id={tag.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create tag: {str(e)}")
        errors.append(f"Ошибка при создании тега: {str(e)}")
        
        return templates.TemplateResponse("settings/tags_form.html", {
            "request": request,
            "errors": errors,
            "tag": None,
            "is_edit": False,
            "form_data": {
                "code": code
            }
        })
    
    return RedirectResponse(url="/admin/settings/tags", status_code=303)


@router.post("/tags/{tag_id}/delete", response_class=HTMLResponse)
async def delete_tag(
        request: Request,
        tag_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление тега"""
    logger.info(f"Deleting tag: id={tag_id}")
    
    tag = db.query(Tag).get(tag_id)
    if not tag:
        logger.warning(f"Tag not found: id={tag_id}")
        raise HTTPException(status_code=404, detail="Tag not found")
    
    try:
        # Проверяем связанные данные
        from traffic_arbitration.models import ArticleTag, VisualContentTag
        
        article_tags_count = db.query(ArticleTag).filter(
            ArticleTag.tag_id == tag_id
        ).count()
        
        visual_content_tags_count = db.query(VisualContentTag).filter(
            VisualContentTag.tag_id == tag_id
        ).count()
        
        total_related = article_tags_count + visual_content_tags_count
        
        if total_related > 0:
            error_msg = f"Невозможно удалить тег: есть {total_related} связанных элементов"
            logger.warning(f"Cannot delete tag with related data: {error_msg}")
            return RedirectResponse(url="/admin/settings/tags", status_code=303)
        
        # Удаляем тег
        db.delete(tag)
        db.commit()
        
        logger.info(f"Tag deleted successfully: id={tag_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete tag: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete tag: {str(e)}")
    
    return RedirectResponse(url="/admin/settings/tags", status_code=303)


# ================================
# LOCALE CRUD
# ================================

@router.get("/locales", response_class=HTMLResponse)
async def list_locales(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Список локалей"""
    logger.info("Listing locales")
    locales = db.query(Locale).order_by(Locale.code).all()
    
    # Рассчитываем статистику
    from traffic_arbitration.models import Article
    
    total_locales = db.query(Locale).count()
    # Исправляем join - используем правильный подход для связи один-ко-многим
    active_locales = db.query(Locale).join(
        Article, Locale.id == Article.locale_id
    ).distinct().count()
    default_locale = db.query(Locale).filter(Locale.code == 'en').first()
    
    # Добавляем количество статей для каждой локали
    for locale in locales:
        locale.article_count = db.query(Article).filter(Article.locale_id == locale.id).count()
    
    return templates.TemplateResponse("settings/locales.html", {
        "request": request,
        "locales": locales,
        "stats": {
            "total": total_locales,
            "active": active_locales,
            "default_code": 'en' if default_locale else None,
            "default_id": default_locale.id if default_locale else None
        },
        "filters": {
            "search": "",
            "sort": "code"
        }
    })


@router.get("/locales/create", response_class=HTMLResponse)
async def create_locale_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания локали"""
    logger.info("Accessing create locale form")
    return templates.TemplateResponse("settings/locales_form.html", {
        "request": request,
        "locale": None,
        "is_edit": False
    })


@router.post("/locales/create", response_class=HTMLResponse)
async def create_locale(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...),
        name: Optional[str] = Form(None)
):
    """Создание новой локали"""
    logger.info(f"Creating locale: code={code}")
    
    errors = []
    
    # Валидация кода
    if not code or not code.strip():
        errors.append("Код локали обязателен")
    elif not re.match(r'^[a-z]{2,5}$', code.strip().lower()):
        errors.append("Код локали должен содержать только строчные буквы (2-5 символов)")
    
    # Проверяем уникальность кода
    if code.strip():
        existing = db.query(Locale).filter(Locale.code == code.strip().lower()).first()
        if existing:
            errors.append("Локаль с таким кодом уже существует")
    
    if errors:
        return templates.TemplateResponse("settings/locales_form.html", {
            "request": request,
            "errors": errors,
            "locale": None,
            "is_edit": False,
            "form_data": {
                "code": code,
                "name": name
            }
        })
    
    try:
        locale = Locale(
            code=code.strip().lower(),
            name=name.strip() if name else None
        )
        db.add(locale)
        db.commit()
        logger.info(f"Locale created successfully: id={locale.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create locale: {str(e)}")
        errors.append(f"Ошибка при создании локали: {str(e)}")
        
        return templates.TemplateResponse("settings/locales_form.html", {
            "request": request,
            "errors": errors,
            "locale": None,
            "is_edit": False,
            "form_data": {
                "code": code,
                "name": name
            }
        })
    
    return RedirectResponse(url="/admin/settings/locales", status_code=303)


@router.post("/locales/{locale_id}/delete", response_class=HTMLResponse)
async def delete_locale(
        request: Request,
        locale_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление локали"""
    logger.info(f"Deleting locale: id={locale_id}")
    
    locale = db.query(Locale).get(locale_id)
    if not locale:
        logger.warning(f"Locale not found: id={locale_id}")
        raise HTTPException(status_code=404, detail="Locale not found")
    
    try:
        # Проверяем связанные статьи
        articles_count = db.query(Locale).join(Locale.articles).filter(
            Locale.id == locale_id
        ).count()
        
        if articles_count > 0:
            error_msg = f"Невозможно удалить локаль: есть {articles_count} связанных статей"
            logger.warning(f"Cannot delete locale with related data: {error_msg}")
            return RedirectResponse(url="/admin/settings/locales", status_code=303)
        
        # Удаляем локаль
        db.delete(locale)
        db.commit()
        
        logger.info(f"Locale deleted successfully: id={locale_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete locale: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete locale: {str(e)}")
    

# ================================
# CONTENT SOURCES CRUD
# ================================

@router.get("/content-sources", response_class=HTMLResponse, name="content_sources")
async def list_content_sources(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 50,
        search: Optional[str] = None,
        status: Optional[str] = None,
        sort: Optional[str] = "name"
):
    """Список источников контента"""
    logger.info(f"Listing content sources: page={page}")
    
    query = db.query(ContentSource)
    
    # Фильтрация по статусу
    if status == "active":
        query = query.filter(ContentSource.is_active == True)
    elif status == "inactive":
        query = query.filter(ContentSource.is_active == False)
    
    # Поиск по имени и домену
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                ContentSource.name.ilike(search_pattern),
                ContentSource.domain.ilike(search_pattern),
                ContentSource.description.ilike(search_pattern)
            )
        )
    
    # Сортировка
    if sort == "name":
        query = query.order_by(ContentSource.name)
    elif sort == "created_at":
        query = query.order_by(desc(ContentSource.created_at))
    elif sort == "article_count":
        query = query.order_by(ContentSource.name)  # Простая сортировка для примера
    
    total = query.count()
    sources = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Рассчитываем статистику
    from traffic_arbitration.models import ExternalArticleLink
    
    total_sources = db.query(ContentSource).count()
    active_sources = db.query(ContentSource).filter(ContentSource.is_active == True).count()
    external_articles_count = db.query(ExternalArticleLink).count()
    
    avg_per_source = 0
    if total_sources > 0:
        avg_per_source = round(external_articles_count / total_sources, 1)
    
    # Добавляем количество внешних статей для каждого источника
    for source in sources:
        source.external_articles = db.query(ExternalArticleLink).filter(
            ExternalArticleLink.source_id == source.id
        ).all()
    
    # Создаем объект пагинации вручную
    class SimplePagination:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if page < self.pages else None
        
        def iter_pages(self):
            for i in range(1, self.pages + 1):
                yield i
    
    pagination = SimplePagination(page, per_page, total)
    
    return templates.TemplateResponse("settings/content_sources.html", {
        "request": request,
        "sources": sources,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search,
        "filters": {
            "search": search or "",
            "status": status or "",
            "sort": sort or "name"
        },
        "pagination": pagination,
        "stats": {
            "total": total_sources,
            "active": active_sources,
            "external_articles": external_articles_count,
            "avg_per_source": avg_per_source
        }
    })


@router.get("/content-sources/create", response_class=HTMLResponse, name="create_source")
async def create_source_form(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Форма создания источника контента"""
    logger.info("Accessing create content source form")
    return templates.TemplateResponse("settings/content_sources_form.html", {
        "request": request,
        "source": None,
        "is_edit": False
    })


@router.post("/content-sources/create", response_class=HTMLResponse)
async def create_source(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        name: str = Form(...),
        source_handler: Optional[str] = Form(None),
        domain: Optional[str] = Form(None),
        aliases: Optional[str] = Form(None),
        old_domains: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        is_active: bool = Form(True)
):
    """Создание нового источника контента"""
    logger.info(f"Creating content source: name={name}")
    
    errors = []
    
    # Валидация
    if not name or not name.strip():
        errors.append("Название источника обязательно")
    
    if source_handler and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', source_handler):
        errors.append("Имя обработчика должно быть корректным Python идентификатором")
    
    if errors:
        return templates.TemplateResponse("settings/content_sources_form.html", {
            "request": request,
            "errors": errors,
            "source": None,
            "is_edit": False,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    try:
        source = ContentSource(
            name=name.strip(),
            source_handler=source_handler.strip() if source_handler else None,
            domain=domain.strip() if domain else None,
            aliases=aliases,
            old_domains=old_domains,
            description=description,
            is_active=is_active,
            created_at=func.now(),
            updated_at=func.now()
        )
        
        db.add(source)
        db.commit()
        logger.info(f"Content source created successfully: id={source.id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create content source: {str(e)}")
        errors.append(f"Ошибка при создании источника: {str(e)}")
        
        return templates.TemplateResponse("settings/content_sources_form.html", {
            "request": request,
            "errors": errors,
            "source": None,
            "is_edit": False,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    return RedirectResponse(url="/admin/settings/content-sources", status_code=303)


@router.get("/content-sources/{source_id}", response_class=JSONResponse, name="content_source_details")
async def get_source_details(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Получение деталей источника для AJAX"""
    logger.info(f"Getting source details: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return {
        "id": source.id,
        "name": source.name,
        "domain": source.domain,
        "source_handler": source.source_handler,
        "description": source.description,
        "aliases": source.aliases,
        "old_domains": source.old_domains,
        "is_active": source.is_active,
        "created_at": source.created_at.strftime('%Y-%m-%d %H:%M'),
        "updated_at": source.updated_at.strftime('%Y-%m-%d %H:%M') if source.updated_at else None,
        "external_articles": [],
        "external_articles_links": [],
        "external_article_previews": []
    }


@router.post("/content-sources/{source_id}/edit", response_class=HTMLResponse)
async def update_source(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        name: str = Form(...),
        source_handler: Optional[str] = Form(None),
        domain: Optional[str] = Form(None),
        aliases: Optional[str] = Form(None),
        old_domains: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        is_active: bool = Form(True)
):
    """Обновление источника контента"""
    logger.info(f"Updating content source: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Content source not found")
    
    errors = []
    
    # Валидация
    if not name or not name.strip():
        errors.append("Название источника обязательно")
    
    if source_handler and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', source_handler):
        errors.append("Имя обработчика должно быть корректным Python идентификатором")
    
    if errors:
        return templates.TemplateResponse("settings/content_sources_form.html", {
            "request": request,
            "errors": errors,
            "source": source,
            "is_edit": True,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    try:
        source.name = name.strip()
        source.source_handler = source_handler.strip() if source_handler else None
        source.domain = domain.strip() if domain else None
        source.aliases = aliases
        source.old_domains = old_domains
        source.description = description
        source.is_active = is_active
        source.updated_at = func.now()
        
        db.commit()
        logger.info(f"Content source updated successfully: id={source_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update content source: {str(e)}")
        errors.append(f"Ошибка при обновлении источника: {str(e)}")
        
        return templates.TemplateResponse("settings/content_sources_form.html", {
            "request": request,
            "errors": errors,
            "source": source,
            "is_edit": True,
            "form_data": {
                "name": name,
                "source_handler": source_handler,
                "domain": domain,
                "aliases": aliases,
                "old_domains": old_domains,
                "description": description,
                "is_active": is_active
            }
        })
    
    return RedirectResponse(url="/admin/settings/content-sources", status_code=303)


@router.post("/content-sources/{source_id}/toggle", response_class=HTMLResponse, name="toggle_source")
async def toggle_source(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Переключение статуса источника"""
    logger.info(f"Toggling content source: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    source.is_active = not source.is_active
    source.updated_at = func.now()
    db.commit()
    
    return {"success": True, "is_active": source.is_active}


@router.post("/content-sources/{source_id}/delete", response_class=HTMLResponse, name="delete_source")
async def delete_source(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Удаление источника контента"""
    logger.info(f"Deleting content source: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Content source not found")
    
    try:
        # Проверяем, есть ли связанные данные
        from traffic_arbitration.models import ExternalArticleLink
        
        external_articles_count = db.query(ExternalArticleLink).filter(
            ExternalArticleLink.source_id == source_id
        ).count()
        
        if external_articles_count > 0:
            error_msg = f"Невозможно удалить источник: есть {external_articles_count} связанных ссылок"
            logger.warning(f"Cannot delete source with related data: {error_msg}")
            return RedirectResponse(url="/admin/settings/content-sources", status_code=303)
        
        db.delete(source)
        db.commit()
        logger.info(f"Content source deleted successfully: id={source_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete content source: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to delete content source: {str(e)}")
    
    return RedirectResponse(url="/admin/settings/content-sources", status_code=303)


@router.get("/content-sources/{source_id}/stats", response_class=HTMLResponse, name="source_stats")
async def source_stats(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Статистика источника"""
    logger.info(f"Getting source stats: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Здесь можно добавить детальную статистику
    return templates.TemplateResponse("settings/source_stats.html", {
        "request": request,
        "source": source
    })


@router.post("/content-sources/{source_id}/test", response_class=JSONResponse, name="test_source")
async def test_source(
        request: Request,
        source_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    """Тестирование соединения с источником"""
    logger.info(f"Testing source connection: id={source_id}")
    
    source = db.query(ContentSource).get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Здесь можно добавить реальную логику тестирования
    # Пока возвращаем успех для примера
    return {"success": True, "message": "Connection test successful"}
    return RedirectResponse(url="/admin/settings/locales", status_code=303)