import json
import os
import re
import time
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.country import Country
from app.models.legal import (
    LegalArticle,
    LegalArticleRelation,
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


def is_archived_or_rejected_document(document: LegalDocument) -> bool:
    return (document.status == "archived") or (document.review_status in ["archived", "rejected"])


def active_documents_query(db):
    return (
        db.query(LegalDocument)
        .filter(LegalDocument.status != "archived")
        .filter(~LegalDocument.review_status.in_(["archived", "rejected"]))
    )


def archived_documents_query(db):
    return (
        db.query(LegalDocument)
        .filter(
            (LegalDocument.status == "archived")
            | (LegalDocument.review_status.in_(["archived", "rejected"]))
        )
    )


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


def reverse_preserving_numbers(text: str) -> str:
    """
    يعالج مشكلة شائعة في ملفات PDF العربية: بعض الأسطر تُستخرج معكوسة حرفيًا
    بسبب اتجاه RTL. نعكس السطر، ثم نعيد الأرقام إلى ترتيبها الصحيح.
    """
    fixed = unicodedata.normalize("NFKC", (text or "")[::-1])
    fixed = re.sub(r"[0-9٠-٩]+", lambda match: match.group(0)[::-1], fixed)
    return " ".join(fixed.strip().split())


def line_looks_reversed_arabic_pdf(line: str) -> bool:
    """
    يحدد الأسطر المستخرجة من PDF بصيغة عربية معكوسة/Presentation Forms.
    هذا يظهر كثيرًا في ملفات ديوان التشريع والرأي عند استخدام pdfplumber.
    """
    if not line:
        return False

    # Arabic Presentation Forms: FB50-FDFF, FE70-FEFF
    has_presentation_forms = any(
        ("\ufb50" <= ch <= "\ufdff") or ("\ufe70" <= ch <= "\ufeff")
        for ch in line
    )

    if has_presentation_forms:
        return True

    reversed_markers = [
        "ةدﺎﻤﻟا",
        "ةداملا",
        "تﻼﻳﺪﻌﺗ",
        "تﺎﻃﺎﺒﺗرا",
    ]

    return any(marker in line for marker in reversed_markers)


def normalize_pdf_extracted_line(line: str) -> str:
    if line_looks_reversed_arabic_pdf(line):
        return reverse_preserving_numbers(line)

    return normalize_legal_line(line)


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from legal PDFs.

    نستخدم pdfplumber أولًا لأنه يعطي ترتيب الأسطر في ملفات ديوان التشريع والرأي
    بشكل يمكن إصلاحه. بعدها نعكس الأسطر العربية المعكوسة ونحافظ على ترتيب الأرقام.

    إذا لم تكن pdfplumber مثبتة، نرجع إلى pypdf كخطة بديلة.
    """
    pages_text: list[str] = []

    try:
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(
                    x_tolerance=1,
                    y_tolerance=3,
                    layout=False,
                ) or ""

                fixed_lines = []
                for raw_line in page_text.split("\n"):
                    fixed_line = normalize_pdf_extracted_line(raw_line)
                    if fixed_line:
                        fixed_lines.append(fixed_line)

                if fixed_lines:
                    pages_text.append("\n".join(fixed_lines))

        extracted = "\n\n".join(pages_text).strip()
        if extracted:
            return extracted

    except Exception:
        # fallback below
        pass

    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("pdf_library_missing") from exc

    reader = PdfReader(file_path)
    pages_text = []

    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            fixed_lines = [normalize_legal_line(line) for line in text.split("\n")]
            pages_text.append("\n".join(line for line in fixed_lines if line))

    return "\n\n".join(pages_text).strip()


ARABIC_DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


METADATA_LABELS = {
    "link": "ارتباطات المادة",
    "amendment": "تعديلات المادة",
    "case_law": "الأحكام القضائية",
    "related_legislation": "التشريعات المرتبطة",
    "interpretation": "تفسير",
}


SITE_NOISE_COMPACT_KEYWORDS = [
    "روابطذاتصلة",
    "شاهدالفيديو",
    "الفيديوالايضاحي",
    "ديوانالتشريعوالرأي",
    "التشريعاتالأردنية",
    "التشريعاتاالردنية",
    "خريطةالموقع",
    "اشتركفينشرةالإخبارية",
    "اشتركفينشرةاالخبارية",
    "الاقتراحاتوالاستفسارات",
    "ادخلالاسم",
    "ادخلالبريد",
    "ادخلالموضوع",
    "ادخلالرسالة",
    "copyright",
    "allrightsreserved",
    "dewanlob",
]


def normalize_legal_line(line: str) -> str:
    """
    Normalize Arabic lines extracted from official PDFs.

    Some files from ديوان التشريع والرأي are extracted by pypdf using Arabic
    presentation-form characters such as اﻟﻤﺎدة instead of المادة.
    NFKC converts these characters back to normal Arabic letters.
    """
    line = line or ""
    line = unicodedata.normalize("NFKC", line)
    line = line.replace("\u200f", "").replace("\u200e", "")
    line = line.replace("ـ", "")
    line = line.replace("اال", "الا")
    line = line.replace("اأ", "الأ")
    line = line.replace("اإ", "الإ")
    line = line.replace("اآ", "الآ")
    return " ".join(line.strip().split())


def compact_arabic_text(text: str) -> str:
    normalized = normalize_legal_line(text).lower()
    normalized = normalized.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    normalized = normalized.replace("ة", "ه")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def western_digits(value: str) -> str:
    return (value or "").translate(ARABIC_DIGIT_TRANSLATION)


def is_noise_line(line: str) -> bool:
    normalized = normalize_legal_line(line)
    compact = compact_arabic_text(normalized)

    if not normalized:
        return True

    if len(normalized) <= 2 and not re.search(r"[0-9٠-٩]", normalized):
        return True

    if compact in {"e", "", "", "", "", "", "", "", "", "", "", "", "", "", ""}:
        return True

    return any(keyword in compact for keyword in SITE_NOISE_COMPACT_KEYWORDS)


def classify_metadata_line(line: str) -> str | None:
    compact = compact_arabic_text(line)

    if "تعديلاتالماده" in compact or "تعديلاتالمادة" in compact or "تعديالتالماده" in compact or "تعديالتالمادة" in compact:
        return "amendment"

    if "الاحكامالقضائيه" in compact or "الاحكامالقضائية" in compact or "االحكامالقضائيه" in compact or "االحكامالقضائية" in compact:
        return "case_law"

    if "التشريعاتالمرتبطه" in compact or "التشريعاتالمرتبطة" in compact:
        return "related_legislation"

    if "ارتباطاتالماده" in compact or "ارتباطاتالمادة" in compact:
        return "link"

    if compact.startswith("تفسير") or compact == "تفسير":
        return "interpretation"

    return None


def metadata_relation_from_line(line: str, relation_type: str) -> dict:
    clean_line = normalize_legal_line(line)
    count_match = re.search(r"([0-9٠-٩]+)", clean_line)
    count_text = ""

    if count_match:
        count_text = western_digits(count_match.group(1))

    title = METADATA_LABELS.get(relation_type, "بيانات مرتبطة")
    description = f"ورد في ملف ديوان التشريع والرأي: {clean_line}"

    if count_text:
        description += f" — العدد المشار إليه: {count_text}"

    return {
        "relation_type": relation_type,
        "title": title,
        "description": description,
        "reference_text": clean_line,
        "source_name": "ديوان التشريع والرأي",
        "source_url": "",
    }


def expand_mixed_article_header_lines(lines: list[str]) -> list[str]:
    """
    بعض ملفات ديوان التشريع والرأي تخرج السطر بهذا الشكل بعد الإصلاح:
        المادة 59 ارتباطات المادة
    وهذا يعني أن عنوان المادة والميتا داتا ظهرا في نفس السطر.
    نقسمه إلى:
        المادة 59
        ارتباطات المادة
    حتى يتعرف النظام على المادة ويحفظ الارتباطات كبيانات مرتبطة.
    """
    expanded: list[str] = []

    for line in lines:
        normalized = normalize_legal_line(line)

        match = re.match(
            r"^(?:المادة|مادة)\s*[\(\[]?\s*([0-9٠-٩]+)\s*[\)\]]?\s+(.+)$",
            normalized,
        )

        if match:
            article_number = western_digits(match.group(1))
            remainder = normalize_legal_line(match.group(2))

            # نقسم فقط إذا كان باقي السطر ميتاداتا/ضجيج وليس بداية نص المادة.
            if classify_metadata_line(remainder) or is_noise_line(remainder):
                expanded.append(f"المادة {article_number}")
                if remainder:
                    expanded.append(remainder)
                continue

        expanded.append(normalized)

    return expanded



def detect_article_header_line(line: str) -> tuple[bool, str, str]:
    """
    Detect article headers in several LOB/PDF extraction formats.

    Supported examples:
    - المادة 1
    - المادة (1)
    - مادة 1
    - 1المادة
    - 1 المادة
    - المادة 1 يبدأ النص هنا...
    - 1المادة يبدأ النص هنا...

    Returns: (is_header, article_number, payload_after_header)
    """
    normalized = normalize_legal_line(line)

    if not normalized:
        return False, "", ""

    if classify_metadata_line(normalized):
        return False, "", ""

    compact = compact_arabic_text(normalized)
    if any(keyword in compact for keyword in SITE_NOISE_COMPACT_KEYWORDS):
        return False, "", ""

    patterns = [
        r"^(?:المادة|مادة)\s*[\(\[]?\s*([0-9٠-٩]+)\s*[\)\]]?\s*[:：\-–—.]?\s*(.*)$",
        r"^([0-9٠-٩]+)\s*(?:المادة|مادة)\s*[:：\-–—.]?\s*(.*)$",
    ]

    for pattern in patterns:
        match = re.match(pattern, normalized)
        if not match:
            continue

        number = western_digits(match.group(1))
        payload = normalize_legal_line(match.group(2) if len(match.groups()) >= 2 else "")

        # Avoid wrongly treating table-of-content / metadata counters as article text.
        if payload and (classify_metadata_line(payload) or is_noise_line(payload)):
            payload = ""

        return True, number, payload

    return False, "", ""


def is_article_header_line(line: str) -> tuple[bool, str]:
    is_header, article_number, _payload = detect_article_header_line(line)
    return is_header, article_number


def split_legal_articles(extracted_text: str) -> list[dict]:
    """
    Robust legal-article splitter for Arabic official PDFs.

    Improvements:
    - Supports article headers with body text on the same line.
    - Supports RTL/PDF forms such as 1المادة.
    - Ignores metadata labels and site footer text.
    - Keeps relations separate from article body.
    - Handles long laws such as مجلة الأحكام العدلية without considering article count an error.
    """
    text = extracted_text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    raw_lines = text.split("\n")
    lines = [normalize_legal_line(line) for line in raw_lines]
    lines = expand_mixed_article_header_lines(lines)

    articles: list[dict] = []
    current_number: str | None = None
    current_body: list[str] = []
    current_relations: list[dict] = []
    pending_relations: list[dict] = []

    def flush_current():
        nonlocal current_number, current_body, current_relations
        if not current_number:
            return

        article_text = "\n".join(line for line in current_body if line).strip()
        if not article_text:
            current_number = None
            current_body = []
            current_relations = []
            return

        seen_relations: set[tuple[str, str]] = set()
        relations: list[dict] = []
        for relation in current_relations:
            key = (relation.get("relation_type", ""), relation.get("reference_text", ""))
            if key in seen_relations:
                continue
            seen_relations.add(key)
            relations.append(relation)

        articles.append(
            {
                "article_number": current_number,
                "article_title": "",
                "article_text": article_text,
                "article_text_clean": clean_article_text(article_text),
                "relations": relations,
            }
        )

        current_number = None
        current_body = []
        current_relations = []

    for raw_line in lines:
        line = normalize_legal_line(raw_line)
        if not line:
            continue

        relation_type = classify_metadata_line(line)
        if relation_type:
            relation_data = metadata_relation_from_line(line, relation_type)
            if current_number:
                current_relations.append(relation_data)
            else:
                pending_relations.append(relation_data)
            continue

        is_header, article_number, payload = detect_article_header_line(line)
        if is_header:
            flush_current()
            current_number = article_number
            current_body = []
            current_relations = list(pending_relations)
            pending_relations = []
            if payload and not is_noise_line(payload):
                current_body.append(payload)
            continue

        if is_noise_line(line):
            continue

        # Lines before the first article are metadata/title lines, not article body.
        if not current_number:
            continue

        current_body.append(line)

    flush_current()

    # Deduplicate exact duplicate article numbers by keeping the longest text.
    by_number: dict[str, dict] = {}
    for article in articles:
        number = str(article.get("article_number", "")).strip()
        if not number:
            continue
        existing = by_number.get(number)
        if not existing or len(article.get("article_text", "")) > len(existing.get("article_text", "")):
            by_number[number] = article

    def sort_key(item: dict):
        try:
            return int(item.get("article_number") or 0)
        except Exception:
            return 10**9

    return sorted(by_number.values(), key=sort_key)

def create_article_relations(db, article: LegalArticle, relations: list[dict]):
    for relation_data in relations or []:
        relation = LegalArticleRelation(
            article_id=article.id,
            relation_type=relation_data.get("relation_type", "raw_note"),
            title=relation_data.get("title", ""),
            description=relation_data.get("description", ""),
            reference_text=relation_data.get("reference_text", ""),
            source_name=relation_data.get("source_name", ""),
            source_url=relation_data.get("source_url", ""),
            created_at=datetime.utcnow(),
        )

        db.add(relation)


def delete_articles_for_document(db, document_id: int):
    """
    حذف جميع المواد القانونية المرتبطة بتشريع محدد مع جميع البيانات التابعة لها:
    - علاقات المادة: تعديلات، أحكام، تشريعات مرتبطة، تفسيرات
    - نسخ المادة
    - مواضيع وكلمات مفتاحية المادة
    - المواد نفسها
    """
    db.execute(
        text(
            """
            DELETE FROM legal_article_relations
            WHERE article_id IN (
                SELECT id FROM legal_articles WHERE document_id = :document_id
            )
            """
        ),
        {"document_id": document_id},
    )

    db.execute(
        text(
            """
            DELETE FROM legal_article_versions
            WHERE article_id IN (
                SELECT id FROM legal_articles WHERE document_id = :document_id
            )
            """
        ),
        {"document_id": document_id},
    )

    db.execute(
        text(
            """
            DELETE FROM legal_article_topics
            WHERE article_id IN (
                SELECT id FROM legal_articles WHERE document_id = :document_id
            )
            """
        ),
        {"document_id": document_id},
    )

    db.execute(
        text(
            """
            DELETE FROM legal_article_keywords
            WHERE article_id IN (
                SELECT id FROM legal_articles WHERE document_id = :document_id
            )
            """
        ),
        {"document_id": document_id},
    )

    db.execute(
        text("DELETE FROM legal_articles WHERE document_id = :document_id"),
        {"document_id": document_id},
    )




def _safe_json_loads(value: str):
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _create_background_job(
    db,
    *,
    country_id=None,
    staff_user_id=None,
    filename: str,
    file_path: str,
    job_type: str,
    document_id: int | None = None,
    extra: dict | None = None,
):
    payload = {
        "job_type": job_type,
        "document_id": document_id,
        **(extra or {}),
    }

    job = LegalImportJob(
        country_id=country_id,
        staff_user_id=staff_user_id,
        filename=filename,
        file_path=file_path,
        status="pending",
        result_json=json.dumps(payload, ensure_ascii=False),
        error_message="",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


REVIEWER_JOB_TYPES = [
    "quality_check",
    "quality_repair",
    "quality_check_batch",
    "quality_repair_batch",
]


def _latest_reviewer_jobs(db, document_id: int | None = None, limit: int = 120):
    jobs = (
        db.query(LegalImportJob)
        .order_by(LegalImportJob.created_at.desc())
        .limit(limit)
        .all()
    )

    filtered = []

    for job in jobs:
        data = _safe_json_loads(job.result_json)
        job_type = data.get("job_type")

        if job_type not in REVIEWER_JOB_TYPES:
            continue

        if document_id is not None:
            document_ids = [str(item) for item in data.get("document_ids", [])]
            current_document_id = str(data.get("document_id", ""))
            if str(document_id) != current_document_id and str(document_id) not in document_ids:
                continue

        filtered.append({
            "id": job.id,
            "type": job_type,
            "status": job.status,
            "filename": job.filename,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "document_id": data.get("document_id"),
            "document_ids": data.get("document_ids", []),
            "document_title": data.get("document_title", ""),
            "document_titles": data.get("document_titles", []),
            "progress": data.get("progress", []),
            "current_step": data.get("current_step", ""),
            "processed_count": data.get("processed_count", 0),
            "total_count": data.get("total_count", 0),
            "per_document_results": data.get("per_document_results", []),
            "report": data.get("report"),
            "repair_result": data.get("repair_result"),
        })

    return filtered


def _latest_completed_quality_report(db, document_id: int):
    jobs = _latest_reviewer_jobs(db, document_id=document_id, limit=100)

    for job in jobs:
        if job["type"] in ["quality_check", "quality_repair"] and job["status"] in ["completed", "completed_with_warnings"]:
            report = job.get("report")
            if report:
                return report

    return None


def process_quality_check_job(job_id: int, document_id: int):
    from app.services.legal_quality_checker import check_document_quality

    db = SessionLocal()
    try:
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if job:
            job.status = "processing"
            job.updated_at = datetime.utcnow()
            db.commit()

        if not document:
            if job:
                data = _safe_json_loads(job.result_json)
                data["error"] = "document_not_found"
                job.status = "failed"
                job.error_message = "document_not_found"
                job.result_json = json.dumps(data, ensure_ascii=False)
                job.updated_at = datetime.utcnow()
                db.commit()
            return

        report = check_document_quality(db, document_id)
        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        data = _safe_json_loads(job.result_json if job else "{}")
        data.update({
            "job_type": "quality_check",
            "document_id": document_id,
            "document_title": document.title_ar,
            "report": report,
            "completed_at": datetime.utcnow().isoformat(),
        })

        if job:
            critical = int(summary.get("critical_count") or 0)
            warning = int(summary.get("warning_count") or 0)
            job.status = "completed_with_warnings" if (critical or warning) else "completed"
            job.result_json = json.dumps(data, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.commit()

    except Exception as exc:
        db.rollback()
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            data = _safe_json_loads(job.result_json)
            data["error"] = str(exc)
            job.status = "failed"
            job.error_message = str(exc)
            job.result_json = json.dumps(data, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def process_quality_repair_job(job_id: int, document_id: int, staff_id: int):
    from app.services.legal_quality_checker import check_document_quality, repair_document_quality

    db = SessionLocal()
    try:
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if job:
            job.status = "processing"
            job.updated_at = datetime.utcnow()
            db.commit()

        if not document:
            if job:
                data = _safe_json_loads(job.result_json)
                data["error"] = "document_not_found"
                job.status = "failed"
                job.error_message = "document_not_found"
                job.result_json = json.dumps(data, ensure_ascii=False)
                job.updated_at = datetime.utcnow()
                db.commit()
            return

        repair_result = repair_document_quality(db, document_id, staff_id)
        db.commit()

        report = check_document_quality(db, document_id)
        summary = report.get("summary", {}) if isinstance(report, dict) else {}

        data = _safe_json_loads(job.result_json if job else "{}")
        data.update({
            "job_type": "quality_repair",
            "document_id": document_id,
            "document_title": document.title_ar,
            "repair_result": repair_result,
            "report": report,
            "completed_at": datetime.utcnow().isoformat(),
        })

        if job:
            critical = int(summary.get("critical_count") or 0)
            warning = int(summary.get("warning_count") or 0)
            job.status = "completed_with_warnings" if (critical or warning) else "completed"
            job.result_json = json.dumps(data, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.commit()

    except Exception as exc:
        db.rollback()
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            data = _safe_json_loads(job.result_json)
            data["error"] = str(exc)
            job.status = "failed"
            job.error_message = str(exc)
            job.result_json = json.dumps(data, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _update_reviewer_job_progress(db, job_id: int, message: str, *, status: str | None = None, extra: dict | None = None):
    job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
    if not job:
        return

    data = _safe_json_loads(job.result_json)
    progress = data.get("progress") or []
    progress.append({
        "time": datetime.utcnow().isoformat(),
        "message": message,
    })
    data["progress"] = progress[-80:]
    data["current_step"] = message
    if extra:
        data.update(extra)
    if status:
        job.status = status
    job.result_json = json.dumps(data, ensure_ascii=False)
    job.updated_at = datetime.utcnow()
    db.commit()


def _build_bulk_issue_details(report: dict, max_items_per_level: int = 80) -> dict:
    """
    Build a detailed, UI-friendly issue report for one document inside bulk review.
    This prevents the bulk reviewer from only saying "has errors" and instead lists
    every detected issue with article number, reason, and suggested repair.
    """
    issues = report.get("issues", []) if isinstance(report, dict) else []
    critical_errors = []
    warnings = []
    info_items = []

    for issue in issues:
        item = {
            "level": issue.get("level", ""),
            "scope": issue.get("scope", ""),
            "article_id": issue.get("article_id"),
            "article_number": issue.get("article_number") or "",
            "message": issue.get("message", ""),
            "repair_action": issue.get("repair_action", "") or "تحتاج مراجعة مسؤول البيانات.",
        }

        if item["level"] == "critical":
            critical_errors.append(item)
        elif item["level"] == "warning":
            warnings.append(item)
        else:
            info_items.append(item)

    repair_plan = report.get("repair_plan", []) if isinstance(report, dict) else []
    missing_numbers = report.get("missing_numbers", []) if isinstance(report, dict) else []

    return {
        "critical_errors": critical_errors[:max_items_per_level],
        "warnings": warnings[:max_items_per_level],
        "info_items": info_items[:max_items_per_level],
        "critical_errors_total": len(critical_errors),
        "warnings_total": len(warnings),
        "info_total": len(info_items),
        "repair_plan": repair_plan,
        "missing_numbers": missing_numbers[:200],
        "missing_numbers_total": len(missing_numbers),
        "has_more_critical": len(critical_errors) > max_items_per_level,
        "has_more_warnings": len(warnings) > max_items_per_level,
        "has_more_info": len(info_items) > max_items_per_level,
    }


def process_quality_check_batch_job(job_id: int, document_ids: list[int]):
    from app.services.legal_quality_checker import check_document_quality

    db = SessionLocal()
    try:
        total_count = len(document_ids)
        _update_reviewer_job_progress(
            db,
            job_id,
            f"بدأ تدقيق {total_count} تشريع/تشريعات بالخلفية.",
            status="processing",
            extra={"total_count": total_count, "processed_count": 0, "per_document_results": []},
        )

        per_document_results = []
        unresolved_any = False
        failed_any = False

        for index, document_id in enumerate(document_ids, start=1):
            document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
            if not document:
                failed_any = True
                per_document_results.append({
                    "document_id": document_id,
                    "title": "تشريع غير موجود",
                    "status": "failed",
                    "message": "لم يتم العثور على التشريع.",
                })
                _update_reviewer_job_progress(
                    db,
                    job_id,
                    f"فشل تدقيق التشريع رقم {document_id}: غير موجود.",
                    extra={"processed_count": index, "per_document_results": per_document_results},
                )
                continue

            _update_reviewer_job_progress(
                db,
                job_id,
                f"جاري تدقيق: {document.title_ar}",
                extra={"processed_count": index - 1, "per_document_results": per_document_results},
            )

            try:
                report = check_document_quality(db, document.id)
                summary = report.get("summary", {}) if isinstance(report, dict) else {}
                critical_count = int(summary.get("critical_count") or 0)
                warning_count = int(summary.get("warning_count") or 0)
                status = "needs_review" if (critical_count or warning_count) else "clean"
                if critical_count or warning_count:
                    unresolved_any = True

                issue_details = _build_bulk_issue_details(report)
                per_document_results.append({
                    "document_id": document.id,
                    "title": document.title_ar,
                    "status": status,
                    "critical_count": critical_count,
                    "warning_count": warning_count,
                    "articles_count": int(summary.get("articles_count") or 0),
                    "critical_errors": issue_details["critical_errors"],
                    "warnings": issue_details["warnings"],
                    "info_items": issue_details["info_items"],
                    "critical_errors_total": issue_details["critical_errors_total"],
                    "warnings_total": issue_details["warnings_total"],
                    "info_total": issue_details["info_total"],
                    "has_more_critical": issue_details["has_more_critical"],
                    "has_more_warnings": issue_details["has_more_warnings"],
                    "has_more_info": issue_details["has_more_info"],
                    "repair_plan": issue_details["repair_plan"],
                    "missing_numbers": issue_details["missing_numbers"],
                    "missing_numbers_total": issue_details["missing_numbers_total"],
                    "report": report,
                })

                _update_reviewer_job_progress(
                    db,
                    job_id,
                    f"اكتمل تدقيق {document.title_ar}: أخطاء حرجة {critical_count}، تحذيرات {warning_count}.",
                    extra={"processed_count": index, "per_document_results": per_document_results},
                )
            except Exception as exc:
                failed_any = True
                per_document_results.append({
                    "document_id": document.id,
                    "title": document.title_ar,
                    "status": "failed",
                    "message": str(exc),
                })
                _update_reviewer_job_progress(
                    db,
                    job_id,
                    f"فشل تدقيق {document.title_ar}: {exc}",
                    extra={"processed_count": index, "per_document_results": per_document_results},
                )

        final_status = "completed"
        if failed_any:
            final_status = "completed_with_errors"
        elif unresolved_any:
            final_status = "completed_with_warnings"

        _update_reviewer_job_progress(
            db,
            job_id,
            "انتهى التدقيق الجماعي.",
            status=final_status,
            extra={
                "processed_count": total_count,
                "total_count": total_count,
                "per_document_results": per_document_results,
                "completed_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as exc:
        db.rollback()
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            data = _safe_json_loads(job.result_json)
            data["error"] = str(exc)
            job.status = "failed"
            job.error_message = str(exc)
            job.result_json = json.dumps(data, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def process_quality_repair_batch_job(job_id: int, document_ids: list[int], staff_id: int):
    from app.services.legal_quality_checker import check_document_quality, repair_document_quality

    db = SessionLocal()
    try:
        total_count = len(document_ids)
        _update_reviewer_job_progress(
            db,
            job_id,
            f"بدأت معالجة أخطاء {total_count} تشريع/تشريعات بالخلفية.",
            status="processing",
            extra={"total_count": total_count, "processed_count": 0, "per_document_results": []},
        )

        per_document_results = []
        unresolved_any = False
        failed_any = False

        for index, document_id in enumerate(document_ids, start=1):
            document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
            if not document:
                failed_any = True
                per_document_results.append({
                    "document_id": document_id,
                    "title": "تشريع غير موجود",
                    "status": "failed",
                    "message": "لم يتم العثور على التشريع.",
                })
                _update_reviewer_job_progress(
                    db,
                    job_id,
                    f"فشل معالجة التشريع رقم {document_id}: غير موجود.",
                    extra={"processed_count": index, "per_document_results": per_document_results},
                )
                continue

            _update_reviewer_job_progress(
                db,
                job_id,
                f"جاري معالجة أخطاء: {document.title_ar}",
                extra={"processed_count": index - 1, "per_document_results": per_document_results},
            )

            try:
                repair_result = repair_document_quality(db, document.id, staff_id)
                db.commit()
                report = check_document_quality(db, document.id)
                summary = report.get("summary", {}) if isinstance(report, dict) else {}
                critical_count = int(summary.get("critical_count") or 0)
                warning_count = int(summary.get("warning_count") or 0)
                status = "repaired_clean" if not (critical_count or warning_count) else "repaired_with_unresolved_issues"
                if critical_count or warning_count:
                    unresolved_any = True

                issue_details = _build_bulk_issue_details(report)
                unresolved_items = issue_details["critical_errors"] + issue_details["warnings"]

                per_document_results.append({
                    "document_id": document.id,
                    "title": document.title_ar,
                    "status": status,
                    "critical_count": critical_count,
                    "warning_count": warning_count,
                    "articles_count": int(summary.get("articles_count") or 0),
                    "critical_errors": issue_details["critical_errors"],
                    "warnings": issue_details["warnings"],
                    "info_items": issue_details["info_items"],
                    "critical_errors_total": issue_details["critical_errors_total"],
                    "warnings_total": issue_details["warnings_total"],
                    "info_total": issue_details["info_total"],
                    "has_more_critical": issue_details["has_more_critical"],
                    "has_more_warnings": issue_details["has_more_warnings"],
                    "has_more_info": issue_details["has_more_info"],
                    "repair_plan": issue_details["repair_plan"],
                    "missing_numbers": issue_details["missing_numbers"],
                    "missing_numbers_total": issue_details["missing_numbers_total"],
                    "repair_result": repair_result,
                    "unresolved_items": unresolved_items[:80],
                    "report": report,
                })

                _update_reviewer_job_progress(
                    db,
                    job_id,
                    f"انتهت معالجة {document.title_ar}: متبقي أخطاء حرجة {critical_count}، تحذيرات {warning_count}.",
                    extra={"processed_count": index, "per_document_results": per_document_results},
                )
            except Exception as exc:
                db.rollback()
                failed_any = True
                per_document_results.append({
                    "document_id": document.id,
                    "title": document.title_ar,
                    "status": "failed",
                    "message": str(exc),
                })
                _update_reviewer_job_progress(
                    db,
                    job_id,
                    f"فشلت معالجة {document.title_ar}: {exc}",
                    extra={"processed_count": index, "per_document_results": per_document_results},
                )

        final_status = "completed"
        if failed_any:
            final_status = "completed_with_errors"
        elif unresolved_any:
            final_status = "completed_with_unresolved_issues"

        _update_reviewer_job_progress(
            db,
            job_id,
            "انتهت المعالجة الجماعية.",
            status=final_status,
            extra={
                "processed_count": total_count,
                "total_count": total_count,
                "per_document_results": per_document_results,
                "completed_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as exc:
        db.rollback()
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            data = _safe_json_loads(job.result_json)
            data["error"] = str(exc)
            job.status = "failed"
            job.error_message = str(exc)
            job.result_json = json.dumps(data, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _create_batch_reviewer_job(db, *, staff, documents, job_type: str, filename: str):
    document_ids = [doc.id for doc in documents]
    document_titles = [doc.title_ar for doc in documents]
    return _create_background_job(
        db,
        country_id=None,
        staff_user_id=staff.id,
        filename=filename,
        file_path="",
        job_type=job_type,
        document_id=None,
        extra={
            "document_ids": document_ids,
            "document_titles": document_titles,
            "total_count": len(document_ids),
            "processed_count": 0,
            "per_document_results": [],
            "progress": [{"time": datetime.utcnow().isoformat(), "message": "تم إنشاء العملية وهي بانتظار التنفيذ."}],
            "current_step": "بانتظار التنفيذ",
        },
    )


@router.get("/internal/legal-reviewer", response_class=HTMLResponse)
async def legal_reviewer_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()
    try:
        documents = (
            db.query(LegalDocument)
            .order_by(LegalDocument.updated_at.desc(), LegalDocument.created_at.desc())
            .all()
        )
        counts = {}
        for document in documents:
            counts[document.id] = db.query(LegalArticle).filter(LegalArticle.document_id == document.id).count()

        reviewer_jobs = _latest_reviewer_jobs(db, document_id=None, limit=30)

        return templates.TemplateResponse(
            request=request,
            name="internal/legal_reviewer.html",
            context={
                "request": request,
                "staff": staff,
                "documents": documents,
                "counts": counts,
                "report": None,
                "selected_document": None,
                "reviewer_jobs": reviewer_jobs,
                "latest_job": None,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )
    finally:
        db.close()


@router.get("/internal/legal-reviewer/{document_id}", response_class=HTMLResponse)
async def legal_reviewer_document(request: Request, document_id: int):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()
    try:
        documents = (
            db.query(LegalDocument)
            .order_by(LegalDocument.updated_at.desc(), LegalDocument.created_at.desc())
            .all()
        )
        counts = {doc.id: db.query(LegalArticle).filter(LegalArticle.document_id == doc.id).count() for doc in documents}
        selected_document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        reviewer_jobs = _latest_reviewer_jobs(db, document_id=document_id, limit=30)
        latest_job = reviewer_jobs[0] if reviewer_jobs else None
        report = _latest_completed_quality_report(db, document_id)

        return templates.TemplateResponse(
            request=request,
            name="internal/legal_reviewer.html",
            context={
                "request": request,
                "staff": staff,
                "documents": documents,
                "counts": counts,
                "report": report,
                "selected_document": selected_document,
                "reviewer_jobs": reviewer_jobs,
                "latest_job": latest_job,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )
    finally:
        db.close()


@router.post("/internal/legal-reviewer/{document_id}/check-background")
async def legal_reviewer_check_background(
    request: Request,
    background_tasks: BackgroundTasks,
    document_id: int,
):
    staff = get_current_staff_optional(request)

    if not staff:
        return JSONResponse({"ok": False, "error": "not_logged_in"}, status_code=401)

    if not can_manage_legal_documents(staff):
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)

    db = SessionLocal()
    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
        if not document:
            return JSONResponse({"ok": False, "error": "document_not_found"}, status_code=404)

        job = _create_background_job(
            db,
            country_id=document.country_id,
            staff_user_id=staff.id,
            filename=f"تدقيق التشريع: {document.title_ar}",
            file_path=document.uploaded_file_path or "",
            job_type="quality_check",
            document_id=document.id,
            extra={"document_title": document.title_ar},
        )

        background_tasks.add_task(process_quality_check_job, job.id, document.id)

        return JSONResponse({
            "ok": True,
            "message": "بدأ تدقيق التشريع بالخلفية. يمكنك متابعة استخدام الموقع.",
            "job_id": job.id,
            "status": job.status,
        })
    finally:
        db.close()


@router.post("/internal/legal-reviewer/{document_id}/repair")
@router.post("/internal/legal-reviewer/{document_id}/repair-background")
async def legal_reviewer_repair_background(
    request: Request,
    background_tasks: BackgroundTasks,
    document_id: int,
):
    staff = get_current_staff_optional(request)

    if not staff:
        return JSONResponse({"ok": False, "error": "not_logged_in"}, status_code=401)

    if not can_manage_legal_documents(staff):
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)

    db = SessionLocal()
    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
        if not document:
            return JSONResponse({"ok": False, "error": "document_not_found"}, status_code=404)

        job = _create_background_job(
            db,
            country_id=document.country_id,
            staff_user_id=staff.id,
            filename=f"معالجة أخطاء التشريع: {document.title_ar}",
            file_path=document.uploaded_file_path or "",
            job_type="quality_repair",
            document_id=document.id,
            extra={"document_title": document.title_ar},
        )

        background_tasks.add_task(process_quality_repair_job, job.id, document.id, staff.id)

        return JSONResponse({
            "ok": True,
            "message": "بدأت معالجة أخطاء التشريع بالخلفية. يمكنك متابعة استخدام الموقع.",
            "job_id": job.id,
            "status": job.status,
        })
    finally:
        db.close()


@router.post("/internal/legal-reviewer/check-selected-background")
async def legal_reviewer_check_selected_background(
    request: Request,
    background_tasks: BackgroundTasks,
    document_ids: list[int] = Form(default=[]),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return JSONResponse({"ok": False, "error": "not_logged_in"}, status_code=401)

    if not can_manage_legal_documents(staff):
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)

    document_ids = list(dict.fromkeys([int(item) for item in document_ids if int(item) > 0]))
    if not document_ids:
        return JSONResponse({"ok": False, "error": "no_documents_selected"}, status_code=400)

    db = SessionLocal()
    try:
        documents = (
            db.query(LegalDocument)
            .filter(LegalDocument.id.in_(document_ids))
            .order_by(LegalDocument.title_ar.asc())
            .all()
        )

        if not documents:
            return JSONResponse({"ok": False, "error": "documents_not_found"}, status_code=404)

        job = _create_batch_reviewer_job(
            db,
            staff=staff,
            documents=documents,
            job_type="quality_check_batch",
            filename=f"تدقيق {len(documents)} تشريع/تشريعات محددة",
        )

        background_tasks.add_task(process_quality_check_batch_job, job.id, [doc.id for doc in documents])

        return JSONResponse({
            "ok": True,
            "message": f"بدأ تدقيق {len(documents)} تشريع/تشريعات بالخلفية.",
            "job_id": job.id,
            "status": job.status,
        })
    finally:
        db.close()


@router.post("/internal/legal-reviewer/check-all-background")
async def legal_reviewer_check_all_background(
    request: Request,
    background_tasks: BackgroundTasks,
):
    staff = get_current_staff_optional(request)

    if not staff:
        return JSONResponse({"ok": False, "error": "not_logged_in"}, status_code=401)

    if not can_manage_legal_documents(staff):
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)

    db = SessionLocal()
    try:
        documents = (
            db.query(LegalDocument)
            .order_by(LegalDocument.title_ar.asc())
            .all()
        )

        if not documents:
            return JSONResponse({"ok": False, "error": "no_documents"}, status_code=400)

        job = _create_batch_reviewer_job(
            db,
            staff=staff,
            documents=documents,
            job_type="quality_check_batch",
            filename=f"تدقيق جميع التشريعات ({len(documents)})",
        )

        background_tasks.add_task(process_quality_check_batch_job, job.id, [doc.id for doc in documents])

        return JSONResponse({
            "ok": True,
            "message": f"بدأ تدقيق جميع التشريعات وعددها {len(documents)} بالخلفية.",
            "job_id": job.id,
            "status": job.status,
        })
    finally:
        db.close()


@router.post("/internal/legal-reviewer/repair-selected-background")
async def legal_reviewer_repair_selected_background(
    request: Request,
    background_tasks: BackgroundTasks,
    document_ids: list[int] = Form(default=[]),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return JSONResponse({"ok": False, "error": "not_logged_in"}, status_code=401)

    if not can_manage_legal_documents(staff):
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)

    document_ids = list(dict.fromkeys([int(item) for item in document_ids if int(item) > 0]))
    if not document_ids:
        return JSONResponse({"ok": False, "error": "no_documents_selected"}, status_code=400)

    db = SessionLocal()
    try:
        documents = (
            db.query(LegalDocument)
            .filter(LegalDocument.id.in_(document_ids))
            .order_by(LegalDocument.title_ar.asc())
            .all()
        )

        if not documents:
            return JSONResponse({"ok": False, "error": "documents_not_found"}, status_code=404)

        job = _create_batch_reviewer_job(
            db,
            staff=staff,
            documents=documents,
            job_type="quality_repair_batch",
            filename=f"معالجة أخطاء {len(documents)} تشريع/تشريعات محددة",
        )

        background_tasks.add_task(process_quality_repair_batch_job, job.id, [doc.id for doc in documents], staff.id)

        return JSONResponse({
            "ok": True,
            "message": f"بدأت معالجة أخطاء {len(documents)} تشريع/تشريعات بالخلفية.",
            "job_id": job.id,
            "status": job.status,
        })
    finally:
        db.close()


@router.post("/internal/legal-reviewer/repair-all-background")
async def legal_reviewer_repair_all_background(
    request: Request,
    background_tasks: BackgroundTasks,
):
    staff = get_current_staff_optional(request)

    if not staff:
        return JSONResponse({"ok": False, "error": "not_logged_in"}, status_code=401)

    if not can_manage_legal_documents(staff):
        return JSONResponse({"ok": False, "error": "not_allowed"}, status_code=403)

    db = SessionLocal()
    try:
        documents = (
            db.query(LegalDocument)
            .order_by(LegalDocument.title_ar.asc())
            .all()
        )

        if not documents:
            return JSONResponse({"ok": False, "error": "no_documents"}, status_code=400)

        job = _create_batch_reviewer_job(
            db,
            staff=staff,
            documents=documents,
            job_type="quality_repair_batch",
            filename=f"معالجة أخطاء جميع التشريعات ({len(documents)})",
        )

        background_tasks.add_task(process_quality_repair_batch_job, job.id, [doc.id for doc in documents], staff.id)

        return JSONResponse({
            "ok": True,
            "message": f"بدأت معالجة أخطاء جميع التشريعات وعددها {len(documents)} بالخلفية.",
            "job_id": job.id,
            "status": job.status,
        })
    finally:
        db.close()


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
            active_documents_query(db)
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
                "is_archived_page": False,
            },
        )

    finally:
        db.close()


@router.get("/internal/legal-documents/archived", response_class=HTMLResponse)
async def legal_documents_archived(request: Request):
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
            archived_documents_query(db)
            .order_by(LegalDocument.updated_at.desc(), LegalDocument.created_at.desc())
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
                "is_archived_page": True,
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
    # All newly created legal documents must be reviewed before they appear to the assistant.
    status = "active"
    review_status = "pending_review"
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


def process_pdf_import_job(job_id: int, staff_id: int, document_id: int, file_path: str, auto_split_articles: str = "yes"):
    db = SessionLocal()
    try:
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
        if job:
            job.status = "processing"
            job.updated_at = datetime.utcnow()
            db.commit()
        if not document:
            if job:
                job.status = "failed"
                job.error_message = "document_not_found"
                job.updated_at = datetime.utcnow()
                db.commit()
            return

        extracted_text = extract_text_from_pdf(file_path)
        created_articles = 0
        if auto_split_articles == "yes" and extracted_text:
            articles = split_legal_articles(extracted_text)
            for article_data in articles:
                article = LegalArticle(
                    document_id=document.id,
                    country_id=document.country_id,
                    article_number=article_data["article_number"],
                    article_title=article_data.get("article_title", ""),
                    article_text=article_data["article_text"],
                    article_text_clean=article_data.get("article_text_clean") or clean_article_text(article_data["article_text"]),
                    chapter="",
                    section="",
                    status="active",
                    review_status="pending_review",
                    effective_date=document.effective_date,
                    repealed_date="",
                    notes="تم استخراج هذه المادة تلقائيًا من ملف PDF وتحتاج مراجعة.",
                    source_confidence=document.source_confidence,
                    last_verified_at=None,
                    created_by_id=staff_id,
                    updated_by_id=staff_id,
                    reviewed_by_id=None,
                    reviewed_at=None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(article)
                db.flush()
                db.add(
                    LegalArticleVersion(
                        article_id=article.id,
                        version_number=1,
                        article_text=article.article_text,
                        article_text_clean=article.article_text_clean,
                        change_reason="Auto imported from PDF",
                        status="active",
                        effective_date=article.effective_date,
                        created_by_id=staff_id,
                        created_at=datetime.utcnow(),
                    )
                )
                create_article_relations(db=db, article=article, relations=article_data.get("relations", []))
                created_articles += 1

        if job:
            job.status = "completed"
            job.result_json = json.dumps(
                {
                    "document_id": document.id,
                    "filename": job.filename,
                    "extracted_text_length": len(extracted_text),
                    "created_articles": created_articles,
                    "metadata_relations_supported": True,
                    "auto_split_articles": auto_split_articles,
                },
                ensure_ascii=False,
            )
            job.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/internal/legal-documents/upload-pdf")
async def legal_document_upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
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
    status = "active"
    review_status = "pending_review"
    source_confidence = source_confidence.strip() or "official"

    if not title_ar:
        return RedirectResponse(url="/internal/legal-documents?error=missing_title", status_code=303)
    if document_type not in DOCUMENT_TYPES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_document_type", status_code=303)
    if source_confidence not in SOURCE_CONFIDENCE:
        source_confidence = "official"
    if not (pdf_file.filename or "").lower().endswith(".pdf"):
        return RedirectResponse(url="/internal/legal-documents?error=not_pdf", status_code=303)

    file_bytes = await pdf_file.read()
    if not file_bytes:
        return RedirectResponse(url="/internal/legal-documents?error=empty_file", status_code=303)
    if len(file_bytes) > 30 * 1024 * 1024:
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
            status="pending",
            result_json="",
            error_message="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(import_job)
        db.commit()
        db.refresh(document)
        db.refresh(import_job)
        background_tasks.add_task(process_pdf_import_job, import_job.id, staff.id, document.id, stored_path, auto_split_articles)
        return RedirectResponse(url="/internal/legal-documents?success=pdf_import_started", status_code=303)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def process_bulk_zip_import_job(job_id: int, staff_id: int, country_id: int, zip_path: str):
    db = SessionLocal()
    try:
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            job.status = "processing"
            job.updated_at = datetime.utcnow()
            db.commit()

        upload_dir = ensure_legal_upload_dir()
        imported = []
        failed = []

        with zipfile.ZipFile(zip_path, "r") as archive:
            members = [m for m in archive.namelist() if m.lower().endswith(".pdf") and not m.endswith("/")]
            for member in members:
                try:
                    original_name = Path(member).name
                    document_title = Path(original_name).stem.strip() or original_name
                    stored_name = f"bulk_{int(time.time())}_{safe_filename(original_name)}"
                    output_path = os.path.join(upload_dir, stored_name)
                    with archive.open(member) as source, open(output_path, "wb") as target:
                        target.write(source.read())

                    document = LegalDocument(
                        country_id=country_id,
                        jurisdiction_id=None,
                        title_ar=document_title,
                        title_en="",
                        document_type="law",
                        source_name="ديوان التشريع والرأي الأردني",
                        source_url="https://www.lob.gov.jo",
                        official_reference="",
                        issue_date="",
                        effective_date="",
                        status="active",
                        review_status="pending_review",
                        source_confidence="official",
                        uploaded_file_path=output_path,
                        created_by_id=staff_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(document)
                    db.flush()

                    text_content = extract_text_from_pdf(output_path)
                    articles = split_legal_articles(text_content)
                    created_articles = 0
                    for article_data in articles:
                        article = LegalArticle(
                            document_id=document.id,
                            country_id=document.country_id,
                            article_number=article_data["article_number"],
                            article_title=article_data.get("article_title", ""),
                            article_text=article_data["article_text"],
                            article_text_clean=article_data.get("article_text_clean") or clean_article_text(article_data["article_text"]),
                            chapter="",
                            section="",
                            status="active",
                            review_status="pending_review",
                            effective_date=document.effective_date,
                            repealed_date="",
                            notes="",
                            source_confidence=document.source_confidence,
                            created_by_id=staff_id,
                            updated_by_id=staff_id,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                        db.add(article)
                        db.flush()
                        create_article_relations(db, article, article_data.get("relations", []))
                        db.add(
                            LegalArticleVersion(
                                article_id=article.id,
                                version_number=1,
                                article_text=article.article_text,
                                article_text_clean=article.article_text_clean,
                                change_reason="Bulk ZIP extraction",
                                status="active",
                                effective_date=article.effective_date,
                                created_by_id=staff_id,
                                created_at=datetime.utcnow(),
                            )
                        )
                        created_articles += 1

                    imported.append({"filename": original_name, "document_id": document.id, "articles": created_articles})
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    failed.append({"filename": member, "error": str(exc)})

        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            job.status = "completed" if not failed else "completed_with_errors"
            job.result_json = json.dumps({"imported": imported, "failed": failed}, ensure_ascii=False)
            job.error_message = "" if not failed else f"فشل {len(failed)} ملف/ملفات أثناء الاستيراد."
            job.updated_at = datetime.utcnow()
            db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(LegalImportJob).filter(LegalImportJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/internal/legal-documents/upload-zip")
async def legal_documents_upload_zip(
    request: Request,
    background_tasks: BackgroundTasks,
    country_id: int = Form(...),
    zip_file: UploadFile = File(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    filename = zip_file.filename or "legal-bulk.zip"
    if not filename.lower().endswith(".zip"):
        return RedirectResponse(url="/internal/legal-documents?error=not_zip", status_code=303)

    upload_dir = ensure_legal_upload_dir()
    stored_filename = f"bulk_{int(time.time())}_{safe_filename(filename)}"
    stored_path = os.path.join(upload_dir, stored_filename)
    content = await zip_file.read()
    if not content:
        return RedirectResponse(url="/internal/legal-documents?error=empty_file", status_code=303)
    with open(stored_path, "wb") as f:
        f.write(content)

    db = SessionLocal()
    try:
        country = db.query(Country).filter(Country.id == country_id).first()
        if not country:
            return RedirectResponse(url="/internal/legal-documents?error=country_not_found", status_code=303)

        job = LegalImportJob(
            country_id=country.id,
            staff_user_id=staff.id,
            filename=filename,
            file_path=stored_path,
            status="pending",
            result_json="",
            error_message="",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        background_tasks.add_task(process_bulk_zip_import_job, job.id, staff.id, country.id, stored_path)
        return RedirectResponse(url="/internal/legal-documents?success=zip_import_started", status_code=303)
    finally:
        db.close()


@router.post("/internal/legal-documents/update")
async def legal_document_update(
    request: Request,
    document_id: int = Form(...),
    title_ar: str = Form(...),
    title_en: str = Form(""),
    document_type: str = Form(...),
    source_name: str = Form(""),
    source_url: str = Form(""),
    official_reference: str = Form(""),
    issue_date: str = Form(""),
    effective_date: str = Form(""),
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
    source_confidence = source_confidence.strip()

    if not title_ar:
        return RedirectResponse(url="/internal/legal-documents?error=missing_title", status_code=303)

    if document_type not in DOCUMENT_TYPES:
        return RedirectResponse(url="/internal/legal-documents?error=invalid_document_type", status_code=303)

    if source_confidence not in SOURCE_CONFIDENCE:
        source_confidence = "medium"

    db = SessionLocal()

    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if not document:
            return RedirectResponse(url="/internal/legal-documents?error=document_not_found", status_code=303)

        document.title_ar = title_ar
        document.title_en = title_en
        document.document_type = document_type
        document.source_name = source_name
        document.source_url = source_url
        document.official_reference = official_reference
        document.issue_date = issue_date
        document.effective_date = effective_date
        document.source_confidence = source_confidence
        document.status = "active"
        document.review_status = "pending_review"
        document.reviewed_by_id = None
        document.reviewed_at = None
        document.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/legal-documents?success=updated_pending_review", status_code=303)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.post("/internal/legal-documents/delete-articles")
async def legal_document_delete_articles(
    request: Request,
    document_id: int = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if not document:
            return RedirectResponse(url="/internal/legal-documents?error=document_not_found", status_code=303)

        delete_articles_for_document(db, document.id)
        document.updated_at = datetime.utcnow()
        db.commit()

        return RedirectResponse(
            url=f"/internal/legal-documents?success=document_articles_deleted",
            status_code=303,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.post("/internal/legal-documents/delete")
async def legal_document_delete(
    request: Request,
    document_id: int = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_legal_documents(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()

        if not document:
            return RedirectResponse(url="/internal/legal-documents?error=document_not_found", status_code=303)

        uploaded_file_path = document.uploaded_file_path or ""

        delete_articles_for_document(db, document.id)

        db.execute(
            text(
                """
                DELETE FROM legal_import_jobs
                WHERE file_path = :file_path
                OR result_json LIKE :document_id_pattern
                """
            ),
            {
                "file_path": uploaded_file_path,
                "document_id_pattern": f'%"document_id": {document.id}%',
            },
        )

        db.delete(document)
        db.commit()

        if uploaded_file_path:
            try:
                file_path = Path(uploaded_file_path)
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
            except Exception:
                pass

        return RedirectResponse(url="/internal/legal-documents?success=document_deleted", status_code=303)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.post("/internal/legal-documents/approve")
async def legal_document_approve(request: Request, document_id: int = Form(...)):
    return await legal_document_update_status(request, document_id=document_id, status="active", review_status="approved")


@router.post("/internal/legal-documents/reject")
async def legal_document_reject(request: Request, document_id: int = Form(...)):
    return await legal_document_update_status(request, document_id=document_id, status="active", review_status="rejected")


@router.post("/internal/legal-documents/archive")
async def legal_document_archive(request: Request, document_id: int = Form(...)):
    return await legal_document_update_status(request, document_id=document_id, status="archived", review_status="archived")


@router.post("/internal/legal-documents/return-to-review")
async def legal_document_return_to_review(request: Request, document_id: int = Form(...)):
    return await legal_document_update_status(request, document_id=document_id, status="active", review_status="pending_review")


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
            now = datetime.utcnow()
            document.reviewed_by_id = staff.id
            document.reviewed_at = now

            # اعتماد التشريع يعتمد جميع مواده تلقائيًا.
            db.query(LegalArticle).filter(LegalArticle.document_id == document.id).update(
                {
                    LegalArticle.status: "active",
                    LegalArticle.review_status: "approved",
                    LegalArticle.reviewed_by_id: staff.id,
                    LegalArticle.reviewed_at: now,
                    LegalArticle.last_verified_at: now,
                    LegalArticle.updated_at: now,
                },
                synchronize_session=False,
            )

        db.commit()

        if review_status in ["archived", "rejected"] or status == "archived":
            return RedirectResponse(url="/internal/legal-documents/archived?success=status_updated", status_code=303)

        return RedirectResponse(url="/internal/legal-documents?success=status_updated", status_code=303)

    finally:
        db.close()