import json
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.auth.dependencies import require_user
from app.database import (
    UPLOAD_DIR,
    can_analyze,
    can_upload_document,
    execute,
    fetch_one,
    now_iso,
)
from app.schemas.legal import AnalyzeRequest, AnalyzeResponse, DocumentAnalysisResponse
from app.services.ai_service import analyze_legal_document, analyze_legal_question

router = APIRouter()


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


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request, payload: AnalyzeRequest) -> AnalyzeResponse:
    user = require_user(request)
    allowed, msg = can_analyze(user)
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)

    case_id = _verify_case_access(payload.case_id, user["id"])

    # The user's real plan controls the depth, not a browser-provided plan.
    plan_map = {"free": "المجانية", "individual": "الأفراد", "business": "الأعمال", "lawyer": "المحامون"}
    payload.plan = plan_map.get(user.get("plan", "free"), "المجانية")

    try:
        result = await analyze_legal_question(payload)
        execute(
            "INSERT INTO case_messages (case_id, user_id, question, answer_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (case_id, user["id"], payload.question, result.model_dump_json(ensure_ascii=False), now_iso()),
        )
        if case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), case_id))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze-document", response_model=DocumentAnalysisResponse)
async def analyze_document(
    request: Request,
    file: UploadFile = File(...),
    country: str = Form("الأردن"),
    document_type: str = Form("مستند قانوني"),
    plan: str = Form("المجانية"),
    question: str = Form(""),
    case_id: int | None = Form(None),
) -> DocumentAnalysisResponse:
    user = require_user(request)
    allowed, msg = can_upload_document(user)
    if not allowed:
        raise HTTPException(status_code=403, detail=msg)

    linked_case_id = _verify_case_access(case_id, user["id"])

    plan_map = {"free": "المجانية", "individual": "الأفراد", "business": "الأعمال", "lawyer": "المحامون"}
    plan = plan_map.get(user.get("plan", "free"), "المجانية")

    try:
        file_bytes = await file.read()
        result = await analyze_legal_document(
            file_bytes=file_bytes,
            filename=file.filename or "uploaded_document",
            content_type=file.content_type or "application/octet-stream",
            country=country,
            document_type=document_type,
            plan=plan,
            question=question,
        )

        # Save uploaded file only after successful analysis.
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        stored_name = f"{user['id']}_{int(__import__('time').time())}_{_safe_filename(file.filename or 'document')}"
        stored_path = UPLOAD_DIR / stored_name
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
                result.model_dump_json(ensure_ascii=False),
                now_iso(),
            ),
        )
        if linked_case_id:
            execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), linked_case_id))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
