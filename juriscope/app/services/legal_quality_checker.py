import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.legal import LegalArticle, LegalArticleRelation, LegalArticleVersion, LegalDocument


FOOTER_NOISE_KEYWORDS = [
    "في سياق سعي ديوان التشريع",
    "روابط ذات صلة",
    "اشترك في نشرة",
    "النشرة الإخبارية",
    "النشرة الاخبارية",
    "اتصل بنا",
    "خريطة الموقع",
    "CopyRight",
    "AllRights Reserved",
    "dewanlob",
    "ادخل الاسم",
    "ادخل البريد",
    "ادخل الموضوع",
    "ادخل الرسالة",
    "الاقتراحات و الاستفسارات",
]

METADATA_LABEL_KEYWORDS = [
    "ارتباطات المادة",
    "تعديلات المادة",
    "تعديالت المادة",
    "الأحكام القضائية",
    "االحكام القضائية",
    "التشريعات المرتبطة",
    "تفسير",
]


@dataclass
class QualityIssue:
    level: str
    scope: str
    message: str
    repair_action: str = ""
    article_id: int | None = None
    article_number: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_arabic_text(text: str) -> str:
    text = text or ""
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", normalize_arabic_text(text))


def contains_any_keyword(text: str, keywords: list[str]) -> str | None:
    normalized = normalize_arabic_text(text)
    compact = compact_text(text)
    for keyword in keywords:
        normalized_keyword = normalize_arabic_text(keyword)
        compact_keyword = compact_text(keyword)
        if normalized_keyword and normalized_keyword in normalized:
            return keyword
        if compact_keyword and compact_keyword in compact:
            return keyword
    return None


def article_number_to_int(article_number: str) -> int | None:
    value = (article_number or "").strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    match = re.search(r"\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def clean_footer_from_text(text_value: str) -> tuple[str, bool]:
    text_value = text_value or ""
    lower_compact = compact_text(text_value)
    earliest = None
    for keyword in FOOTER_NOISE_KEYWORDS:
        key = compact_text(keyword)
        if not key:
            continue
        index = lower_compact.find(key)
        if index < 0:
            continue
        # Find approximate real index by normalizing progressively. Simpler: search non-compact forms too.
        direct = normalize_arabic_text(text_value).find(normalize_arabic_text(keyword))
        if direct >= 0:
            real_index = direct
        else:
            real_index = 0
            running = ""
            for pos, ch in enumerate(text_value):
                running += compact_text(ch)
                if len(running) >= index:
                    real_index = pos
                    break
        earliest = real_index if earliest is None else min(earliest, real_index)
    if earliest is None:
        return text_value, False
    cleaned = text_value[:earliest].strip()
    return cleaned, cleaned != text_value.strip()


def build_articles_from_uploaded_file(document: LegalDocument) -> list[dict[str, Any]]:
    if not document.uploaded_file_path:
        return []
    try:
        from app.routes.internal_legal import extract_text_from_pdf, split_legal_articles
        text_value = extract_text_from_pdf(document.uploaded_file_path)
        return split_legal_articles(text_value)
    except Exception:
        return []


def check_document_quality(db: Session, document_id: int) -> dict[str, Any]:
    document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
    if not document:
        return {
            "document": None,
            "summary": {"status": "failed", "critical_count": 1, "warning_count": 0, "info_count": 0, "can_approve": False, "articles_count": 0},
            "issues": [QualityIssue("critical", "document", "التشريع غير موجود.").to_dict()],
            "article_reports": [],
            "repair_plan": [],
        }

    articles = (
        db.query(LegalArticle)
        .filter(LegalArticle.document_id == document.id)
        .order_by(LegalArticle.article_number.asc(), LegalArticle.id.asc())
        .all()
    )

    issues: list[QualityIssue] = []
    article_reports: list[dict[str, Any]] = []
    repair_plan: list[str] = []

    if not (document.title_ar or "").strip():
        issues.append(QualityIssue("critical", "document", "اسم التشريع بالعربي فارغ.", "إدخال اسم التشريع من شاشة تعديل التشريع."))
    if not (document.source_name or "").strip():
        issues.append(QualityIssue("warning", "document", "اسم المصدر الرسمي غير مدخل.", "تعبئة اسم المصدر الرسمي من بيانات التشريع."))
    if not (document.official_reference or "").strip():
        issues.append(QualityIssue("warning", "document", "المرجع الرسمي غير مدخل.", "تعبئة المرجع الرسمي عند توفره."))
    if not articles:
        issues.append(QualityIssue("critical", "document", "لا توجد مواد مستخرجة لهذا التشريع.", "إعادة استخراج المواد من ملف PDF أو إضافة المواد يدويًا."))

    numbers: list[int] = []
    seen_numbers: dict[str, int] = {}

    for article in articles:
        text_value = article.article_text or ""
        clean_text = " ".join(text_value.split())
        article_issues: list[QualityIssue] = []
        number_key = (article.article_number or "").strip()
        if not number_key:
            article_issues.append(QualityIssue("critical", "article", "رقم المادة فارغ.", "تعديل رقم المادة يدويًا.", article.id, article.article_number))
        else:
            seen_numbers[number_key] = seen_numbers.get(number_key, 0) + 1
        number_int = article_number_to_int(article.article_number)
        if number_int is not None:
            numbers.append(number_int)
        if not clean_text:
            article_issues.append(QualityIssue("critical", "article", "نص المادة فارغ.", "إعادة استخراج المادة أو إدخال نصها يدويًا.", article.id, article.article_number))
        elif len(clean_text) < 20:
            article_issues.append(QualityIssue("warning", "article", "نص المادة قصير جدًا وقد يكون استخراجًا ناقصًا.", "مراجعة المادة أو إعادة استخراجها من النص الأصلي.", article.id, article.article_number))
        footer_keyword = contains_any_keyword(text_value, FOOTER_NOISE_KEYWORDS)
        if footer_keyword:
            article_issues.append(QualityIssue("critical", "article", f"يوجد Footer أو نص واجهة داخل المادة: {footer_keyword}", "سيقوم الإصلاح بقص النص من بداية الـ Footer حتى نهاية المادة.", article.id, article.article_number))
        metadata_keyword = contains_any_keyword(text_value, METADATA_LABEL_KEYWORDS)
        if metadata_keyword:
            article_issues.append(QualityIssue("warning", "article", f"قد تكون بيانات مرتبطة دخلت داخل نص المادة: {metadata_keyword}", "سيحاول الإصلاح نقلها إلى علاقات المادة أو حذفها من النص القانوني.", article.id, article.article_number))
        if re.search(r"[0-9٠-٩]+\s*كانون\s+الثاني.*[0-9٠-٩]+\s*كانون\s+الأول", text_value):
            article_issues.append(QualityIssue("info", "article", "تحتوي المادة على تواريخ/أرقام؛ يفضل التأكد من ترتيبها.", "لا يتم تعديل التواريخ تلقائيًا إلا إذا وُجدت مشكلة واضحة.", article.id, article.article_number))
        for issue in article_issues:
            issues.append(issue)
        article_reports.append({
            "article_id": article.id,
            "article_number": article.article_number,
            "article_title": article.article_title,
            "status": article.status,
            "review_status": article.review_status,
            "text_length": len(clean_text),
            "issues": [issue.to_dict() for issue in article_issues],
        })

    duplicates = sorted(number for number, count in seen_numbers.items() if count > 1)
    for duplicate in duplicates:
        issues.append(QualityIssue("critical", "document", f"يوجد تكرار في رقم المادة: {duplicate}", "سيقوم الإصلاح بالإبقاء على النسخة الأطول وحذف التكرارات الأقصر."))

    missing_numbers: list[int] = []
    unique_numbers = sorted(set(numbers))
    if len(unique_numbers) >= 3:
        available = set(unique_numbers)
        for number in range(unique_numbers[0], unique_numbers[-1] + 1):
            if number not in available:
                missing_numbers.append(number)
        if missing_numbers:
            shown = ", ".join(str(n) for n in missing_numbers[:30])
            suffix = "..." if len(missing_numbers) > 30 else ""
            issues.append(QualityIssue("warning", "document", f"قد توجد أرقام مواد ناقصة في التسلسل: {shown}{suffix}", "سيحاول الإصلاح إعادة استخراج المواد الناقصة من ملف PDF الأصلي. إذا لم يجدها ستبقى كتقرير يحتاج إدخالًا يدويًا."))

    if any(issue.article_id and "Footer" in issue.message for issue in issues):
        repair_plan.append("إزالة Footer ونصوص واجهة ديوان التشريع والرأي من المواد المتأثرة.")
    if duplicates:
        repair_plan.append("حذف المواد المكررة مع الإبقاء على النص الأطول لكل رقم مادة.")
    if missing_numbers:
        repair_plan.append("إعادة قراءة ملف PDF الأصلي ومحاولة إضافة المواد الناقصة المكتشفة في التسلسل.")
    if any("بيانات مرتبطة" in issue.message for issue in issues):
        repair_plan.append("تنظيف عبارات الارتباطات/التعديلات من نص المادة عند دخولها بالخطأ.")

    critical_count = sum(1 for issue in issues if issue.level == "critical")
    warning_count = sum(1 for issue in issues if issue.level == "warning")
    info_count = sum(1 for issue in issues if issue.level == "info")
    status = "failed" if critical_count else ("needs_review" if warning_count else "passed")

    return {
        "document": {
            "id": document.id,
            "title_ar": document.title_ar,
            "title_en": document.title_en,
            "status": document.status,
            "review_status": document.review_status,
            "source_name": document.source_name,
            "official_reference": document.official_reference,
            "source_confidence": document.source_confidence,
        },
        "summary": {
            "status": status,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "articles_count": len(articles),
            "can_approve": critical_count == 0,
        },
        "issues": [issue.to_dict() for issue in issues],
        "article_reports": article_reports,
        "repair_plan": repair_plan,
        "missing_numbers": missing_numbers,
    }


def repair_document_quality(db: Session, document_id: int, staff_user_id: int | None = None) -> dict[str, Any]:
    document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
    if not document:
        return {"changed": False, "message": "document_not_found"}

    changed = False
    actions: list[str] = []

    # 1) Clean footer/noise from article text.
    articles = db.query(LegalArticle).filter(LegalArticle.document_id == document.id).all()
    for article in articles:
        cleaned, did_clean = clean_footer_from_text(article.article_text or "")
        if did_clean and cleaned:
            article.article_text = cleaned
            article.article_text_clean = " ".join(cleaned.split())
            article.review_status = "pending_review"
            article.status = "active"
            article.updated_by_id = staff_user_id
            article.updated_at = datetime.utcnow()
            article.reviewed_by_id = None
            article.reviewed_at = None
            article.last_verified_at = None
            changed = True
            actions.append(f"تم تنظيف Footer من المادة {article.article_number}.")

    # 2) Remove duplicate article numbers, keeping the longest text.
    articles = db.query(LegalArticle).filter(LegalArticle.document_id == document.id).all()
    grouped: dict[str, list[LegalArticle]] = {}
    for article in articles:
        key = (article.article_number or "").strip()
        if key:
            grouped.setdefault(key, []).append(article)
    for number, group in grouped.items():
        if len(group) <= 1:
            continue
        keeper = max(group, key=lambda a: len(a.article_text or ""))
        for article in group:
            if article.id == keeper.id:
                continue
            db.execute(text("DELETE FROM legal_article_relations WHERE article_id = :article_id"), {"article_id": article.id})
            db.execute(text("DELETE FROM legal_article_versions WHERE article_id = :article_id"), {"article_id": article.id})
            db.execute(text("DELETE FROM legal_article_topics WHERE article_id = :article_id"), {"article_id": article.id})
            db.execute(text("DELETE FROM legal_article_keywords WHERE article_id = :article_id"), {"article_id": article.id})
            db.delete(article)
            changed = True
        actions.append(f"تم حذف التكرارات للمادة {number} والإبقاء على النسخة الأطول.")

    # 3) Try to restore missing articles from original PDF using improved extractor.
    existing_numbers = {
        article_number_to_int(a.article_number)
        for a in db.query(LegalArticle).filter(LegalArticle.document_id == document.id).all()
    }
    existing_numbers = {n for n in existing_numbers if n is not None}
    if len(existing_numbers) >= 3:
        missing = [n for n in range(min(existing_numbers), max(existing_numbers) + 1) if n not in existing_numbers]
    else:
        missing = []

    if missing and document.uploaded_file_path:
        extracted_articles = build_articles_from_uploaded_file(document)
        by_number = {}
        for article_data in extracted_articles:
            number_int = article_number_to_int(str(article_data.get("article_number", "")))
            if number_int is not None:
                by_number[number_int] = article_data
        for number in missing:
            data = by_number.get(number)
            if not data:
                continue
            text_value = (data.get("article_text") or "").strip()
            if not text_value:
                continue
            article = LegalArticle(
                document_id=document.id,
                country_id=document.country_id,
                article_number=str(number),
                article_title=data.get("article_title", ""),
                article_text=text_value,
                article_text_clean=" ".join(text_value.split()),
                chapter="",
                section="",
                status="active",
                review_status="pending_review",
                effective_date=document.effective_date,
                repealed_date="",
                notes="تمت إضافتها تلقائيًا بواسطة مدقق التشريعات بعد اكتشاف نقص في التسلسل.",
                source_confidence=document.source_confidence,
                created_by_id=staff_user_id,
                updated_by_id=staff_user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(article)
            db.flush()
            for relation_data in data.get("relations", []) or []:
                db.add(LegalArticleRelation(
                    article_id=article.id,
                    relation_type=relation_data.get("relation_type", "raw_note"),
                    title=relation_data.get("title", ""),
                    description=relation_data.get("description", ""),
                    reference_text=relation_data.get("reference_text", ""),
                    source_name=relation_data.get("source_name", "ديوان التشريع والرأي"),
                    source_url=relation_data.get("source_url", ""),
                    created_at=datetime.utcnow(),
                ))
            db.add(LegalArticleVersion(
                article_id=article.id,
                version_number=1,
                article_text=article.article_text,
                article_text_clean=article.article_text_clean,
                change_reason="Added automatically by legal quality checker",
                status="active",
                effective_date=article.effective_date,
                created_by_id=staff_user_id,
                created_at=datetime.utcnow(),
            ))
            changed = True
            actions.append(f"تمت إضافة المادة الناقصة رقم {number} من ملف PDF الأصلي.")

    if changed:
        document.status = "active"
        document.review_status = "pending_review"
        document.reviewed_by_id = None
        document.reviewed_at = None
        document.updated_at = datetime.utcnow()

    return {"changed": changed, "actions": actions}
