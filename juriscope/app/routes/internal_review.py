from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.country import Country
from app.models.legal import LegalArticle, LegalDocument


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "legal_reviewer",
]


ARTICLE_STATUSES = {
    "active": "نافذة",
    "amended": "معدلة",
    "repealed": "ملغاة",
    "archived": "مؤرشفة",
}


REVIEW_STATUSES = {
    "draft": "مسودة",
    "pending_review": "بانتظار المراجعة",
    "approved": "معتمدة",
    "rejected": "مرفوضة",
    "archived": "مؤرشفة",
}


def can_review_legal_articles(staff) -> bool:
    return staff_has_role(staff, ALLOWED_ROLES)


@router.get("/internal/review-queue", response_class=HTMLResponse)
async def review_queue_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_review_legal_articles(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        pending_articles = (
            db.query(LegalArticle)
            .filter(LegalArticle.review_status == "pending_review")
            .order_by(LegalArticle.created_at.asc())
            .all()
        )

        draft_articles = (
            db.query(LegalArticle)
            .filter(LegalArticle.review_status == "draft")
            .order_by(LegalArticle.created_at.asc())
            .limit(50)
            .all()
        )

        rejected_articles = (
            db.query(LegalArticle)
            .filter(LegalArticle.review_status == "rejected")
            .order_by(LegalArticle.updated_at.desc())
            .limit(30)
            .all()
        )

        documents = db.query(LegalDocument).all()
        countries = db.query(Country).all()

        document_map = {document.id: document for document in documents}
        country_map = {country.id: country for country in countries}

        return templates.TemplateResponse(
            request=request,
            name="internal/review_queue.html",
            context={
                "request": request,
                "staff": staff,
                "pending_articles": pending_articles,
                "draft_articles": draft_articles,
                "rejected_articles": rejected_articles,
                "document_map": document_map,
                "country_map": country_map,
                "article_statuses": ARTICLE_STATUSES,
                "review_statuses": REVIEW_STATUSES,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/review-queue/update")
async def review_queue_update(
    request: Request,
    article_id: int = Form(...),
    action: str = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_review_legal_articles(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    action = action.strip()

    if action not in {"approve", "reject", "archive", "back_to_pending"}:
        return RedirectResponse(url="/internal/review-queue?error=invalid_action", status_code=303)

    db = SessionLocal()

    try:
        article = db.query(LegalArticle).filter(LegalArticle.id == article_id).first()

        if not article:
            return RedirectResponse(url="/internal/review-queue?error=article_not_found", status_code=303)

        if action == "approve":
            article.review_status = "approved"
            article.status = "active"
            article.reviewed_by_id = staff.id
            article.reviewed_at = datetime.utcnow()
            article.last_verified_at = datetime.utcnow()
            article.updated_by_id = staff.id
            article.updated_at = datetime.utcnow()

        elif action == "reject":
            article.review_status = "rejected"
            article.reviewed_by_id = staff.id
            article.reviewed_at = datetime.utcnow()
            article.updated_by_id = staff.id
            article.updated_at = datetime.utcnow()

        elif action == "archive":
            article.review_status = "archived"
            article.status = "archived"
            article.updated_by_id = staff.id
            article.updated_at = datetime.utcnow()

        elif action == "back_to_pending":
            article.review_status = "pending_review"
            article.updated_by_id = staff.id
            article.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/review-queue?success=updated", status_code=303)

    finally:
        db.close()