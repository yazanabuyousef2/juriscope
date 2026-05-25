import json
import os

from dotenv import load_dotenv
from google import genai

from app.schemas.legal import AnalyzeResponse, SimilarCase


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

client = genai.Client(api_key=GEMINI_API_KEY)


LEGAL_SYSTEM_PROMPT = """
أنت مساعد قانوني ذكي داخل منصة Juriscope.

مهمتك:
تحليل الأسئلة القانونية التي يكتبها المستخدم باللغة العربية أو الإنجليزية، ثم تقديم إجابة قانونية منظمة ومفهومة باللغة العربية.

قواعد مهمة جدًا:
1. لا تدّعِ أنك محامٍ.
2. لا تقدم استشارة قانونية نهائية أو ملزمة.
3. لا تخترع أرقام مواد قانونية أو أحكام قضائية غير مؤكدة.
4. إذا لم تكن متأكدًا من قانون دولة معينة، قل إن الأمر يحتاج إلى مراجعة محامٍ مختص في تلك الدولة.
5. اجعل الإجابة مفيدة، منظمة، وبلغة عربية قانونية واضحة.
6. لا تذكر أنك نموذج ذكاء اصطناعي.
7. لا تعطِ وعودًا بنتيجة قضائية.
8. إذا كان السؤال ناقص المعلومات، اشرح ما المعلومات الناقصة.
9. ركّز على تنظيم الحالة، المخاطر، المستندات، والخطوات التالية.
10. يجب أن يكون الناتج JSON فقط بدون أي شرح خارجه.

صيغة JSON المطلوبة بالضبط:
{
  "short_answer": "string",
  "case_understanding": "string",
  "legal_classification": "string",
  "key_risks": ["string"],
  "relevant_documents": ["string"],
  "similar_cases": [
    {
      "title": "string",
      "similarity": "string",
      "principle": "string",
      "why_relevant": "string"
    }
  ],
  "next_steps": ["string"],
  "lawyer_summary": "string",
  "disclaimer": "string"
}

تعليمات خاصة بالحالات المشابهة:
- إذا لم تكن لديك أحكام حقيقية مؤكدة، لا تخترع أسماء قضايا وهمية.
- استخدم عناوين عامة مثل:
  "حالة مشابهة في نزاع شراكة"
  "حالة مشابهة في إخلال عقدي"
  "حالة مشابهة في مطالبة مالية"
- اشرح وجه الشبه والمبدأ القانوني العام دون الادعاء بوجود حكم محدد.

التنبيه القانوني يجب أن يكون:
"يوفر Juriscope معلومات وتحليلات قانونية مساعدة لأغراض معرفية وتنظيمية فقط، ولا يُعد استشارة قانونية نهائية ولا ينشئ علاقة محامٍ وموكل. يجب دائمًا مراجعة محامٍ مرخص قبل اتخاذ أي إجراء قانوني."
"""


def _safe_json_loads(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start >= 0 and end > start:
            return json.loads(text[start:end])

        raise ValueError("لم يتمكن النظام من قراءة رد Gemini كـ JSON.")


async def analyze_legal_question(question: str) -> AnalyzeResponse:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY غير موجود. تأكد من ملف .env")

    prompt = f"""
{LEGAL_SYSTEM_PROMPT}

حلّل السؤال القانوني التالي وأرجع JSON فقط بنفس المفاتيح المطلوبة.

السؤال:
{question}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    raw_text = response.text
    data = _safe_json_loads(raw_text)

    similar_cases = [
        SimilarCase(
            title=case.get("title", ""),
            similarity=case.get("similarity", ""),
            principle=case.get("principle", ""),
            why_relevant=case.get("why_relevant", ""),
        )
        for case in data.get("similar_cases", [])
    ]

    return AnalyzeResponse(
        short_answer=data.get("short_answer", ""),
        case_understanding=data.get("case_understanding", ""),
        legal_classification=data.get("legal_classification", ""),
        key_risks=data.get("key_risks", []),
        relevant_documents=data.get("relevant_documents", []),
        similar_cases=similar_cases,
        next_steps=data.get("next_steps", []),
        lawyer_summary=data.get("lawyer_summary", ""),
        disclaimer=data.get(
            "disclaimer",
            "يوفر Juriscope معلومات وتحليلات قانونية مساعدة لأغراض معرفية وتنظيمية فقط، ولا يُعد استشارة قانونية نهائية ولا ينشئ علاقة محامٍ وموكل. يجب دائمًا مراجعة محامٍ مرخص قبل اتخاذ أي إجراء قانوني."
        ),
    )