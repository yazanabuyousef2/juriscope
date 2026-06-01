import json
import logging
import re
import traceback
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import require_user, is_staff_mode_user, is_unlimited_user
from app.database import UPLOAD_DIR, can_analyze, can_upload_document, execute, fetch_one, fetch_all, now_iso
from app.db.session import SessionLocal
from app.services.ai_service import (
    generate_content_with_retry,
    analyze_legal_document,
    analyze_legal_documents,
    analyze_legal_question,
    analyze_legal_question_with_documents,
)
from app.services.legal_retrieval_service import build_legal_source_policy, build_sources_context, build_strict_source_guard_note, search_legal_sources
from app.services.legal_assistant_engine import build_engine_context
from app.services.legal_query_classifier import classify_query
from app.services.persona_engine import normalize_persona
from app.services.actor_identity import get_effective_user_id
from app.services.workspace_tools import (
    generate_workspace_tool_output,
    get_workspace_tools_for_persona,
    remaining_tool_labels,
)

router = APIRouter()
logger = logging.getLogger("mizan.api")



class LegalQuestionRequest(BaseModel):
    question: str
    country: Optional[str] = "الأردن"
    case_type: str = "غير محدد"
    selected_case_type: Optional[str] = "غير محدد"
    case_id: Optional[int] = None
    criminal_details: Optional[Dict[str, Any]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    assistant_mode: Optional[str] = "case_analysis"
    audience_mode: Optional[str] = None


class WorkspaceToolRequest(BaseModel):
    tool_key: Optional[str] = None
    tool_label: Optional[str] = None
    question: Optional[str] = ""
    country: Optional[str] = "الأردن"
    case_type: Optional[str] = "غير محدد"
    selected_case_type: Optional[str] = "غير محدد"
    assistant_mode: Optional[str] = "legal_drafting"
    audience_mode: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = None
    used_tools: Optional[List[Any]] = None
    available_tools: Optional[List[Any]] = None
    case_id: Optional[int] = None


def _verify_case_access(case_id: int | None, user_id: int) -> int | None:
    if not case_id:
        return None
    case = fetch_one("SELECT id FROM cases WHERE id = ? AND user_id = ?", (case_id, user_id))
    if not case:
        raise HTTPException(status_code=404, detail="القضية غير موجودة أو لا تملك صلاحية الوصول إليها.")
    return case_id


def _safe_filename(name: str) -> str:
    name = name or "uploaded_document"
    name = re.sub(r"[^A-Za-z0-9_.\-\u0600-\u06FF ]+", "_", name)
    return name[:120]


def _clean_case_type(value: Optional[str]) -> str:
    value = (value or "").strip()
    return value or "غير محدد"


def _clean_conversation_history(value: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not value:
        return []
    cleaned = []
    for item in value[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role not in ["user", "assistant"] or not content:
            continue
        cleaned.append(
            {
                "role": role,
                "content": content[:1200],
                "request_type": str(item.get("request_type", ""))[:100],
                "detected_case_type": str(item.get("detected_case_type", ""))[:100],
                "selected_case_type": str(item.get("selected_case_type", ""))[:100],
            }
        )
    return cleaned


def _parse_json_field(value: Any, fallback: Any):
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _parse_optional_int(value: Any) -> Optional[int]:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="رقم القضية غير صحيح.")


def _user_plan(user: dict) -> str:
    return user.get("plan_code") or user.get("plan") or "free"


def _user_role(user: dict) -> str:
    return normalize_persona(user.get("user_role") or "individual")


def _effective_user_role(user: dict, requested_role: Optional[str] = None) -> str:
    # Staff/internal users may preview any persona. Regular users remain limited to their account role unless frontend sends a valid same-role mode.
    account_role = _user_role(user)
    if is_staff_mode_user(user):
        return normalize_persona(requested_role, fallback=account_role)
    if requested_role:
        requested = normalize_persona(requested_role, fallback=account_role)
        # Allow individual users to preview simple/business/student modes, but never silently upgrade to staff-only judge/government unless their account role has it.
        allowed_preview = {account_role, "individual", "lawyer", "company", "law_student", "legal_researcher"}
        if requested in allowed_preview:
            return requested
    return account_role


def _user_country(user: dict, fallback: str = "الأردن") -> str:
    return user.get("country_name") or user.get("country") or fallback or "الأردن"


def _user_country_code(user: dict) -> str:
    return user.get("country_code") or "JO"


def _try_legal_sources(question: str, country_name: str, country_code: str) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        return search_legal_sources(
            db=db,
            query=question,
            country_code=country_code,
            country_name=country_name,
            limit=8,
            approved_only=True,
            active_only=True,
        )
    except Exception:
        return []
    finally:
        db.close()


def _build_full_context(question: str, country_name: str, country_code: str, assistant_mode: str = "case_analysis") -> dict:
    """Build complete retrieval + guard context using the engine."""
    try:
        return build_engine_context(
            query=question,
            country_name=country_name,
            country_code=country_code,
            assistant_mode=assistant_mode,
        )
    except Exception:
        # Fallback to direct retrieval
        sources = _try_legal_sources(question, country_name, country_code)
        return {
            "sources": sources,
            "sources_context": build_sources_context(sources),
            "source_policy": build_legal_source_policy(sources) + "\n\n" + build_strict_source_guard_note(question, sources),
            "has_valid_sources": len(sources) > 0,
            "missing_laws": [],
        }


async def _read_uploaded_files(files: List[UploadFile]) -> List[Dict[str, Any]]:
    cleaned_files: List[Dict[str, Any]] = []
    for file in files:
        if not file:
            continue
        file_bytes = await file.read()
        if not file_bytes:
            continue
        cleaned_files.append(
            {
                "file_bytes": file_bytes,
                "filename": file.filename or "uploaded_document",
                "content_type": file.content_type or "application/octet-stream",
            }
        )
    return cleaned_files


def _store_uploaded_documents(
    *,
    user_id: int,
    case_id: Optional[int],
    uploaded_files: List[Dict[str, Any]],
    analysis_result: Dict[str, Any],
    document_type: str = "مستند قانوني",
):
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    for index, item in enumerate(uploaded_files, start=1):
        filename = item.get("filename") or f"uploaded_document_{index}"
        file_bytes = item.get("file_bytes") or b""
        content_type = item.get("content_type") or "application/octet-stream"
        stored_name = f"{user_id}_{int(time.time())}_{index}_{_safe_filename(filename)}"
        stored_path = Path(UPLOAD_DIR) / stored_name
        stored_path.write_bytes(file_bytes)

        try:
            execute(
                """
                INSERT INTO case_documents (case_id, user_id, filename, stored_path, content_type, analysis_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    user_id,
                    filename,
                    str(stored_path),
                    content_type,
                    json.dumps(analysis_result, ensure_ascii=False),
                    now_iso(),
                ),
            )
        except Exception:
            pass

        try:
            execute(
                """
                INSERT INTO documents (
                    user_id,
                    case_id,
                    filename,
                    stored_filename,
                    file_path,
                    mime_type,
                    file_size_bytes,
                    document_type,
                    analysis_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    case_id,
                    filename,
                    stored_name,
                    str(stored_path),
                    content_type,
                    len(file_bytes),
                    document_type,
                    json.dumps(analysis_result, ensure_ascii=False),
                    now_iso(),
                ),
            )
        except Exception:
            pass


def _safe_json_loads(value: Any, fallback: Any):
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _pick_row_value(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return default


def _save_analysis_record(
    *,
    user_id: int,
    case_id: Optional[int],
    question: str,
    result: Dict[str, Any],
    country_name: str,
    country_code: str,
    case_type: str,
    plan: str,
    user_role: str,
    assistant_mode: str,
) -> Optional[int]:
    """Save analysis while supporting both old and new DB schemas.

    Claude's version added history/feedback fields, while our current branch
    already has Persona Engine. This helper stores the richest record possible
    and safely falls back if a database still has an older analyses schema.
    """
    answer_json = json.dumps(result, ensure_ascii=False)
    sources_json = json.dumps(result.get("legal_sources") or [], ensure_ascii=False)
    confidence_level = str(result.get("confidence_level") or "")
    model_used = str(result.get("model_used") or "")
    now = now_iso()

    attempts = [
        (
            """
            INSERT INTO analyses (
                user_id, case_id, question, answer_json,
                country_code, country_name, case_type, assistant_mode,
                confidence_level, plan_code, user_role, model_used, sources_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, case_id, question, answer_json,
                country_code, country_name, case_type, assistant_mode,
                confidence_level, plan, user_role, model_used, sources_json, now,
            ),
        ),
        (
            """
            INSERT INTO analyses (
                user_id, case_id, question, answer_json,
                country_code, country_name, case_type,
                confidence_level, plan_code, user_role, model_used, sources_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, case_id, question, answer_json,
                country_code, country_name, case_type,
                confidence_level, plan, user_role, model_used, sources_json, now,
            ),
        ),
        (
            """
            INSERT INTO analyses (user_id, case_id, question, answer_json, country, case_type, plan, user_role, model_used, sources_json, confidence_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, case_id, question, answer_json, country_name, case_type, plan, user_role, model_used, sources_json, confidence_level, now),
        ),
        (
            """
            INSERT INTO analyses (user_id, case_id, question, answer_json, country, case_type, plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, case_id, question, answer_json, country_name, case_type, plan, now),
        ),
    ]

    for query, params in attempts:
        try:
            inserted_id = execute(query, params)
            if inserted_id:
                return int(inserted_id)
            return None
        except Exception:
            continue

    return None




@router.get("/ai-health")
async def ai_health():
    """Small production-safe diagnostic endpoint for Render/Gemini provider status."""
    from google.genai import types

    try:
        response = generate_content_with_retry(
            contents="أجب بكلمة OK فقط.",
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=16,
            ),
            retries=0,
        )
        text = getattr(response, "text", "") or ""
        return {"ok": True, "provider": "gemini", "sample": text[:80]}
    except Exception as exc:
        logger.error("AI_HEALTH_ERROR %s", repr(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze")
async def analyze(request: Request, payload: LegalQuestionRequest):
    user = require_user(request)

    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_analyze(get_effective_user_id(user), _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="يرجى كتابة السؤال القانوني.")

    case_id = None
    if not staff_mode:
        case_id = _verify_case_access(payload.case_id, get_effective_user_id(user))

    country_name = _user_country(user, payload.country or "الأردن")
    country_code = _user_country_code(user)
    selected_case_type = _clean_case_type(payload.selected_case_type or payload.case_type)
    conversation_history = _clean_conversation_history(payload.conversation_history)
    effective_user_role = _effective_user_role(user, payload.audience_mode)

    _engine_ctx = _build_full_context(question, country_name, country_code, payload.assistant_mode or "case_analysis")
    legal_sources = _engine_ctx["sources"]
    legal_sources_context = _engine_ctx["sources_context"]
    legal_source_policy = _engine_ctx["source_policy"]

    try:
        result = await analyze_legal_question(
            question=question,
            country=country_name,
            case_type=selected_case_type,
            selected_case_type=selected_case_type,
            conversation_history=conversation_history,
            plan=_user_plan(user),
            user_role=effective_user_role,
            criminal_details=payload.criminal_details or {},
            legal_sources_context=legal_sources_context,
            legal_source_policy=legal_source_policy,
            legal_sources=legal_sources,
            assistant_mode=payload.assistant_mode or "case_analysis",
        )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode
        result["effective_user_role"] = effective_user_role

        if staff_mode:
            result["staff_mode_note"] = "تم تنفيذ هذا التحليل بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."

        final_case_type = result.get("detected_case_type") or selected_case_type

        execute(
            """
            INSERT INTO case_messages (case_id, user_id, question, answer_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, get_effective_user_id(user), question, json.dumps(result, ensure_ascii=False), now_iso()),
        )

        analysis_id = _save_analysis_record(
            user_id=get_effective_user_id(user),
            case_id=case_id,
            question=question,
            result=result,
            country_name=country_name,
            country_code=country_code,
            case_type=final_case_type,
            plan=_user_plan(user),
            user_role=effective_user_role,
            assistant_mode=payload.assistant_mode or "case_analysis",
        )
        if analysis_id:
            result["id"] = analysis_id
            result["analysis_id"] = analysis_id

        if case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), case_id))

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ANALYZE_ROUTE_ERROR %s", repr(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze-with-documents")
async def analyze_with_documents(request: Request):
    user = require_user(request)
    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_analyze(get_effective_user_id(user), _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)
        allowed_doc, msg_doc = can_upload_document(get_effective_user_id(user), _user_plan(user))
        if not allowed_doc:
            raise HTTPException(status_code=403, detail=msg_doc)

    form = await request.form()
    files = list(form.getlist("files")) or list(form.getlist("file"))
    files = [file for file in files if hasattr(file, "read") and hasattr(file, "filename")]

    uploaded_files = await _read_uploaded_files(files)
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="يرجى رفع ملف واحد على الأقل مع السؤال.")

    question = str(form.get("question") or "").strip()
    if not question:
        question = "حلل الملفات المرفقة واشرح القضية أو الموقف القانوني المرتبط بها."

    safe_case_id = _parse_optional_int(form.get("case_id"))
    linked_case_id = _verify_case_access(safe_case_id, get_effective_user_id(user))

    country_name = _user_country(user, str(form.get("country") or "الأردن"))
    country_code = _user_country_code(user)
    selected_case_type = _clean_case_type(str(form.get("selected_case_type") or form.get("case_type") or "غير محدد"))
    assistant_mode = str(form.get("assistant_mode") or "case_analysis").strip() or "case_analysis"
    audience_mode = str(form.get("audience_mode") or "").strip()
    effective_user_role = _effective_user_role(user, audience_mode)
    conversation_history = _clean_conversation_history(_parse_json_field(form.get("conversation_history"), []))
    criminal_details = _parse_json_field(form.get("criminal_details"), {})

    _doc_engine_ctx = _build_full_context(question, country_name, country_code, assistant_mode)
    legal_sources = _doc_engine_ctx["sources"]
    legal_sources_context = _doc_engine_ctx["sources_context"]
    legal_source_policy = _doc_engine_ctx["source_policy"]

    try:
        result = await analyze_legal_question_with_documents(
            question=question,
            document_files=uploaded_files,
            country=country_name,
            case_type=selected_case_type,
            selected_case_type=selected_case_type,
            conversation_history=conversation_history,
            plan=_user_plan(user),
            user_role=effective_user_role,
            criminal_details=criminal_details,
            legal_sources_context=legal_sources_context,
            legal_source_policy=legal_source_policy,
            legal_sources=legal_sources,
            assistant_mode=assistant_mode,
        )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode
        result["effective_user_role"] = effective_user_role

        if staff_mode:
            result["staff_mode_note"] = "تم تحليل السؤال مع الملفات بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."

        _store_uploaded_documents(
            user_id=get_effective_user_id(user),
            case_id=linked_case_id,
            uploaded_files=uploaded_files,
            analysis_result=result,
            document_type="مرفقات سؤال قانوني",
        )

        final_case_type = result.get("detected_case_type") or selected_case_type

        execute(
            """
            INSERT INTO case_messages (case_id, user_id, question, answer_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (linked_case_id, get_effective_user_id(user), question, json.dumps(result, ensure_ascii=False), now_iso()),
        )

        analysis_id = _save_analysis_record(
            user_id=get_effective_user_id(user),
            case_id=linked_case_id,
            question=question,
            result=result,
            country_name=country_name,
            country_code=country_code,
            case_type=final_case_type,
            plan=_user_plan(user),
            user_role=effective_user_role,
            assistant_mode=assistant_mode,
        )
        if analysis_id:
            result["id"] = analysis_id
            result["analysis_id"] = analysis_id

        if linked_case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), linked_case_id))

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API_ROUTE_ERROR %s", repr(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze-document")
async def analyze_document(request: Request):
    user = require_user(request)

    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_upload_document(get_effective_user_id(user), _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

    form = await request.form()
    files = list(form.getlist("files")) or list(form.getlist("file"))
    files = [file for file in files if hasattr(file, "read") and hasattr(file, "filename")]

    uploaded_files = await _read_uploaded_files(files)
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="يرجى رفع ملف واحد على الأقل.")

    safe_case_id = _parse_optional_int(form.get("case_id"))
    linked_case_id = _verify_case_access(safe_case_id, get_effective_user_id(user))

    country_name = _user_country(user, str(form.get("country") or "الأردن"))
    selected_case_type = _clean_case_type(str(form.get("selected_case_type") or "غير محدد"))
    document_type = str(form.get("document_type") or "مستند قانوني")
    question = str(form.get("question") or "")
    audience_mode = str(form.get("audience_mode") or "").strip()
    effective_user_role = _effective_user_role(user, audience_mode)

    try:
        if len(uploaded_files) == 1:
            only = uploaded_files[0]
            result = await analyze_legal_document(
                file_bytes=only["file_bytes"],
                filename=only["filename"],
                content_type=only["content_type"],
                country=country_name,
                document_type=document_type,
                selected_case_type=selected_case_type,
                plan=_user_plan(user),
                user_role=effective_user_role,
                question=question,
            )
            result["uploaded_documents"] = [
                {
                    "filename": only["filename"],
                    "content_type": only["content_type"],
                    "size_bytes": len(only["file_bytes"]),
                }
            ]
        else:
            result = await analyze_legal_documents(
                document_files=uploaded_files,
                country=country_name,
                document_type=document_type,
                selected_case_type=selected_case_type,
                plan=_user_plan(user),
                user_role=effective_user_role,
                question=question,
            )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode
        result["effective_user_role"] = effective_user_role

        if staff_mode:
            result["staff_mode_note"] = "تم تحليل هذه المستندات بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."

        _store_uploaded_documents(
            user_id=get_effective_user_id(user),
            case_id=linked_case_id,
            uploaded_files=uploaded_files,
            analysis_result=result,
            document_type=document_type,
        )

        if linked_case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), linked_case_id))

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API_ROUTE_ERROR %s", repr(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc))



@router.get("/workspace-tools")
async def workspace_tools(request: Request, audience_mode: Optional[str] = None):
    """Return available workspace tools for the current user/persona."""
    user = require_user(request)
    effective_user_role = _effective_user_role(user, audience_mode)
    return {
        "audience_mode": effective_user_role,
        "tools": get_workspace_tools_for_persona(effective_user_role),
    }


@router.post("/workspace-tool")
async def run_workspace_tool(request: Request, payload: WorkspaceToolRequest):
    """Generate an actionable workspace artifact from a selected Mizan tool."""
    user = require_user(request)
    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_analyze(get_effective_user_id(user), _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

    linked_case_id = _verify_case_access(payload.case_id, get_effective_user_id(user))
    country_name = _user_country(user, payload.country or "الأردن")
    selected_case_type = _clean_case_type(payload.selected_case_type or payload.case_type or "غير محدد")
    effective_user_role = _effective_user_role(user, payload.audience_mode)

    try:
        result = await generate_workspace_tool_output(
            tool_key=payload.tool_key,
            tool_label=payload.tool_label,
            question=(payload.question or "").strip(),
            analysis=payload.analysis or {},
            country=country_name,
            case_type=selected_case_type,
            audience_mode=effective_user_role,
            used_tools=payload.used_tools or [],
            extra_tool_labels=payload.available_tools or [],
        )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["effective_user_role"] = effective_user_role
        result["persona_label"] = normalize_persona(effective_user_role)
        result["remaining_tools"] = result.get("remaining_tools") or remaining_tool_labels(
            effective_user_role,
            used_tools=[*(payload.used_tools or []), result.get("tool_label")],
            extra_labels=payload.available_tools or [],
        )

        if linked_case_id:
            # Store the generated workspace output as a case message when a case is linked.
            try:
                execute(
                    """
                    INSERT INTO case_messages (case_id, user_id, question, answer_json, assistant_mode, confidence_level, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        linked_case_id,
                        get_effective_user_id(user),
                        f"Workspace tool: {result.get('tool_label')}",
                        json.dumps(result, ensure_ascii=False),
                        payload.assistant_mode or "workspace_tool",
                        "workspace",
                        now_iso(),
                    ),
                )
            except Exception:
                pass

            if linked_case_id:
                execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), linked_case_id))

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API_ROUTE_ERROR %s", repr(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================
# Analysis History & Feedback Endpoints
# ============================================================

class FeedbackRequest(BaseModel):
    analysis_id: Optional[int] = None
    rating: int  # 1 = thumbs up, -1 = thumbs down
    comment: Optional[str] = ""
    assistant_mode: Optional[str] = ""
    confidence_level: Optional[str] = ""


@router.get("/analysis-history")
async def get_analysis_history(request: Request):
    """Return paginated analysis history for the current user without breaking older schemas."""
    user = require_user(request)

    try:
        page = int(request.query_params.get("page", "1"))
        per_page = int(request.query_params.get("per_page", "20"))
    except (ValueError, TypeError):
        page, per_page = 1, 20

    search = str(request.query_params.get("search") or "").strip().lower()
    mode_filter = str(request.query_params.get("mode") or "").strip()

    page = max(1, page)
    per_page = min(50, max(5, per_page))
    offset = (page - 1) * per_page

    rows = fetch_all(
        """
        SELECT *
        FROM analyses
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (get_effective_user_id(user), per_page, offset),
    )

    # Keep count simple and stable across old/new schemas.
    total_row = fetch_one(
        "SELECT COUNT(*) AS cnt FROM analyses WHERE user_id = ?",
        (get_effective_user_id(user),),
    )
    total = total_row["cnt"] if total_row else 0

    items = []
    for row in (rows or []):
        answer = _safe_json_loads(row.get("answer_json"), {})
        assistant_mode = _pick_row_value(row, "assistant_mode", default=str(answer.get("assistant_mode") or answer.get("request_type") or ""))
        confidence_level = _pick_row_value(row, "confidence_level", default=str(answer.get("confidence_level") or ""))
        question = str(row.get("question") or "")
        summary = str(answer.get("professional_summary") or answer.get("short_answer") or answer.get("lawyer_summary") or "")

        if mode_filter and assistant_mode != mode_filter:
            continue
        if search and search not in question.lower() and search not in summary.lower():
            continue

        items.append({
            "id": row.get("id"),
            "question": question[:200],
            "professional_summary": summary[:300],
            "country_name": _pick_row_value(row, "country_name", "country", default=""),
            "case_type": _pick_row_value(row, "case_type", default=""),
            "assistant_mode": assistant_mode,
            "confidence_level": confidence_level,
            "created_at": str(row.get("created_at") or ""),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_more": (offset + per_page) < total,
    }


@router.get("/analysis/{analysis_id}")
async def get_analysis_detail(request: Request, analysis_id: int):
    """Return full analysis data for a given analysis ID."""
    user = require_user(request)

    row = fetch_one(
        """
        SELECT *
        FROM analyses
        WHERE id = ? AND user_id = ?
        """,
        (analysis_id, get_effective_user_id(user)),
    )

    if not row:
        raise HTTPException(status_code=404, detail="التحليل غير موجود.")

    answer = _safe_json_loads(row.get("answer_json"), {})
    sources = _safe_json_loads(row.get("sources_json"), [])
    if sources and not answer.get("legal_sources"):
        answer["legal_sources"] = sources

    assistant_mode = _pick_row_value(row, "assistant_mode", default=str(answer.get("assistant_mode") or answer.get("request_type") or ""))
    confidence_level = _pick_row_value(row, "confidence_level", default=str(answer.get("confidence_level") or ""))

    return {
        "id": row.get("id"),
        "question": row.get("question") or "",
        "country_name": _pick_row_value(row, "country_name", "country", default=""),
        "case_type": row.get("case_type") or "",
        "assistant_mode": assistant_mode,
        "confidence_level": confidence_level,
        "created_at": str(row.get("created_at") or ""),
        "answer": answer,
    }


@router.post("/analysis-feedback")
async def submit_analysis_feedback(request: Request, payload: FeedbackRequest):
    """Submit thumbs up/down feedback for an analysis."""
    user = require_user(request)

    if payload.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="التقييم يجب أن يكون 1 أو -1.")

    if payload.analysis_id:
        row = fetch_one(
            "SELECT id FROM analyses WHERE id = ? AND user_id = ?",
            (payload.analysis_id, get_effective_user_id(user)),
        )
        if not row:
            raise HTTPException(status_code=404, detail="التحليل غير موجود.")

    try:
        execute(
            """
            INSERT INTO analysis_feedback
                (user_id, analysis_id, rating, comment, assistant_mode, confidence_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                get_effective_user_id(user),
                payload.analysis_id,
                payload.rating,
                (payload.comment or "")[:500],
                payload.assistant_mode or "",
                payload.confidence_level or "",
                now_iso(),
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"خطأ في حفظ التقييم: {str(exc)}")

    return {"success": True, "message": "شكراً على تقييمك — يساعدنا على تحسين جودة Mizan."}


@router.get("/analysis-stats")
async def get_analysis_stats(request: Request):
    """Return basic usage stats for the current user."""
    user = require_user(request)

    total = fetch_one(
        "SELECT COUNT(*) AS cnt FROM analyses WHERE user_id = ?",
        (get_effective_user_id(user),),
    )
    positive_feedback = fetch_one(
        "SELECT COUNT(*) AS cnt FROM analysis_feedback WHERE user_id = ? AND rating = 1",
        (get_effective_user_id(user),),
    )

    analyses_this_month = 0
    try:
        month_row = fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM analyses
            WHERE user_id = ?
              AND created_at >= date_trunc('month', NOW())
            """,
            (get_effective_user_id(user),),
        )
        analyses_this_month = month_row["cnt"] if month_row else 0
    except Exception:
        analyses_this_month = total["cnt"] if total else 0

    return {
        "total_analyses": total["cnt"] if total else 0,
        "analyses_this_month": analyses_this_month,
        "positive_feedback_count": positive_feedback["cnt"] if positive_feedback else 0,
    }
