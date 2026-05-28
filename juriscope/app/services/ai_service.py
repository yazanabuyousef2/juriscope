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

DEFAULT_DISCLAIMER = (
    "هذا التحليل أولي ومساعد ولا يُعد استشارة قانونية نهائية. يجب مراجعة محامٍ مرخص "
    "أو مصدر رسمي قبل اتخاذ أي إجراء قانوني."
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
    if value in AUDIENCE_MODES:
        return value
    if user_role in AUDIENCE_MODES:
        return user_role
    return "individual"


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
    if request_type == "legal_article_request":
        return ["case_type_correction", "short_answer", "articles_requested", "verified_legal_materials", "mizan_sources_summary", "legal_sources", "disclaimer"]
    if request_type == "legislation_request":
        return ["case_type_correction", "short_answer", "legislation_summary", "verified_legal_materials", "mizan_sources_summary", "legal_sources", "disclaimer"]
    if request_type == "procedure_guidance":
        return ["case_type_correction", "short_answer", "plain_explanation", "procedure_steps", "relevant_documents", "when_to_consult_lawyer", "disclaimer"]
    if request_type == "lawyer_brief":
        return ["case_type_correction", "short_answer", "case_understanding", "legal_classification", "legal_basis", "proof_points", "defenses_or_arguments", "key_risks", "lawyer_summary", "verified_legal_materials", "legal_sources", "disclaimer"]
    if request_type == "case_analysis":
        if user_role == "individual":
            return ["case_type_correction", "short_answer", "plain_explanation", "practical_meaning", "legal_classification", "key_risks", "relevant_documents", "next_steps", "when_to_consult_lawyer", "verified_legal_materials", "disclaimer"]
        if user_role == "lawyer":
            return ["case_type_correction", "short_answer", "case_understanding", "legal_classification", "legal_basis", "analysis_based_on_sources", "proof_points", "defenses_or_arguments", "key_risks", "relevant_documents", "lawyer_summary", "verified_legal_materials", "legal_sources", "confidence", "disclaimer"]
        return ["case_type_correction", "short_answer", "case_understanding", "legal_classification", "key_risks", "next_steps", "verified_legal_materials", "disclaimer"]
    return ["case_type_correction", "short_answer", "plain_explanation", "practical_meaning", "legal_basis", "when_to_consult_lawyer", "disclaimer"]


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
        "audience_mode": audience_mode,
        "cards_to_show": _clean_card_list(data.get("cards_to_show"), request_type, audience_mode),
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
    roles = {
        "individual": "نوع المستخدم: فرد. اكتب بلغة بسيطة وعملية، وركز على ماذا يعني الموقف وما الخطوات ومتى يحتاج محامي.",
        "lawyer": f"نوع المستخدم: محامٍ. استخدم أسلوبًا قانونيًا احترافيًا ضمن البيئة القانونية في {country}، وركز على التكييف والدفوع والإثبات.",
        "company": "نوع المستخدم: شركة / رجل أعمال. ركز على المخاطر القانونية والمالية والتشغيلية والوقاية.",
        "judge": "نوع المستخدم: قاضٍ. استخدم أسلوبًا محايدًا ولا تصدر حكمًا نهائيًا.",
        "law_student": "نوع المستخدم: طالب قانون. اجعل الجواب تعليميًا ومنظمًا مع شرح القاعدة والتطبيق.",
        "legal_researcher": "نوع المستخدم: باحث قانوني. استخدم أسلوبًا تحليليًا ومنظمًا.",
        "government_employee": "نوع المستخدم: موظف حكومي. ركز على الاختصاص والإجراءات وحدود الصلاحية.",
    }
    return roles.get(user_role, roles["individual"])


def get_plan_instruction(plan: str) -> str:
    if plan in ["enterprise", "premium", "staff_unlimited"]:
        return "قدّم تحليلًا عميقًا عند الحاجة، لكن لا تعرض كروت غير لازمة إذا كان السؤال بسيطًا."
    if plan in ["pro", "lawyer", "business"]:
        return "قدّم تحليلًا منظمًا مع مخاطر ومستندات وخطوات عملية."
    return "اجعل الإجابة واضحة ومختصرة وحذرة."


def get_accuracy_rules() -> str:
    return """
قواعد الدقة:
- مصادر Mizan المعتمدة هي المصدر الأساسي للتشريعات والمواد.
- لا تذكر رقم مادة قانونية إلا إذا كان موجودًا ضمن مصادر Mizan المرفقة.
- لا تخترع أحكامًا قضائية أو سوابق.
- استخدم التحليل العام فقط للتفسير والخطوات العملية.
- في القضايا الجنائية لا تعتبر الشخص مذنبًا، استخدم: الفعل المنسوب، في حال ثبوت الفعل.
"""


def get_request_type_instruction() -> str:
    return """
صنّف الطلب إلى request_type واحد:
general_question: سؤال عام.
case_analysis: وقائع أو نزاع.
legal_article_request: طلب مادة قانونية محددة.
legislation_request: طلب قانون أو تشريع كامل أو ملخص تشريع.
procedure_guidance: سؤال عن خطوات وإجراءات.
lawyer_brief: ملخص لمحامٍ أو تحضير ملف.
لا تعرض كل الكروت دائمًا، واجعل cards_to_show مناسبة.
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
) -> Dict[str, Any]:
    legal_sources = legal_sources or []
    criminal_details = criminal_details or {}
    selected_case_type = _normalize_case_type(selected_case_type or case_type)

    prompt = f"""
أنت Mizan، مساعد قانوني ذكي باللغة العربية.

معلومات الحساب:
- الدولة القانونية: {country}
- نوع المستخدم: {user_role}
- الباقة: {plan}
- نوع القضية الذي اختاره المستخدم: {selected_case_type}

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
  "request_type": "general_question | case_analysis | legal_article_request | legislation_request | procedure_guidance | lawyer_brief",
  "audience_mode": "{user_role}",
  "cards_to_show": ["short_answer"],
  "selected_case_type": "{selected_case_type}",
  "detected_case_type": "غير محدد | مدني | جنائي | تجاري | عمالي | أحوال شخصية | إداري | عقاري | تنفيذ | عقود | شركات | إيجارات | شيكات ومطالبات مالية | ملكية فكرية | أخرى",
  "case_type_match": true,
  "case_type_correction_note": "",
  "short_answer": "",
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
