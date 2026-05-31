"""
legal_source_guard.py — Mizan Legal Source Guard

Enforces that the AI assistant ONLY uses approved, relevant legal sources.
Prevents using unrelated legislation in answers.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.services.legal_query_classifier import (
    LAW_ALIAS_GROUPS,
    _normalize,
    detect_requested_laws,
)


# ---------------------------------------------------------------------------
# Source relevance checking
# ---------------------------------------------------------------------------

def _document_matches_law(document_title: str, canonical_law: str) -> bool:
    """Check if a document title matches a canonical law name."""
    norm_title = _normalize(document_title or "")
    norm_law = _normalize(canonical_law or "")
    if not norm_title or not norm_law:
        return False

    if norm_law in norm_title or norm_title in norm_law:
        return True

    aliases = LAW_ALIAS_GROUPS.get(canonical_law, [])
    return any(_normalize(a) and _normalize(a) in norm_title for a in aliases)


def filter_sources_by_relevance(
    query: str,
    sources: List[Dict[str, Any]],
    strict: bool = True,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Filter sources to only those relevant to the query.

    Returns:
        (filtered_sources, rejected_titles)
    """
    if not sources:
        return [], []

    requested_laws = detect_requested_laws(query)

    # If no specific law detected and not strict, return all sources
    if not requested_laws and not strict:
        return sources, []

    # If no specific law detected but strict mode: return sources as-is
    # (no filtering — retrieval already handles relevance scoring)
    if not requested_laws:
        return sources, []

    # Strict: only keep sources that belong to one of the requested laws
    kept = []
    rejected = []

    for src in sources:
        title = src.get("document_title", "") or ""
        matches_any = any(_document_matches_law(title, law) for law in requested_laws)
        if matches_any:
            kept.append(src)
        else:
            if title and title not in rejected:
                rejected.append(title)

    return kept, rejected


def evaluate_source_quality(
    query: str,
    sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Evaluate the quality and coverage of retrieved sources for the query.

    Returns a dict with:
        - has_valid_sources: bool
        - requested_laws: list
        - found_laws: list
        - missing_laws: list
        - rejected_sources: list
        - filtered_sources: list
        - guard_note: str
        - confidence_modifier: str (boosts or downgrades confidence)
    """
    requested_laws = detect_requested_laws(query)
    filtered, rejected = filter_sources_by_relevance(query, sources, strict=True)

    found_laws = []
    for law in requested_laws:
        for src in filtered:
            if _document_matches_law(src.get("document_title", ""), law):
                if law not in found_laws:
                    found_laws.append(law)
                break

    missing_laws = [law for law in requested_laws if law not in found_laws]

    guard_note = _build_guard_note(requested_laws, found_laws, missing_laws, rejected)
    confidence_modifier = _compute_confidence_modifier(requested_laws, found_laws, missing_laws, filtered)

    return {
        "has_valid_sources": len(filtered) > 0,
        "requested_laws": requested_laws,
        "found_laws": found_laws,
        "missing_laws": missing_laws,
        "rejected_sources": rejected,
        "filtered_sources": filtered,
        "guard_note": guard_note,
        "confidence_modifier": confidence_modifier,
    }


def _build_guard_note(
    requested_laws: List[str],
    found_laws: List[str],
    missing_laws: List[str],
    rejected: List[str],
) -> str:
    parts = []

    if missing_laws:
        laws_str = "، ".join(missing_laws)
        parts.append(
            f"تنبيه حارس المصادر [SOURCE GUARD]:\n"
            f"السؤال يستدعي الاعتماد على: {laws_str}.\n"
            f"هذا التشريع غير متوفر أو غير معتمد ضمن مصادر Mizan الحالية.\n"
            f"يُمنع منعًا باتًا استخدام أي تشريع آخر بدلًا منه.\n"
            f"يجب التصريح بوضوح: 'لا توجد مصادر معتمدة كافية داخل Mizan للإجابة الجازمة على هذا السؤال.'"
        )

    if rejected:
        rejected_str = "، ".join(rejected[:4])
        parts.append(
            f"تم استبعاد المصادر التالية لعدم انتمائها للتشريع المطلوب: {rejected_str}.\n"
            f"لا تستخدم هذه المصادر في الإجابة."
        )

    if not parts:
        if requested_laws and found_laws:
            parts.append(
                f"حارس المصادر: تم التحقق من أن المصادر المسترجعة تنتمي للتشريع المطلوب: "
                f"{'، '.join(found_laws)}."
            )
        else:
            parts.append(
                "حارس المصادر: استخدم فقط المصادر القانونية المعتمدة المرفقة. "
                "إذا لم تكن مناسبة موضوعيًا، صرّح بذلك."
            )

    return "\n\n".join(parts)


def _compute_confidence_modifier(
    requested_laws: List[str],
    found_laws: List[str],
    missing_laws: List[str],
    filtered_sources: List[Dict[str, Any]],
) -> str:
    if missing_laws:
        return "منخفض"  # Critical: requested law missing
    if not filtered_sources:
        return "منخفض"
    if len(filtered_sources) >= 3 and not missing_laws:
        return "مرتفع"
    return "متوسط"


def build_source_guard_context(evaluation: Dict[str, Any]) -> str:
    """Build the source guard context string to inject into the AI prompt."""
    lines = [evaluation["guard_note"]]

    if evaluation["missing_laws"]:
        lines.append(
            "\nقاعدة مطلقة: لا يجوز الإجابة من قوانين أخرى بدلًا عن التشريع الناقص. "
            "يجب الإعلان الصريح عن غياب المصدر."
        )

    return "\n".join(lines)
