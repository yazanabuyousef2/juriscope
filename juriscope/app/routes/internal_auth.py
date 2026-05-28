from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional
from app.models.case import Analysis, Case
from app.models.legal import LegalArticle, LegalDocument
from app.models.staff import StaffUser
from app.models.support import SupportTicket
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


STAFF_ROLES = {
    "superadmin": "Super Admin / Owner",
    "developer": "Developer",
    "admin": "Admin",
    "legal_reviewer": "Legal Reviewer",
    "data_entry": "Data Entry",
    "customer_service": "Customer Service",
}


@router.get("/internal/login")
async def internal_login_redirect():
    return RedirectResponse(url="/login", status_code=303)


@router.get("/internal/logout")
async def internal_logout_redirect():
    return RedirectResponse(url="/logout", status_code=303)


@router.get("/internal/dashboard", response_class=HTMLResponse)
async def internal_dashboard(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

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