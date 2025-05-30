from fastapi import APIRouter, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List
from datetime import datetime, timedelta
from PIL import Image
import io
import requests
from traffic_arbitration.models import Article, ExternalArticle, Locale, Category, Geo, Tag, VisualContent, \
    ExternalArticlePreview, ContentSource, ExternalArticleLink, ArticleCategory, ArticleGeo, ArticleTag
from .dependencies import verify_credentials, get_db
from .schemas import ArticleCreate, ArticleResponse, CategoryCreate, GeoCreate, TagCreate
from traffic_arbitration.common.logging import logger

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


@router.get("/", response_class=HTMLResponse)
async def list_articles(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        page: int = 1,
        per_page: int = 100,
        sort: str = "created_at",
        order: str = "desc",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        preset: Optional[str] = None,
        source_id: Optional[int] = None,
        locale_id: Optional[int] = None,
        is_active: Optional[str] = "all",
        category_ids: Optional[str] = None,
        geo_ids: Optional[str] = None,
        tag_ids: Optional[str] = None
):
    logger.info(f"Listing articles: page={page}, per_page={per_page}, sort={sort}, order={order}")
    category_ids_list = [int(x) for x in category_ids.split(",") if x] if category_ids else []
    geo_ids_list = [int(x) for x in geo_ids.split(",") if x] if geo_ids else []
    tag_ids_list = [int(x) for x in tag_ids.split(",") if x] if tag_ids else []

    query = db.query(Article).join(Locale)
    if date_from or date_to or preset:
        if preset == "today":
            date_from = datetime.utcnow().date().isoformat()
            date_to = date_from
        elif preset == "yesterday":
            date_from = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
            date_to = date_from
        elif preset == "7days":
            date_from = (datetime.utcnow().date() - timedelta(days=7)).isoformat()
            date_to = datetime.utcnow().date().isoformat()
        elif preset == "30days":
            date_from = (datetime.utcnow().date() - timedelta(days=30)).isoformat()
            date_to = datetime.utcnow().date().isoformat()
        if date_from:
            query = query.filter(Article.created_at >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.filter(Article.created_at <= datetime.fromisoformat(date_to) + timedelta(days=1))
    if source_id:
        query = query.join(ExternalArticle).join(ExternalArticleLink).join(ContentSource).filter(
            ContentSource.id == source_id)
    if locale_id:
        query = query.filter(Article.locale_id == locale_id)
    if is_active != "all":
        query = query.filter(Article.is_active == (is_active == "true"))
    if category_ids_list:
        query = query.join(ArticleCategory).filter(ArticleCategory.category_id.in_(category_ids_list))
    if geo_ids_list:
        query = query.join(ArticleGeo).filter(ArticleGeo.geo_id.in_(geo_ids_list))
    if tag_ids_list:
        query = query.join(ArticleTag).filter(ArticleTag.tag_id.in_(tag_ids_list))

    if sort in ["created_at", "updated_at", "title", "source_datetime", "is_active"]:
        order_by = getattr(Article, sort)
        if order == "desc":
            order_by = order_by.desc()
        query = query.order_by(order_by)

    total = query.count()
    articles = query.offset((page - 1) * per_page).limit(per_page).all()
    sources = db.query(ContentSource).all()
    locales = db.query(Locale).all()
    categories = db.query(Category).all()
    geo_tags = db.query(Geo).all()
    tags = db.query(Tag).all()

    return templates.TemplateResponse("articles/list.html", {
        "request": request,
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "sources": sources,
        "locales": locales,
        "categories": categories,
        "geo_tags": geo_tags,
        "tags": tags,
        "sort": sort,
        "order": order,
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "preset": preset,
            "source_id": source_id,
            "locale_id": locale_id,
            "is_active": is_active,
            "category_ids": category_ids_list,
            "geo_ids": geo_ids_list,
            "tag_ids": tag_ids_list
        }
    })


@router.get("/create", response_class=HTMLResponse)
async def create_article_form(request: Request, db: Session = Depends(get_db),
                              username: str = Depends(verify_credentials)):
    logger.info("Accessing create article form")
    locales = db.query(Locale).all()
    sources = db.query(ContentSource).all()
    categories = db.query(Category).all()
    geo_tags = db.query(Geo).all()
    tags = db.query(Tag).all()
    articles = db.query(Article).all()
    external_articles = db.query(ExternalArticle).all()
    return templates.TemplateResponse("articles/form.html", {
        "request": request,
        "locales": locales,
        "sources": sources,
        "categories": categories,
        "geo_tags": geo_tags,
        "tags": tags,
        "articles": articles,
        "external_articles": external_articles,
        "article": None,
        "external_article": None
    })


@router.post("/create", response_class=HTMLResponse)
async def create_article(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        title: str = Form(...),
        text: str = Form(...),
        locale_id: int = Form(...),
        parent_id: Optional[int] = Form(None),
        external_article_id: Optional[int] = Form(None),
        is_active: bool = Form(True),
        source_datetime: Optional[str] = Form(None),
        image_url: Optional[str] = Form(None),
        image_file: Optional[UploadFile] = File(None),
        category_ids: Optional[str] = Form(None),
        geo_ids: Optional[str] = Form(None),
        tag_ids: Optional[str] = Form(None)
):
    logger.info(f"Creating article: title={title}")
    errors = []
    image_id = None
    category_ids_list = [int(x) for x in category_ids.split(",") if x] if category_ids else []
    geo_ids_list = [int(x) for x in geo_ids.split(",") if x] if geo_ids else []
    tag_ids_list = [int(x) for x in tag_ids.split(",") if x] if tag_ids else []

    if image_file and image_file.filename:
        try:
            image_data = await image_file.read()
            image = Image.open(io.BytesIO(image_data))
            extension = image_file.filename.split(".")[-1].lower()
            name = image_file.filename
            visual_content = VisualContent(
                data=image_data,
                name=name,
                extension=extension,
                width=image.width,
                height=image.height,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(visual_content)
            db.flush()
            image_id = visual_content.id
            logger.info(f"Image file uploaded: id={image_id}, name={name}")
        except Exception as e:
            errors.append(f"Failed to process image file: {str(e)}")
            logger.error(f"Image file processing failed: {str(e)}")
    elif image_url:
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            image_data = response.content
            image = Image.open(io.BytesIO(image_data))
            extension = image_url.split(".")[-1].lower() if "." in image_url else "jpg"
            name = image_url.split("/")[-1]
            existing_visual = db.query(VisualContent).filter(VisualContent.link == image_url).first()
            if not existing_visual:
                visual_content = VisualContent(
                    link=image_url,
                    data=image_data,
                    name=name,
                    extension=extension,
                    width=image.width,
                    height=image.height,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(visual_content)
                db.flush()
                image_id = visual_content.id
                logger.info(f"Image from URL uploaded: id={image_id}, url={image_url}")
            else:
                image_id = existing_visual.id
                logger.info(f"Existing image found: id={image_id}, url={image_url}")
        except Exception as e:
            errors.append(f"Failed to load image from URL: {str(e)}")
            logger.error(f"Image URL loading failed: {str(e)}")

    if external_article_id:
        external_article = db.query(ExternalArticle).get(external_article_id)
        if external_article:
            external_article.is_processed = True
            if not image_id:
                preview = db.query(ExternalArticlePreview).filter(
                    ExternalArticlePreview.link_id == external_article.link_id).first()
                if preview and preview.image_link:
                    visual_content = db.query(VisualContent).filter(VisualContent.link == preview.image_link).first()
                    if visual_content:
                        image_id = visual_content.id
                        logger.info(f"Image from preview used: id={image_id}")
        else:
            external_article = None
    else:
        external_article = None

    article = Article(
        title=title,
        text=text,
        parent_id=parent_id,
        external_article_id=external_article_id,
        locale_id=locale_id,
        image_id=image_id,
        is_active=is_active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        source_datetime=datetime.fromisoformat(source_datetime) if source_datetime else None
    )
    db.add(article)
    db.flush()

    for cat_id in category_ids_list:
        db.add(ArticleCategory(article_id=article.id, category_id=cat_id))
    for geo_id in geo_ids_list:
        db.add(ArticleGeo(article_id=article.id, geo_id=geo_id))
    for tag_id in tag_ids_list:
        db.add(ArticleTag(article_id=article.id, tag_id=tag_id))

    try:
        db.commit()
        logger.info(f"Article created successfully: id={article.id}")
    except Exception as e:
        db.rollback()
        errors.append(f"Failed to save article: {str(e)}")
        logger.error(f"Article creation failed: {str(e)}")

    if errors:
        locales = db.query(Locale).all()
        sources = db.query(ContentSource).all()
        categories = db.query(Category).all()
        geo_tags = db.query(Geo).all()
        tags = db.query(Tag).all()
        articles = db.query(Article).all()
        external_articles = db.query(ExternalArticle).all()
        return templates.TemplateResponse("articles/form.html", {
            "request": request,
            "errors": errors,
            "article": article,
            "locales": locales,
            "sources": sources,
            "categories": categories,
            "geo_tags": geo_tags,
            "tags": tags,
            "articles": articles,
            "external_articles": external_articles,
            "external_article": external_article
        })

    return RedirectResponse(url="/admin", status_code=303)


@router.get("/{article_id}/edit", response_class=HTMLResponse)
async def edit_article_form(
        request: Request,
        article_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    logger.info(f"Accessing edit form for article: id={article_id}")
    article = db.query(Article).get(article_id)
    if not article:
        logger.warning(f"Article not found: id={article_id}")
        raise HTTPException(status_code=404, detail="Article not found")
    locales = db.query(Locale).all()
    sources = db.query(ContentSource).all()
    categories = db.query(Category).all()
    geo_tags = db.query(Geo).all()
    tags = db.query(Tag).all()
    articles = db.query(Article).filter(Article.id != article_id).all()
    external_articles = db.query(ExternalArticle).all()
    return templates.TemplateResponse("articles/form.html", {
        "request": request,
        "article": article,
        "locales": locales,
        "sources": sources,
        "categories": categories,
        "geo_tags": geo_tags,
        "tags": tags,
        "articles": articles,
        "external_articles": external_articles,
        "external_article": article.external_article
    })


@router.post("/{article_id}/edit", response_class=HTMLResponse)
async def update_article(
        request: Request,
        article_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        title: str = Form(...),
        text: str = Form(...),
        locale_id: int = Form(...),
        parent_id: Optional[int] = Form(None),
        external_article_id: Optional[int] = Form(None),
        is_active: bool = Form(True),
        source_datetime: Optional[str] = Form(None),
        image_url: Optional[str] = Form(None),
        image_file: Optional[UploadFile] = File(None),
        category_ids: Optional[str] = Form(None),
        geo_ids: Optional[str] = Form(None),
        tag_ids: Optional[str] = Form(None)
):
    logger.info(f"Updating article: id={article_id}")
    article = db.query(Article).get(article_id)
    if not article:
        logger.warning(f"Article not found: id={article_id}")
        raise HTTPException(status_code=404, detail="Article not found")

    errors = []
    image_id = article.image_id
    category_ids_list = [int(x) for x in category_ids.split(",") if x] if category_ids else []
    geo_ids_list = [int(x) for x in geo_ids.split(",") if x] if geo_ids else []
    tag_ids_list = [int(x) for x in tag_ids.split(",") if x] if tag_ids else []

    if image_file and image_file.filename:
        try:
            image_data = await image_file.read()
            image = Image.open(io.BytesIO(image_data))
            extension = image_file.filename.split(".")[-1].lower()
            name = image_file.filename
            visual_content = VisualContent(
                data=image_data,
                name=name,
                extension=extension,
                width=image.width,
                height=image.height,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(visual_content)
            db.flush()
            image_id = visual_content.id
            logger.info(f"New image file uploaded: id={image_id}")
        except Exception as e:
            errors.append(f"Failed to process image file: {str(e)}")
            logger.error(f"Image file processing failed: {str(e)}")
    elif image_url:
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            image_data = response.content
            image = Image.open(io.BytesIO(image_data))
            extension = image_url.split(".")[-1].lower() if "." in image_url else "jpg"
            name = image_url.split("/")[-1]
            existing_visual = db.query(VisualContent).filter(VisualContent.link == image_url).first()
            if not existing_visual:
                visual_content = VisualContent(
                    link=image_url,
                    data=image_data,
                    name=name,
                    extension=extension,
                    width=image.width,
                    height=image.height,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(visual_content)
                db.flush()
                image_id = visual_content.id
                logger.info(f"New image from URL uploaded: id={image_id}")
            else:
                image_id = existing_visual.id
                logger.info(f"Existing image found: id={image_id}")
        except Exception as e:
            errors.append(f"Failed to load image from URL: {str(e)}")
            logger.error(f"Image URL loading failed: {str(e)}")

    article.title = title
    article.text = text
    article.locale_id = locale_id
    article.parent_id = parent_id
    article.external_article_id = external_article_id
    article.is_active = is_active
    article.image_id = image_id
    article.updated_at = datetime.utcnow()
    article.source_datetime = datetime.fromisoformat(source_datetime) if source_datetime else None

    db.query(ArticleCategory).filter(ArticleCategory.article_id == article_id).delete()
    db.query(ArticleGeo).filter(ArticleGeo.article_id == article_id).delete()
    db.query(ArticleTag).filter(ArticleTag.article_id == article_id).delete()

    for cat_id in category_ids_list:
        db.add(ArticleCategory(article_id=article.id, category_id=cat_id))
    for geo_id in geo_ids_list:
        db.add(ArticleGeo(article_id=article.id, geo_id=geo_id))
    for tag_id in tag_ids_list:
        db.add(ArticleTag(article_id=article.id, tag_id=tag_id))

    try:
        db.commit()
        logger.info(f"Article updated successfully: id={article_id}")
    except Exception as e:
        db.rollback()
        errors.append(f"Failed to update article: {str(e)}")
        logger.error(f"Article update failed: {str(e)}")

    if errors:
        locales = db.query(Locale).all()
        sources = db.query(ContentSource).all()
        categories = db.query(Category).all()
        geo_tags = db.query(Geo).all()
        tags = db.query(Tag).all()
        articles = db.query(Article).filter(Article.id != article_id).all()
        external_articles = db.query(ExternalArticle).all()
        return templates.TemplateResponse("articles/form.html", {
            "request": request,
            "errors": errors,
            "article": article,
            "locales": locales,
            "sources": sources,
            "categories": categories,
            "geo_tags": geo_tags,
            "tags": tags,
            "articles": articles,
            "external_articles": external_articles,
            "external_article": article.external_article
        })

    return RedirectResponse(url="/admin", status_code=303)


@router.get("/{article_id}/compare", response_class=HTMLResponse)
async def compare_article(
        request: Request,
        article_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    logger.info(f"Comparing article: id={article_id}")
    article = db.query(Article).get(article_id)
    if not article:
        logger.warning(f"Article not found: id={article_id}")
        raise HTTPException(status_code=404, detail="Article not found")
    external_article = article.external_article if article.external_article_id else None
    return templates.TemplateResponse("articles/compare.html", {
        "request": request,
        "article": article,
        "external_article": external_article
    })


@router.post("/categories", response_class=HTMLResponse)
async def create_category(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...),
        description: Optional[str] = Form(None)
):
    logger.info(f"Creating category: code={code}")
    category = Category(code=code, description=description)
    db.add(category)
    try:
        db.commit()
        logger.info(f"Category created: code={code}")
    except Exception as e:
        db.rollback()
        logger.error(f"Category creation failed: {str(e)}")
        return templates.TemplateResponse("articles/form.html", {
            "request": request,
            "errors": [f"Failed to create category: {str(e)}"],
            "article": None
        })
    return RedirectResponse(url="/admin/create", status_code=303)


@router.post("/geo", response_class=HTMLResponse)
async def create_geo(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...),
        description: Optional[str] = Form(None)
):
    logger.info(f"Creating geo: code={code}")
    geo = Geo(code=code, description=description)
    db.add(geo)
    try:
        db.commit()
        logger.info(f"Geo created: code={code}")
    except Exception as e:
        db.rollback()
        logger.error(f"Geo creation failed: {str(e)}")
        return templates.TemplateResponse("articles/form.html", {
            "request": request,
            "errors": [f"Failed to create geo: {str(e)}"],
            "article": None
        })
    return RedirectResponse(url="/admin/create", status_code=303)


@router.post("/tags", response_class=HTMLResponse)
async def create_tag(
        request: Request,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials),
        code: str = Form(...)
):
    logger.info(f"Creating tag: code={code}")
    tag = Tag(code=code)
    db.add(tag)
    try:
        db.commit()
        logger.info(f"Tag created: code={code}")
    except Exception as e:
        db.rollback()
        logger.error(f"Tag creation failed: {str(e)}")
        return templates.TemplateResponse("articles/form.html", {
            "request": request,
            "errors": [f"Failed to create tag: {str(e)}"],
            "article": None
        })
    return RedirectResponse(url="/admin/create", status_code=303)


@router.post("/{article_id}/delete", response_class=HTMLResponse)
async def delete_article(
        request: Request,
        article_id: int,
        db: Session = Depends(get_db),
        username: str = Depends(verify_credentials)
):
    logger.info(f"Deleting article: id={article_id}")
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        logger.warning(f"Article not found: id={article_id}")
        raise HTTPException(status_code=404, detail="Article not found")
    try:
        db.delete(article.delete)
        db.commit()
        logger.info(f"Article deleted successfully: id={article_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete article: {str(e)}")
        raise HTTPException(status_code=400, detail="Failed to delete article: {str(e)}")

    return RedirectResponse(url="/admin", status_code=303)
