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

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

REQUEST_TYPES = [
    "general_question",
    "case_analysis",
    "legal_research",
    "legal_article_request",
    "legislation_request",
    "procedure_guidance",
    "lawyer_brief",
    "document_analysis",
    "contract_review",
    "legal_drafting",
    "litigation_strategy",
    "corporate_advisory",
]

ASSISTANT_MODES = [
    "case_analysis",
    "legal_research",
    "document_analysis",
    "contract_review",
    "legal_drafting",
    "litigation_strategy",
    "corporate_advisory",
]

AUDIENCE_MODES = [
    "legal_professional",
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
    "professional_summary",
    "facts_assumptions",
    "legal_issues",
    "governing_law",
    "source_based_analysis",
    "application_to_facts",
    "strengths",
    "weaknesses",
    "opposing_arguments",
    "strategic_recommendations",
    "drafting_notes",
    "missing_information",
    "final_recommendation",
    "source_limitations",
    "lawyer_summary",
    "confidence",
    "disclaimer",
    "legal_sources",
]

DEFAULT_DISCLAIMER = (
    "هذا المخرج تحليل قانوني مهني مساعد مبني على الوقائع والمستندات والمصادر المتاحة داخل النظام، "
    "ولا يغني عن مسؤولية المحامي أو المستشار في التحقق النهائي من النصوص والوقائع والإجراءات قبل الاستخدام."
)


def generate_content_with_retry(contents, config, retries: int = 2):
    if not client:
        raise RuntimeError("GEMINI_API_KEY غير موجود. أضفه في Environment Variables على Render أو في ملف .env محليًا.")

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
                retryable = any(term in error_text.lower() for term in ["503", "unavailable", "overloaded", "temporarily", "rate"])
                if not retryable:
                    raise
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError("مزود الذكاء الاصطناعي مشغول حاليًا. يرجى إعادة المحاولة بعد قليل.") from last_error


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
    return value if value in REQUEST_TYPES else "general_question"


def _normalize_audience_mode(value: Any, user_role: str) -> str:
    value = str(value or "").strip()
    if value == "individual":
        value = "legal_professional"
    if value in AUDIENCE_MODES:
        return value
    if user_role == "individual":
        return "legal_professional"
    if user_role in AUDIENCE_MODES:
        return user_role
    return "legal_professional"


def _normalize_assistant_mode(value: Any) -> str:
    value = str(value or "").strip()
    return value if value in ASSISTANT_MODES else "case_analysis"


def _normalize_case_type(value: Any) -> str:
    value = str(value or "").strip()
    if not value:
        return "غير محدد"
    return value if value in VALID_CASE_TYPES else value


def _case_type_matches(selected_case_type: str, detected_case_type: str) -> bool:
    selected = _normalize_case_type(selected_case_type)
    detected = _normalize_case_type(detected_case_type)
    if selected == "غير محدد" or detected == "غير محدد":
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
    return get_default_cards_for_request(request_type, user_role)


def get_default_cards_for_request(request_type: str, user_role: str) -> List[str]:
    # Professional legal workbench: always favor structured legal work product over simple chat.
    base = [
        "case_type_correction",
        "professional_summary",
        "facts_assumptions",
        "legal_issues",
        "governing_law",
        "verified_legal_materials",
        "source_based_analysis",
        "application_to_facts",
        "strengths",
        "weaknesses",
        "opposing_arguments",
        "strategic_recommendations",
        "missing_information",
        "final_recommendation",
        "confidence",
        "legal_sources",
        "disclaimer",
    ]

    if request_type == "legal_research":
        return [
            "case_type_correction", "professional_summary", "legal_issues", "governing_law",
            "verified_legal_materials", "source_based_analysis", "source_limitations",
            "confidence", "legal_sources", "disclaimer"
        ]

    if request_type == "contract_review":
        return [
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "source_based_analysis", "key_risks", "business_risks",
            "weaknesses", "strategic_recommendations", "drafting_notes", "missing_information",
            "confidence", "legal_sources", "disclaimer"
        ]

    if request_type == "legal_drafting":
        return [
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "drafting_notes", "source_based_analysis", "missing_information",
            "final_recommendation", "confidence", "legal_sources", "disclaimer"
        ]

    if request_type == "litigation_strategy":
        return [
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "application_to_facts", "strengths", "weaknesses",
            "opposing_arguments", "proof_points", "strategic_recommendations", "relevant_documents",
            "missing_information", "confidence", "legal_sources", "disclaimer"
        ]

    if request_type == "document_analysis":
        return [
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "source_based_analysis", "application_to_facts", "key_risks",
            "relevant_documents", "missing_information", "strategic_recommendations",
            "confidence", "legal_sources", "disclaimer"
        ]

    return base

def _normalize_legal_result(data: Dict[str, Any], user_role: str, selected_case_type: str) -> Dict[str, Any]:
    criminal = data.get("criminal_penalty_estimate") or {}
    if not isinstance(criminal, dict):
        criminal = {}

    request_type = _normalize_request_type(data.get("request_type"))
    audience_mode = _normalize_audience_mode(data.get("audience_mode"), user_role)
    selected = _normalize_case_type(data.get("selected_case_type") or selected_case_type or "غير محدد")
    detected = _normalize_case_type(data.get("detected_case_type") or "غير محدد")

    case_type_match = data.get("case_type_match")
    if not isinstance(case_type_match, bool):
        case_type_match = _case_type_matches(selected, detected)

    correction_note = data.get("case_type_correction_note", "")
    if not correction_note and not case_type_match and selected != "غير محدد":
        correction_note = f"تم اختيار نوع القضية على أنه ({selected})، لكن من خلال الوقائع أو السؤال يظهر أن التصنيف الأقرب هو ({detected}). لذلك تم بناء التحليل على النوع الأقرب قانونيًا."

    return {
        "request_type": request_type,
        "assistant_mode": _normalize_assistant_mode(data.get("assistant_mode") or request_type),
        "audience_mode": audience_mode,
        "cards_to_show": _clean_card_list(data.get("cards_to_show"), request_type, audience_mode),
        "selected_case_type": selected,
        "detected_case_type": detected,
        "case_type_match": case_type_match,
        "case_type_correction_note": correction_note,
        "short_answer": data.get("short_answer", ""),
        "professional_summary": data.get("professional_summary", "") or data.get("executive_summary", "") or data.get("short_answer", ""),
        "facts_assumptions": _ensure_list(data.get("facts_assumptions")),
        "legal_issues": _ensure_list(data.get("legal_issues")),
        "governing_law": _ensure_list(data.get("governing_law")),
        "source_based_analysis": data.get("source_based_analysis", "") or data.get("analysis_based_on_sources", ""),
        "application_to_facts": data.get("application_to_facts", ""),
        "strengths": _ensure_list(data.get("strengths")),
        "weaknesses": _ensure_list(data.get("weaknesses")),
        "opposing_arguments": _ensure_list(data.get("opposing_arguments")),
        "strategic_recommendations": _ensure_list(data.get("strategic_recommendations")),
        "drafting_notes": _ensure_list(data.get("drafting_notes")),
        "missing_information": _ensure_list(data.get("missing_information")),
        "final_recommendation": data.get("final_recommendation", ""),
        "source_limitations": _ensure_list(data.get("source_limitations")),
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
        "disclaimer": data.get("disclaimer", DEFAULT_DISCLAIMER),
        "criminal_penalty_estimate": {
            "show": bool(criminal.get("show", False)),
            "alleged_crime": criminal.get("alleged_crime", ""),
            "possible_penalty_range": criminal.get("possible_penalty_range", ""),
            "factors_that_may_increase_penalty": _ensure_list(criminal.get("factors_that_may_increase_penalty")),
            "factors_that_may_reduce_penalty": _ensure_list(criminal.get("factors_that_may_reduce_penalty")),
            "important_warning": criminal.get("important_warning", ""),
        },
    }


def _normalize_document_result(data: Dict[str, Any], selected_case_type: str, user_role: str) -> Dict[str, Any]:
    selected = _normalize_case_type(data.get("selected_case_type") or selected_case_type or "غير محدد")
    detected = _normalize_case_type(data.get("detected_case_type") or "غير محدد")
    match = data.get("case_type_match") if isinstance(data.get("case_type_match"), bool) else _case_type_matches(selected, detected)
    return {
        "request_type": "document_analysis",
        "audience_mode": _normalize_audience_mode(data.get("audience_mode"), user_role),
        "cards_to_show": _clean_card_list(data.get("cards_to_show"), "document_analysis", user_role),
        "selected_case_type": selected,
        "detected_case_type": detected,
        "case_type_match": match,
        "case_type_correction_note": data.get("case_type_correction_note", ""),
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
        "disclaimer": data.get("disclaimer", DEFAULT_DISCLAIMER),
    }


def get_country_legal_style(country: str) -> str:
    return f"""
اعتمد أسلوبًا مناسبًا للبيئة القانونية في {country}.
لا تستخدم قوانين دولة أخرى عند تحليل حساب من {country}.
إذا لم تكن المادة موجودة ضمن مصادر Mizan المرفقة، لا تذكر رقمها.
"""


def get_role_instruction(user_role: str, country: str) -> str:
    normalized = "legal_professional" if user_role == "individual" else (user_role or "legal_professional")
    roles = {
        "legal_professional": f"نوع المستخدم: مهني قانوني. اكتب كأنك محامٍ خبير في {country}: تحلل الوقائع، تربطها بالنصوص، تذكر المخاطر والدفوع، ولا تقدم جوابًا عامًا أو سطحيًا.",
        "lawyer": f"نوع المستخدم: محامٍ. استخدم أسلوبًا قانونيًا احترافيًا عميقًا ضمن البيئة القانونية في {country}، وركز على التكييف والدفوع والإثبات والاستراتيجية.",
        "company": "نوع المستخدم: شركة / دائرة قانونية. ركز على المخاطر القانونية والتعاقدية والمالية والامتثال والبدائل العملية.",
        "judge": "نوع المستخدم: قاضٍ أو باحث قضائي. استخدم أسلوبًا محايدًا ومتوازنًا ولا تصدر حكمًا نهائيًا دون وقائع كاملة.",
        "law_student": "نوع المستخدم: طالب أو متدرب قانوني. اجعل الجواب تعليميًا ومنظمًا مع قاعدة وتطبيق، لكن بنفس معيار الدقة المهنية.",
        "legal_researcher": "نوع المستخدم: باحث قانوني. استخدم أسلوبًا تحليليًا ومنظمًا مع تمييز النصوص المؤكدة عن الاستنتاجات.",
        "government_employee": "نوع المستخدم: موظف حكومي. ركز على الاختصاص والإجراءات وحدود الصلاحية والامتثال للتشريعات.",
    }
    return roles.get(normalized, roles["legal_professional"])

def get_plan_instruction(plan: str) -> str:
    if plan in ["enterprise", "premium", "staff_unlimited"]:
        return "قدّم تحليلًا عميقًا عند الحاجة، لكن لا تعرض كروت غير لازمة إذا كان السؤال بسيطًا."
    if plan in ["pro", "lawyer", "business"]:
        return "قدّم تحليلًا منظمًا مع مخاطر ومستندات وخطوات عملية."
    return "اجعل الإجابة واضحة ومختصرة وحذرة."


def get_accuracy_rules() -> str:
    return """
قواعد الدقة المهنية:
- مصادر Mizan المعتمدة هي المصدر الأساسي لأي نص تشريعي أو رقم مادة.
- لا تذكر رقم مادة قانونية إلا إذا كان موجودًا ضمن مصادر Mizan المرفقة أو صرح المستخدم بالنص.
- إذا لم توجد مصادر كافية، قل بوضوح إن الرأي غير مكتمل ولا تخترع نصوصًا.
- فرّق دائمًا بين: نص قانوني مؤكد، استنتاج قانوني، افتراض واقعي، ومعلومة ناقصة.
- لا تخترع أحكامًا قضائية أو سوابق.
- لا تستخدم قانونًا آخر بدل القانون المطلوب. إذا كان السؤال عن الدستور فلا تستخدم قانون الضمان أو البلديات أو التعليم العالي.
- إذا كانت المصادر المسترجعة لا تنتمي للتشريع المطلوب أو لا تعالج السؤال موضوعيًا، صرّح بذلك ولا تبنِ عليها الجواب.
- لا تعطي نتيجة قطعية إذا كانت الوقائع أو المستندات ناقصة.
- في القضايا الجنائية لا تعتبر الشخص مذنبًا، استخدم: الفعل المنسوب، في حال ثبوت الفعل.
- يجب أن يكون الجواب مفيدًا لمحامٍ: دفوع، مخاطر، إثبات، استراتيجية، ومعلومات ناقصة.
"""




def build_no_source_professional_result(
    *,
    question: str,
    selected_case_type: str,
    assistant_mode: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Safe result when Mizan has no reliable approved sources for a legal-source-dependent question."""
    limitation = reason or "لم يتم العثور على مصدر قانوني معتمد ومطابق داخل قاعدة بيانات Mizan لهذا السؤال."
    return {
        "request_type": "legal_research",
        "assistant_mode": assistant_mode,
        "audience_mode": "legal_professional",
        "cards_to_show": [
            "professional_summary",
            "legal_issues",
            "source_limitations",
            "missing_information",
            "final_recommendation",
            "confidence",
            "legal_sources",
            "disclaimer",
        ],
        "selected_case_type": selected_case_type,
        "detected_case_type": selected_case_type or "غير محدد",
        "case_type_match": True,
        "case_type_correction_note": "",
        "short_answer": "",
        "professional_summary": "لا يمكن تقديم إجابة قانونية جازمة من مصادر Mizan المعتمدة لأن المصدر القانوني المطابق للسؤال غير متوفر أو غير معتمد ضمن قاعدة البيانات الحالية.",
        "facts_assumptions": [],
        "legal_issues": ["تحديد المصدر القانوني المعتمد اللازم للإجابة.", "منع الاعتماد على تشريعات غير مرتبطة بالسؤال."],
        "governing_law": [],
        "source_based_analysis": "",
        "application_to_facts": "",
        "strengths": [],
        "weaknesses": ["غياب مصدر قانوني معتمد ومطابق داخل Mizan يمنع بناء رأي قانوني مهني جازم."],
        "opposing_arguments": [],
        "strategic_recommendations": [
            "إدخال واعتماد التشريع الصحيح داخل Mizan أولًا إذا كان السؤال يتطلب نصًا تشريعيًا محددًا.",
            "إعادة طرح السؤال بعد اعتماد التشريع أو إرفاق النص القانوني المطلوب كمستند.",
        ],
        "drafting_notes": [],
        "missing_information": [
            "النص القانوني المعتمد المطابق للسؤال داخل قاعدة بيانات Mizan.",
            "تحديد التشريع أو المادة المطلوب الاعتماد عليها إن كان السؤال عامًا.",
        ],
        "final_recommendation": "لا تعتمد على هذا الجواب كرأي قانوني نهائي قبل توفير المصدر القانوني المعتمد المطابق للسؤال.",
        "source_limitations": [limitation],
        "plain_explanation": "",
        "practical_meaning": "",
        "country_context": "",
        "case_understanding": "",
        "legal_classification": "",
        "legal_basis": "",
        "articles_requested": [],
        "legislation_summary": "",
        "legal_accuracy_note": limitation,
        "confidence_level": "منخفض",
        "confidence_reason": "لا توجد مصادر قانونية معتمدة ومطابقة داخل Mizan يمكن البناء عليها.",
        "mizan_sources_summary": "",
        "analysis_based_on_sources": "",
        "general_legal_reasoning": "",
        "source_dependency_level": "منخفض",
        "verified_legal_materials": [],
        "unverified_legal_points": [limitation],
        "key_risks": ["خطر استخدام تشريع غير مرتبط أو غير معتمد إذا تم تجاوز حارس المصادر."],
        "business_risks": [],
        "relevant_documents": [],
        "proof_points": [],
        "defenses_or_arguments": [],
        "similar_cases": [],
        "next_steps": [],
        "procedure_steps": [],
        "when_to_consult_lawyer": "",
        "educational_notes": "",
        "lawyer_summary": "",
        "role_based_guidance": "",
        "plan_based_depth": "",
        "combined_role_plan_note": "",
        "disclaimer": DEFAULT_DISCLAIMER,
        "criminal_penalty_estimate": {
            "show": False,
            "alleged_crime": "",
            "possible_penalty_range": "",
            "factors_that_may_increase_penalty": [],
            "factors_that_may_reduce_penalty": [],
            "important_warning": "",
        },
        "legal_sources": [],
    }

def get_request_type_instruction() -> str:
    return """
صنّف الطلب إلى request_type واحد:
general_question: سؤال عام يحتاج جوابًا مهنيًا.
case_analysis: وقائع أو نزاع أو تحليل موقف قانوني.
legal_research: بحث قانوني في النصوص والمصادر.
legal_article_request: طلب مادة قانونية محددة.
legislation_request: طلب قانون أو تشريع كامل أو ملخص تشريع.
procedure_guidance: سؤال عن خطوات وإجراءات.
lawyer_brief: ملخص أو تحضير ملف لمحامٍ.
document_analysis: تحليل مستندات.
contract_review: مراجعة عقد أو اتفاقية.
legal_drafting: صياغة مذكرة أو إنذار أو لائحة أو خطاب.
litigation_strategy: استراتيجية دعوى أو دفاع أو تفاوض.
corporate_advisory: رأي قانوني لشركة أو امتثال.
اجعل cards_to_show مناسبة للمهمة ولا تكتفِ بجواب مختصر.
"""


def get_case_type_instruction() -> str:
    return """
حدد detected_case_type دائمًا من السؤال والسياق.
إذا selected_case_type = غير محدد، حدد التصنيف تلقائيًا دون تنبيه تصحيح.
إذا اختار المستخدم نوعًا خاطئًا، اجعل case_type_match=false واكتب case_type_correction_note وحلل حسب detected_case_type الصحيح.
القيم المسموحة: غير محدد، مدني، جنائي، تجاري، عمالي، أحوال شخصية، إداري، عقاري، تنفيذ، عقود، شركات، إيجارات، شيكات ومطالبات مالية، ملكية فكرية، أخرى.
"""


def build_conversation_history_text(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
    if not conversation_history:
        return "لا يوجد سياق محادثة سابق."
    lines = []
    for item in conversation_history[-8:]:
        if not isinstance(item, dict):
            continue
        role = "المستخدم" if item.get("role") == "user" else "Mizan"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content[:1200]}")
    return "\n\n".join(lines) if lines else "لا يوجد سياق محادثة سابق."


async def analyze_legal_question(
    question: str,
    country: str,
    case_type: str = "غير محدد",
    selected_case_type: str = "غير محدد",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    plan: str = "free",
    user_role: str = "individual",
    criminal_details: Optional[Dict[str, Any]] = None,
    legal_sources_context: str = "",
    legal_source_policy: str = "",
    legal_sources: Optional[List[Dict[str, Any]]] = None,
    assistant_mode: str = "case_analysis",
) -> Dict[str, Any]:
    legal_sources = legal_sources or []
    criminal_details = criminal_details or {}
    selected_case_type = _normalize_case_type(selected_case_type or case_type)
    assistant_mode = _normalize_assistant_mode(assistant_mode)

    source_dependent_terms = [
        "الدستور", "دستوري", "دستورية", "مادة", "قانون", "تشريع",
        "صلاحيات", "حقوق", "حرية الرأي", "حرية التعبير", "مجلس النواب", "مجلس الأعيان",
    ]
    if not legal_sources and any(term in (question or "") for term in source_dependent_terms):
        return build_no_source_professional_result(
            question=question,
            selected_case_type=selected_case_type,
            assistant_mode=assistant_mode,
            reason="لم يتم العثور على مصادر Mizan معتمدة ومطابقة للسؤال. تم منع استخدام مصادر غير مرتبطة.",
        )

    # Determine missing laws for source guard
    from app.services.legal_source_guard import evaluate_source_quality
    _guard_eval = evaluate_source_quality(question, legal_sources)
    _missing_laws = _guard_eval.get("missing_laws", [])
    _has_sources = _guard_eval.get("has_valid_sources", len(legal_sources) > 0)

    prompt = f"""
أنت Mizan، مساعد قانوني احترافي باللغة العربية، تعمل كمحامٍ خبير ومحلل قانوني متقدم للمحامين والشركات والمستشارين.
لا تتعامل مع الطلب كدردشة عامة؛ تعامل معه كملف عمل قانوني مهني — Legal Workbench.

معلومات الحساب:
- الدولة القانونية: {country}
- نوع المستخدم: {user_role}
- الباقة: {plan}
- نوع القضية الذي اختاره المستخدم: {selected_case_type}
- وضع المساعد المطلوب: {assistant_mode}

تعليمات الوضع:
{get_mode_system_instruction(assistant_mode)}

تعليمات الدولة:
{get_country_legal_style(country)}

تعليمات نوع المستخدم:
{get_role_instruction(user_role, country)}

تعليمات الباقة:
{get_plan_instruction(plan)}

تعليمات نوع الطلب:
{get_request_type_instruction()}

تعليمات نوع القضية:
{get_case_type_instruction()}

قواعد الدقة:
{get_accuracy_rules()}

هيكل الجواب المهني:
{get_professional_response_template_instruction(assistant_mode)}

{get_confidence_engine_instruction(_has_sources, _missing_laws, assistant_mode)}

سياسة الاعتماد على مصادر Mizan:
{legal_source_policy}

قاعدة مطلقة [SOURCE GUARD]:
إذا لم تكن المصادر المسترجعة من نفس التشريع المطلوب أو ذات صلة مباشرة بالسؤال، اعتبرها غير صالحة ولا تستخدمها.
إذا لم توجد مصادر صالحة وكان السؤال يتطلب نصًا تشريعيًا محددًا، قل صراحة:
"لا توجد مصادر معتمدة كافية داخل Mizan للإجابة الجازمة على هذا السؤال."
لا تستبدل التشريع الغائب بتشريع آخر غير مرتبط.

مصادر Mizan القانونية المسترجعة:
{legal_sources_context}

سياق المحادثة السابقة:
{build_conversation_history_text(conversation_history)}

تفاصيل جنائية إضافية:
{json.dumps(criminal_details, ensure_ascii=False)}

سؤال المستخدم الحالي:
{question}

أرجع JSON فقط بدون Markdown بهذا الشكل:
{{
  "request_type": "general_question | case_analysis | legal_research | legal_article_request | legislation_request | procedure_guidance | lawyer_brief | document_analysis | contract_review | legal_drafting | litigation_strategy | corporate_advisory",
  "assistant_mode": "{assistant_mode}",
  "audience_mode": "legal_professional",
  "cards_to_show": ["short_answer"],
  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",
  "short_answer": "",
  "professional_summary": "خلاصة قانونية مهنية مركزة",
  "facts_assumptions": [],
  "legal_issues": [],
  "governing_law": [],
  "source_based_analysis": "",
  "application_to_facts": "",
  "strengths": [],
  "weaknesses": [],
  "opposing_arguments": [],
  "strategic_recommendations": [],
  "drafting_notes": [],
  "missing_information": [],
  "final_recommendation": "",
  "source_limitations": [],
  "plain_explanation": "",
  "practical_meaning": "",
  "country_context": "",
  "case_understanding": "",
  "legal_classification": "",
  "legal_basis": "",
  "articles_requested": [],
  "legislation_summary": "",
  "mizan_sources_summary": "",
  "analysis_based_on_sources": "",
  "general_legal_reasoning": "",
  "source_dependency_level": "مرتفع أو متوسط أو منخفض",
  "legal_accuracy_note": "",
  "confidence_level": "مرتفع أو متوسط أو منخفض",
  "confidence_reason": "",
  "verified_legal_materials": [],
  "unverified_legal_points": [],
  "key_risks": [],
  "business_risks": [],
  "relevant_documents": [],
  "proof_points": [],
  "defenses_or_arguments": [],
  "similar_cases": [],
  "criminal_penalty_estimate": {{"show": false, "alleged_crime": "", "possible_penalty_range": "", "factors_that_may_increase_penalty": [], "factors_that_may_reduce_penalty": [], "important_warning": ""}},
  "next_steps": [],
  "procedure_steps": [],
  "when_to_consult_lawyer": "",
  "educational_notes": "",
  "role_based_guidance": "",
  "plan_based_depth": "",
  "combined_role_plan_note": "",
  "lawyer_summary": "",
  "disclaimer": "{DEFAULT_DISCLAIMER}"
}}
"""

    response = generate_content_with_retry(
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
    )
    data = _safe_json_loads(response.text or "")
    result = _normalize_legal_result(data, user_role=user_role, selected_case_type=selected_case_type)
    result["legal_sources"] = legal_sources
    return result


async def analyze_legal_question_with_documents(
    question: str,
    document_files: List[Dict[str, Any]],
    country: str,
    case_type: str = "غير محدد",
    selected_case_type: str = "غير محدد",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    plan: str = "free",
    user_role: str = "individual",
    criminal_details: Optional[Dict[str, Any]] = None,
    legal_sources_context: str = "",
    legal_source_policy: str = "",
    legal_sources: Optional[List[Dict[str, Any]]] = None,
    assistant_mode: str = "case_analysis",
) -> Dict[str, Any]:
    """
    تحليل سؤال قانوني مع مستندات مرفقة.
    يستخدم Gemini لقراءة الملفات مباشرة، ثم يربط محتوى الملفات بسؤال المستخدم ووقائع القضية.
    """
    if not document_files:
        return await analyze_legal_question(
            question=question,
            country=country,
            case_type=case_type,
            selected_case_type=selected_case_type,
            conversation_history=conversation_history,
            plan=plan,
            user_role=user_role,
            criminal_details=criminal_details,
            legal_sources_context=legal_sources_context,
            legal_source_policy=legal_source_policy,
            legal_sources=legal_sources,
            assistant_mode=assistant_mode,
        )

    legal_sources = legal_sources or []
    criminal_details = criminal_details or {}
    selected_case_type = _normalize_case_type(selected_case_type or case_type)
    assistant_mode = _normalize_assistant_mode(assistant_mode)

    is_staff_unlimited = (plan or "").strip().lower() == "staff_unlimited"

    # لا نضع حدًا لعدد الملفات لحسابات الموظفين.
    # يبقى حد الحجم موجودًا لحماية الذاكرة وقيود مزود الذكاء الاصطناعي.
    if not is_staff_unlimited and len(document_files) > 10:
        raise ValueError("يمكن رفع 10 ملفات كحد أقصى في الطلب الواحد.")

    total_size = sum(len(item.get("file_bytes") or b"") for item in document_files)
    max_total_size = 200 * 1024 * 1024 if is_staff_unlimited else 60 * 1024 * 1024
    if total_size > max_total_size:
        max_mb = max_total_size // (1024 * 1024)
        raise ValueError(f"إجمالي حجم الملفات كبير جدًا. الحد الحالي {max_mb}MB للطلب الواحد.")

    file_descriptions = []
    file_parts = []

    for index, item in enumerate(document_files, start=1):
        file_bytes = item.get("file_bytes") or b""
        filename = item.get("filename") or f"document_{index}"
        content_type = item.get("content_type") or "application/octet-stream"

        if not file_bytes:
            continue

        max_file_size = 50 * 1024 * 1024 if is_staff_unlimited else 20 * 1024 * 1024
        if len(file_bytes) > max_file_size:
            max_file_mb = max_file_size // (1024 * 1024)
            raise ValueError(f"حجم الملف {filename} كبير جدًا. الحد الحالي {max_file_mb}MB لكل ملف.")

        file_descriptions.append(
            f"{index}. {filename} — النوع: {content_type} — الحجم: {len(file_bytes)} bytes"
        )
        file_parts.append(types.Part.from_bytes(data=file_bytes, mime_type=content_type))

    if not file_parts:
        raise ValueError("لم تصل ملفات صالحة للتحليل.")

    # Determine missing laws for source guard
    from app.services.legal_source_guard import evaluate_source_quality as _eval_quality
    _doc_guard = _eval_quality(question, legal_sources or [])
    _doc_missing = _doc_guard.get("missing_laws", [])
    _doc_has_sources = _doc_guard.get("has_valid_sources", len(legal_sources or []) > 0)

    prompt = f"""
أنت Mizan، مساعد قانوني احترافي باللغة العربية، تعمل كمحامٍ خبير ومحلل قانوني متقدم.

المهمة:
حلّل سؤال المستخدم بناءً على الملفات القانونية المرفقة، واربط بين محتوى الملفات والوقائع والسؤال والتشريعات المعتمدة.
لا تكتفِ بتلخيص الملفات؛ يجب أن تنتج تحليلًا قانونيًا مهنيًا يتضمن الوقائع، المسائل، النصوص، التطبيق، المخاطر، الاستراتيجية، والمعلومات الناقصة.

معلومات الحساب:
- الدولة القانونية: {country}
- نوع المستخدم: {user_role}
- الباقة: {plan}
- نوع القضية الذي اختاره المستخدم: {selected_case_type}
- وضع المساعد المطلوب: {assistant_mode}

الملفات المرفقة:
{chr(10).join(file_descriptions)}

تعليمات الدولة:
{get_country_legal_style(country)}

تعليمات نوع المستخدم:
{get_role_instruction(user_role, country)}

تعليمات الباقة:
{get_plan_instruction(plan)}

تعليمات نوع الطلب:
{get_request_type_instruction()}

تعليمات نوع القضية:
{get_case_type_instruction()}

قواعد الدقة:
{get_accuracy_rules()}

سياسة الاعتماد على مصادر Mizan:
{legal_source_policy}

قاعدة حاسمة:
إذا لم تكن المصادر المسترجعة من نفس التشريع المطلوب أو ذات صلة مباشرة بالسؤال، اعتبرها غير صالحة ولا تستخدمها.
إذا لم توجد مصادر صالحة، اذكر ذلك بوضوح ولا تقدّم جوابًا جازمًا ولا تستبدلها بمصادر أخرى.

مصادر Mizan القانونية المسترجعة:
{legal_sources_context}

سياق المحادثة السابقة:
{build_conversation_history_text(conversation_history)}

تفاصيل جنائية إضافية:
{json.dumps(criminal_details, ensure_ascii=False)}

سؤال المستخدم الحالي:
{question}

تعليمات خاصة بالملفات:
- استخرج من الملفات: الأطراف، الوقائع، التواريخ، الالتزامات، المستندات الناقصة، المخاطر، والتناقضات إن وجدت.
- إذا كان السؤال عن شرح القضية، قدّم case_understanding واضحًا.
- إذا كان السؤال عن موقف قانوني، قدّم legal_classification وproof_points وkey_risks.
- إذا وجدت تناقضًا بين الملفات، اذكره ضمن key_risks أو unverified_legal_points.
- إذا كان النص غير واضح بسبب صورة أو PDF ممسوح، اذكر أثر ذلك على الثقة.
- لا تذكر مواد قانونية بأرقام إلا إذا كانت ضمن مصادر Mizan المرفقة.

أرجع JSON فقط بدون Markdown بهذا الشكل:
{{
  "request_type": "case_analysis | lawyer_brief | procedure_guidance | general_question | document_analysis | contract_review | legal_drafting | litigation_strategy",
  "assistant_mode": "{assistant_mode}",
  "audience_mode": "legal_professional",
  "cards_to_show": ["case_type_correction", "short_answer", "case_understanding", "legal_classification", "proof_points", "key_risks", "relevant_documents", "next_steps", "verified_legal_materials", "legal_sources", "disclaimer"],
  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",
  "short_answer": "",
  "professional_summary": "خلاصة قانونية مهنية مركزة",
  "facts_assumptions": [],
  "legal_issues": [],
  "governing_law": [],
  "source_based_analysis": "",
  "application_to_facts": "",
  "strengths": [],
  "weaknesses": [],
  "opposing_arguments": [],
  "strategic_recommendations": [],
  "drafting_notes": [],
  "missing_information": [],
  "final_recommendation": "",
  "source_limitations": [],
  "plain_explanation": "",
  "practical_meaning": "",
  "country_context": "",
  "case_understanding": "",
  "legal_classification": "",
  "legal_basis": "",
  "articles_requested": [],
  "legislation_summary": "",
  "mizan_sources_summary": "",
  "analysis_based_on_sources": "",
  "general_legal_reasoning": "",
  "source_dependency_level": "مرتفع أو متوسط أو منخفض",
  "legal_accuracy_note": "",
  "confidence_level": "مرتفع أو متوسط أو منخفض",
  "confidence_reason": "",
  "verified_legal_materials": [],
  "unverified_legal_points": [],
  "key_risks": [],
  "business_risks": [],
  "relevant_documents": [],
  "proof_points": [],
  "defenses_or_arguments": [],
  "similar_cases": [],
  "criminal_penalty_estimate": {{"show": false, "alleged_crime": "", "possible_penalty_range": "", "factors_that_may_increase_penalty": [], "factors_that_may_reduce_penalty": [], "important_warning": ""}},
  "next_steps": [],
  "procedure_steps": [],
  "when_to_consult_lawyer": "",
  "educational_notes": "",
  "role_based_guidance": "",
  "plan_based_depth": "",
  "combined_role_plan_note": "",
  "lawyer_summary": "",
  "disclaimer": "{DEFAULT_DISCLAIMER}"
}}
"""

    response = generate_content_with_retry(
        contents=[prompt, *file_parts],
        config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
    )
    data = _safe_json_loads(response.text or "")
    result = _normalize_legal_result(data, user_role=user_role, selected_case_type=selected_case_type)
    result["legal_sources"] = legal_sources
    result["uploaded_documents"] = [
        {
            "filename": item.get("filename") or f"document_{i + 1}",
            "content_type": item.get("content_type") or "application/octet-stream",
            "size_bytes": len(item.get("file_bytes") or b""),
        }
        for i, item in enumerate(document_files)
    ]
    return result


async def analyze_legal_documents(
    document_files: List[Dict[str, Any]],
    country: str = "الأردن",
    document_type: str = "مستند قانوني",
    selected_case_type: str = "غير محدد",
    plan: str = "free",
    user_role: str = "individual",
    question: str = "",
) -> Dict[str, Any]:
    """
    تحليل مجموعة مستندات قانونية مع سؤال اختياري.
    """
    if not document_files:
        raise ValueError("يرجى رفع ملف واحد على الأقل.")

    is_staff_unlimited = (plan or "").strip().lower() == "staff_unlimited"

    # لا نضع حدًا لعدد الملفات لحسابات الموظفين.
    # يبقى حد الحجم موجودًا لحماية الذاكرة وقيود مزود الذكاء الاصطناعي.
    if not is_staff_unlimited and len(document_files) > 10:
        raise ValueError("يمكن رفع 10 ملفات كحد أقصى في الطلب الواحد.")

    total_size = sum(len(item.get("file_bytes") or b"") for item in document_files)
    max_total_size = 200 * 1024 * 1024 if is_staff_unlimited else 60 * 1024 * 1024
    if total_size > max_total_size:
        max_mb = max_total_size // (1024 * 1024)
        raise ValueError(f"إجمالي حجم الملفات كبير جدًا. الحد الحالي {max_mb}MB للطلب الواحد.")

    file_descriptions = []
    file_parts = []

    for index, item in enumerate(document_files, start=1):
        file_bytes = item.get("file_bytes") or b""
        filename = item.get("filename") or f"document_{index}"
        content_type = item.get("content_type") or "application/octet-stream"

        if not file_bytes:
            continue

        max_file_size = 50 * 1024 * 1024 if is_staff_unlimited else 20 * 1024 * 1024
        if len(file_bytes) > max_file_size:
            max_file_mb = max_file_size // (1024 * 1024)
            raise ValueError(f"حجم الملف {filename} كبير جدًا. الحد الحالي {max_file_mb}MB لكل ملف.")

        file_descriptions.append(
            f"{index}. {filename} — النوع: {content_type} — الحجم: {len(file_bytes)} bytes"
        )
        file_parts.append(types.Part.from_bytes(data=file_bytes, mime_type=content_type))

    if not file_parts:
        raise ValueError("لم تصل ملفات صالحة للتحليل.")

    selected_case_type = _normalize_case_type(selected_case_type)

    prompt = f"""
أنت Mizan، مساعد قانوني لتحليل المستندات القانونية باللغة العربية.

الدولة: {country}
نوع المستخدم: {user_role}
الباقة: {plan}
نوع المستند المختار: {document_type}
نوع القضية المختار: {selected_case_type}
سؤال المستخدم أو ملاحظاته: {question or "لا يوجد"}

الملفات المرفقة:
{chr(10).join(file_descriptions)}

{get_case_type_instruction()}
{get_accuracy_rules()}

حلل جميع المستندات المرفقة معًا وليس كل ملف بمعزل عن الآخر.
استخرج الروابط بين الملفات، الأطراف، الوقائع، الالتزامات، المخاطر، التناقضات، والمستندات الناقصة.
إذا سأل المستخدم سؤالًا محددًا، أجب عنه بناءً على الملفات.
إذا كانت بعض الملفات غير واضحة أو PDF ممسوح، اذكر ذلك في confidence_reason.

أرجع JSON فقط:
{{
  "request_type": "document_analysis",
  "audience_mode": "{user_role}",
  "cards_to_show": ["case_type_correction", "short_answer", "plain_explanation", "case_understanding", "key_risks", "relevant_documents", "proof_points", "verified_legal_materials", "disclaimer"],
  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",
  "document_type": "{document_type}",
  "summary": "",
  "country_context": "",
  "confidence_level": "مرتفع أو متوسط أو منخفض",
  "confidence_reason": "",
  "parties": [],
  "main_obligations": [],
  "risky_clauses": [],
  "legal_gaps": [],
  "missing_clauses": [],
  "suggested_edits": [],
  "verified_legal_materials": [],
  "unverified_legal_points": [],
  "risk_level": "منخفض أو متوسط أو مرتفع",
  "lawyer_summary": "",
  "disclaimer": "{DEFAULT_DISCLAIMER}"
}}
"""

    response = generate_content_with_retry(
        contents=[prompt, *file_parts],
        config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
    )
    data = _safe_json_loads(response.text or "")
    result = _normalize_document_result(data, selected_case_type=selected_case_type, user_role=user_role)
    result["uploaded_documents"] = [
        {
            "filename": item.get("filename") or f"document_{i + 1}",
            "content_type": item.get("content_type") or "application/octet-stream",
            "size_bytes": len(item.get("file_bytes") or b""),
        }
        for i, item in enumerate(document_files)
    ]
    return result


async def analyze_legal_document(
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
    country: str = "الأردن",
    document_type: str = "مستند قانوني",
    selected_case_type: str = "غير محدد",
    plan: str = "free",
    user_role: str = "individual",
    question: str = "",
) -> Dict[str, Any]:
    if len(file_bytes or b"") > 20 * 1024 * 1024:
        raise ValueError("حجم الملف كبير جدًا. الحد الحالي 20MB.")

    prompt = f"""
أنت Mizan، مساعد قانوني لتحليل المستندات القانونية باللغة العربية.

الدولة: {country}
نوع المستخدم: {user_role}
الباقة: {plan}
نوع المستند المختار: {document_type}
اسم الملف: {filename}
نوع القضية المختار: {selected_case_type}
سؤال المستخدم: {question or "لا يوجد"}

{get_case_type_instruction()}
{get_accuracy_rules()}

حلل المستند المرفق. إذا لم يكن واضحًا صرّح بذلك. أرجع JSON فقط:
{{
  "request_type": "document_analysis",
  "audience_mode": "{user_role}",
  "cards_to_show": ["case_type_correction", "short_answer", "plain_explanation", "key_risks", "relevant_documents", "verified_legal_materials", "disclaimer"],
  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",
  "document_type": "",
  "summary": "",
  "country_context": "",
  "confidence_level": "مرتفع أو متوسط أو منخفض",
  "confidence_reason": "",
  "parties": [],
  "main_obligations": [],
  "risky_clauses": [],
  "legal_gaps": [],
  "missing_clauses": [],
  "suggested_edits": [],
  "verified_legal_materials": [],
  "unverified_legal_points": [],
  "risk_level": "منخفض أو متوسط أو مرتفع",
  "lawyer_summary": "",
  "disclaimer": "{DEFAULT_DISCLAIMER}"
}}
"""
    file_part = types.Part.from_bytes(data=file_bytes, mime_type=content_type or "application/octet-stream")
    response = generate_content_with_retry(
        contents=[prompt, file_part],
        config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
    )
    data = _safe_json_loads(response.text or "")
    return _normalize_document_result(data, selected_case_type=selected_case_type, user_role=user_role)


# ============================================================
# Professional Legal Response Template Engine (added)
# ============================================================

def get_mode_system_instruction(assistant_mode: str) -> str:
    """Return mode-specific instructions for the professional assistant."""
    instructions = {
        "legal_research": (
            "وضع البحث القانوني:\n"
            "- ابحث في التشريعات المعتمدة المرفقة وأجب بدقة عالية.\n"
            "- لا تذكر أرقام مواد إلا إذا كانت في المصادر المرفقة.\n"
            "- وضّح الفرق بين ما هو نص قانوني مؤكد وما هو تفسير أو استنتاج.\n"
            "- إذا لم توجد مصادر مناسبة، أعلن ذلك صراحة."
        ),
        "case_analysis": (
            "وضع تحليل القضية:\n"
            "- حلل الوقائع قانونيًا وحدد المسائل القانونية بدقة.\n"
            "- طبّق النصوص القانونية المعتمدة على الوقائع.\n"
            "- قدّم نقاط القوة والضعف ودفوع الخصم والمخاطر.\n"
            "- أوجز الاستراتيجية والخطوات العملية الموصى بها."
        ),
        "document_analysis": (
            "وضع تحليل المستندات:\n"
            "- استخرج الأطراف، الالتزامات، التواريخ، المبالغ، المخاطر.\n"
            "- حدد نوع المستند (عقد/إنذار/مذكرة/حكم/مراسلة).\n"
            "- اربط المستندات بالتشريعات المعتمدة.\n"
            "- أذكر المستندات الناقصة والتناقضات إن وجدت."
        ),
        "contract_review": (
            "وضع مراجعة العقد:\n"
            "- حدد البنود الخطرة، الغامضة، الناقصة بدقة.\n"
            "- بيّن الانحياز لأي طرف إن وجد.\n"
            "- اقترح صياغة بديلة للبنود الإشكالية.\n"
            "- قدّم توصيات تفاوضية عملية."
        ),
        "legal_drafting": (
            "وضع الصياغة القانونية:\n"
            "- أنتج المستند القانوني المطلوب بأسلوب رسمي محكم.\n"
            "- استخدم المصطلحات القانونية الصحيحة.\n"
            "- أشر إلى المصادر التشريعية التي بنيت عليها الصياغة.\n"
            "- فرّق بين الصياغة والتحليل في مخرجك."
        ),
        "litigation_strategy": (
            "وضع الاستراتيجية القضائية:\n"
            "- قدّم أفضل مسار قانوني موثّق بالمصادر.\n"
            "- حدد نقاط القوة والضعف ودفوع الخصم المحتملة.\n"
            "- اذكر المستندات المطلوبة لتعزيز الموقف.\n"
            "- قدّم خطوات عملية محددة ودرجة المخاطرة."
        ),
        "corporate_advisory": (
            "وضع الاستشارة المؤسسية:\n"
            "- ركز على المخاطر القانونية للشركة وآليات الامتثال.\n"
            "- حلل الوضع من منظور الحوكمة والمسؤولية القانونية.\n"
            "- قدّم بدائل قانونية عملية وقابلة للتطبيق.\n"
            "- أشر إلى التشريعات ذات الصلة بنشاط الشركة."
        ),
    }
    return instructions.get(assistant_mode or "case_analysis", instructions["case_analysis"])


def get_professional_response_template_instruction(assistant_mode: str) -> str:
    """Build the professional structured response template instruction."""
    base = """
هيكل الجواب القانوني الاحترافي المطلوب (استخدم ما يناسب السؤال وتجنب التطويل غير الضروري):

1. professional_summary: الخلاصة القانونية المهنية (موجزة ومركزة).
2. facts_assumptions: الوقائع والافتراضات المعتمدة في التحليل.
3. legal_issues: المسائل القانونية محل البحث.
4. governing_law: النصوص أو القواعد القانونية الحاكمة (فقط من مصادر Mizan).
5. source_based_analysis: التحليل القانوني المبني على المصادر المعتمدة.
6. application_to_facts: تطبيق القانون على الوقائع أو السؤال.
7. strengths: نقاط القوة في الموقف القانوني.
8. weaknesses: نقاط الضعف والمخاطر.
9. opposing_arguments: دفوع أو احتمالات الطرف الآخر.
10. missing_information: المستندات أو المعلومات الناقصة.
11. strategic_recommendations: التوصية أو الإجراء المقترح.
12. confidence_level: درجة الثقة (مرتفع/متوسط/منخفض) مع السبب في confidence_reason.
13. legal_sources: المصادر المستخدمة (من مصادر Mizan فقط).

قواعد الجواب:
- لا تجبر كل جواب على استخدام كل الأقسام إذا كان السؤال بسيطًا.
- إذا السؤال بسيط، يكفي professional_summary + legal_issues + governing_law + confidence.
- لا تجعل الجواب سطحيًا أو بلا مصادر إذا كانت المصادر متوفرة.
"""

    mode_additions = {
        "contract_review": "\n- أضف risky_clauses و business_risks و drafting_notes في مخرجك.",
        "legal_drafting": "\n- أضف drafting_notes كاملًا ومنظمًا. يجب أن ينتج عن هذا الوضع مستند قانوني قابل للاستخدام.",
        "litigation_strategy": "\n- أضف proof_points و opposing_arguments و strategic_recommendations بشكل مفصل.",
        "corporate_advisory": "\n- أضف business_risks و key_risks بشكل محدد وقابل للتطبيق.",
    }

    return base + mode_additions.get(assistant_mode or "", "")


def get_confidence_engine_instruction(
    has_sources: bool,
    missing_laws: list,
    assistant_mode: str,
) -> str:
    """Confidence engine instruction for the prompt."""
    if missing_laws:
        laws_str = "، ".join(missing_laws)
        return (
            f"محرك الثقة [CONFIDENCE ENGINE]:\n"
            f"التشريع المطلوب ({laws_str}) غير متوفر في Mizan.\n"
            f"يجب أن يكون confidence_level = 'منخفض'.\n"
            f"اذكر في confidence_reason: 'التشريع المطلوب غير متوفر أو غير معتمد ضمن Mizan.'"
        )
    if has_sources:
        return (
            "محرك الثقة [CONFIDENCE ENGINE]:\n"
            "توجد مصادر قانونية معتمدة مرتبطة بالسؤال.\n"
            "درجة الثقة تعتمد على: وضوح الوقائع، كفاية المصادر، مدى تغطيتها للسؤال.\n"
            "استخدم 'مرتفع' إذا كانت المصادر كافية والوقائع واضحة.\n"
            "استخدم 'متوسط' إذا كانت المصادر جزئية أو الوقائع غير مكتملة.\n"
            "استخدم 'منخفض' إذا كانت المصادر غير كافية أو الوقائع ناقصة جدًا."
        )
    return (
        "محرك الثقة [CONFIDENCE ENGINE]:\n"
        "لا توجد مصادر قانونية معتمدة مرتبطة.\n"
        "يجب أن يكون confidence_level = 'منخفض'.\n"
        "اذكر في confidence_reason: 'لا توجد مصادر معتمدة في Mizan لهذا السؤال.'"
    )
