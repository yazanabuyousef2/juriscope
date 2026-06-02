import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.genai import types

from app.services.ai_service import generate_content_with_retry, _safe_json_loads, _extract_gemini_text
from app.services.persona_engine import get_persona_label, get_persona_tools, normalize_persona


TOOL_CATALOG: Dict[str, Dict[str, Any]] = {
    "defense_memo": {
        "label": "مذكرة دفاع",
        "aliases": ["مذكرة دفاع", "دفاع", "مذكرة"],
        "document_type": "legal_memo",
        "description": "مسودة مذكرة دفاع مبنية على الوقائع والتحليل السابق، مع دفوع ومخاطر ونواقص.",
        "sections": ["العنوان", "الوقائع", "المسائل القانونية", "الدفوع", "الرد على دفوع الخصم", "المستندات الناقصة", "الطلبات"],
    },
    "claim_statement": {
        "label": "لائحة دعوى",
        "aliases": ["لائحة دعوى", "دعوى", "صحيفة دعوى"],
        "document_type": "claim_draft",
        "description": "مسودة لائحة دعوى/مطالبة قابلة للمراجعة.",
        "sections": ["الأطراف", "الاختصاص", "الوقائع", "السند القانوني", "البينات", "الطلبات"],
    },
    "reply_statement": {
        "label": "لائحة جوابية",
        "aliases": ["لائحة جوابية", "جوابية", "لائحة رد"],
        "document_type": "reply_draft",
        "description": "مسودة جوابية منظمة على ادعاءات الطرف الآخر.",
        "sections": ["مقدمة", "الرد على الوقائع", "الدفوع الشكلية", "الدفوع الموضوعية", "البينات", "الطلبات"],
    },
    "legal_notice": {
        "label": "إنذار عدلي / خطاب مطالبة",
        "aliases": ["إنذار", "انذار", "إنذار عدلي", "خطاب مطالبة", "مطالبة"],
        "document_type": "notice_draft",
        "description": "صياغة إنذار أو مطالبة رسمية أولية.",
        "sections": ["المرسل", "المخاطب", "الوقائع", "المطالبة", "المهلة", "التحفظات"],
    },
    "case_timeline": {
        "label": "Timeline للقضية",
        "aliases": ["Timeline", "تايم لاين", "خط زمني", "الخط الزمني"],
        "document_type": "timeline",
        "description": "ترتيب الأحداث والإجراءات والمهل القانونية المحتملة.",
        "sections": ["الأحداث المؤكدة", "الأحداث غير المؤكدة", "المواعيد الحرجة", "ما يجب التحقق منه"],
    },
    "evidence_list": {
        "label": "قائمة بينات ومستندات",
        "aliases": ["بينات", "مستندات", "قائمة بينات", "قائمة مستندات", "الأدلة"],
        "document_type": "evidence_checklist",
        "description": "قائمة منظمة بالأدلة والمستندات المطلوبة لدعم الموقف.",
        "sections": ["المستندات المتوفرة", "المستندات الناقصة", "الشهود/القرائن", "أولوية التحصيل"],
    },
    "litigation_strategy": {
        "label": "استراتيجية تفاوض أو تقاضي",
        "aliases": ["استراتيجية", "تقاضي", "تفاوض", "خطة تقاضي", "استراتيجية تفاوض"],
        "document_type": "strategy_plan",
        "description": "خطة عملية للخيارات المتاحة والمخاطر والخطوة القادمة.",
        "sections": ["الهدف", "الخيار الودي", "الخيار القضائي", "المخاطر", "التوصية"],
    },
    "contract_review": {
        "label": "تحليل عقد",
        "aliases": ["تحليل عقد", "مراجعة عقد", "عقد", "كشف البنود الخطرة"],
        "document_type": "contract_review",
        "description": "مراجعة بنود عقد أو اتفاقية مع مخاطر وتعديلات مقترحة.",
        "sections": ["ملخص العقد", "الالتزامات", "البنود الخطرة", "البنود الناقصة", "تعديلات مقترحة"],
    },
    "risk_score": {
        "label": "Risk Score / مصفوفة مخاطر",
        "aliases": ["Risk Score", "مصفوفة مخاطر", "المخاطر", "تقييم مخاطر"],
        "document_type": "risk_matrix",
        "description": "تقدير أولي لمستوى المخاطر القانونية والمالية والإجرائية.",
        "sections": ["مخاطر عالية", "مخاطر متوسطة", "مخاطر منخفضة", "كيف نقلل الخطر"],
    },
    "lawyer_brief": {
        "label": "ملخص جاهز للمحامي",
        "aliases": ["ملخص للمحامي", "ملخص جاهز", "lawyer summary", "ملخص"],
        "document_type": "lawyer_brief",
        "description": "ملخص قصير ومنظم يمكن إرساله لمحامٍ.",
        "sections": ["موضوع الحالة", "الوقائع", "المشكلة القانونية", "المستندات", "الأسئلة للمحامي"],
    },
    "official_letter": {
        "label": "صياغة كتاب رسمي",
        "aliases": ["كتاب رسمي", "صياغة كتاب", "خطاب رسمي"],
        "document_type": "official_letter",
        "description": "صياغة كتاب رسمي أولي لجهة إدارية أو مخاطبة رسمية.",
        "sections": ["المخاطب", "الموضوع", "الوقائع", "الطلب", "التحفظات"],
    },
    "study_notes": {
        "label": "شرح مادة / ملخص تعليمي",
        "aliases": ["شرح مادة", "تلخيص قانون", "ملخص تعليمي", "تعليمي"],
        "document_type": "study_notes",
        "description": "شرح تعليمي مبسط مناسب لطالب الحقوق.",
        "sections": ["الفكرة", "التعريف", "الشرح", "مثال", "أسئلة مراجعة"],
    },
    "flashcards": {
        "label": "Flashcards / بطاقات مراجعة",
        "aliases": ["Flashcards", "فلاش كارد", "بطاقات مراجعة", "أسئلة تدريبية"],
        "document_type": "flashcards",
        "description": "بطاقات وأسئلة مراجعة تعليمية من التحليل.",
        "sections": ["بطاقات سؤال/جواب", "مصطلحات", "أسئلة قصيرة"],
    },

    "workspace_plan": {
        "label": "خطة عمل Workspace",
        "aliases": ["خطة عمل", "خطة Workspace", "بناء خطة", "خطة الملف"],
        "document_type": "workspace_plan",
        "description": "خطة تشغيل كاملة للملف: مراحل، مهام، مستندات، ومخرجات مطلوبة.",
        "sections": ["هدف الملف", "المراحل", "الأدوات المقترحة", "المستندات المطلوبة", "المهام العاجلة"],
    },
    "client_intake": {
        "label": "نموذج معلومات للعميل",
        "aliases": ["نموذج عميل", "أسئلة للعميل", "معلومات ناقصة", "استبيان"],
        "document_type": "client_intake",
        "description": "قائمة أسئلة ومعلومات يجب جمعها من العميل أو صاحب العلاقة.",
        "sections": ["بيانات عامة", "وقائع أساسية", "مواعيد مهمة", "مستندات مطلوبة", "أسئلة حاسمة"],
    },
    "document_index": {
        "label": "فهرس مستندات الملف",
        "aliases": ["فهرس مستندات", "تنظيم المستندات", "ملف مستندات"],
        "document_type": "document_index",
        "description": "ترتيب المستندات حسب النوع والأهمية وما ينقص كل مستند.",
        "sections": ["المستند", "الغرض منه", "الحالة", "الأهمية", "ملاحظات"],
    },
    "deadline_checklist": {
        "label": "قائمة المدد والتنبيهات",
        "aliases": ["مدد", "مواعيد", "مهل", "تنبيهات", "سقوط حق"],
        "document_type": "deadline_checklist",
        "description": "قائمة بالمدد والمواعيد الحرجة التي يجب التحقق منها.",
        "sections": ["التاريخ المعروف", "الإجراء المرتبط", "درجة الخطورة", "ما يجب التحقق منه"],
    },
    "hearing_prep": {
        "label": "تحضير جلسة / اجتماع",
        "aliases": ["تحضير جلسة", "جلسة", "تحضير اجتماع", "أسئلة جلسة"],
        "document_type": "hearing_preparation",
        "description": "تحضير عملي للجلسة أو الاجتماع: نقاط حديث، أسئلة، مستندات، ومخاطر.",
        "sections": ["هدف الجلسة", "النقاط التي يجب طرحها", "الأسئلة المتوقعة", "المستندات", "التحفظات"],
    },
    "settlement_offer": {
        "label": "مسودة عرض تسوية",
        "aliases": ["تسوية", "عرض تسوية", "صلح", "تفاوض"],
        "document_type": "settlement_offer",
        "description": "مسودة عرض تسوية أو خطة تفاوض تحفظ الحقوق قدر الإمكان.",
        "sections": ["مقدمة", "أساس النزاع", "عرض التسوية", "المهلة", "عدم التنازل عن الحقوق"],
    },
    "compliance_checklist": {
        "label": "Checklist امتثال ومخاطر",
        "aliases": ["امتثال", "Compliance", "مخاطر شركة", "Checklist"],
        "document_type": "compliance_checklist",
        "description": "قائمة تحقق للشركات والجهات الحكومية قبل اتخاذ قرار أو توقيع.",
        "sections": ["الالتزامات", "الموافقات", "المخاطر", "الإجراءات المطلوبة", "قرار مقترح"],
    },
    "plain_summary": {
        "label": "تبسيط الجواب وخطوات عملية",
        "aliases": ["تبسيط", "اشرح ببساطة", "خطوات عملية", "ماذا أفعل"],
        "document_type": "plain_summary",
        "description": "تحويل التحليل إلى خطوات بسيطة لشخص غير متخصص.",
        "sections": ["ماذا يعني هذا؟", "ماذا تفعل الآن؟", "متى تحتاج محامي؟"],
    },
}

PERSONA_TOOL_KEYS: Dict[str, List[str]] = {
    "individual": ["workspace_plan", "plain_summary", "lawyer_brief", "client_intake", "legal_notice", "evidence_list", "case_timeline"],
    "lawyer": ["workspace_plan", "client_intake", "defense_memo", "claim_statement", "reply_statement", "case_timeline", "deadline_checklist", "evidence_list", "document_index", "hearing_prep", "settlement_offer", "litigation_strategy", "legal_notice", "risk_score"],
    "legal_professional": ["workspace_plan", "client_intake", "defense_memo", "claim_statement", "reply_statement", "case_timeline", "deadline_checklist", "evidence_list", "document_index", "hearing_prep", "litigation_strategy", "risk_score"],
    "company": ["workspace_plan", "contract_review", "risk_score", "compliance_checklist", "legal_notice", "settlement_offer", "evidence_list", "document_index", "litigation_strategy", "official_letter"],
    "judge": ["workspace_plan", "case_timeline", "evidence_list", "document_index", "risk_score", "lawyer_brief", "hearing_prep"],
    "law_student": ["workspace_plan", "study_notes", "flashcards", "plain_summary"],
    "legal_researcher": ["workspace_plan", "lawyer_brief", "case_timeline", "document_index", "risk_score", "study_notes"],
    "government_employee": ["workspace_plan", "official_letter", "case_timeline", "deadline_checklist", "evidence_list", "document_index", "compliance_checklist", "risk_score"],
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def resolve_tool_key(tool_key: Optional[str] = None, tool_label: Optional[str] = None, persona: str = "individual") -> str:
    if tool_key and tool_key in TOOL_CATALOG:
        return tool_key

    label_norm = _norm(tool_label or "")
    if label_norm:
        for key, meta in TOOL_CATALOG.items():
            labels = [meta.get("label", ""), *meta.get("aliases", [])]
            if any(_norm(item) and (_norm(item) in label_norm or label_norm in _norm(item)) for item in labels):
                return key

    # Try mapping persona default tool names from persona_engine into known tools.
    persona_tools = get_persona_tools(persona)
    for persona_tool in persona_tools:
        if tool_label and _norm(tool_label) in _norm(persona_tool):
            return resolve_tool_key(tool_label=persona_tool, persona=persona)

    return PERSONA_TOOL_KEYS.get(normalize_persona(persona), PERSONA_TOOL_KEYS["individual"])[0]


def get_workspace_tools_for_persona(persona: object, extra_labels: Optional[List[Any]] = None) -> List[Dict[str, str]]:
    persona_key = normalize_persona(persona)
    keys = list(PERSONA_TOOL_KEYS.get(persona_key, PERSONA_TOOL_KEYS["individual"]))

    for label in extra_labels or []:
        key = resolve_tool_key(tool_label=str(label), persona=persona_key)
        if key not in keys:
            keys.append(key)

    return [
        {
            "key": key,
            "label": str(TOOL_CATALOG[key]["label"]),
            "description": str(TOOL_CATALOG[key]["description"]),
            "document_type": str(TOOL_CATALOG[key]["document_type"]),
        }
        for key in keys
        if key in TOOL_CATALOG
    ]


def remaining_tool_labels(persona: object, used_tools: Optional[List[Any]] = None, extra_labels: Optional[List[Any]] = None) -> List[str]:
    persona_key = normalize_persona(persona)
    used_keys = {resolve_tool_key(tool_label=str(item), persona=persona_key) for item in (used_tools or [])}
    remaining = []
    for tool in get_workspace_tools_for_persona(persona_key, extra_labels=extra_labels):
        if tool["key"] not in used_keys:
            remaining.append(tool["label"])
    return remaining


def _compact_analysis_context(analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(analysis, dict):
        return {}
    allowed = [
        "short_answer", "professional_summary", "facts_assumptions", "legal_issues", "governing_law",
        "source_based_analysis", "application_to_facts", "strengths", "weaknesses", "opposing_arguments",
        "strategic_recommendations", "drafting_notes", "missing_information", "final_recommendation",
        "key_risks", "business_risks", "relevant_documents", "proof_points", "defenses_or_arguments",
        "source_reasoning", "risk_matrix", "litigation_timeline", "document_intelligence", "next_steps",
        "procedure_steps", "lawyer_summary", "legal_sources", "confidence_level", "confidence_reason",
    ]
    return {key: analysis.get(key) for key in allowed if analysis.get(key) not in (None, "", [])}


async def generate_workspace_tool_output(
    *,
    tool_key: Optional[str],
    tool_label: Optional[str],
    question: str,
    analysis: Optional[Dict[str, Any]],
    country: str,
    case_type: str,
    audience_mode: str,
    used_tools: Optional[List[Any]] = None,
    extra_tool_labels: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    persona = normalize_persona(audience_mode)
    selected_key = resolve_tool_key(tool_key=tool_key, tool_label=tool_label, persona=persona)
    meta = TOOL_CATALOG[selected_key]
    selected_label = str(meta["label"])
    compact_analysis = _compact_analysis_context(analysis)
    persona_label = get_persona_label(persona)
    sections = "\n".join(f"- {item}" for item in meta.get("sections", []))
    remaining = remaining_tool_labels(persona, used_tools=[*(used_tools or []), selected_label], extra_labels=extra_tool_labels)

    prompt = f"""
أنت Mizan Workspace، مساعد قانوني عملي يحول التحليل السابق إلى أداة تنفيذية داخل مساحة العمل.

نوع المستخدم: {persona_label}
الدولة القانونية: {country}
نوع القضية: {case_type}
الأداة المطلوبة: {selected_label}
وصف الأداة: {meta['description']}
الأقسام المطلوبة في المخرج:
{sections}

سؤال/وقائع المستخدم الأصلية:
{question or 'غير مذكور'}

ملخص التحليل السابق داخل Mizan:
{json.dumps(compact_analysis, ensure_ascii=False, indent=2)}

قواعد صارمة:
- اكتب بالعربية الفصحى الواضحة.
- لا تخترع مواد قانونية أو أرقام مواد غير موجودة في التحليل السابق أو المصادر.
- إذا احتجت بيانات ناقصة، ضعها في missing_information ولا تفترضها.
- اجعل الناتج قابلًا للنسخ والمراجعة البشرية.
- إذا كانت الأداة مذكرة/لائحة/إنذار، اجعلها مسودة مهنية لاستخدامها بعد مراجعة محامٍ.
- حافظ على الفرق بين نوع المستخدم: المحامي يحتاج صياغة أعمق، الشركة تحتاج مخاطر وقرار، الفرد يحتاج خطوات بسيطة.

أرجع JSON فقط بهذا الشكل:
{{
  "tool_key": "{selected_key}",
  "tool_label": "{selected_label}",
  "title": "عنوان واضح للمخرج",
  "document_type": "{meta['document_type']}",
  "content_markdown": "النص الكامل المنظم للأداة المطلوبة بصيغة Markdown عربية",
  "missing_information": [],
  "next_actions": [],
  "quality_warning": "تنبيه مناسب قبل الاستخدام النهائي",
  "remaining_tools": {json.dumps(remaining, ensure_ascii=False)}
}}
""".strip()

    response = generate_content_with_retry(
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.15, response_mime_type="application/json"),
    )
    data = _safe_json_loads(_extract_gemini_text(response))

    return {
        "tool_key": selected_key,
        "tool_label": str(data.get("tool_label") or selected_label),
        "title": str(data.get("title") or selected_label),
        "document_type": str(data.get("document_type") or meta["document_type"]),
        "content_markdown": str(data.get("content_markdown") or ""),
        "missing_information": data.get("missing_information") if isinstance(data.get("missing_information"), list) else [],
        "next_actions": data.get("next_actions") if isinstance(data.get("next_actions"), list) else [],
        "quality_warning": str(data.get("quality_warning") or "هذا مخرج أولي داخل مساحة عمل Mizan ويحتاج مراجعة مختص قبل الاستخدام الرسمي."),
        "remaining_tools": data.get("remaining_tools") if isinstance(data.get("remaining_tools"), list) else remaining,
        "created_at": datetime.utcnow().isoformat(),
    }
