from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError

from app.auth.security import hash_password
from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional
from app.models.staff import StaffUser


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

OWNER_EMAIL = "yazanabuyousef2@gmail.com"


STAFF_ROLES = {
    "superadmin": "Super Admin / Owner",
    "developer": "Developer",
    "admin": "Admin",
    "legal_reviewer": "Legal Reviewer",
    "data_entry": "Data Entry",
    "customer_service": "Customer Service",
}


CREATABLE_STAFF_ROLES = {
    "developer": "Developer",
    "admin": "Admin",
    "legal_reviewer": "Legal Reviewer",
    "data_entry": "Data Entry",
    "customer_service": "Customer Service",
}


def is_superadmin(staff) -> bool:
    return bool(staff and staff.role == "superadmin" and staff.email == OWNER_EMAIL)


def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False

    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    has_symbol = any(not ch.isalnum() for ch in password)

    return has_upper and has_lower and has_digit and has_symbol


def enforce_single_superadmin(db):
    staff_users = db.query(StaffUser).all()

    owner = db.query(StaffUser).filter(StaffUser.email == OWNER_EMAIL).first()

    if owner:
        owner.role = "superadmin"
        owner.is_active = True

    for staff in staff_users:
        if staff.email != OWNER_EMAIL and staff.role == "superadmin":
            staff.role = "admin"
            staff.is_active = False

    db.commit()


@router.get("/internal/staff", response_class=HTMLResponse)
async def staff_index(request: Request):
    current_staff = get_current_staff_optional(request)

    if not current_staff:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        enforce_single_superadmin(db)

        current_staff = db.query(StaffUser).filter(StaffUser.id == current_staff.id).first()

        if not is_superadmin(current_staff):
            return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

        staff_users = (
            db.query(StaffUser)
            .order_by(StaffUser.created_at.desc())
            .all()
        )

        return templates.TemplateResponse(
            request=request,
            name="internal/staff.html",
            context={
                "request": request,
                "staff": current_staff,
                "staff_users": staff_users,
                "roles": STAFF_ROLES,
                "creatable_roles": CREATABLE_STAFF_ROLES,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/staff/create")
async def staff_create(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
):
    current_staff = get_current_staff_optional(request)

    if not current_staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(current_staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    full_name = full_name.strip()
    email = email.strip().lower()
    role = role.strip()

    if role == "superadmin":
        return RedirectResponse(url="/internal/staff?error=cannot_create_superadmin", status_code=303)

    if role not in CREATABLE_STAFF_ROLES:
        return RedirectResponse(url="/internal/staff?error=invalid_role", status_code=303)

    if not full_name or not email or not password:
        return RedirectResponse(url="/internal/staff?error=missing_fields", status_code=303)

    if not is_strong_password(password):
        return RedirectResponse(url="/internal/staff?error=weak_password", status_code=303)

    db = SessionLocal()

    try:
        enforce_single_superadmin(db)

        existing = db.query(StaffUser).filter(StaffUser.email == email).first()

        if existing:
            return RedirectResponse(url="/internal/staff?error=email_exists", status_code=303)

        new_staff = StaffUser(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            created_by_id=current_staff.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(new_staff)
        db.commit()

        return RedirectResponse(url="/internal/staff?success=created", status_code=303)

    finally:
        db.close()


@router.post("/internal/staff/update-role")
async def staff_update_role(
    request: Request,
    staff_id: int = Form(...),
    role: str = Form(...),
):
    current_staff = get_current_staff_optional(request)

    if not current_staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(current_staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    role = role.strip()

    if role == "superadmin":
        return RedirectResponse(url="/internal/staff?error=cannot_assign_superadmin", status_code=303)

    if role not in CREATABLE_STAFF_ROLES:
        return RedirectResponse(url="/internal/staff?error=invalid_role", status_code=303)

    db = SessionLocal()

    try:
        enforce_single_superadmin(db)

        target = db.query(StaffUser).filter(StaffUser.id == staff_id).first()

        if not target:
            return RedirectResponse(url="/internal/staff?error=not_found", status_code=303)

        if target.id == current_staff.id:
            return RedirectResponse(url="/internal/staff?error=cannot_change_self_role", status_code=303)

        if target.email == OWNER_EMAIL or target.role == "superadmin":
            return RedirectResponse(url="/internal/staff?error=cannot_change_superadmin", status_code=303)

        target.role = role
        target.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/staff?success=role_updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/staff/toggle-active")
async def staff_toggle_active(
    request: Request,
    staff_id: int = Form(...),
):
    current_staff = get_current_staff_optional(request)

    if not current_staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(current_staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        enforce_single_superadmin(db)

        target = db.query(StaffUser).filter(StaffUser.id == staff_id).first()

        if not target:
            return RedirectResponse(url="/internal/staff?error=not_found", status_code=303)

        if target.id == current_staff.id:
            return RedirectResponse(url="/internal/staff?error=cannot_disable_self", status_code=303)

        if target.email == OWNER_EMAIL or target.role == "superadmin":
            return RedirectResponse(url="/internal/staff?error=cannot_disable_superadmin", status_code=303)

        target.is_active = not target.is_active
        target.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/staff?success=status_updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/staff/update-password")
async def staff_update_password(
    request: Request,
    staff_id: int = Form(...),
    new_password: str = Form(...),
):
    current_staff = get_current_staff_optional(request)

    if not current_staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(current_staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    if not is_strong_password(new_password):
        return RedirectResponse(url="/internal/staff?error=weak_password", status_code=303)

    db = SessionLocal()

    try:
        enforce_single_superadmin(db)

        target = db.query(StaffUser).filter(StaffUser.id == staff_id).first()

        if not target:
            return RedirectResponse(url="/internal/staff?error=not_found", status_code=303)

        target.password_hash = hash_password(new_password)
        target.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/staff?success=password_updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/staff/delete")
async def staff_delete(
    request: Request,
    staff_id: int = Form(...),
):
    current_staff = get_current_staff_optional(request)

    if not current_staff:
        return RedirectResponse(url="/login", status_code=303)

    if not is_superadmin(current_staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        enforce_single_superadmin(db)

        target = db.query(StaffUser).filter(StaffUser.id == staff_id).first()

        if not target:
            return RedirectResponse(url="/internal/staff?error=not_found", status_code=303)

        if target.id == current_staff.id:
            return RedirectResponse(url="/internal/staff?error=cannot_delete_self", status_code=303)

        if target.email == OWNER_EMAIL or target.role == "superadmin":
            return RedirectResponse(url="/internal/staff?error=cannot_delete_superadmin", status_code=303)

        db.delete(target)
        db.commit()

        return RedirectResponse(url="/internal/staff?success=deleted", status_code=303)

    except IntegrityError:
        db.rollback()
        return RedirectResponse(url="/internal/staff?error=cannot_delete_has_data", status_code=303)

    finally:
        db.close()