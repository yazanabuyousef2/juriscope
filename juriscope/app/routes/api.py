import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import require_user, is_staff_mode_user, is_unlimited_user
from app.database import UPLOAD_DIR, can_analyze, can_upload_document, execute, fetch_one, now_iso
from app.db.session import SessionLocal
from app.services.ai_service import (
    analyze_legal_document,
    analyze_legal_documents,
    analyze_legal_question,
    analyze_legal_question_with_documents,
)
from app.services.legal_retrieval_service import build_legal_source_policy, build_sources_context, build_strict_source_guard_note, search_legal_sources
from app.services.legal_assistant_engine import build_engine_context
from app.services.legal_query_classifier import classify_query

router = APIRouter()


class LegalQuestionRequest(BaseModel):
    question: str
    country: Optional[str] = "الأردن"
    case_type: str = "غير محدد"
    selected_case_type: Optional[str] = "غير محدد"
    case_id: Optional[int] = None
    criminal_details: Optional[Dict[str, Any]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    assistant_mode: Optional[str] = "case_analysis"


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
    return user.get("user_role") or "individual"


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


@router.post("/analyze")
async def analyze(request: Request, payload: LegalQuestionRequest):
    user = require_user(request)

    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_analyze(user["id"], _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="يرجى كتابة السؤال القانوني.")

    case_id = None
    if not staff_mode:
        case_id = _verify_case_access(payload.case_id, user["id"])

    country_name = _user_country(user, payload.country or "الأردن")
    country_code = _user_country_code(user)
    selected_case_type = _clean_case_type(payload.selected_case_type or payload.case_type)
    conversation_history = _clean_conversation_history(payload.conversation_history)

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
            user_role=_user_role(user),
            criminal_details=payload.criminal_details or {},
            legal_sources_context=legal_sources_context,
            legal_source_policy=legal_source_policy,
            legal_sources=legal_sources,
            assistant_mode=payload.assistant_mode or "case_analysis",
        )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode

        if staff_mode:
            result["staff_mode_note"] = "تم تنفيذ هذا التحليل بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."
            return result

        final_case_type = result.get("detected_case_type") or selected_case_type

        execute(
            """
            INSERT INTO case_messages (case_id, user_id, question, answer_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, user["id"], question, json.dumps(result, ensure_ascii=False), now_iso()),
        )

        try:
            execute(
                """
                INSERT INTO analyses (user_id, case_id, question, answer_json, country, case_type, plan, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user["id"], case_id, question, json.dumps(result, ensure_ascii=False), country_name, final_case_type, _user_plan(user), now_iso()),
            )
        except Exception:
            pass

        if case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), case_id))

        return result

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze-with-documents")
async def analyze_with_documents(request: Request):
    user = require_user(request)
    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_analyze(user["id"], _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)
        allowed_doc, msg_doc = can_upload_document(user["id"], _user_plan(user))
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
    linked_case_id = None if staff_mode else _verify_case_access(safe_case_id, user["id"])

    country_name = _user_country(user, str(form.get("country") or "الأردن"))
    country_code = _user_country_code(user)
    selected_case_type = _clean_case_type(str(form.get("selected_case_type") or form.get("case_type") or "غير محدد"))
    assistant_mode = str(form.get("assistant_mode") or "case_analysis").strip() or "case_analysis"
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
            user_role=_user_role(user),
            criminal_details=criminal_details,
            legal_sources_context=legal_sources_context,
            legal_source_policy=legal_source_policy,
            legal_sources=legal_sources,
            assistant_mode=assistant_mode,
        )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode

        if staff_mode:
            result["staff_mode_note"] = "تم تحليل السؤال مع الملفات بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."
            return result

        _store_uploaded_documents(
            user_id=user["id"],
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
            (linked_case_id, user["id"], question, json.dumps(result, ensure_ascii=False), now_iso()),
        )

        try:
            execute(
                """
                INSERT INTO analyses (user_id, case_id, question, answer_json, country, case_type, plan, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user["id"], linked_case_id, question, json.dumps(result, ensure_ascii=False), country_name, final_case_type, _user_plan(user), now_iso()),
            )
        except Exception:
            pass

        if linked_case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), linked_case_id))

        return result

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze-document")
async def analyze_document(request: Request):
    user = require_user(request)

    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    if not unlimited:
        allowed, msg = can_upload_document(user["id"], _user_plan(user))
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

    form = await request.form()
    files = list(form.getlist("files")) or list(form.getlist("file"))
    files = [file for file in files if hasattr(file, "read") and hasattr(file, "filename")]

    uploaded_files = await _read_uploaded_files(files)
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="يرجى رفع ملف واحد على الأقل.")

    safe_case_id = _parse_optional_int(form.get("case_id"))
    linked_case_id = None if staff_mode else _verify_case_access(safe_case_id, user["id"])

    country_name = _user_country(user, str(form.get("country") or "الأردن"))
    selected_case_type = _clean_case_type(str(form.get("selected_case_type") or "غير محدد"))
    document_type = str(form.get("document_type") or "مستند قانوني")
    question = str(form.get("question") or "")

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
                user_role=_user_role(user),
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
                user_role=_user_role(user),
                question=question,
            )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode

        if staff_mode:
            result["staff_mode_note"] = "تم تحليل هذه المستندات بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."
            return result

        _store_uploaded_documents(
            user_id=user["id"],
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
        raise HTTPException(status_code=500, detail=str(exc))
