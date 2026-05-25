import json
import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.schemas.legal import (
    AnalyzeRequest,
    AnalyzeResponse,
    SimilarCase,
    CriminalPenaltyEstimate,
    DocumentAnalysisResponse,
)


load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DEFAULT_DISCLAIMER = (
    "يوفر Juriscope معلومات وتحليلات قانونية مساعدة لأغراض معرفية وتنظيمية فقط، "
    "ولا يُعد استشارة قانونية نهائية ولا ينشئ علاقة محامٍ وموكل. يجب دائمًا مراجعة "
    "محامٍ مرخص قبل اتخاذ أي إجراء قانوني، وخصوصًا قبل توقيع العقود أو تقديم الشكاوى أو رفع الدعاوى."
)

ALLOWED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10MB for Render/Gemini-friendly first version


def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود. أضفه في ملف .env محليًا أو في Environment Variables على Render.")
    return genai.Client(api_key=api_key)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """Parse Gemini output even if it returns JSON inside markdown fences."""
    if not text:
        raise ValueError("لم يصل رد من مزود الذكاء الاصطناعي.")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end])
        raise ValueError("لم يتمكن النظام من قراءة رد Gemini كـ JSON.")


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _plan_instruction(plan: str) -> str:
    if plan == "المجانية":
        return "قدّم جوابًا مختصرًا وأساسيًا مع أهم المخاطر والخطوات فقط."
    if plan == "الأفراد":
        return "قدّم تحليلًا واضحًا وموسعًا للمستخدم غير المتخصص، مع مستندات مطلوبة وأسئلة عملية."
    if plan == "الأعمال":
        return "ركّز على المخاطر التجارية، العقود، الحوكمة، حماية العملاء، والمسؤولية المالية."
    if plan == "المحامون":
        return "استخدم صياغة قانونية أكثر احترافية، واذكر نقاط القوة والضعف، ومسارًا قانونيًا منظمًا للمراجعة."
    return "قدّم تحليلًا منظمًا ومفهومًا."


def _criminal_details_text(request: AnalyzeRequest) -> str:
    details = request.criminal_details
    if not details:
        return "لا توجد تفاصيل جنائية إضافية."

    return f"""
تفاصيل جنائية إضافية إن وُجدت:
- نوع الجرم أو الفعل المنسوب: {details.alleged_crime or "غير مذكور"}
- هل توجد سوابق؟ {details.has_prior_record or "غير معروف"}
- عدد السوابق: {details.prior_count or "غير مذكور"}
- هل يوجد اعتراف؟ {details.confession or "غير معروف"}
- هل يوجد شهود؟ {details.witnesses or "غير معروف"}
- هل يوجد ضرر مادي أو جسدي؟ {details.harm or "غير معروف"}
- ظروف مخففة محتملة: {details.mitigating_factors or "غير مذكور"}
- ظروف مشددة محتملة: {details.aggravating_factors or "غير مذكور"}
"""


def _build_prompt(request: AnalyzeRequest) -> str:
    is_criminal = request.case_type == "جنائي"

    return f"""
أنت Juriscope، مساعد قانوني ذكي باللغة العربية.

المستخدم اختار:
- الدولة: {request.country}
- نوع القضية: {request.case_type}
- الباقة: {request.plan}

تعليمات الباقة:
{_plan_instruction(request.plan)}

مهمتك:
حلّل السؤال القانوني بناءً على الدولة المختارة ونوع القضية. يجب أن يكون الجواب باللغة العربية وبصيغة JSON فقط.

قواعد قانونية وأخلاقية مهمة:
1. لا تدّعِ أنك محامٍ، ولا تقدّم استشارة قانونية نهائية.
2. لا تخترع أرقام مواد قانونية أو أسماء أحكام قضائية غير مؤكدة.
3. إذا لم تكن متأكدًا من نص قانوني محدد أو عقوبة دقيقة في دولة معينة، قل إن الأمر يحتاج إلى مراجعة النص الرسمي ومحامٍ مختص في تلك الدولة.
4. يجب أن يتأثر التحليل بالدولة المختارة: {request.country}.
5. لا تضمن نتيجة قضائية أو حكمًا نهائيًا.
6. لا تستخدم مصطلح "مذنب" أو "الحكم المتوقع للمذنب".
7. في القضايا الجنائية استخدم عبارات مثل: "الفعل المنسوب"، "في حال ثبوت الفعل"، "العقوبة المحتملة"، "النطاق العقابي المحتمل".
8. للحالات المشابهة، لا تخترع أسماء قضايا حقيقية. استخدم أوصافًا عامة مثل "حالة مشابهة في نزاع شراكة" أو "حالة مشابهة في دعوى جنائية".
9. إذا كانت المعلومات ناقصة، اذكر المعلومات الناقصة ضمن التحليل والخطوات.
10. أرجع JSON فقط، بدون markdown وبدون أي شرح خارج JSON.

{_criminal_details_text(request) if is_criminal else ""}

السؤال:
{request.question}

أرجع JSON بهذه المفاتيح بالضبط:
{{
  "short_answer": "إجابة مختصرة واضحة",
  "country_context": "شرح مختصر كيف تؤثر الدولة المختارة على التحليل",
  "case_understanding": "فهم الحالة وإعادة صياغتها قانونيًا",
  "legal_classification": "التكييف أو التصنيف القانوني الأولي",
  "key_risks": ["مخاطر قانونية رئيسية"],
  "relevant_documents": ["مستندات أو أدلة مطلوبة"],
  "similar_cases": [
    {{
      "title": "عنوان عام لحالة مشابهة دون اختراع حكم حقيقي",
      "similarity": "نسبة تقريبية مثل 80%",
      "principle": "المبدأ القانوني العام",
      "why_relevant": "سبب ارتباطها بالحالة"
    }}
  ],
  "next_steps": ["خطوات عملية مقترحة"],
  "lawyer_summary": "ملخص احترافي يمكن إرساله للمحامي",
  "criminal_penalty_estimate": {{
    "show": {"true" if is_criminal else "false"},
    "alleged_crime": "الفعل المنسوب إذا كانت القضية جنائية",
    "possible_penalty_range": "النطاق العقابي المحتمل في حال ثبوت الفعل، أو فارغ لغير الجنائي",
    "factors_that_may_increase_penalty": ["عوامل قد تشدد العقوبة"],
    "factors_that_may_reduce_penalty": ["عوامل قد تخفف العقوبة"],
    "important_warning": "تنبيه مهم حول أن التقدير ليس حكمًا نهائيًا"
  }},
  "disclaimer": "{DEFAULT_DISCLAIMER}"
}}
"""


def _normalize_response(data: Dict[str, Any], request: AnalyzeRequest) -> AnalyzeResponse:
    penalty_data = data.get("criminal_penalty_estimate") or {}
    is_criminal = request.case_type == "جنائي"

    similar_cases = [
        SimilarCase(
            title=str(case.get("title", "")),
            similarity=str(case.get("similarity", "")),
            principle=str(case.get("principle", "")),
            why_relevant=str(case.get("why_relevant", "")),
        )
        for case in data.get("similar_cases", [])
        if isinstance(case, dict)
    ]

    penalty = CriminalPenaltyEstimate(
        show=bool(penalty_data.get("show", is_criminal)) if is_criminal else False,
        alleged_crime=str(penalty_data.get("alleged_crime", "")),
        possible_penalty_range=str(penalty_data.get("possible_penalty_range", "")),
        factors_that_may_increase_penalty=_as_list(penalty_data.get("factors_that_may_increase_penalty", [])),
        factors_that_may_reduce_penalty=_as_list(penalty_data.get("factors_that_may_reduce_penalty", [])),
        important_warning=str(
            penalty_data.get(
                "important_warning",
                "هذا تقدير عام وليس حكمًا قضائيًا، ويعتمد القرار النهائي على المحكمة المختصة والأدلة والتكييف القانوني والنصوص السارية."
            )
        ),
    )

    return AnalyzeResponse(
        short_answer=str(data.get("short_answer", "")),
        country_context=str(data.get("country_context", f"تم توجيه التحليل وفق الدولة المختارة: {request.country}.")),
        case_understanding=str(data.get("case_understanding", "")),
        legal_classification=str(data.get("legal_classification", "")),
        key_risks=_as_list(data.get("key_risks", [])),
        relevant_documents=_as_list(data.get("relevant_documents", [])),
        similar_cases=similar_cases,
        next_steps=_as_list(data.get("next_steps", [])),
        lawyer_summary=str(data.get("lawyer_summary", "")),
        criminal_penalty_estimate=penalty,
        disclaimer=str(data.get("disclaimer", DEFAULT_DISCLAIMER)),
    )


async def analyze_legal_question(request: AnalyzeRequest) -> AnalyzeResponse:
    client = _client()
    prompt = _build_prompt(request)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    raw_text = response.text or ""
    data = _safe_json_loads(raw_text)
    return _normalize_response(data, request)


def _document_prompt(country: str, document_type: str, plan: str, question: str, filename: str) -> str:
    return f"""
أنت Juriscope، مساعد قانوني ذكي متخصص في تحليل المستندات القانونية باللغة العربية.

المستخدم رفع مستندًا قانونيًا لتحليله.
- الدولة المختارة: {country}
- نوع المستند المختار: {document_type}
- الباقة: {plan}
- اسم الملف: {filename}
- سؤال أو ملاحظة المستخدم: {question or "لا توجد ملاحظة إضافية"}

تعليمات مهمة جدًا:
1. اقرأ محتوى الملف المرفق، حتى لو كان PDF ممسوحًا أو صورة لعقد أو مستند.
2. استخرج النص والمعنى القانوني قدر الإمكان من الملف.
3. لا تقل إنك لا تستطيع قراءة المستند إلا إذا كان غير واضح فعلًا.
4. حلّل المستند وفق الدولة المختارة، لكن لا تخترع أرقام مواد قانونية أو أحكامًا غير مؤكدة.
5. ركّز على الثغرات، البنود الخطرة، الالتزامات، البنود الناقصة، والتعديلات المقترحة.
6. لا تحكم ببطلان العقد بشكل قطعي. استخدم عبارات مثل: "قد يسبب خطرًا"، "يحتاج إلى مراجعة"، "قد يكون غير متوازن".
7. لا تقدّم استشارة قانونية نهائية ولا تستبدل مراجعة محامٍ مرخص.
8. إذا كان المستند غير واضح أو ناقصًا، اذكر ذلك ضمن الثغرات والتنبيه.
9. أرجع JSON فقط، بدون markdown وبدون شرح خارجه.

تعليمات الباقة:
{_plan_instruction(plan)}

أرجع JSON بهذه المفاتيح بالضبط:
{{
  "document_type": "نوع المستند بعد قراءته، مثل عقد شراكة أو عقد عمل",
  "country_context": "كيف تؤثر الدولة المختارة على قراءة المستند",
  "summary": "ملخص واضح للمستند",
  "parties": ["الأطراف المذكورون في المستند"],
  "main_obligations": ["الالتزامات الرئيسية على كل طرف"],
  "risky_clauses": ["البنود الخطرة أو غير المتوازنة"],
  "legal_gaps": ["الثغرات القانونية أو الغموض في الصياغة"],
  "missing_clauses": ["بنود مهمة ناقصة يجب إضافتها"],
  "suggested_edits": ["تعديلات أو صياغات مقترحة لتحسين المستند"],
  "risk_level": "منخفض أو متوسط أو مرتفع مع سبب مختصر",
  "lawyer_summary": "ملخص جاهز للمحامي عن المستند ومخاطره",
  "disclaimer": "{DEFAULT_DISCLAIMER}"
}}
"""


def _normalize_document_response(data: Dict[str, Any], country: str, document_type: str) -> DocumentAnalysisResponse:
    return DocumentAnalysisResponse(
        document_type=str(data.get("document_type", document_type)),
        country_context=str(data.get("country_context", f"تمت قراءة المستند وفق الدولة المختارة: {country}.")),
        summary=str(data.get("summary", "")),
        parties=_as_list(data.get("parties", [])),
        main_obligations=_as_list(data.get("main_obligations", [])),
        risky_clauses=_as_list(data.get("risky_clauses", [])),
        legal_gaps=_as_list(data.get("legal_gaps", [])),
        missing_clauses=_as_list(data.get("missing_clauses", [])),
        suggested_edits=_as_list(data.get("suggested_edits", [])),
        risk_level=str(data.get("risk_level", "غير محدد")),
        lawyer_summary=str(data.get("lawyer_summary", "")),
        disclaimer=str(data.get("disclaimer", DEFAULT_DISCLAIMER)),
    )


async def analyze_legal_document(
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    country: str,
    document_type: str,
    plan: str,
    question: str = "",
) -> DocumentAnalysisResponse:
    if not file_bytes:
        raise ValueError("لم يتم رفع أي ملف.")

    if len(file_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        raise ValueError("الملف كبير جدًا. الحد الحالي 10MB. يرجى رفع نسخة مختصرة أو ملف أصغر.")

    mime_type = content_type or "application/octet-stream"
    if mime_type not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise ValueError("نوع الملف غير مدعوم. الرجاء رفع PDF أو صورة بصيغة JPG/PNG/WEBP.")

    client = _client()
    prompt = _document_prompt(country, document_type, plan, question, filename)
    file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt, file_part],
    )

    raw_text = response.text or ""
    data = _safe_json_loads(raw_text)
    return _normalize_document_response(data, country, document_type)
