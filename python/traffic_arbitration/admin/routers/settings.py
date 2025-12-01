from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from traffic_arbitration.models import Category, Geo, Tag, Locale
from traffic_arbitration.admin.schemas import (
    CategoryCreate, CategoryResponse, GeoCreate, GeoResponse,
    TagCreate, TagResponse, LocaleCreate, LocaleUpdate, LocaleResponse
)
from traffic_arbitration.admin.dependencies import verify_credentials, get_db
from traffic_arbitration.common.logging import logger

router = APIRouter()
templates = Jinja2Templates(directory="traffic_arbitration/admin/templates")


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
        return RedirectResponse(url="/admin/articles/create", status_code=303)
    return RedirectResponse(url="/admin/articles/create", status_code=303)


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
        return RedirectResponse(url="/admin/articles/create", status_code=303)
    return RedirectResponse(url="/admin/articles/create", status_code=303)


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
        return RedirectResponse(url="/admin/articles/create", status_code=303)
    return RedirectResponse(url="/admin/articles/create", status_code=303)