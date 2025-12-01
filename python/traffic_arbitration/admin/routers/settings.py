from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func
from typing import Optional, List
import re
from traffic_arbitration.models import Category, Geo, Tag, Locale, CategoryLabel, GeoLabel
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
    
    return templates.TemplateResponse("settings/categories.html", {
        "request": request,
        "categories": categories,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search
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
    
    return templates.TemplateResponse("settings/geo.html", {
        "request": request,
        "geo_items": geo_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search
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
    
    return templates.TemplateResponse("settings/tags.html", {
        "request": request,
        "tags": tags,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search
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
    
    return templates.TemplateResponse("settings/locales.html", {
        "request": request,
        "locales": locales
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
    
    return RedirectResponse(url="/admin/settings/locales", status_code=303)