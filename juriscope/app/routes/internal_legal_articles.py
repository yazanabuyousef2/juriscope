from datetime import datetime

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.country import Country
from app.models.legal import LegalArticle, LegalArticleVersion, LegalDocument


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "legal_reviewer",
    "data_entry",
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


SOURCE_CONFIDENCE = {
    "official": "رسمي",
    "high": "عالية",
    "medium": "متوسطة",
    "low": "منخفضة",
}


def can_manage_legal_articles(staff) -> bool:
    return staff_has_role(staff, ALLOWED_ROLES)


def clean_article_text(text: str) -> str:
    return " ".join((text or "").split())


@router.get("/internal/legal-articles", response_class=HTMLResponse)
async def legal_articles_index(
    request: Request,
    document_id: int | None = Query(default=None),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_legal_articles(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        documents = (
            db.query(LegalDocument)
            .order_by(LegalDocument.created_at.desc())
            .all()
        )

        selected_document = None

        if document_id:
            selected_document = (
                db.query(LegalDocument)
                .filter(LegalDocument.id == document_id)
                .first()
            )

        query = db.query(LegalArticle).order_by(LegalArticle.created_at.desc())

        if selected_document:
            query = query.filter(LegalArticle.document_id == selected_document.id)

        articles = query.all()

        countries = db.query(Country).all()
        country_map = {country.id: country for country in countries}
        document_map = {document.id: document for document in documents}

        return templates.TemplateResponse(
            request=request,
            name="internal/legal_articles.html",
            context={
                "request": request,
                "staff": staff,
                "documents": documents,
                "selected_document": selected_document,
                "articles": articles,
                "country_map": country_map,
                "document_map": document_map,
                "article_statuses": ARTICLE_STATUSES,
                "review_statuses": REVIEW_STATUSES,
                "source_confidence": SOURCE_CONFIDENCE,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/legal-articles/create")
async def legal_article_create(
    request: Request,
    document_id: int = Form(...),
    article_number: str = Form(...),
    article_title: str = Form(""),
    article_text: str = Form(...),
    chapter: str = Form(""),
    section: str = Form(""),
    status: str = Form("active"),
    review_status: str = Form("draft"),
    effective_date: str = Form(""),
    repealed_date: str = Form(""),
    notes: str = Form(""),
    source_confidence: str = Form("medium"),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_legal_articles(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    article_number = article_number.strip()
    article_title = article_title.strip()
    article_text = article_text.strip()
    chapter = chapter.strip()
    section = section.strip()
    status = status.strip()
    review_status = review_status.strip()
    effective_date = effective_date.strip()
    repealed_date = repealed_date.strip()
    notes = notes.strip()
    source_confidence = source_confidence.strip()

    if not article_number:
        return RedirectResponse(
            url=f"/internal/legal-articles?document_id={document_id}&error=missing_article_number",
            status_code=303,
        )

    if not article_text:
        return RedirectResponse(
            url=f"/internal/legal-articles?document_id={document_id}&error=missing_article_text",
            status_code=303,
        )

    if status not in ARTICLE_STATUSES:
        return RedirectResponse(
            url=f"/internal/legal-articles?document_id={document_id}&error=invalid_status",
            status_code=303,
        )

    if review_status not in REVIEW_STATUSES:
        return RedirectResponse(
            url=f"/internal/legal-articles?document_id={document_id}&error=invalid_review_status",
            status_code=303,
        )

    if source_confidence not in SOURCE_CONFIDENCE:
        source_confidence = "medium"

    db = SessionLocal()

    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if not document:
            return RedirectResponse(url="/internal/legal-articles?error=document_not_found", status_code=303)

        article = LegalArticle(
            document_id=document.id,
            country_id=document.country_id,
            article_number=article_number,
            article_title=article_title,
            article_text=article_text,
            article_text_clean=clean_article_text(article_text),
            chapter=chapter,
            section=section,
            status=status,
            review_status=review_status,
            effective_date=effective_date,
            repealed_date=repealed_date,
            notes=notes,
            source_confidence=source_confidence,
            last_verified_at=datetime.utcnow() if review_status == "approved" else None,
            created_by_id=staff.id,
            updated_by_id=staff.id,
            reviewed_by_id=staff.id if review_status == "approved" else None,
            reviewed_at=datetime.utcnow() if review_status == "approved" else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(article)
        db.flush()

        version = LegalArticleVersion(
            article_id=article.id,
            version_number=1,
            article_text=article_text,
            article_text_clean=clean_article_text(article_text),
            change_reason="Initial article creation",
            status="active",
            effective_date=effective_date,
            created_by_id=staff.id,
            created_at=datetime.utcnow(),
        )

        db.add(version)
        db.commit()

        return RedirectResponse(
            url=f"/internal/legal-articles?document_id={document.id}&success=created",
            status_code=303,
        )

    finally:
        db.close()


@router.post("/internal/legal-articles/update-status")
async def legal_article_update_status(
    request: Request,
    article_id: int = Form(...),
    status: str = Form(...),
    review_status: str = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_legal_articles(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    status = status.strip()
    review_status = review_status.strip()

    if status not in ARTICLE_STATUSES:
        return RedirectResponse(url="/internal/legal-articles?error=invalid_status", status_code=303)

    if review_status not in REVIEW_STATUSES:
        return RedirectResponse(url="/internal/legal-articles?error=invalid_review_status", status_code=303)

    db = SessionLocal()

    try:
        article = db.query(LegalArticle).filter(LegalArticle.id == article_id).first()

        if not article:
            return RedirectResponse(url="/internal/legal-articles?error=article_not_found", status_code=303)

        article.status = status
        article.review_status = review_status
        article.updated_by_id = staff.id
        article.updated_at = datetime.utcnow()

        if review_status == "approved":
            article.reviewed_by_id = staff.id
            article.reviewed_at = datetime.utcnow()
            article.last_verified_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(
            url=f"/internal/legal-articles?document_id={article.document_id}&success=status_updated",
            status_code=303,
        )

    finally:
        db.close()