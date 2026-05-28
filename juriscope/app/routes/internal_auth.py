import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.security import verify_password
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional
from app.models.case import Analysis, Case
from app.models.legal import LegalArticle, LegalDocument
from app.models.staff import StaffSession, StaffUser
from app.models.support import SupportTicket
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


STAFF_ROLES = {
    "superadmin": "Super Admin / Owner",
    "developer": "Developer",
    "admin": "Admin",
    "legal_reviewer": "Legal Reviewer",
    "data_entry": "Data Entry",
    "customer_service": "Customer Service",
    "accountant": "Accountant",
}


@router.get("/internal/login", response_class=HTMLResponse)
async def internal_login_page(request: Request):
    staff = get_current_staff_optional(request)
    if staff:
        return RedirectResponse(url="/internal/dashboard", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="internal/login.html",
        context={"request": request, "staff": None, "error": ""},
    )


@router.post("/internal/login", response_class=HTMLResponse)
async def internal_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    db = SessionLocal()

    try:
        staff = (
            db.query(StaffUser)
            .filter(StaffUser.email == email, StaffUser.is_active == True)
            .first()
        )

        if not staff or not verify_password(password, staff.password_hash):
            return templates.TemplateResponse(
                request=request,
                name="internal/login.html",
                context={"request": request, "staff": None, "error": "بيانات الدخول غير صحيحة."},
            )

        token = secrets.token_urlsafe(32)
        session = StaffSession(
            staff_user_id=staff.id,
            token=token,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=8),
        )
        staff.last_login_at = datetime.utcnow()
        db.add(session)
        db.commit()

        response = RedirectResponse(url="/internal/dashboard", status_code=303)
        response.set_cookie(
            settings.STAFF_SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 8,
        )
        return response

    finally:
        db.close()


@router.get("/internal/logout")
async def internal_logout(request: Request):
    token = request.cookies.get(settings.STAFF_SESSION_COOKIE_NAME, "")
    db = SessionLocal()

    try:
        if token:
            db.query(StaffSession).filter(StaffSession.token == token).delete()
            db.commit()
    finally:
        db.close()

    response = RedirectResponse(url="/internal/login", status_code=303)
    response.delete_cookie(settings.STAFF_SESSION_COOKIE_NAME)
    return response


@router.get("/internal/dashboard", response_class=HTMLResponse)
async def internal_dashboard(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    db = SessionLocal()

    try:
        users_count = db.query(User).count()
        staff_count = db.query(StaffUser).count()
        cases_count = db.query(Case).count()
        analyses_count = db.query(Analysis).count()
        legal_documents_count = db.query(LegalDocument).count()
        legal_articles_count = db.query(LegalArticle).count()

        pending_articles_count = (
            db.query(LegalArticle)
            .filter(LegalArticle.review_status == "pending_review")
            .count()
        )

        support_tickets_count = (
            db.query(SupportTicket)
            .filter(SupportTicket.status == "open")
            .count()
        )

        return templates.TemplateResponse(
            request=request,
            name="internal/dashboard.html",
            context={
                "request": request,
                "staff": staff,
                "roles": STAFF_ROLES,
                "stats": {
                    "users": users_count,
                    "staff": staff_count,
                    "cases": cases_count,
                    "analyses": analyses_count,
                    "legal_documents": legal_documents_count,
                    "legal_articles": legal_articles_count,
                    "pending_articles": pending_articles_count,
                    "support_tickets": support_tickets_count,
                },
            },
        )

    finally:
        db.close()
