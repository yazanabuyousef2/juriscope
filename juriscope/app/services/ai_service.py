import json
import os
import re
from typing import Any, Dict

from dotenv import load_dotenv
from google import genai

from app.schemas.legal import (
    AnalyzeRequest,
    AnalyzeResponse,
    SimilarCase,
    CriminalPenaltyEstimate,
)


load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DEFAULT_DISCLAIMER = (
    "يوفر Juriscope معلومات وتحليلات قانونية مساعدة لأغراض معرفية وتنظيمية فقط، "
    "ولا يُعد استشارة قانونية نهائية ولا ينشئ علاقة محامٍ وموكل. يجب دائمًا مراجعة "
    "محامٍ مرخص قبل اتخاذ أي إجراء قانوني."
)


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

    increase = penalty_data.get("factors_that_may_increase_penalty", [])
    reduce = penalty_data.get("factors_that_may_reduce_penalty", [])

    penalty = CriminalPenaltyEstimate(
        show=bool(penalty_data.get("show", is_criminal)) if is_criminal else False,
        alleged_crime=str(penalty_data.get("alleged_crime", "")),
        possible_penalty_range=str(penalty_data.get("possible_penalty_range", "")),
        factors_that_may_increase_penalty=[str(x) for x in increase] if isinstance(increase, list) else [],
        factors_that_may_reduce_penalty=[str(x) for x in reduce] if isinstance(reduce, list) else [],
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
        key_risks=[str(x) for x in data.get("key_risks", [])] if isinstance(data.get("key_risks", []), list) else [],
        relevant_documents=[str(x) for x in data.get("relevant_documents", [])] if isinstance(data.get("relevant_documents", []), list) else [],
        similar_cases=similar_cases,
        next_steps=[str(x) for x in data.get("next_steps", [])] if isinstance(data.get("next_steps", []), list) else [],
        lawyer_summary=str(data.get("lawyer_summary", "")),
        criminal_penalty_estimate=penalty,
        disclaimer=str(data.get("disclaimer", DEFAULT_DISCLAIMER)),
    )


async def analyze_legal_question(request: AnalyzeRequest) -> AnalyzeResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود. أضفه في ملف .env محليًا أو في Environment Variables على Render.")

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(request)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    raw_text = response.text or ""
    data = _safe_json_loads(raw_text)
    return _normalize_response(data, request)
