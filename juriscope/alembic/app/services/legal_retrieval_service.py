import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.country import Country
from app.models.legal import LegalArticle, LegalDocument


ARABIC_STOPWORDS = {
    "في",
    "من",
    "على",
    "عن",
    "إلى",
    "الى",
    "أو",
    "او",
    "و",
    "ثم",
    "كما",
    "إذا",
    "اذا",
    "أن",
    "ان",
    "إن",
    "كان",
    "كانت",
    "ذلك",
    "هذه",
    "هذا",
    "هو",
    "هي",
    "هم",
    "ما",
    "لا",
    "لم",
    "لن",
    "قد",
    "كل",
    "أي",
    "اي",
    "مع",
    "بين",
    "بعد",
    "قبل",
    "عند",
    "حتى",
    "بأن",
    "انه",
    "أنها",
    "هناك",
    "ضمن",
    "حسب",
    "بسبب",
    "بخصوص",
    "حول",
    "ضد",
    "لدى",
    "له",
    "لها",
    "عليه",
    "عليها",
    "يكون",
    "تكون",
    "يوجد",
    "تم",
    "هل",
    "ماهي",
    "ما",
    "لو",
    "اذا",
    "أريد",
    "اريد",
    "بدي",
    "شو",
    "ليش",
    "كيف",
}


LEGAL_KEYWORD_BOOSTS = {
    "عقد": 3,
    "فسخ": 3,
    "تعويض": 3,
    "ضرر": 2,
    "إيجار": 3,
    "ايجار": 3,
    "أجرة": 2,
    "اجرة": 2,
    "شيك": 4,
    "كمبيالة": 4,
    "جريمة": 3,
    "سرقة": 4,
    "احتيال": 4,
    "نصب": 4,
    "خيانة": 4,
    "أمانة": 4,
    "امانة": 4,
    "قتل": 5,
    "ضرب": 4,
    "إيذاء": 4,
    "ايذاء": 4,
    "طلاق": 4,
    "نفقة": 4,
    "حضانة": 4,
    "ميراث": 4,
    "شركة": 3,
    "شركات": 3,
    "عامل": 3,
    "عمل": 2,
    "فصل": 3,
    "راتب": 3,
    "أجر": 3,
    "اجر": 3,
    "ضريبة": 3,
    "تنفيذ": 3,
    "حكم": 2,
    "محكمة": 2,
    "دعوى": 2,
    "قضية": 2,
    "بينات": 3,
    "إثبات": 3,
    "اثبات": 3,
    "مسؤولية": 3,
    "مسؤوليه": 3,
    "غرامة": 3,
    "غرامه": 3,
    "حبس": 4,
    "سجن": 4,
}


@dataclass
class LegalSourceResult:
    article_id: int
    document_id: int
    country_id: int
    country_code: str
    country_name: str
    document_title: str
    document_type: str
    document_status: str
    document_review_status: str
    article_number: str
    article_title: str
    article_text: str
    article_status: str
    article_review_status: str
    source_confidence: str
    score: float
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "document_id": self.document_id,
            "country_id": self.country_id,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "document_status": self.document_status,
            "document_review_status": self.document_review_status,
            "article_number": self.article_number,
            "article_title": self.article_title,
            "article_text": self.article_text,
            "article_status": self.article_status,
            "article_review_status": self.article_review_status,
            "source_confidence": self.source_confidence,
            "score": self.score,
            "matched_terms": self.matched_terms,
        }


def normalize_arabic(text: str) -> str:
    text = text or ""

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip().lower()


def extract_terms(query: str) -> list[str]:
    normalized = normalize_arabic(query)
    raw_terms = normalized.split()

    terms = []

    for term in raw_terms:
        term = term.strip()

        if len(term) < 2:
            continue

        if term in ARABIC_STOPWORDS:
            continue

        if term not in terms:
            terms.append(term)

    return terms


def source_confidence_score(source_confidence: str) -> float:
    scores = {
        "official": 10.0,
        "high": 6.0,
        "medium": 3.0,
        "low": 0.0,
    }

    return scores.get(source_confidence or "", 0.0)


def review_status_score(review_status: str) -> float:
    scores = {
        "approved": 15.0,
        "pending_review": -25.0,
        "draft": -30.0,
        "rejected": -100.0,
        "archived": -100.0,
    }

    return scores.get(review_status or "", 0.0)


def status_score(status: str) -> float:
    scores = {
        "active": 8.0,
        "amended": -5.0,
        "repealed": -100.0,
        "archived": -100.0,
    }

    return scores.get(status or "", 0.0)


def calculate_score(
    query_terms: list[str],
    article: LegalArticle,
    document: LegalDocument,
) -> tuple[float, list[str]]:
    article_text = normalize_arabic(article.article_text or "")
    article_title = normalize_arabic(article.article_title or "")
    article_number = normalize_arabic(article.article_number or "")
    document_title = normalize_arabic(document.title_ar or "")

    matched_terms = []
    score = 0.0

    for term in query_terms:
        term_score = 0.0

        if term in article_number:
            term_score += 15

        if term in document_title:
            term_score += 10

        if term in article_title:
            term_score += 10

        count_in_text = article_text.count(term)

        if count_in_text:
            term_score += min(count_in_text * 2, 18)

        for legal_keyword, boost in LEGAL_KEYWORD_BOOSTS.items():
            normalized_keyword = normalize_arabic(legal_keyword)

            if term == normalized_keyword:
                term_score += boost

        if term_score > 0:
            matched_terms.append(term)
            score += term_score

    score += source_confidence_score(article.source_confidence)

    score += review_status_score(article.review_status)
    score += review_status_score(document.review_status)

    score += status_score(article.status)
    score += status_score(document.status)

    return score, matched_terms


def get_country_by_code_or_name(
    db: Session,
    country_code: Optional[str] = None,
    country_name: Optional[str] = None,
) -> Optional[Country]:
    if country_code:
        country = (
            db.query(Country)
            .filter(Country.code == country_code.strip().upper())
            .first()
        )

        if country:
            return country

    if country_name:
        return (
            db.query(Country)
            .filter(Country.name_ar == country_name.strip())
            .first()
        )

    return None


def search_legal_sources(
    db: Session,
    query: str,
    country_code: Optional[str] = None,
    country_name: Optional[str] = None,
    country_id: Optional[int] = None,
    limit: int = 8,
    approved_only: bool = True,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    query = (query or "").strip()

    if not query:
        return []

    query_terms = extract_terms(query)

    if not query_terms:
        return []

    country = None

    if country_id:
        country = db.query(Country).filter(Country.id == country_id).first()
    else:
        country = get_country_by_code_or_name(
            db,
            country_code=country_code,
            country_name=country_name,
        )

    if not country:
        return []

    articles_query = (
        db.query(LegalArticle, LegalDocument, Country)
        .join(LegalDocument, LegalDocument.id == LegalArticle.document_id)
        .join(Country, Country.id == LegalArticle.country_id)
        .filter(LegalArticle.country_id == country.id)
    )

    if approved_only:
        articles_query = articles_query.filter(
            LegalArticle.review_status == "approved",
            LegalDocument.review_status == "approved",
        )

    if active_only:
        articles_query = articles_query.filter(
            LegalArticle.status == "active",
            LegalDocument.status == "active",
        )

    articles_query = articles_query.limit(700)

    rows = articles_query.all()

    results: list[LegalSourceResult] = []

    for article, document, row_country in rows:
        score, matched_terms = calculate_score(query_terms, article, document)

        if score <= 0:
            continue

        result = LegalSourceResult(
            article_id=article.id,
            document_id=document.id,
            country_id=row_country.id,
            country_code=row_country.code,
            country_name=row_country.name_ar,
            document_title=document.title_ar,
            document_type=document.document_type,
            document_status=document.status,
            document_review_status=document.review_status,
            article_number=article.article_number,
            article_title=article.article_title,
            article_text=article.article_text,
            article_status=article.status,
            article_review_status=article.review_status,
            source_confidence=article.source_confidence,
            score=round(score, 2),
            matched_terms=matched_terms,
        )

        results.append(result)

    results.sort(key=lambda item: item.score, reverse=True)

    return [item.to_dict() for item in results[:limit]]


def build_sources_context(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return """
لم يتم العثور على مواد قانونية معتمدة مناسبة داخل قاعدة بيانات Mizan.

تعليمات للمساعد:
- يمكنك تقديم تحليل قانوني عام وحذر.
- يجب التصريح بوضوح أن قاعدة بيانات Mizan لم تجد نصًا قانونيًا معتمدًا مناسبًا لهذا السؤال.
- لا تذكر أرقام مواد أو تنسب نصوصًا لقوانين محددة.
- لا تخترع مواد أو أحكامًا قضائية.
""".strip()

    blocks = []

    for index, source in enumerate(sources, start=1):
        block = f"""
[مصدر قانوني معتمد رقم {index}]
الدولة: {source.get("country_name", "")}
التشريع: {source.get("document_title", "")}
نوع المصدر: {source.get("document_type", "")}
حالة التشريع: {source.get("document_status", "")}
حالة مراجعة التشريع: {source.get("document_review_status", "")}

رقم المادة: {source.get("article_number", "")}
عنوان المادة: {source.get("article_title", "")}
حالة المادة: {source.get("article_status", "")}
حالة مراجعة المادة: {source.get("article_review_status", "")}
ثقة المصدر: {source.get("source_confidence", "")}
درجة الصلة: {source.get("score", "")}
الكلمات المطابقة: {", ".join(source.get("matched_terms", []))}

نص المادة:
{source.get("article_text", "")}
""".strip()

        blocks.append(block)

    return "\n\n---\n\n".join(blocks)


def build_legal_source_policy(sources: list[dict[str, Any]]) -> str:
    if sources:
        return """
سياسة الاعتماد على المصادر القانونية في Mizan:

1. يجب أن يكون التحليل مبنيًا أولًا وبشكل رئيسي على المصادر القانونية المعتمدة المرفقة من قاعدة بيانات Mizan.
2. استخدم فهمك القانوني العام فقط كمصدر ثانوي لتفسير النصوص، تنظيم التحليل، شرح المخاطر، واقتراح الخطوات العملية.
3. النسبة الأكبر من الجواب يجب أن تكون مستندة إلى التشريعات والمواد القانونية المعتمدة المرفقة.
4. لا يجوز أن يخالف التحليل العام أي نص قانوني معتمد مرفق.
5. لا تذكر أي رقم مادة أو اسم قانون أو نص قانوني إلا إذا كان موجودًا ضمن المصادر المرفقة.
6. إذا كانت المصادر لا تكفي للوصول إلى نتيجة قطعية، صرّح بذلك بوضوح.
7. فرّق في الجواب بين:
   - ما هو مستند إلى مصادر Mizan المعتمدة.
   - ما هو تحليل عام أو استنتاج قانوني مساعد.
8. لا تخترع أحكامًا قضائية أو سوابق أو أرقام مواد.
""".strip()

    return """
سياسة الاعتماد على المصادر القانونية في Mizan:

لم يتم العثور على مصادر قانونية معتمدة مناسبة من قاعدة بيانات Mizan لهذا السؤال.

لذلك:
1. قدم تحليلًا عامًا حذرًا باعتباره إرشادًا أوليًا فقط.
2. صرّح بوضوح أن الجواب غير مبني على مادة معتمدة من قاعدة بيانات Mizan.
3. لا تذكر أرقام مواد قانونية.
4. لا تنسب الكلام إلى قانون محدد إلا إذا كان مؤكدًا من سياق السؤال نفسه.
5. ركز على المخاطر، الأسئلة الناقصة، والخطوات العملية.
6. اطلب مراجعة محامٍ أو مصدر رسمي عند الحاجة.
""".strip()