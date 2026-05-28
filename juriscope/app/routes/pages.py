from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import get_current_user_optional, require_user
from app.database import fetch_all, fetch_one, user_usage, user_limits

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PLAN_NAMES = {
    "free": "المجانية",
    "basic": "Basic",
    "pro": "Pro",
    "premium": "Premium",
    "enterprise": "Enterprise",
    "individual": "الأفراد",
    "business": "الأعمال",
    "lawyer": "المحامون",
}


def build_usage_and_limits(user):
    if not user:
        return {
            "usage": {"analyses": 0, "documents": 0, "cases": 0},
            "limits": {"analyses_per_month": 0, "documents_per_month": 0, "cases": 0},
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


def ctx(request: Request, extra: dict | None = None):
    user = get_current_user_optional(request)
    data = {
        "request": request,
        "user": user,
        "plan_names": PLAN_NAMES,
        **build_usage_and_limits(user),
    }

    if extra:
        data.update(extra)

    return data


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context=ctx(request))


@router.get("/assistant", response_class=HTMLResponse)
async def assistant(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login?next=/assistant", status_code=303)

    cases = fetch_all(
        """
        SELECT id, title, country, case_type, status
        FROM cases
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (user["id"],),
    )

    return templates.TemplateResponse(
        request=request,
        name="assistant.html",
        context=ctx(request, {"user": user, "cases": cases}),
    )


@router.get("/features", response_class=HTMLResponse)
async def features(request: Request):
    return templates.TemplateResponse(request=request, name="features.html", context=ctx(request))


@router.get("/use-cases", response_class=HTMLResponse)
async def use_cases(request: Request):
    return templates.TemplateResponse(request=request, name="use_cases.html", context=ctx(request))


@router.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    return templates.TemplateResponse(request=request, name="pricing.html", context=ctx(request))


@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login?next=/profile", status_code=303)

    cases_count = fetch_one("SELECT COUNT(*) AS count FROM cases WHERE user_id = ?", (user["id"],))
    analyses_count = fetch_one("SELECT COUNT(*) AS count FROM analyses WHERE user_id = ?", (user["id"],))
    documents_count = fetch_one("SELECT COUNT(*) AS count FROM documents WHERE user_id = ?", (user["id"],))

    recent_cases = fetch_all(
        """
        SELECT id, title, country, case_type, status, updated_at
        FROM cases
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT 5
        """,
        (user["id"],),
    )

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context=ctx(
            request,
            {
                "user": user,
                "cases_count": cases_count["count"] if cases_count else 0,
                "analyses_count": analyses_count["count"] if analyses_count else 0,
                "documents_count": documents_count["count"] if documents_count else 0,
                "recent_cases": recent_cases,
            },
        ),
    )
