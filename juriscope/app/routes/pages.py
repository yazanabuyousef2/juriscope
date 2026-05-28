from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import (
    get_current_user_optional,
    require_user,
    is_staff_mode_user,
    is_unlimited_user,
)
from app.database import fetch_all, user_limits, user_usage


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def build_usage_and_limits(user):
    if not user:
        return {
            "usage": {
                "analyses": 0,
                "documents": 0,
                "cases": 0,
            },
            "limits": {
                "analyses_per_month": 0,
                "documents_per_month": 0,
                "cases": 0,
            },
        }

    if is_staff_mode_user(user) or is_unlimited_user(user):
        return {
            "usage": {
                "analyses": 0,
                "documents": 0,
                "cases": 0,
            },
            "limits": {
                "analyses_per_month": "غير محدود",
                "documents_per_month": "غير محدود",
                "cases": "غير محدود",
            },
        }

    raw_usage = user_usage(user["id"])
    raw_limits = user_limits(user["plan"])

    return {
        "usage": {
            "analyses": raw_usage.get("monthly_analyses", 0),
            "documents": raw_usage.get("monthly_documents", 0),
            "cases": raw_usage.get("cases", 0),
        },
        "limits": {
            "analyses_per_month": raw_limits.get("monthly_analyses", 999999),
            "documents_per_month": raw_limits.get("monthly_documents", 999999),
            "cases": raw_limits.get("cases", 999999),
        },
    }


def ctx(request: Request):
    user = get_current_user_optional(request)
    usage_data = build_usage_and_limits(user)

    return {
        "request": request,
        "user": user,
        "is_staff_mode": is_staff_mode_user(user),
        "is_unlimited_user": is_unlimited_user(user),
        **usage_data,
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=ctx(request),
    )


@router.get("/features", response_class=HTMLResponse)
async def features(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="features.html",
        context=ctx(request),
    )


@router.get("/use-cases", response_class=HTMLResponse)
async def use_cases(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="use_cases.html",
        context=ctx(request),
    )


@router.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pricing.html",
        context=ctx(request),
    )


@router.get("/assistant", response_class=HTMLResponse)
async def assistant(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login?next=/assistant", status_code=303)

    if is_staff_mode_user(user):
        cases = []
    else:
        cases = fetch_all(
            """
            SELECT id, title, country, case_type, status, updated_at
            FROM cases
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user["id"],),
        )

    usage_data = build_usage_and_limits(user)

    return templates.TemplateResponse(
        request=request,
        name="assistant.html",
        context={
            "request": request,
            "user": user,
            "cases": cases,
            "is_staff_mode": is_staff_mode_user(user),
            "is_unlimited_user": is_unlimited_user(user),
            **usage_data,
        },
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login?next=/profile", status_code=303)

    usage_data = build_usage_and_limits(user)

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "request": request,
            "user": user,
            "is_staff_mode": is_staff_mode_user(user),
            "is_unlimited_user": is_unlimited_user(user),
            **usage_data,
        },
    )