from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.subscription import SubscriptionPlan
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "customer_service",
]


SUPERADMIN_ONLY_ROLES = [
    "superadmin",
]


USER_ROLES = {
    "individual": "فرد / مستخدم عادي",
    "lawyer": "محامي",
    "company": "شركة / رجل أعمال",
    "judge": "قاضٍ",
    "law_student": "طالب قانون",
    "legal_researcher": "باحث قانوني",
    "government_employee": "موظف حكومي",
}


def can_manage_users(staff) -> bool:
    return staff_has_role(staff, ALLOWED_ROLES)


def is_superadmin(staff) -> bool:
    return bool(staff and staff.role == "superadmin")


@router.get("/internal/users", response_class=HTMLResponse)
async def users_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_users(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    search = request.query_params.get("search", "").strip()
    role_filter = request.query_params.get("role", "").strip()
    plan_filter = request.query_params.get("plan", "").strip()
    status_filter = request.query_params.get("status", "").strip()

    db = SessionLocal()

    try:
        query = db.query(User)

        if search:
            like_value = f"%{search}%"
            query = query.filter(
                (User.full_name.ilike(like_value))
                | (User.email.ilike(like_value))
                | (User.phone.ilike(like_value))
            )

        if role_filter:
            query = query.filter(User.user_role == role_filter)

        if plan_filter:
            query = query.filter(User.plan_code == plan_filter)

        if status_filter == "active":
            query = query.filter(User.is_active == True)

        if status_filter == "inactive":
            query = query.filter(User.is_active == False)

        users = query.order_by(User.created_at.desc()).limit(300).all()

        plans = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.price_monthly.asc())
            .all()
        )

        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        inactive_users = db.query(User).filter(User.is_active == False).count()

        return templates.TemplateResponse(
            request=request,
            name="internal/users.html",
            context={
                "request": request,
                "staff": staff,
                "users": users,
                "plans": plans,
                "user_roles": USER_ROLES,
                "search": search,
                "role_filter": role_filter,
                "plan_filter": plan_filter,
                "status_filter": status_filter,
                "stats": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "inactive_users": inactive_users,
                    "shown_users": len(users),
                },
                "can_delete_users": is_superadmin(staff),
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/users/update")
async def users_update(
    request: Request,
    user_id: int = Form(...),
    user_role: str = Form(...),
    plan_code: str = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_users(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    user_role = user_role.strip()
    plan_code = plan_code.strip()

    if user_role not in USER_ROLES:
        return RedirectResponse(url="/internal/users?error=invalid_user_role", status_code=303)

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return RedirectResponse(url="/internal/users?error=user_not_found", status_code=303)

        plan = (
            db.query(SubscriptionPlan)
            .filter(
                SubscriptionPlan.code == plan_code,
                SubscriptionPlan.is_active == True,
            )
            .first()
        )

        if not plan:
            return RedirectResponse(url="/internal/users?error=plan_not_found", status_code=303)

        user.user_role = user_role
        user.plan_code = plan_code
        user.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/users?success=updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/users/toggle-active")
async def users_toggle_active(
    request: Request,
    user_id: int = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_users(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return RedirectResponse(url="/internal/users?error=user_not_found", status_code=303)

        user.is_active = not user.is_active
        user.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/users?success=status_updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/users/delete")
async def users_delete(
    request: Request,
    user_id: int = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not is_superadmin(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return RedirectResponse(url="/internal/users?error=user_not_found", status_code=303)

        db.delete(user)
        db.commit()

        return RedirectResponse(url="/internal/users?success=deleted", status_code=303)

    except IntegrityError:
        db.rollback()
        return RedirectResponse(url="/internal/users?error=cannot_delete_has_data", status_code=303)

    finally:
        db.close()