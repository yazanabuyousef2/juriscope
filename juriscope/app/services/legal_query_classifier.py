"""
legal_query_classifier.py — Mizan Legal Query Classifier

Classifies incoming legal queries BEFORE retrieval to:
1. Detect the requested legislation/law.
2. Determine the task type.
3. Identify if sources are needed.
4. Check if clarification is needed.
"""

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Law alias mapping — canonical name → list of aliases (Arabic, normalised)
# ---------------------------------------------------------------------------

LAW_ALIAS_GROUPS: Dict[str, List[str]] = {
    "الدستور الأردني": [
        "الدستور",
        "الدستور الاردني",
        "دستور المملكة الاردنية الهاشمية",
        "دستوري",
        "دستورية",
        "الحقوق الدستورية",
        "حرية الراي",
        "حرية التعبير",
        "مجلس النواب",
        "مجلس الاعيان",
        "السلطة التشريعية",
        "السلطة التنفيذية",
        "السلطة القضائية",
        "الحقوق والحريات",
    ],
    "قانون العمل": [
        "قانون العمل",
        "عمال",
        "عامل",
        "صاحب العمل",
        "فصل تعسفي",
        "اجور العمال",
        "حقوق العمال",
        "اجازة العمال",
        "ساعات العمل",
        "نهاية الخدمة",
        "التعويضات العمالية",
    ],
    "قانون العقوبات": [
        "قانون العقوبات",
        "جريمة",
        "جنحة",
        "جناية",
        "سرقة",
        "احتيال",
        "اساءة ائتمان",
        "تهديد",
        "تزوير",
        "رشوة",
        "جرائم جنائية",
        "الجنايات والجنح",
        "عقوبة جريمة",
    ],
    "قانون المالكين والمستأجرين": [
        "المالكين والمستاجرين",
        "المالك والمستاجر",
        "الايجار",
        "الإيجار",
        "المستاجر",
        "المؤجر",
        "اخلاء الماجور",
        "بدل الايجار",
        "عقد الايجار",
        "اخلاء المستاجر",
        "شروط الاخلاء",
        "الإيجارات",
    ],
    "القانون المدني": [
        "القانون المدني",
        "المسؤولية المدنية",
        "العقد",
        "الالتزام",
        "التعويض المدني",
        "الضرر المدني",
        "الفسخ",
        "البطلان",
        "عيوب الارادة",
    ],
    "قانون الشركات": [
        "قانون الشركات",
        "شركة",
        "شركات",
        "مساهم",
        "حصص",
        "مدير الشركة",
        "الشركة المساهمة",
        "شركة ذات مسؤولية محدودة",
        "تأسيس شركة",
        "حل الشركة",
        "اندماج شركات",
    ],
    "قانون البينات": [
        "قانون البينات",
        "البينات",
        "الاثبات",
        "إثبات",
        "شهادة",
        "شهادة الشهود",
        "القرائن",
        "الاعتراف",
        "المستندات الرسمية",
        "الخبرة",
    ],
    "قانون التنفيذ": [
        "قانون التنفيذ",
        "التنفيذ",
        "الحجز",
        "السند التنفيذي",
        "حجز الاموال",
        "البيع بالمزاد",
        "تنفيذ الاحكام",
    ],
    "قانون حماية البيانات الشخصية": [
        "حماية البيانات",
        "البيانات الشخصية",
        "معالجة البيانات",
        "صاحب البيانات",
        "الخصوصية",
        "تسريب البيانات",
        "بيانات المستخدمين",
        "جمع البيانات",
        "حذف البيانات",
    ],
    "قانون حماية المستهلك": [
        "حماية المستهلك",
        "المستهلك",
        "سلعة معيبة",
        "المزود",
        "الغش التجاري",
        "الاعلان الكاذب",
        "حق الاسترداد",
        "الضمان",
    ],
    "قانون المعاملات الإلكترونية": [
        "المعاملات الالكترونية",
        "التوقيع الالكتروني",
        "التجارة الالكترونية",
        "العقود الالكترونية",
        "البيانات الالكترونية",
    ],
    "قانون الأمن السيبراني": [
        "الامن السيبراني",
        "الجرائم الالكترونية",
        "جريمة الكترونية",
        "اختراق الانظمة",
        "قرصنة",
    ],
    "قانون أصول المحاكمات المدنية": [
        "اصول المحاكمات المدنية",
        "الاختصاص القضائي",
        "رفع الدعوى",
        "الدعوى المدنية",
        "التبليغ القضائي",
        "الطعن بالحكم",
        "الاستئناف",
        "التمييز",
    ],
    "قانون أصول المحاكمات الجزائية": [
        "اصول المحاكمات الجزائية",
        "التحقيق الجنائي",
        "توقيف المتهم",
        "التفتيش",
        "الاحتجاز",
        "المحاكمة الجنائية",
    ],
    "قانون الأحوال الشخصية": [
        "الاحوال الشخصية",
        "الزواج",
        "الطلاق",
        "النفقة",
        "الحضانة",
        "المهر",
        "الميراث",
        "الوصية",
        "الخلع",
    ],
}

# Task type keywords
TASK_KEYWORDS: Dict[str, List[str]] = {
    "legal_research": [
        "ما هو", "ما هي", "ما القانون", "ما التشريع", "ما النص",
        "اشرح", "وضح", "ما المقصود", "تعريف", "مفهوم", "ما تنص",
        "ما الفرق", "بحث قانوني", "هل يوجد قانون",
    ],
    "case_analysis": [
        "حلل", "تحليل", "وقائع", "قضية", "نزاع", "خلاف", "حادثة",
        "موقف قانوني", "ما الحكم", "هل يحق", "ما المسؤولية",
        "ما العقوبة", "هل يمكن", "ما الحل",
    ],
    "document_analysis": [
        "حلل هذا العقد", "راجع هذا", "فحص المستند", "اقرأ هذا",
        "ما رأيك في", "تحليل عقد", "مراجعة مستند",
    ],
    "contract_review": [
        "مراجعة عقد", "راجع العقد", "البنود الخطرة", "عقد شراكة",
        "عقد عمل", "عقد ايجار", "عقد بيع", "اتفاقية",
        "مخاطر العقد", "البنود الغامضة",
    ],
    "legal_drafting": [
        "اكتب", "صياغة", "اصغ", "انشئ", "ضع", "إنذار",
        "مذكرة", "لائحة", "رأي قانوني", "خطاب مطالبة",
        "عقد جديد", "نموذج",
    ],
    "litigation_strategy": [
        "استراتيجية", "استراتيجي", "كيف أرفع", "كيف أدافع",
        "كيف أربح", "فرص النجاح", "احتمال", "نقاط القوة",
        "نقاط الضعف", "خطوات الدعوى",
    ],
    "corporate_advisory": [
        "شركة", "امتثال", "إلتزام قانوني", "مخاطر الشركة",
        "حوكمة", "مجلس الادارة", "استشارة شركة",
    ],
}

NEEDS_DOCUMENT_TERMS = [
    "عقد", "اتفاقية", "وثيقة", "مستند", "صك", "سند", "حكم",
    "قرار محكمة", "انذار", "مذكرة", "لائحة",
]

VAGUE_TERMS = [
    "كيف", "ماذا أفعل", "ما رأيك", "هل يمكن",
    "ساعدني", "أريد معرفة", "ما الأفضل",
]


def _normalize(text: str) -> str:
    """Normalise Arabic text for comparison."""
    if not text:
        return ""
    replacements = {"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ـ": ""}
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def detect_requested_laws(query: str) -> List[str]:
    """Return all canonical law names detected in the query (may be multiple)."""
    norm_query = _normalize(query or "")
    if not norm_query:
        return []

    detected = []
    for canonical, aliases in LAW_ALIAS_GROUPS.items():
        for alias in aliases:
            norm_alias = _normalize(alias)
            if norm_alias and norm_alias in norm_query:
                if canonical not in detected:
                    detected.append(canonical)
                break

    return detected


def detect_task_type(query: str, assistant_mode: Optional[str] = None) -> str:
    """Detect the most likely task type from the query."""
    # If caller already specified a mode, trust it
    valid_modes = {
        "case_analysis", "legal_research", "document_analysis",
        "contract_review", "legal_drafting", "litigation_strategy", "corporate_advisory",
    }
    if assistant_mode and assistant_mode in valid_modes:
        return assistant_mode

    norm_query = _normalize(query or "")
    scores: Dict[str, int] = {k: 0 for k in TASK_KEYWORDS}

    for task, keywords in TASK_KEYWORDS.items():
        for kw in keywords:
            if _normalize(kw) in norm_query:
                scores[task] += 1

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "case_analysis"
    return best


def needs_legal_sources(query: str, task_type: str) -> bool:
    """True if the query likely needs legislation from the database."""
    source_dependent_tasks = {
        "legal_research", "case_analysis", "contract_review",
        "litigation_strategy", "corporate_advisory",
    }
    if task_type not in source_dependent_tasks:
        return False

    norm = _normalize(query or "")
    source_terms = [
        "قانون", "تشريع", "مادة", "نص", "حكم", "دستور",
        "لائحة تنظيمية", "ما ينص", "يحظر", "يلزم", "يشترط",
        "حق قانوني", "واجب قانوني",
    ]
    return any(_normalize(t) in norm for t in source_terms)


def needs_clarification(query: str) -> bool:
    """True if the query is likely too vague to answer well."""
    norm = _normalize(query or "")
    if len(norm.split()) < 4:
        return True
    vague_only = all(_normalize(t) in norm for t in VAGUE_TERMS[:2]) and len(norm.split()) < 8
    return vague_only


def classify_query(
    query: str,
    assistant_mode: Optional[str] = None,
    country: str = "الأردن",
) -> Dict[str, Any]:
    """
    Full query classification.

    Returns:
        {
            "country": str,
            "task_type": str,
            "requested_laws": List[str],
            "needs_sources": bool,
            "needs_documents": bool,
            "needs_clarification": bool,
        }
    """
    task_type = detect_task_type(query, assistant_mode)
    requested_laws = detect_requested_laws(query)
    norm = _normalize(query or "")

    doc_needed = any(_normalize(t) in norm for t in NEEDS_DOCUMENT_TERMS)

    return {
        "country": country or "الأردن",
        "task_type": task_type,
        "requested_laws": requested_laws,
        "needs_sources": needs_legal_sources(query, task_type),
        "needs_documents": doc_needed,
        "needs_clarification": needs_clarification(query),
    }
