import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import require_user
from app.database import UPLOAD_DIR, can_analyze, can_upload_document, execute, fetch_one, now_iso
from app.db.session import SessionLocal
from app.services.ai_service import analyze_legal_document, analyze_legal_question
from app.services.legal_retrieval_service import build_legal_source_policy, build_sources_context, search_legal_sources

router = APIRouter()


class LegalQuestionRequest(BaseModel):
    question: str
    country: Optional[str] = "الأردن"
    case_type: str = "غير محدد"
    selected_case_type: Optional[str] = "غير محدد"
    case_id: Optional[int] = None
    criminal_details: Optional[Dict[str, Any]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None


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


@router.post("/analyze")
async def analyze(request: Request, payload: LegalQuestionRequest):
    user = require_user(request)
    allowed, msg = can_analyze(user)
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="يرجى كتابة السؤال القانوني.")

    case_id = _verify_case_access(payload.case_id, user["id"])
    country_name = _user_country(user, payload.country or "الأردن")
    country_code = _user_country_code(user)
    selected_case_type = _clean_case_type(payload.selected_case_type or payload.case_type)
    conversation_history = _clean_conversation_history(payload.conversation_history)

    legal_sources = _try_legal_sources(question, country_name, country_code)
    legal_sources_context = build_sources_context(legal_sources)
    legal_source_policy = build_legal_source_policy(legal_sources)

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
        )

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


@router.post("/analyze-document")
async def analyze_document(
    request: Request,
    file: UploadFile = File(...),
    country: str = Form("الأردن"),
    document_type: str = Form("مستند قانوني"),
    plan: str = Form(""),
    question: str = Form(""),
    case_id: str = Form(""),
    selected_case_type: str = Form("غير محدد"),
):
    user = require_user(request)
    allowed, msg = can_upload_document(user)
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)

    safe_case_id: Optional[int] = None
    if case_id and str(case_id).strip():
        try:
            safe_case_id = int(case_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="رقم القضية غير صحيح.")

    linked_case_id = _verify_case_access(safe_case_id, user["id"])
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="الملف فارغ.")

    country_name = _user_country(user, country or "الأردن")
    selected_case_type = _clean_case_type(selected_case_type)

    try:
        result = await analyze_legal_document(
            file_bytes=file_bytes,
            filename=file.filename or "uploaded_document",
            content_type=file.content_type or "application/octet-stream",
            country=country_name,
            document_type=document_type,
            selected_case_type=selected_case_type,
            plan=_user_plan(user),
            user_role=_user_role(user),
            question=question,
        )

        Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        stored_name = f"{user['id']}_{int(time.time())}_{_safe_filename(file.filename or 'document')}"
        stored_path = Path(UPLOAD_DIR) / stored_name
        stored_path.write_bytes(file_bytes)

        execute(
            """
            INSERT INTO case_documents (case_id, user_id, filename, stored_path, content_type, analysis_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                linked_case_id,
                user["id"],
                file.filename or "uploaded_document",
                str(stored_path),
                file.content_type or "application/octet-stream",
                json.dumps(result, ensure_ascii=False),
                now_iso(),
            ),
        )

        try:
            execute(
                """
                INSERT INTO documents (user_id, case_id, filename, document_type, analysis_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], linked_case_id, file.filename or "uploaded_document", document_type, json.dumps(result, ensure_ascii=False), now_iso()),
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
