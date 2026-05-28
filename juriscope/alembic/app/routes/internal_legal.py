import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.country import Country
from app.models.legal import (
    LegalArticle,
    LegalArticleVersion,
    LegalDocument,
    LegalImportJob,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "legal_reviewer",
    "data_entry",
]


DOCUMENT_TYPES = {
    "law": "قانون",
    "regulation": "نظام",
    "instruction": "تعليمات",
    "decision": "قرار",
    "case_law": "حكم قضائي",
    "court_principle": "مبدأ قضائي",
    "doctrine": "فقه قانوني",
}


REVIEW_STATUSES = {
    "draft": "مسودة",
    "pending_review": "بانتظار المراجعة",
    "approved": "معتمد",
    "rejected": "مرفوض",
    "archived": "مؤرشف",
}


DOCUMENT_STATUSES = {
    "active": "نافذ",
    "amended": "معدل",
    "repealed": "ملغى",
    "archived": "مؤرشف",
}


SOURCE_CONFIDENCE = {
    "official": "رسمي",
    "high": "عالية",
    "medium": "متوسطة",
    "low": "منخفضة",
}


def can_manage_legal_documents(staff) -> bool:
    return staff_has_role(staff, ALLOWED_ROLES)


def clean_article_text(text: str) -> str:
    return " ".join((text or "").split())


def ensure_legal_upload_dir() -> str:
    upload_dir = settings.LEGAL_UPLOAD_DIR or "data/legal_uploads"
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def safe_filename(filename: str) -> str:
    filename = filename or "legal-document.pdf"
    filename = filename.replace("\\", "_").replace("/", "_")
    filename = re.sub(r"[^A-Za-z0-9\u0600-\u06FF._ -]", "_", filename)
    return filename


def extract_text_from_pdf(file_path: str) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("pdf_library_missing") from exc

    reader = PdfReader(file_path)
    pages_text = []

    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(text)

    return "\n\n".join(pages_text).strip()


def split_legal_articles(extracted_text: str) -> list[dict]:
    """
    تقسيم أولي للمواد القانونية.
    يدعم أنماطًا مثل:
    المادة 1
    المادة (1)
    مادة 1
    مادة (1)
    المــادة ١
    """

    text = extracted_text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    pattern = re.compile(
        r"(?P<header>(?:المادة|مادة)\s*[\(\[]?\s*(?P<number>[0-9٠-٩]+)\s*[\)\]]?)",
        flags=re.MULTILINE,
    )

    matches = list(pattern.finditer(text))

    if not matches:
        return []

    articles = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        chunk = text[start:end].strip()
        header = match.group("header").strip()
        number = match.group("number").strip()

        body = chunk.replace(header, "", 1).strip()

        if not body:
            body = chunk

        articles.append(
            {
                "article_number": number,
                "article_title": "",
                "article_text": body,
                "article_text_clean": clean_article_text(body),
            }
        )

    return articles


@router.get("/internal/legal-documents", response_class=HTMLResponse)
async def legal_documents_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        countries = (
            db.query(Country)
            .filter(Country.is_active == True)
            .order_by(Country.name_ar.asc())
            .all()
        )

        documents = (
            db.query(LegalDocument)
            .order_by(LegalDocument.created_at.desc())
            .all()
        )

        import_jobs = (
            db.query(LegalImportJob)
            .order_by(LegalImportJob.created_at.desc())
            .limit(10)
            .all()
        )

        country_map = {country.id: country for country in countries}

        return templates.TemplateResponse(
            request=request,
            name="internal/legal_documents.html",
            context={
                "request": request,
                "staff": staff,
                "countries": countries,
                "documents": documents,
                "import_jobs": import_jobs,
                "country_map": country_map,
                "document_types": DOCUMENT_TYPES,
                "review_statuses": REVIEW_STATUSES,
                "document_statuses": DOCUMENT_STATUSES,
                "source_confidence": SOURCE_CONFIDENCE,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/legal-documents/create")
async def legal_document_create(
    request: Request,
    country_id: int = Form(...),
    title_ar: str = Form(...),
    title_en: str = Form(""),
    document_type: str = Form(...),
    source_name: str = Form(""),
    source_url: str = Form(""),
    official_reference: str = Form(""),
    issue_date: str = Form(""),
    effective_date: str = Form(""),
    status: str = Form("active"),
    review_status: str = Form("draft"),
    source_confidence: str = Form("medium"),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    title_ar = title_ar.strip()
    title_en = title_en.strip()
    source_name = source_name.strip()
    source_url = source_url.strip()
    official_reference = official_reference.strip()
    issue_date = issue_date.strip()
    effective_date = effective_date.strip()
    status = status.strip()
    review_status = review_status.strip()
    source_confidence = source_confidence.strip()

    if not title_ar:
        return RedirectResponse(url="/internal/legal-documents?error=missing_title", status_code=303)

    if document_type not in DOCUMENT_TYPES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_document_type", status_code=303)

    if status not in DOCUMENT_STATUSES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_status", status_code=303)

    if review_status not in REVIEW_STATUSES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_review_status", status_code=303)

    if source_confidence not in SOURCE_CONFIDENCE:
        source_confidence = "medium"

    db = SessionLocal()

    try:
        country = db.query(Country).filter(Country.id == country_id).first()

        if not country:
            return RedirectResponse(url="/internal/legal-documents?error=country_not_found", status_code=303)

        document = LegalDocument(
            country_id=country.id,
            jurisdiction_id=None,
            title_ar=title_ar,
            title_en=title_en,
            document_type=document_type,
            source_name=source_name,
            source_url=source_url,
            official_reference=official_reference,
            issue_date=issue_date,
            effective_date=effective_date,
            status=status,
            review_status=review_status,
            source_confidence=source_confidence,
            uploaded_file_path="",
            created_by_id=staff.id,
            reviewed_by_id=staff.id if review_status == "approved" else None,
            reviewed_at=datetime.utcnow() if review_status == "approved" else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(document)
        db.commit()

        return RedirectResponse(url="/internal/legal-documents?success=created", status_code=303)

    finally:
        db.close()


@router.post("/internal/legal-documents/upload-pdf")
async def legal_document_upload_pdf(
    request: Request,
    country_id: int = Form(...),
    title_ar: str = Form(...),
    title_en: str = Form(""),
    document_type: str = Form(...),
    source_name: str = Form(""),
    source_url: str = Form(""),
    official_reference: str = Form(""),
    issue_date: str = Form(""),
    effective_date: str = Form(""),
    status: str = Form("active"),
    review_status: str = Form("pending_review"),
    source_confidence: str = Form("official"),
    auto_split_articles: str = Form("yes"),
    pdf_file: UploadFile = File(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    title_ar = title_ar.strip()
    title_en = title_en.strip()
    source_name = source_name.strip()
    source_url = source_url.strip()
    official_reference = official_reference.strip()
    issue_date = issue_date.strip()
    effective_date = effective_date.strip()
    status = status.strip()
    review_status = review_status.strip()
    source_confidence = source_confidence.strip()

    if not title_ar:
        return RedirectResponse(url="/internal/legal-documents?error=missing_title", status_code=303)

    if document_type not in DOCUMENT_TYPES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_document_type", status_code=303)

    if status not in DOCUMENT_STATUSES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_status", status_code=303)

    if review_status not in REVIEW_STATUSES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_review_status", status_code=303)

    if source_confidence not in SOURCE_CONFIDENCE:
        source_confidence = "official"

    if not pdf_file.filename.lower().endswith(".pdf"):
        return RedirectResponse(url="/internal/legal-documents?error=not_pdf", status_code=303)

    file_bytes = await pdf_file.read()

    if not file_bytes:
        return RedirectResponse(url="/internal/legal-documents?error=empty_file", status_code=303)

    max_size = 30 * 1024 * 1024

    if len(file_bytes) > max_size:
        return RedirectResponse(url="/internal/legal-documents?error=file_too_large", status_code=303)

    upload_dir = ensure_legal_upload_dir()
    stored_filename = f"{int(time.time())}_{safe_filename(pdf_file.filename)}"
    stored_path = os.path.join(upload_dir, stored_filename)

    with open(stored_path, "wb") as f:
        f.write(file_bytes)

    db = SessionLocal()

    try:
        country = db.query(Country).filter(Country.id == country_id).first()

        if not country:
            return RedirectResponse(url="/internal/legal-documents?error=country_not_found", status_code=303)

        document = LegalDocument(
            country_id=country.id,
            jurisdiction_id=None,
            title_ar=title_ar,
            title_en=title_en,
            document_type=document_type,
            source_name=source_name,
            source_url=source_url,
            official_reference=official_reference,
            issue_date=issue_date,
            effective_date=effective_date,
            status=status,
            review_status=review_status,
            source_confidence=source_confidence,
            uploaded_file_path=stored_path,
            created_by_id=staff.id,
            reviewed_by_id=None,
            reviewed_at=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(document)
        db.flush()

        import_job = LegalImportJob(
            country_id=country.id,
            staff_user_id=staff.id,
            filename=pdf_file.filename,
            file_path=stored_path,
            status="processing",
            result_json="",
            error_message="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(import_job)
        db.flush()

        extracted_text = ""

        try:
            extracted_text = extract_text_from_pdf(stored_path)
        except RuntimeError as exc:
            import_job.status = "failed"
            import_job.error_message = str(exc)
            import_job.updated_at = datetime.utcnow()
            db.commit()

            if str(exc) == "pdf_library_missing":
                return RedirectResponse(url="/internal/legal-documents?error=pdf_library_missing", status_code=303)

            return RedirectResponse(url="/internal/legal-documents?error=pdf_extract_failed", status_code=303)
        except Exception as exc:
            import_job.status = "failed"
            import_job.error_message = str(exc)
            import_job.updated_at = datetime.utcnow()
            db.commit()
            return RedirectResponse(url="/internal/legal-documents?error=pdf_extract_failed", status_code=303)

        created_articles = 0

        if auto_split_articles == "yes" and extracted_text:
            articles = split_legal_articles(extracted_text)

            for article_data in articles:
                article = LegalArticle(
                    document_id=document.id,
                    country_id=document.country_id,
                    article_number=article_data["article_number"],
                    article_title=article_data["article_title"],
                    article_text=article_data["article_text"],
                    article_text_clean=article_data["article_text_clean"],
                    chapter="",
                    section="",
                    status="active",
                    review_status="pending_review",
                    effective_date=effective_date,
                    repealed_date="",
                    notes="تم استخراج هذه المادة تلقائيًا من ملف PDF وتحتاج مراجعة.",
                    source_confidence=source_confidence,
                    last_verified_at=None,
                    created_by_id=staff.id,
                    updated_by_id=staff.id,
                    reviewed_by_id=None,
                    reviewed_at=None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                db.add(article)
                db.flush()

                version = LegalArticleVersion(
                    article_id=article.id,
                    version_number=1,
                    article_text=article.article_text,
                    article_text_clean=article.article_text_clean,
                    change_reason="Auto imported from PDF",
                    status="active",
                    effective_date=effective_date,
                    created_by_id=staff.id,
                    created_at=datetime.utcnow(),
                )

                db.add(version)
                created_articles += 1

        import_job.status = "completed"
        import_job.result_json = json.dumps(
            {
                "document_id": document.id,
                "filename": pdf_file.filename,
                "extracted_text_length": len(extracted_text),
                "created_articles": created_articles,
                "auto_split_articles": auto_split_articles,
            },
            ensure_ascii=False,
        )
        import_job.updated_at = datetime.utcnow()

        db.commit()

        if created_articles > 0:
            return RedirectResponse(
                url=f"/internal/legal-articles?document_id={document.id}&success=created",
                status_code=303,
            )

        return RedirectResponse(
            url=f"/internal/legal-documents?success=pdf_uploaded_no_articles",
            status_code=303,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.post("/internal/legal-documents/update-status")
async def legal_document_update_status(
    request: Request,
    document_id: int = Form(...),
    status: str = Form(...),
    review_status: str = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    status = status.strip()
    review_status = review_status.strip()

    if status not in DOCUMENT_STATUSES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_status", status_code=303)

    if review_status not in REVIEW_STATUSES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_review_status", status_code=303)

    db = SessionLocal()

    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if not document:
            return RedirectResponse(url="/internal/legal-documents?error=document_not_found", status_code=303)

        document.status = status
        document.review_status = review_status
        document.updated_at = datetime.utcnow()

        if review_status == "approved":
            document.reviewed_by_id = staff.id
            document.reviewed_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/legal-documents?success=status_updated", status_code=303)

    finally:
        db.close()