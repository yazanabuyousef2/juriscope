"""
persona_engine.py — Mizan Persona & Response Blueprint Engine

Centralizes user-role thinking, response structure, cards, disclaimers, and tool hints.
This is the layer that makes Mizan answer differently for an individual, lawyer,
company, judge, law student, researcher, or government employee.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


SUPPORTED_PERSONAS = [
    "individual",
    "legal_professional",
    "lawyer",
    "company",
    "judge",
    "law_student",
    "legal_researcher",
    "government_employee",
]

PERSONA_ALIASES = {
    "general_user": "individual",
    "user": "individual",
    "normal": "individual",
    "person": "individual",
    "محامي": "lawyer",
    "lawyer_jo": "lawyer",
    "business": "company",
    "corporate": "company",
    "student": "law_student",
    "researcher": "legal_researcher",
    "government": "government_employee",
    "gov": "government_employee",
}


@dataclass(frozen=True)
class PersonaBlueprint:
    key: str
    label_ar: str
    thinking_ar: str
    answer_shape_ar: str
    preferred_cards: List[str]
    default_tools: List[str]
    disclaimer: str
    tone_ar: str


def normalize_persona(value: object, fallback: str = "individual") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback if fallback in SUPPORTED_PERSONAS else "individual"

    lowered = raw.lower()
    mapped = PERSONA_ALIASES.get(lowered, lowered)
    if mapped in SUPPORTED_PERSONAS:
        return mapped

    if raw in SUPPORTED_PERSONAS:
        return raw

    return fallback if fallback in SUPPORTED_PERSONAS else "individual"


PERSONAS: Dict[str, PersonaBlueprint] = {
    "individual": PersonaBlueprint(
        key="individual",
        label_ar="مستخدم عادي",
        thinking_ar=(
            "يفكر كمستخدم غير متخصص: يريد أن يعرف هل وضعه خطير، ماذا يفعل الآن، "
            "ما المعلومات الناقصة، وهل يحتاج إلى محامٍ أو جهة رسمية. لا يريد إغراقًا بالمواد القانونية."
        ),
        answer_shape_ar=(
            "استخدم بنية بسيطة: ملخص الحالة، التصنيف القانوني المحتمل، معنى ذلك عمليًا، "
            "المعلومات الناقصة، الخطوات القادمة، متى يحتاج محاميًا."
        ),
        preferred_cards=[
            "case_type_correction", "short_answer", "plain_explanation", "practical_meaning",
            "legal_classification", "key_risks", "next_steps", "when_to_consult_lawyer",
            "confidence", "disclaimer",
        ],
        default_tools=[
            "تلخيص الحالة للمحامي", "قائمة المستندات المطلوبة", "خطوات عملية آمنة", "إنذار أو رسالة أولية عند الحاجة",
        ],
        disclaimer=(
            "هذه إجابة إرشادية أولية وليست استشارة قانونية نهائية. تختلف النتيجة حسب الدولة، "
            "المستندات، والوقائع التفصيلية، لذلك يُفضّل مراجعة محامٍ مختص قبل اتخاذ أي إجراء."
        ),
        tone_ar="بسيط، واضح، عملي، غير مخيف، بدون مصطلحات زائدة.",
    ),
    "legal_professional": PersonaBlueprint(
        key="legal_professional",
        label_ar="مهني قانوني",
        thinking_ar=(
            "يفكر كمهني قانوني يحتاج تحليلًا منظمًا: الوقائع، المسائل، النصوص، التطبيق، "
            "المخاطر، الدفوع، المستندات الناقصة، والتوصية."
        ),
        answer_shape_ar=(
            "استخدم بنية عمل قانوني: خلاصة مهنية، وقائع، مسائل، نصوص حاكمة، تحليل، تطبيق، "
            "مخاطر، دفوع، مستندات ناقصة، توصية."
        ),
        preferred_cards=[
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "verified_legal_materials", "source_based_analysis", "application_to_facts",
            "strengths", "weaknesses", "opposing_arguments", "strategic_recommendations",
            "missing_information", "confidence", "legal_sources", "disclaimer",
        ],
        default_tools=["بحث قانوني", "تحليل موقف", "مذكرة مختصرة", "قائمة مستندات", "تقدير مخاطر"],
        disclaimer=(
            "هذه صياغة تحليلية أولية مبنية على الوقائع المذكورة، ويجب مطابقتها مع النصوص الرسمية "
            "والبينات والمواعيد الإجرائية قبل استخدامها في أي إجراء."
        ),
        tone_ar="مهني، تحليلي، مباشر، مع فصل النصوص المؤكدة عن الاستنتاجات.",
    ),
    "lawyer": PersonaBlueprint(
        key="lawyer",
        label_ar="محامٍ",
        thinking_ar=(
            "يفكر المحامي الأردني/العربي عادة بالنص القانوني المباشر، الاختصاص، المدد، التبليغ، "
            "البينات، التكييف، الدفوع، دفوع الخصم، المخاطر الإجرائية، والاستراتيجية القابلة للتحويل إلى مذكرة."
        ),
        answer_shape_ar=(
            "استخدم بنية محامي: المسألة القانونية، الوقائع المؤثرة، النصوص الأساسية والاحتياطية، "
            "التحليل، الدفوع، دفوع الخصم، المخاطر الإجرائية، المستندات الناقصة، الإجراء المقترح، "
            "وصياغة مختصرة قابلة للاستخدام."
        ),
        preferred_cards=[
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "source_based_analysis", "application_to_facts", "strengths",
            "weaknesses", "opposing_arguments", "defenses_or_arguments", "proof_points",
            "strategic_recommendations", "relevant_documents", "missing_information",
            "lawyer_summary", "confidence", "legal_sources", "disclaimer",
        ],
        default_tools=[
            "بحث مواد وتشريعات", "مذكرة دفاع", "لائحة دعوى/جوابية", "تحليل حكم", "حساب مدد", "Timeline للقضية",
            "قائمة بينات ومستندات", "استراتيجية تفاوض أو تقاضي",
        ],
        disclaimer=(
            "هذه صياغة تحليلية أولية مبنية على الوقائع المذكورة، ويجب مطابقتها مع النصوص الرسمية "
            "والبينات والمواعيد الإجرائية قبل استخدامها في أي إجراء."
        ),
        tone_ar="قانوني احترافي عميق، مناسب لمحامٍ، مع تركيز على الدفوع والإثبات والإجراءات.",
    ),
    "company": PersonaBlueprint(
        key="company",
        label_ar="شركة / رجل أعمال",
        thinking_ar=(
            "تفكر الشركة بالمخاطر المالية والتشغيلية، الالتزامات، المسؤولية، الامتثال، أثر القرار على العمل، "
            "والتوصية التنفيذية قبل التوقيع أو الإجراء."
        ),
        answer_shape_ar=(
            "استخدم بنية تنفيذية: ملخص تنفيذي، مستوى الخطر، الالتزامات، المخاطر القانونية والمالية، "
            "النقاط التي تحتاج مراجعة، التوصية العملية، وما يجب فعله قبل التوقيع أو القرار."
        ),
        preferred_cards=[
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "source_based_analysis", "key_risks", "business_risks",
            "weaknesses", "strategic_recommendations", "drafting_notes", "missing_information",
            "final_recommendation", "confidence", "legal_sources", "disclaimer",
        ],
        default_tools=[
            "تحليل عقد", "Risk Score", "استخراج الالتزامات", "كشف البنود الخطرة", "خطاب مطالبة", "Checklist امتثال",
        ],
        disclaimer=(
            "هذه قراءة أولية للمخاطر ولا تغني عن مراجعة العقد أو المستندات كاملة من محامٍ مختص "
            "قبل اتخاذ قرار تجاري أو قانوني."
        ),
        tone_ar="تنفيذي، عملي، موجه للإدارة، يركز على المخاطر والالتزامات والقرار.",
    ),
    "judge": PersonaBlueprint(
        key="judge",
        label_ar="قاضٍ / باحث قضائي",
        thinking_ar=(
            "يحتاج القاضي أو الباحث القضائي عرضًا محايدًا: الوقائع الثابتة مقابل الادعاءات، دفوع الأطراف، "
            "المسائل القانونية، التناقضات، والنواقص دون إصدار حكم نهائي."
        ),
        answer_shape_ar=(
            "استخدم بنية محايدة: عرض الوقائع، المسائل القانونية، موقف كل طرف، النصوص أو المبادئ، "
            "نقاط التحقق، أوجه القوة والضعف في كل اتجاه، وملاحظات بحثية."
        ),
        preferred_cards=[
            "case_type_correction", "professional_summary", "facts_assumptions", "legal_issues",
            "governing_law", "source_based_analysis", "application_to_facts", "strengths", "weaknesses",
            "opposing_arguments", "missing_information", "confidence", "legal_sources", "disclaimer",
        ],
        default_tools=["تلخيص دفوع", "جدول وقائع", "كشف تناقضات", "مقارنة مستندات", "مسودة بحث محايد"],
        disclaimer="هذا عرض بحثي أولي ومحايد ولا يمثل رأيًا قضائيًا أو قرارًا نهائيًا.",
        tone_ar="محايد، متوازن، دقيق، يفصل الثابت عن المدعى به.",
    ),
    "law_student": PersonaBlueprint(
        key="law_student",
        label_ar="طالب حقوق",
        thinking_ar=(
            "يريد الطالب فهم القاعدة والمعنى والفرق بين المفاهيم وكيف يكتبها في الامتحان، مع أمثلة وتبسيط."
        ),
        answer_shape_ar=(
            "استخدم بنية تعليمية: الفكرة ببساطة، التعريف، الشرح، مثال عملي، الفرق عن مفاهيم قريبة، "
            "كيف تكتبها في الامتحان، وأسئلة مراجعة."
        ),
        preferred_cards=[
            "case_type_correction", "plain_explanation", "legal_basis", "educational_notes", "case_understanding",
            "legal_classification", "next_steps", "confidence", "disclaimer",
        ],
        default_tools=["شرح مادة", "تلخيص قانون", "أسئلة تدريبية", "Flashcards", "مقارنة مفاهيم"],
        disclaimer="هذا شرح تعليمي مبسط ولا يغني عن الرجوع إلى النص القانوني الرسمي والمراجع المقررة.",
        tone_ar="تعليمي، مبسط، منظم، مناسب للمذاكرة والفهم.",
    ),
    "legal_researcher": PersonaBlueprint(
        key="legal_researcher",
        label_ar="باحث قانوني",
        thinking_ar=(
            "يريد الباحث خريطة مصادر، تمييز النصوص المؤكدة عن الاستنتاج، حدود البحث، والمواد ذات العلاقة."
        ),
        answer_shape_ar=(
            "استخدم بنية بحثية: نطاق البحث، النصوص المؤكدة، التحليل، حدود المصادر، الثغرات، أسئلة بحث لاحقة."
        ),
        preferred_cards=[
            "case_type_correction", "professional_summary", "legal_issues", "governing_law", "verified_legal_materials",
            "source_based_analysis", "source_limitations", "unverified_legal_points", "confidence", "legal_sources", "disclaimer",
        ],
        default_tools=["بحث تشريعات", "تلخيص مصادر", "مقارنة مواد", "خريطة بحث", "حدود المصادر"],
        disclaimer="هذا تحليل بحثي أولي ويجب استكماله بالرجوع إلى النصوص الرسمية والمراجع المتخصصة.",
        tone_ar="بحثي، موثق، دقيق، يبرز حدود المصادر.",
    ),
    "government_employee": PersonaBlueprint(
        key="government_employee",
        label_ar="جهة حكومية / موظف عام",
        thinking_ar=(
            "يركز الموظف العام على السند القانوني، الاختصاص، الإجراءات، صحة القرار الإداري، تقليل قابلية الطعن، "
            "والصياغة الرسمية."
        ),
        answer_shape_ar=(
            "استخدم بنية رسمية: موضوع الإجراء، السند المحتمل، الاختصاص، الإجراءات المطلوبة، المخاطر الإدارية، "
            "الصياغة الرسمية المقترحة، والمستندات أو الموافقات المطلوبة."
        ),
        preferred_cards=[
            "case_type_correction", "professional_summary", "legal_issues", "governing_law", "procedure_steps",
            "key_risks", "drafting_notes", "missing_information", "final_recommendation", "confidence", "legal_sources", "disclaimer",
        ],
        default_tools=["صياغة كتاب رسمي", "فحص مشروعية إجراء", "Checklist إجراءات", "مقارنة قانون/نظام/تعليمات"],
        disclaimer=(
            "هذه قراءة إرشادية أولية، ويجب التحقق من السند القانوني الرسمي والصلاحيات والإجراءات الداخلية قبل إصدار أي قرار."
        ),
        tone_ar="رسمي، منظم، يركز على الاختصاص والإجراء والسند.",
    ),
}


def get_persona(value: object, fallback: str = "individual") -> PersonaBlueprint:
    return PERSONAS[normalize_persona(value, fallback=fallback)]


def get_persona_label(value: object) -> str:
    return get_persona(value).label_ar


def get_persona_cards(value: object) -> List[str]:
    return list(get_persona(value).preferred_cards)


def get_persona_disclaimer(value: object) -> str:
    return get_persona(value).disclaimer


def get_persona_tools(value: object) -> List[str]:
    return list(get_persona(value).default_tools)


def build_persona_instruction(user_role: object, country: str) -> str:
    persona = get_persona(user_role)
    tools = "\n".join(f"- {tool}" for tool in persona.default_tools)
    cards = "، ".join(persona.preferred_cards)
    return f"""
محرك نوع المستخدم — Persona Engine:
- نوع المستخدم: {persona.label_ar}
- الدولة القانونية: {country}
- طريقة تفكيره: {persona.thinking_ar}
- شكل الرد المناسب: {persona.answer_shape_ar}
- نبرة الرد: {persona.tone_ar}
- الأدوات التي غالبًا يحتاجها داخل النظام:
{tools}
- الكروت/الأقسام المفضلة لهذه الشخصية: {cards}

قاعدة مهمة:
لا تعامل المستخدم العادي كأنه محامٍ. ولا تعامل المحامي كأنه مستخدم عادي.
غيّر مستوى العمق، اللغة، الأدوات، والأسئلة الناقصة حسب نوع المستخدم أعلاه.
""".strip()


def build_role_response_requirements(user_role: object) -> str:
    persona = get_persona(user_role)
    return f"""
متطلبات المخرج حسب نوع المستخدم ({persona.label_ar}):
- role_based_guidance: اكتب توجيهًا مخصصًا لهذا النوع من المستخدم.
- next_steps: اجعلها عملية ومناسبة لهذا المستخدم.
- missing_information: اسأل فقط عن المعلومات التي تغير النتيجة قانونيًا.
- disclaimer: استخدم هذا التنبيه المناسب: {persona.disclaimer}
- إذا كانت الأدوات مناسبة، املأ professional_tools بأدوات عملية يمكن للنظام توفيرها لاحقًا.
""".strip()
