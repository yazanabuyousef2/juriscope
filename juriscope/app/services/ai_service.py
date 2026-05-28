import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")

client = genai.Client(api_key=GEMINI_API_KEY)


REQUEST_TYPES = [
    "general_question",
    "case_analysis",
    "legal_article_request",
    "legislation_request",
    "procedure_guidance",
    "lawyer_brief",
    "document_analysis",
]


AUDIENCE_MODES = [
    "individual",
    "lawyer",
    "company",
    "judge",
    "law_student",
    "legal_researcher",
    "government_employee",
]


VALID_CASE_TYPES = [
    "غير محدد",
    "مدني",
    "جنائي",
    "تجاري",
    "عمالي",
    "أحوال شخصية",
    "إداري",
    "عقاري",
    "تنفيذ",
    "عقود",
    "شركات",
    "إيجارات",
    "شيكات ومطالبات مالية",
    "ملكية فكرية",
    "أخرى",
]


ALL_CARDS = [
    "case_type_correction",
    "short_answer",
    "plain_explanation",
    "practical_meaning",
    "country_context",
    "case_understanding",
    "legal_classification",
    "legal_basis",
    "articles_requested",
    "legislation_summary",
    "mizan_sources_summary",
    "analysis_based_on_sources",
    "general_legal_reasoning",
    "verified_legal_materials",
    "unverified_legal_points",
    "key_risks",
    "business_risks",
    "relevant_documents",
    "proof_points",
    "defenses_or_arguments",
    "similar_cases",
    "criminal_penalty_estimate",
    "next_steps",
    "procedure_steps",
    "when_to_consult_lawyer",
    "educational_notes",
    "role_based_guidance",
    "lawyer_summary",
    "confidence",
    "disclaimer",
    "legal_sources",
]


def generate_content_with_retry(contents, config, retries: int = 2):
    models_to_try = [GEMINI_MODEL]

    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models_to_try.append(GEMINI_FALLBACK_MODEL)

    last_error = None

    for model_name in models_to_try:
        for attempt in range(retries + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                last_error = e
                error_text = str(e)

                is_retryable = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                    or "high demand" in error_text
                    or "temporarily" in error_text
                    or "overloaded" in error_text
                    or "rate" in error_text.lower()
                )

                if not is_retryable:
                    raise

                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(
        "مزود الذكاء الاصطناعي مشغول حاليًا. يرجى إعادة المحاولة بعد قليل."
    ) from last_error


def _safe_json_loads(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("لم يصل رد من مزود الذكاء الاصطناعي.")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1

    if start >= 0 and end > start:
        cleaned = cleaned[start:end]

    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError as e:
        raise ValueError(f"لم يتمكن النظام من قراءة رد Gemini كـ JSON صالح: {str(e)}")


def _ensure_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value

    if value is None or value == "":
        return []

    return [str(value)]


def _normalize_request_type(value: Any) -> str:
    value = str(value or "").strip()

    if value in REQUEST_TYPES:
        return value

    return "general_question"


def _normalize_audience_mode(value: Any, user_role: str) -> str:
    value = str(value or "").strip()

    if value in AUDIENCE_MODES:
        return value

    if user_role in AUDIENCE_MODES:
        return user_role

    return "individual"


def _normalize_case_type(value: Any) -> str:
    value = str(value or "").strip()

    if not value:
        return "غير محدد"

    if value in VALID_CASE_TYPES:
        return value

    return value


def _case_type_matches(selected_case_type: str, detected_case_type: str) -> bool:
    selected = _normalize_case_type(selected_case_type)
    detected = _normalize_case_type(detected_case_type)

    if selected == "غير محدد":
        return True

    if detected == "غير محدد":
        return True

    return selected == detected


def _clean_card_list(cards: Any, request_type: str, user_role: str) -> List[str]:
    incoming = _ensure_list(cards)
    cleaned = []

    for card in incoming:
        card_name = str(card).strip()

        if card_name in ALL_CARDS and card_name not in cleaned:
            cleaned.append(card_name)

    if cleaned:
        if "case_type_correction" not in cleaned:
            cleaned.insert(0, "case_type_correction")
        return cleaned

    return get_default_cards_for_request(request_type=request_type, user_role=user_role)


def get_default_cards_for_request(request_type: str, user_role: str) -> List[str]:
    if request_type == "general_question":
        base = [
            "case_type_correction",
            "short_answer",
            "plain_explanation",
            "legal_basis",
            "verified_legal_materials",
            "unverified_legal_points",
            "confidence",
            "disclaimer",
        ]

    elif request_type == "legal_article_request":
        base = [
            "case_type_correction",
            "short_answer",
            "articles_requested",
            "verified_legal_materials",
            "mizan_sources_summary",
            "legal_sources",
            "disclaimer",
        ]

    elif request_type == "legislation_request":
        base = [
            "case_type_correction",
            "short_answer",
            "legislation_summary",
            "verified_legal_materials",
            "mizan_sources_summary",
            "legal_sources",
            "disclaimer",
        ]

    elif request_type == "procedure_guidance":
        base = [
            "case_type_correction",
            "short_answer",
            "plain_explanation",
            "procedure_steps",
            "relevant_documents",
            "when_to_consult_lawyer",
            "disclaimer",
        ]

    elif request_type == "lawyer_brief":
        base = [
            "case_type_correction",
            "short_answer",
            "case_understanding",
            "legal_classification",
            "legal_basis",
            "proof_points",
            "defenses_or_arguments",
            "key_risks",
            "lawyer_summary",
            "verified_legal_materials",
            "legal_sources",
            "disclaimer",
        ]

    elif request_type == "case_analysis":
        base = [
            "case_type_correction",
            "short_answer",
            "case_understanding",
            "legal_classification",
            "analysis_based_on_sources",
            "general_legal_reasoning",
            "key_risks",
            "relevant_documents",
            "next_steps",
            "verified_legal_materials",
            "unverified_legal_points",
            "confidence",
            "disclaimer",
        ]

    else:
        base = [
            "case_type_correction",
            "short_answer",
            "plain_explanation",
            "disclaimer",
        ]

    if user_role == "individual":
        preferred = [
            "case_type_correction",
            "short_answer",
            "plain_explanation",
            "practical_meaning",
            "next_steps",
            "when_to_consult_lawyer",
            "verified_legal_materials",
            "disclaimer",
        ]

        if request_type == "case_analysis":
            return [
                card for card in preferred
                if card in ALL_CARDS
            ] + [
                card for card in base
                if card not in preferred
            ]

    if user_role == "lawyer":
        lawyer_extra = [
            "legal_classification",
            "legal_basis",
            "proof_points",
            "defenses_or_arguments",
            "key_risks",
            "lawyer_summary",
        ]

        return [
            card for card in base + lawyer_extra
            if card in ALL_CARDS
        ]

    if user_role == "company":
        company_extra = [
            "business_risks",
            "relevant_documents",
            "next_steps",
        ]

        return [
            card for card in base + company_extra
            if card in ALL_CARDS
        ]

    if user_role == "law_student":
        student_extra = [
            "educational_notes",
            "plain_explanation",
            "legal_basis",
        ]

        return [
            card for card in base + student_extra
            if card in ALL_CARDS
        ]

    return [
        card for card in base
        if card in ALL_CARDS
    ]


def _normalize_legal_result(
    data: Dict[str, Any],
    user_role: str = "individual",
    selected_case_type: str = "غير محدد",
) -> Dict[str, Any]:
    criminal = data.get("criminal_penalty_estimate") or {}

    if not isinstance(criminal, dict):
        criminal = {}

    request_type = _normalize_request_type(data.get("request_type"))
    audience_mode = _normalize_audience_mode(data.get("audience_mode"), user_role)

    selected = _normalize_case_type(
        data.get("selected_case_type") or selected_case_type or "غير محدد"
    )
    detected = _normalize_case_type(data.get("detected_case_type") or "غير محدد")

    case_type_match = data.get("case_type_match")
    if not isinstance(case_type_match, bool):
        case_type_match = _case_type_matches(selected, detected)

    correction_note = data.get("case_type_correction_note", "")

    if not correction_note and not case_type_match and selected != "غير محدد":
        correction_note = (
            f"تم اختيار نوع القضية على أنه ({selected})، لكن من خلال الوقائع أو السؤال يظهر أن "
            f"التصنيف الأقرب هو ({detected}). لذلك تم بناء التحليل على النوع الأقرب قانونيًا."
        )

    cards_to_show = _clean_card_list(
        cards=data.get("cards_to_show"),
        request_type=request_type,
        user_role=audience_mode,
    )

    return {
        "request_type": request_type,
        "audience_mode": audience_mode,
        "cards_to_show": cards_to_show,

        "selected_case_type": selected,
        "detected_case_type": detected,
        "case_type_match": case_type_match,
        "case_type_correction_note": correction_note,

        "short_answer": data.get("short_answer", ""),
        "plain_explanation": data.get("plain_explanation", ""),
        "practical_meaning": data.get("practical_meaning", ""),

        "country_context": data.get("country_context", ""),
        "case_understanding": data.get("case_understanding", ""),
        "legal_classification": data.get("legal_classification", ""),

        "legal_basis": data.get("legal_basis", ""),
        "articles_requested": _ensure_list(data.get("articles_requested")),
        "legislation_summary": data.get("legislation_summary", ""),

        "legal_accuracy_note": data.get("legal_accuracy_note", ""),
        "confidence_level": data.get("confidence_level", "منخفض"),
        "confidence_reason": data.get("confidence_reason", ""),

        "mizan_sources_summary": data.get("mizan_sources_summary", ""),
        "analysis_based_on_sources": data.get("analysis_based_on_sources", ""),
        "general_legal_reasoning": data.get("general_legal_reasoning", ""),
        "source_dependency_level": data.get("source_dependency_level", ""),

        "verified_legal_materials": _ensure_list(data.get("verified_legal_materials")),
        "unverified_legal_points": _ensure_list(data.get("unverified_legal_points")),

        "key_risks": _ensure_list(data.get("key_risks")),
        "business_risks": _ensure_list(data.get("business_risks")),
        "relevant_documents": _ensure_list(data.get("relevant_documents")),
        "proof_points": _ensure_list(data.get("proof_points")),
        "defenses_or_arguments": _ensure_list(data.get("defenses_or_arguments")),
        "similar_cases": _ensure_list(data.get("similar_cases")),

        "next_steps": _ensure_list(data.get("next_steps")),
        "procedure_steps": _ensure_list(data.get("procedure_steps")),
        "when_to_consult_lawyer": data.get("when_to_consult_lawyer", ""),
        "educational_notes": data.get("educational_notes", ""),

        "lawyer_summary": data.get("lawyer_summary", ""),
        "role_based_guidance": data.get("role_based_guidance", ""),
        "plan_based_depth": data.get("plan_based_depth", ""),
        "combined_role_plan_note": data.get("combined_role_plan_note", ""),

        "disclaimer": data.get(
            "disclaimer",
            "هذا التحليل أولي ومساعد ولا يُعد استشارة قانونية نهائية. يجب مراجعة محامٍ مرخص قبل اتخاذ أي إجراء قانوني.",
        ),

        "criminal_penalty_estimate": {
            "show": bool(criminal.get("show", False)),
            "alleged_crime": criminal.get("alleged_crime", ""),
            "possible_penalty_range": criminal.get("possible_penalty_range", ""),
            "factors_that_may_increase_penalty": _ensure_list(
                criminal.get("factors_that_may_increase_penalty")
            ),
            "factors_that_may_reduce_penalty": _ensure_list(
                criminal.get("factors_that_may_reduce_penalty")
            ),
            "important_warning": criminal.get("important_warning", ""),
        },
    }


def _normalize_document_result(
    data: Dict[str, Any],
    selected_case_type: str = "غير محدد",
) -> Dict[str, Any]:
    selected = _normalize_case_type(
        data.get("selected_case_type") or selected_case_type or "غير محدد"
    )
    detected = _normalize_case_type(data.get("detected_case_type") or "غير محدد")

    case_type_match = data.get("case_type_match")
    if not isinstance(case_type_match, bool):
        case_type_match = _case_type_matches(selected, detected)

    correction_note = data.get("case_type_correction_note", "")

    if not correction_note and not case_type_match and selected != "غير محدد":
        correction_note = (
            f"تم اختيار نوع القضية على أنه ({selected})، لكن من خلال المستند يظهر أن "
            f"التصنيف الأقرب هو ({detected}). لذلك تم بناء التحليل على النوع الأقرب قانونيًا."
        )

    return {
        "request_type": "document_analysis",
        "audience_mode": data.get("audience_mode", ""),
        "cards_to_show": _clean_card_list(
            data.get("cards_to_show"),
            request_type="document_analysis",
            user_role=data.get("audience_mode", "individual"),
        ),

        "selected_case_type": selected,
        "detected_case_type": detected,
        "case_type_match": case_type_match,
        "case_type_correction_note": correction_note,

        "document_type": data.get("document_type", ""),
        "summary": data.get("summary", ""),
        "country_context": data.get("country_context", ""),
        "confidence_level": data.get("confidence_level", "منخفض"),
        "confidence_reason": data.get("confidence_reason", ""),
        "parties": _ensure_list(data.get("parties")),
        "main_obligations": _ensure_list(data.get("main_obligations")),
        "risky_clauses": _ensure_list(data.get("risky_clauses")),
        "legal_gaps": _ensure_list(data.get("legal_gaps")),
        "missing_clauses": _ensure_list(data.get("missing_clauses")),
        "suggested_edits": _ensure_list(data.get("suggested_edits")),
        "verified_legal_materials": _ensure_list(data.get("verified_legal_materials")),
        "unverified_legal_points": _ensure_list(data.get("unverified_legal_points")),
        "risk_level": data.get("risk_level", ""),
        "lawyer_summary": data.get("lawyer_summary", ""),
        "role_based_guidance": data.get("role_based_guidance", ""),
        "plan_based_depth": data.get("plan_based_depth", ""),
        "combined_role_plan_note": data.get("combined_role_plan_note", ""),
        "disclaimer": data.get(
            "disclaimer",
            "هذا التحليل أولي ومساعد ولا يُعد استشارة قانونية نهائية. يجب مراجعة محامٍ مرخص قبل توقيع أو تعديل أي مستند قانوني.",
        ),
    }


def get_country_legal_style(country: str) -> str:
    styles = {
        "الأردن": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية الأردنية.
راعِ وجود المحاكم النظامية، الدعاوى الحقوقية والجزائية، البينات الخطية والشخصية، الخبرة، الإنذارات العدلية، والواقع العملي في الأردن.
لا تستخدم قوانين السعودية أو الإمارات أو مصر أو أي دولة أخرى عند تحليل حساب أردني.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "السعودية": """
اعتمد أسلوبًا مناسبًا للبيئة القضائية السعودية.
راعِ المنصات العدلية مثل ناجز، المحاكم المختصة، الصياغة الشرعية والنظامية، والتمييز بين الأنظمة واللوائح.
لا تستخدم قوانين الأردن أو الإمارات أو مصر عند تحليل حساب سعودي.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "الإمارات": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية الإماراتية.
راعِ وجود محاكم اتحادية ومحلية، والتمييز عند الحاجة بين القواعد الاتحادية والمحلية، واهتم بالمنازعات المدنية والتجارية والتحكيم.
لا تستخدم قوانين الأردن أو السعودية أو مصر عند تحليل حساب إماراتي.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "مصر": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية المصرية.
راعِ طبيعة المحاكم المصرية، الدعاوى المدنية والجنائية والتجارية، وأهمية المستندات والإنذارات والدفوع الإجرائية.
لا تستخدم قوانين الأردن أو السعودية أو الإمارات عند تحليل حساب مصري.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "العراق": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية العراقية.
راعِ طبيعة الدعاوى المدنية والجزائية والتجارية والعمالية في العراق، وأهمية المستندات الرسمية والبينات.
لا تستخدم قوانين دولة أخرى عند تحليل حساب عراقي.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "قطر": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية القطرية.
راعِ طبيعة المنازعات المدنية والتجارية والعمالية، والتمييز بين التحليل القانوني العام والإجراء القضائي العملي.
لا تستخدم قوانين دولة أخرى عند تحليل حساب قطري.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "الكويت": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية الكويتية.
راعِ طبيعة المحاكم الكويتية، المنازعات المدنية والتجارية والعمالية، وأهمية الإثبات والمستندات.
لا تستخدم قوانين دولة أخرى عند تحليل حساب كويتي.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "البحرين": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية البحرينية.
راعِ طبيعة المنازعات المدنية والتجارية والعمالية والإجراءات القضائية المحلية.
لا تستخدم قوانين دولة أخرى عند تحليل حساب بحريني.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
        "عُمان": """
اعتمد أسلوبًا مناسبًا للبيئة القانونية العُمانية.
راعِ طبيعة المنازعات المدنية والتجارية والعمالية والإجراءات القضائية المحلية.
لا تستخدم قوانين دولة أخرى عند تحليل حساب عُماني.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
""",
    }

    return styles.get(country, styles["الأردن"])


def get_role_instruction(user_role: str, country: str) -> str:
    roles = {
        "individual": """
نوع المستخدم: فرد / مستخدم عادي.
اكتب بلغة واضحة وبسيطة، وتجنب التعقيد القانوني الزائد.
ركز على:
- ماذا يعني الموقف؟
- ما الخطوات العملية؟
- متى يجب مراجعة محامٍ؟
- تجنب المصطلحات المعقدة قدر الإمكان.
لا تعرض كروت المحامين مثل الدفوع أو ملخص مهني إلا إذا طلب المستخدم ذلك صراحة.
""",
        "lawyer": f"""
نوع المستخدم: محامٍ.
فكر كمحامٍ يعمل ضمن البيئة القانونية في {country}.
استخدم أسلوبًا قانونيًا احترافيًا ومنهجيًا.
ركز على:
- التكييف القانوني المحتمل.
- عناصر المسؤولية أو الجريمة.
- عبء الإثبات.
- الدفوع المحتملة.
- الثغرات الإجرائية.
- المستندات والبينة.
- استراتيجية أولية للتعامل مع الملف.
""",
        "company": """
نوع المستخدم: شركة / رجل أعمال.
فكر بطريقة تجمع بين القانون وإدارة المخاطر.
ركز على:
- المخاطر القانونية.
- المخاطر المالية.
- المخاطر التشغيلية.
- أثر النزاع على السمعة والعلاقات التجارية.
- هل التسوية أفضل من التقاضي؟
- ما المستندات التي تحمي الشركة؟
""",
        "judge": """
نوع المستخدم: قاضٍ.
استخدم أسلوبًا محايدًا وتحليليًا.
لا تتبنَ طرفًا.
ركز على:
- الوقائع الثابتة.
- الوقائع محل النزاع.
- عبء الإثبات.
- مدى كفاية البينة.
- الأسئلة التي تحتاج تحقيقًا.
- النقاط القانونية التي يلزم التثبت منها.
لا تصدر حكمًا نهائيًا.
""",
        "law_student": """
نوع المستخدم: طالب قانون.
اجعل الجواب تعليميًا ومنظمًا.
اشرح المفاهيم القانونية بطريقة واضحة.
ركز على:
- تعريف المصطلحات.
- القاعدة القانونية العامة.
- تطبيق القاعدة على الوقائع.
- أمثلة مختصرة عند الحاجة.
""",
        "legal_researcher": """
نوع المستخدم: باحث قانوني.
استخدم أسلوبًا تحليليًا ومنظمًا.
ركز على:
- الإشكالية القانونية.
- القواعد العامة.
- نقاط المقارنة.
- حدود اليقين في التحليل.
- ما يحتاج إلى مصادر رسمية أو أحكام قضائية.
""",
        "government_employee": """
نوع المستخدم: موظف حكومي.
استخدم أسلوبًا عمليًا ورسميًا.
ركز على:
- الاختصاص.
- الإجراءات.
- المستندات المطلوبة.
- حدود الصلاحية.
- متى يجب تحويل الموضوع للجهة المختصة أو المستشار القانوني.
""",
    }

    return roles.get(user_role, roles["individual"])


def get_plan_instruction(plan: str) -> str:
    plans = {
        "free": """
الباقة: Free.
هذه باقة تجربة.
اجعل الإجابة مختصرة وحذرة.
ركز على الفهم العام، أهم المخاطر، وأول خطوة عملية.
""",
        "basic": """
الباقة: Basic.
قدّم إجابة منظمة وواضحة أكثر من Free.
اشرح الفكرة، المخاطر، المستندات الأساسية، والخطوات التالية.
""",
        "pro": """
الباقة: Pro.
قدّم تحليلًا أعمق ومنظمًا.
اشمل عند الحاجة فقط:
- التكييف المحتمل.
- المخاطر.
- المستندات.
- نقاط القوة والضعف.
- خطوات عملية.
- ملخص مناسب للمشاركة مع محام.
""",
        "premium": """
الباقة: Premium.
قدّم تحليلًا موسعًا ومتقدمًا عند الحاجة.
اشمل عند الحاجة فقط:
- التكييف القانوني المحتمل.
- المخاطر التفصيلية.
- الثغرات.
- الدفوع أو الاعتراضات المحتملة حسب نوع المستخدم.
- استراتيجية أولية.
- أسئلة متابعة مهمة.
- مستوى الثقة وحدود الدقة القانونية.
""",
        "enterprise": """
الباقة: Enterprise.
قدّم أعلى مستوى من التحليل المتاح عند الحاجة.
اشمل عند الحاجة فقط:
- تحليل قانوني عميق.
- مخاطر قانونية وتشغيلية وتجارية.
- استراتيجية منظمة.
- سيناريوهات محتملة.
- نقاط امتثال.
- ملخص تنفيذي واضح.
""",
        "staff_unlimited": """
الوضع: Staff Unlimited.
هذا استخدام داخلي غير محدود للموظفين.
قدّم أعلى مستوى من التحليل عند الحاجة، لكن لا تعرض كروت غير لازمة إذا كان السؤال بسيطًا أو عامًا.
""",
    }

    return plans.get(plan, plans["free"])


def get_combined_role_plan_instruction(user_role: str, plan: str, country: str) -> str:
    role_labels = {
        "individual": "فرد / مستخدم عادي",
        "lawyer": "محامي",
        "company": "شركة / رجل أعمال",
        "judge": "قاضٍ",
        "law_student": "طالب قانون",
        "legal_researcher": "باحث قانوني",
        "government_employee": "موظف حكومي",
    }

    plan_labels = {
        "free": "Free",
        "basic": "Basic",
        "pro": "Pro",
        "premium": "Premium",
        "enterprise": "Enterprise",
        "staff_unlimited": "Staff Unlimited",
    }

    role_label = role_labels.get(user_role, "فرد / مستخدم عادي")
    plan_label = plan_labels.get(plan, "Free")

    return f"""
تعليمات المزج بين الباقة ونوع المستخدم:

نوع المستخدم الحالي: {role_label}
الباقة الحالية أو الوضع الحالي: {plan_label}
الدولة القانونية: {country}

القاعدة الأساسية:
- نوع المستخدم يحدد زاوية التفكير وطريقة الصياغة.
- الباقة تحدد عمق التحليل وتفصيله.
- نوع السؤال يحدد الكروت التي يجب عرضها.
- لا تعرض كل الكروت دائمًا.
- إذا كان السؤال عامًا، اجعل الرد مختصرًا وواضحًا.
- إذا كان السؤال تحليل واقعة، اعرض كروت التحليل المناسبة.
- إذا كان السؤال طلب مادة أو تشريع، ركز على النصوص والمصادر فقط.
"""


def get_legal_accuracy_rules() -> str:
    return """
قواعد الدقة القانونية الصارمة:

1. مصادر Mizan المعتمدة هي المصدر الأساسي للتشريعات والمواد القانونية.
2. لا تذكر رقم مادة قانونية إلا إذا كان موجودًا ضمن مصادر Mizan المرفقة.
3. لا تخترع أرقام مواد.
4. لا تخترع أحكامًا قضائية أو سوابق أو اجتهادات.
5. لا تنسب نصًا لقانون محدد إذا لم يكن موجودًا ضمن المصادر المرفقة.
6. استخدم التحليل العام فقط لتفسير النصوص، شرح المخاطر، واقتراح الخطوات العملية.
7. إذا لم تكن هناك مصادر Mizan مناسبة، قل بوضوح إن التحليل عام وغير مستند إلى مادة معتمدة من قاعدة بيانات Mizan.
8. فرّق بين:
   - النص القانوني المعتمد من Mizan.
   - التحليل القانوني المبني على النص.
   - التحليل العام المساعد.
9. استخدم عبارات احتمالية مثل: قد، يحتمل، يتجه التكييف، يلزم التحقق.
10. لا تقل "حتمًا" أو "أكيد" أو "سيحكم القاضي" إلا إذا كانت النتيجة بديهية ومؤكدة من الوقائع والنص.
11. في القضايا الجنائية، لا تعتبر الشخص مذنبًا. استخدم: المشتبه به، المتهم، الفعل المنسوب، في حال ثبوت الفعل.
"""


def build_case_history_text(case_context: Optional[Dict[str, Any]]) -> str:
    if not case_context:
        return "لا توجد قضية محفوظة مرتبطة بهذا السؤال."

    parts = []

    case = case_context.get("case")
    if case:
        parts.append(
            f"""
معلومات القضية المحفوظة:
- العنوان: {case.get("title", "")}
- الدولة: {case.get("country", "")}
- نوع القضية: {case.get("case_type", "")}
- الخصم/الطرف الآخر: {case.get("opponent_name", "")}
- المحكمة: {case.get("court_name", "")}
- رقم القضية: {case.get("case_number", "")}
- الحالة: {case.get("status", "")}
- الملخص: {case.get("summary", "")}
"""
        )

    notes = case_context.get("notes") or []
    if notes:
        notes_text = "\n".join([f"- {n.get('note', '')}" for n in notes[:10]])
        parts.append(f"ملاحظات داخل القضية:\n{notes_text}")

    updates = case_context.get("updates") or []
    if updates:
        updates_text = "\n".join(
            [
                f"- {u.get('hearing_date', '')}: {u.get('update_text', '')}"
                for u in updates[:10]
            ]
        )
        parts.append(f"مستجدات القضية:\n{updates_text}")

    analyses = case_context.get("analyses") or []
    if analyses:
        analyses_text = "\n".join(
            [
                f"- سؤال سابق: {a.get('question', '')}"
                for a in analyses[:5]
            ]
        )
        parts.append(f"أسئلة وتحليلات سابقة مرتبطة بالقضية:\n{analyses_text}")

    documents = case_context.get("documents") or []
    if documents:
        docs_text = "\n".join(
            [
                f"- {d.get('filename', '')} / النوع: {d.get('document_type', '')}"
                for d in documents[:10]
            ]
        )
        parts.append(f"مستندات محفوظة في القضية:\n{docs_text}")

    return "\n\n".join(parts) if parts else "لا توجد تفاصيل محفوظة كافية داخل القضية."


def build_conversation_history_text(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
    if not conversation_history:
        return "لا يوجد سياق محادثة سابق داخل هذا التحليل."

    lines = []

    for item in conversation_history[-8:]:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()

        if not content:
            continue

        label = "المستخدم" if role == "user" else "Mizan"

        detected_case_type = item.get("detected_case_type", "")
        request_type = item.get("request_type", "")

        meta = []
        if request_type:
            meta.append(f"نوع الطلب السابق: {request_type}")
        if detected_case_type:
            meta.append(f"نوع القضية السابق: {detected_case_type}")

        meta_text = f" ({' / '.join(meta)})" if meta else ""

        lines.append(f"{label}{meta_text}: {content[:1200]}")

    return "\n\n".join(lines) if lines else "لا يوجد سياق محادثة سابق داخل هذا التحليل."


def get_request_type_instruction() -> str:
    return """
قبل الإجابة، صنّف طلب المستخدم إلى request_type واحد فقط:

1. general_question:
   إذا كان يسأل سؤالًا عامًا أو يريد فهم مفهوم قانوني.
   مثال: ما معنى إساءة الأمانة؟ ما الفرق بين العقد والاتفاق؟

2. case_analysis:
   إذا كان يذكر واقعة أو نزاعًا ويريد تحليل موقفه.
   مثال: شخص أخذ مني مبلغًا ولم يرجعه، ماذا أفعل؟

3. legal_article_request:
   إذا كان يريد مادة قانونية محددة أو نص مادة.
   مثال: أعطني المادة المتعلقة بإساءة الأمانة.

4. legislation_request:
   إذا كان يريد قانونًا أو تشريعًا كاملًا أو ملخص قانون.
   مثال: أعطني قانون العمل الأردني، أو لخص قانون الشركات.

5. procedure_guidance:
   إذا كان يريد خطوات عملية أو إجراءات.
   مثال: كيف أقدم شكوى؟ ما خطوات رفع دعوى؟

6. lawyer_brief:
   إذا طلب صياغة ملخص لمحامٍ أو تحضير ملف قانوني.

7. document_analysis:
   فقط عند تحليل مستند مرفق.

قاعدة مهمة:
- لا تعرض كل الكروت دائمًا.
- حدد cards_to_show حسب نوع السؤال ونوع المستخدم.
- إذا السؤال بسيط، اجعل cards_to_show قصيرة.
"""


def get_case_type_instruction() -> str:
    return """
تعليمات تحديد نوع القضية:

يجب دائمًا تحليل السؤال وتحديد detected_case_type قبل الإجابة.

القيم المسموحة:
- غير محدد
- مدني
- جنائي
- تجاري
- عمالي
- أحوال شخصية
- إداري
- عقاري
- تنفيذ
- عقود
- شركات
- إيجارات
- شيكات ومطالبات مالية
- ملكية فكرية
- أخرى

القواعد:
1. إذا selected_case_type = "غير محدد":
   - حدد detected_case_type من السؤال أو الوقائع.
   - لا تعرض تنبيه تصحيح، فقط اعرض التصنيف الأقرب.

2. إذا selected_case_type ليس "غير محدد":
   - راجع هل اختيار المستخدم صحيح.
   - إذا كان صحيحًا، اجعل case_type_match = true.
   - إذا كان غير صحيح، اجعل case_type_match = false.
   - في حالة الخطأ، لا تبنِ التحليل على الاختيار الخاطئ.
   - ابنِ التحليل على detected_case_type الصحيح.
   - اكتب case_type_correction_note واضحًا ومحترمًا.

3. مثال:
   إذا اختار المستخدم "مدني" لكن الوقائع تتعلق بإساءة أمانة أو احتيال:
   detected_case_type = "جنائي"
   case_type_match = false
   case_type_correction_note = "تم اختيار مدني، لكن الوقائع أقرب إلى قضية جنائية لأنها تتعلق بفعل قد يدخل في إساءة الأمانة أو الاحتيال، لذلك تم بناء التحليل على التصنيف الجنائي الأقرب."

4. لا تجعل اختيار المستخدم سببًا لإجابة قانونية خاطئة.
"""


async def analyze_legal_question(
    question: str,
    country: str,
    case_type: str,
    selected_case_type: str = "غير محدد",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    plan: str = "free",
    user_role: str = "individual",
    criminal_details: Optional[Dict[str, Any]] = None,
    case_context: Optional[Dict[str, Any]] = None,
    legal_sources_context: str = "",
    legal_source_policy: str = "",
    legal_sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    criminal_details = criminal_details or {}
    legal_sources = legal_sources or []
    selected_case_type = _normalize_case_type(selected_case_type or case_type)
    case_history = build_case_history_text(case_context)
    conversation_history_text = build_conversation_history_text(conversation_history)

    country_style = get_country_legal_style(country)
    role_instruction = get_role_instruction(user_role, country)
    plan_instruction = get_plan_instruction(plan)
    combined_instruction = get_combined_role_plan_instruction(user_role, plan, country)
    accuracy_rules = get_legal_accuracy_rules()
    request_type_instruction = get_request_type_instruction()
    case_type_instruction = get_case_type_instruction()

    prompt = f"""
أنت Mizan، مساعد قانوني ذكي باللغة العربية.

معلومات الحساب:
- الدولة القانونية للحساب: {country}
- نوع المستخدم: {user_role}
- الباقة أو الوضع: {plan}
- نوع القضية الذي اختاره المستخدم: {selected_case_type}

تعليمات الدولة:
{country_style}

تعليمات نوع المستخدم:
{role_instruction}

تعليمات الباقة:
{plan_instruction}

تعليمات المزج بين الباقة ونوع المستخدم:
{combined_instruction}

تعليمات تصنيف نوع الطلب والكروت:
{request_type_instruction}

تعليمات تحديد وتصحيح نوع القضية:
{case_type_instruction}

قواعد الدقة القانونية:
{accuracy_rules}

سياسة الاعتماد على مصادر Mizan:
{legal_source_policy}

مصادر Mizan القانونية المعتمدة المسترجعة لهذا السؤال:
{legal_sources_context}

سياق القضية المحفوظة:
{case_history}

سياق المحادثة السابقة داخل نفس التحليل:
{conversation_history_text}

تفاصيل جنائية إضافية إن وجدت:
{json.dumps(criminal_details, ensure_ascii=False)}

سؤال المستخدم الحالي:
{question}

مهم جدًا:
- لا تفترض أن كل سؤال هو تحليل قضية.
- لا تفترض أن اختيار المستخدم لنوع القضية صحيح.
- حدد detected_case_type دائمًا بناءً على السؤال والسياق.
- إذا كان السؤال متابعة قصيرة مثل "طيب شو أعمل؟"، استخدم سياق المحادثة السابقة لفهم المقصود.
- إذا كان السؤال عامًا، أجب كشرح قانوني عام ولا تعرض كروت قضية.
- إذا كان السؤال طلب مادة قانونية، ركز على النصوص الموجودة في مصادر Mizan.
- إذا كان السؤال طلب تشريع، ركز على ملخص التشريع أو المواد المتاحة فقط.
- إذا كان السؤال إجراء عملي، ركز على الخطوات.
- اجعل التشريعات والمواد القانونية المعتمدة من Mizan هي المصدر الرئيسي إذا كانت موجودة.
- استخدم فهمك العام كمصدر ثانوي فقط للتفسير والترتيب والتحليل العملي.
- لا تذكر أي رقم مادة أو نص قانوني إلا إذا كان موجودًا ضمن مصادر Mizan المرفقة.
- إذا لم توجد مصادر مناسبة من Mizan، قل ذلك بوضوح وقدم تحليلًا عامًا حذرًا.
- يجب أن يكون الرد JSON فقط بدون Markdown.

أرجع JSON بهذا الشكل فقط:
{{
  "request_type": "general_question | case_analysis | legal_article_request | legislation_request | procedure_guidance | lawyer_brief",
  "audience_mode": "{user_role}",
  "cards_to_show": [
    "short_answer"
  ],

  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",

  "short_answer": "جواب مختصر مناسب لنوع الطلب ونوع المستخدم",
  "plain_explanation": "شرح مبسط يظهر غالبًا للفرد أو السؤال العام",
  "practical_meaning": "ماذا يعني هذا للمستخدم العادي عمليًا",

  "country_context": "شرح كيف تؤثر دولة الحساب على الرد عند الحاجة",
  "case_understanding": "فهم موجز للوقائع إذا كان السؤال تحليل حالة",
  "legal_classification": "التكييف القانوني المحتمل إذا كان مناسبًا",

  "legal_basis": "الأساس القانوني العام أو النصي",
  "articles_requested": [
    "المواد القانونية المطلوبة فقط إذا طلب المستخدم مادة أو ظهرت من مصادر Mizan"
  ],
  "legislation_summary": "ملخص التشريع إذا طلب المستخدم قانونًا أو تشريعًا",

  "mizan_sources_summary": "ملخص واضح للمصادر المعتمدة التي تم استخدامها، أو توضيح أنه لم توجد مصادر مناسبة",
  "analysis_based_on_sources": "التحليل المبني مباشرة على مصادر Mizan المعتمدة",
  "general_legal_reasoning": "تحليل عام مساعد لا يخالف المصادر المعتمدة",
  "source_dependency_level": "مرتفع أو متوسط أو منخفض",

  "legal_accuracy_note": "ملاحظة عن دقة المواد القانونية وحدود التحليل",
  "confidence_level": "مرتفع أو متوسط أو منخفض",
  "confidence_reason": "سبب مستوى الثقة",

  "verified_legal_materials": [
    "اذكر فقط المواد أو النصوص الموجودة ضمن مصادر Mizan المرفقة"
  ],
  "unverified_legal_points": [
    "نقاط تحتاج تحقق من محام أو مصدر رسمي"
  ],

  "key_risks": [
    "مخاطر قانونية أو عملية عند الحاجة"
  ],
  "business_risks": [
    "مخاطر تجارية أو تشغيلية للشركات فقط عند الحاجة"
  ],
  "relevant_documents": [
    "مستندات مهمة عند الحاجة"
  ],
  "proof_points": [
    "نقاط الإثبات المهمة للمحامي أو تحليل الحالة"
  ],
  "defenses_or_arguments": [
    "دفوع أو حجج محتملة للمحامي أو المستخدم المتقدم"
  ],
  "similar_cases": [
    {{
      "title": "عنوان عام لحالة مشابهة دون اختراع حكم قضائي",
      "similarity": "وجه الشبه",
      "principle": "المبدأ العام إن وجد",
      "why_relevant": "سبب الارتباط"
    }}
  ],

  "criminal_penalty_estimate": {{
    "show": false,
    "alleged_crime": "",
    "possible_penalty_range": "",
    "factors_that_may_increase_penalty": [],
    "factors_that_may_reduce_penalty": [],
    "important_warning": ""
  }},

  "next_steps": [
    "خطوات عملية عامة"
  ],
  "procedure_steps": [
    "خطوات إجرائية إذا كان السؤال عن إجراء"
  ],
  "when_to_consult_lawyer": "متى يجب مراجعة محام",
  "educational_notes": "شرح تعليمي لطالب القانون عند الحاجة",

  "role_based_guidance": "توجيه خاص حسب نوع المستخدم",
  "plan_based_depth": "كيف أثرت الباقة على عمق التحليل",
  "combined_role_plan_note": "اشرح باختصار كيف تم المزج بين نوع المستخدم والباقة ونوع السؤال",
  "lawyer_summary": "ملخص منظم يمكن مشاركته مع محام فقط عند الحاجة",
  "disclaimer": "تنبيه قانوني واضح"
}}
"""

    response = generate_content_with_retry(
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    data = _safe_json_loads(response.text or "")
    result = _normalize_legal_result(
        data,
        user_role=user_role,
        selected_case_type=selected_case_type,
    )
    result["legal_sources"] = legal_sources

    return result


async def analyze_legal_document(
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    country: str,
    document_type: str,
    selected_case_type: str = "غير محدد",
    plan: str = "free",
    user_role: str = "individual",
    question: str = "",
    case_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    selected_case_type = _normalize_case_type(selected_case_type)

    country_style = get_country_legal_style(country)
    role_instruction = get_role_instruction(user_role, country)
    plan_instruction = get_plan_instruction(plan)
    combined_instruction = get_combined_role_plan_instruction(user_role, plan, country)
    accuracy_rules = get_legal_accuracy_rules()
    case_type_instruction = get_case_type_instruction()
    case_history = build_case_history_text(case_context)

    prompt = f"""
أنت Mizan، مساعد قانوني لتحليل المستندات القانونية باللغة العربية.

معلومات الحساب:
- الدولة القانونية للحساب: {country}
- نوع المستخدم: {user_role}
- الباقة أو الوضع: {plan}
- نوع المستند: {document_type}
- اسم الملف: {filename}
- نوع القضية الذي اختاره المستخدم: {selected_case_type}

تعليمات الدولة:
{country_style}

تعليمات نوع المستخدم:
{role_instruction}

تعليمات الباقة:
{plan_instruction}

تعليمات المزج بين الباقة ونوع المستخدم:
{combined_instruction}

تعليمات تحديد وتصحيح نوع القضية:
{case_type_instruction}

قواعد الدقة القانونية:
{accuracy_rules}

سياق القضية المحفوظة:
{case_history}

سؤال أو ملاحظة المستخدم حول المستند:
{question}

حلل المستند المرفق.
إذا كان المستند صورة أو PDF ممسوح، حاول قراءة محتواه بصريًا قدر الإمكان.
إذا لم يكن النص واضحًا، صرّح بذلك.
لا تذكر مواد قانونية أو أرقام مواد إلا إذا كنت متأكدًا من المستند نفسه أو من مصادر Mizan لاحقًا.
حدد detected_case_type من محتوى المستند أو السؤال.
إذا كان selected_case_type غير صحيح، نبّه المستخدم وصحح التصنيف.
اجعل طريقة الرد ناتجة من المزج بين نوع المستخدم والباقة.
أرجع JSON فقط بدون Markdown بهذا الشكل:

{{
  "request_type": "document_analysis",
  "audience_mode": "{user_role}",
  "cards_to_show": [
    "case_type_correction",
    "short_answer",
    "plain_explanation",
    "key_risks",
    "relevant_documents",
    "verified_legal_materials",
    "disclaimer"
  ],

  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",

  "document_type": "نوع المستند",
  "summary": "ملخص المستند",
  "country_context": "تأثير دولة الحساب على التحليل",
  "confidence_level": "مرتفع أو متوسط أو منخفض",
  "confidence_reason": "سبب مستوى الثقة",
  "parties": [],
  "main_obligations": [],
  "risky_clauses": [],
  "legal_gaps": [],
  "missing_clauses": [],
  "suggested_edits": [],
  "verified_legal_materials": [],
  "unverified_legal_points": [],
  "risk_level": "منخفض أو متوسط أو مرتفع",
  "role_based_guidance": "توجيه خاص حسب نوع المستخدم",
  "plan_based_depth": "كيف أثرت الباقة على عمق التحليل",
  "combined_role_plan_note": "اشرح باختصار كيف تم المزج بين نوع المستخدم والباقة في هذا الرد",
  "lawyer_summary": "ملخص للمحامي إذا كان مناسبًا",
  "disclaimer": "تنبيه قانوني"
}}
"""

    file_part = types.Part.from_bytes(
        data=file_bytes,
        mime_type=mime_type or "application/octet-stream",
    )

    response = generate_content_with_retry(
        contents=[prompt, file_part],
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    data = _safe_json_loads(response.text or "")
    return _normalize_document_result(
        data,
        selected_case_type=selected_case_type,
    )