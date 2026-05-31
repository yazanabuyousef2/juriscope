"""
legal_assistant_engine.py — Mizan Legal Assistant Engine

Orchestrates the full professional legal assistant pipeline:
1. Query classification
2. Source retrieval + guard
3. Confidence evaluation
4. Prompt building per mode
5. Calling AI service
"""

from typing import Any, Dict, List, Optional

from app.services.legal_query_classifier import classify_query
from app.services.legal_source_guard import evaluate_source_quality, build_source_guard_context
from app.services.legal_retrieval_service import (
    build_sources_context,
    build_legal_source_policy,
    build_strict_source_guard_note,
    search_legal_sources,
)
from app.db.session import SessionLocal


def get_legal_sources_for_query(
    query: str,
    country_name: str,
    country_code: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Retrieve legal sources with source guard filtering."""
    db = SessionLocal()
    try:
        raw_sources = search_legal_sources(
            db=db,
            query=query,
            country_code=country_code,
            country_name=country_name,
            limit=limit,
            approved_only=True,
            active_only=True,
        )
        return raw_sources
    except Exception:
        return []
    finally:
        db.close()


def build_engine_context(
    query: str,
    country_name: str,
    country_code: str,
    assistant_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full engine context for a query:
    - classification
    - sources
    - guard evaluation
    - prompt context strings
    """
    classification = classify_query(query, assistant_mode=assistant_mode, country=country_name)
    sources = get_legal_sources_for_query(query, country_name, country_code)

    guard_eval = evaluate_source_quality(query, sources)

    # If specific laws requested but not found, use empty sources
    if guard_eval["missing_laws"] and not guard_eval["found_laws"]:
        effective_sources = []
    else:
        effective_sources = guard_eval["filtered_sources"] if guard_eval["filtered_sources"] else sources

    sources_context = build_sources_context(effective_sources)
    source_policy = build_legal_source_policy(effective_sources)
    guard_note = build_strict_source_guard_note(query, effective_sources)
    full_policy = source_policy + "\n\n" + guard_note

    return {
        "classification": classification,
        "sources": effective_sources,
        "sources_context": sources_context,
        "source_policy": full_policy,
        "guard_evaluation": guard_eval,
        "confidence_modifier": guard_eval["confidence_modifier"],
        "has_valid_sources": guard_eval["has_valid_sources"],
        "missing_laws": guard_eval["missing_laws"],
        "requested_laws": guard_eval["requested_laws"],
    }


def get_mode_system_instruction(assistant_mode: str) -> str:
    """Return mode-specific instruction injected into the AI prompt."""
    instructions = {
        "legal_research": (
            "أنت في وضع البحث القانوني. "
            "ابحث في التشريعات المعتمدة المرفقة وأجب بدقة. "
            "لا تذكر أرقام مواد إلا إذا كانت في المصادر المرفقة. "
            "إذا لم توجد مصادر، أعلن ذلك صراحة."
        ),
        "case_analysis": (
            "أنت في وضع تحليل القضية. "
            "حلل الوقائع قانونيًا، حدد المسائل القانونية، طبّق النصوص على الوقائع، "
            "وقدّم نقاط القوة والضعف والمخاطر والاستراتيجية."
        ),
        "document_analysis": (
            "أنت في وضع تحليل المستندات. "
            "استخرج الأطراف، الالتزامات، التواريخ، المخاطر، البنود الغامضة، "
            "والمستندات الناقصة. اربط المستندات بالتشريعات المعتمدة."
        ),
        "contract_review": (
            "أنت في وضع مراجعة العقد. "
            "حدد البنود الخطرة، الغامضة، الناقصة، والانحياز لطرف. "
            "اقترح صياغة بديلة وتوصيات تفاوضية."
        ),
        "legal_drafting": (
            "أنت في وضع الصياغة القانونية. "
            "أنتج المستند القانوني المطلوب (مذكرة/إنذار/لائحة/رأي قانوني/خطاب مطالبة) "
            "بأسلوب قانوني رسمي محكم، مع الإشارة إلى المصادر المعتمدة."
        ),
        "litigation_strategy": (
            "أنت في وضع الاستراتيجية القانونية. "
            "قدّم أفضل مسار، نقاط القوة، نقاط الضعف، دفوع الخصم، "
            "المستندات المطلوبة، الخطوات العملية، درجة المخاطرة، والتوصية النهائية."
        ),
        "corporate_advisory": (
            "أنت في وضع الاستشارة المؤسسية. "
            "ركز على المخاطر القانونية، الامتثال التشريعي، الحوكمة، "
            "والبدائل العملية للشركة."
        ),
    }
    return instructions.get(assistant_mode or "case_analysis", instructions["case_analysis"])


def get_confidence_instruction(confidence_modifier: str, missing_laws: List[str]) -> str:
    """Build confidence engine instruction for the prompt."""
    if missing_laws:
        laws_str = "، ".join(missing_laws)
        return (
            f"محرك الثقة: يجب أن يكون confidence_level = 'منخفض' لأن التشريع المطلوب "
            f"({laws_str}) غير متوفر في Mizan. "
            f"اذكر ذلك في confidence_reason."
        )
    if confidence_modifier == "مرتفع":
        return (
            "محرك الثقة: توجد مصادر قانونية معتمدة كافية ومرتبطة. "
            "يمكن أن يكون confidence_level = 'مرتفع' إذا كانت الوقائع كافية."
        )
    if confidence_modifier == "متوسط":
        return (
            "محرك الثقة: توجد مصادر لكنها محدودة أو قد لا تغطي كل جوانب السؤال. "
            "confidence_level = 'متوسط' مع ذكر السبب."
        )
    return (
        "محرك الثقة: لا توجد مصادر كافية. "
        "confidence_level = 'منخفض' مع تفسير واضح."
    )
