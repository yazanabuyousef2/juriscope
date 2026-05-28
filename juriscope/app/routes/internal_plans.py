from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional
from app.models.subscription import SubscriptionPlan


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def is_superadmin(staff) -> bool:
    return bool(staff and staff.role == "superadmin")


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def plan_to_row(plan: SubscriptionPlan) -> dict:
    return {
        "id": getattr(plan, "id", None),
        "code": getattr(plan, "code", ""),
        "name_ar": getattr(plan, "name_ar", ""),
        "name_en": getattr(plan, "name_en", ""),
        "description_ar": getattr(plan, "description_ar", ""),
        "price_monthly": getattr(plan, "price_monthly", 0),
        "monthly_analyses": getattr(plan, "monthly_analyses", 0),
        "monthly_documents": getattr(plan, "monthly_documents", 0),
        "max_cases": getattr(plan, "max_cases", 0),
        "max_file_size_mb": getattr(plan, "max_file_size_mb", 15),
        "can_upload_documents": getattr(plan, "can_upload_documents", False),
        "is_active": getattr(plan, "is_active", True),
        "recommended_for": getattr(plan, "recommended_for", ""),
        "created_at": getattr(plan, "created_at", ""),
        "updated_at": getattr(plan, "updated_at", ""),
    }


def set_if_exists(obj, field_name: str, value):
    if hasattr(obj, field_name):
        setattr(obj, field_name, value)


@router.get("/internal/subscription-plans", response_class=HTMLResponse)
async def subscription_plans_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        plans = (
            db.query(SubscriptionPlan)
            .order_by(SubscriptionPlan.price_monthly.asc())
            .all()
        )

        return templates.TemplateResponse(
            request=request,
            name="internal/subscription_plans.html",
            context={
                "request": request,
                "staff": staff,
                "plans": [plan_to_row(plan) for plan in plans],
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/subscription-plans/update")
async def subscription_plan_update(
    request: Request,
    plan_id: int = Form(...),
    name_ar: str = Form(""),
    name_en: str = Form(""),
    description_ar: str = Form(""),
    price_monthly: str = Form("0"),
    monthly_analyses: str = Form("0"),
    monthly_documents: str = Form("0"),
    max_cases: str = Form("0"),
    max_file_size_mb: str = Form("15"),
    can_upload_documents: str = Form("no"),
    is_active: str = Form("no"),
    recommended_for: str = Form(""),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

        if not plan:
            return RedirectResponse(url="/internal/subscription-plans?error=plan_not_found", status_code=303)

        set_if_exists(plan, "name_ar", name_ar.strip())
        set_if_exists(plan, "name_en", name_en.strip())
        set_if_exists(plan, "description_ar", description_ar.strip())
        set_if_exists(plan, "price_monthly", safe_float(price_monthly, 0.0))
        set_if_exists(plan, "monthly_analyses", safe_int(monthly_analyses, 0))
        set_if_exists(plan, "monthly_documents", safe_int(monthly_documents, 0))
        set_if_exists(plan, "max_cases", safe_int(max_cases, 0))
        set_if_exists(plan, "max_file_size_mb", safe_int(max_file_size_mb, 15))
        set_if_exists(plan, "can_upload_documents", can_upload_documents == "yes")
        set_if_exists(plan, "is_active", is_active == "yes")
        set_if_exists(plan, "recommended_for", recommended_for.strip())
        set_if_exists(plan, "updated_at", datetime.utcnow())

        db.commit()

        return RedirectResponse(url="/internal/subscription-plans?success=updated", status_code=303)

    finally:
        db.close()