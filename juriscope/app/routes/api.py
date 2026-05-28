import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_user, is_staff_mode_user, is_unlimited_user
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.case import Analysis, Case, CaseNote, CaseUpdate, Document
from app.models.subscription import SubscriptionPlan
from app.services.ai_service import analyze_legal_document, analyze_legal_question
from app.services.legal_retrieval_service import (
    build_legal_source_policy,
    build_sources_context,
    search_legal_sources,
)


router = APIRouter()
settings = get_settings()


class LegalQuestionRequest(BaseModel):
    question: str
    country: Optional[str] = None

    # القيمة القادمة من الواجهة.
    # للفرد والشركة غالبًا تكون "غير محدد".
    case_type: str = "غير محدد"
    selected_case_type: Optional[str] = "غير محدد"

    case_id: Optional[int] = None
    criminal_details: Optional[Dict[str, Any]] = None

    # آخر الرسائل داخل نفس التحليل، حتى يستطيع المستخدم متابعة النقاش.
    conversation_history: Optional[List[Dict[str, Any]]] = None


def get_user_role(user: dict) -> str:
    return user.get("user_role") or "individual"


def get_user_country_name(user: dict) -> str:
    return user.get("country_name") or user.get("country") or "الأردن"


def get_user_country_code(user: dict) -> str:
    return user.get("country_code") or "JO"


def get_user_plan(user: dict) -> str:
    if is_staff_mode_user(user):
        return "staff_unlimited"

    return user.get("plan_code") or user.get("plan") or "free"


def get_user_id_or_none(user: dict) -> Optional[int]:
    if is_staff_mode_user(user):
        return None

    user_id = user.get("id")

    if user_id is None:
        return None

    return int(user_id)


def clean_case_type(value: Optional[str]) -> str:
    value = (value or "").strip()

    if not value:
        return "غير محدد"

    return value


def clean_conversation_history(value: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not value:
        return []

    cleaned = []

    for item in value[-8:]:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()

        if role not in ["user", "assistant"]:
            continue

        if not content:
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


def get_subscription_plan(db: Session, plan_code: str) -> Optional[SubscriptionPlan]:
    return (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.code == plan_code,
            SubscriptionPlan.is_active == True,
        )
        .first()
    )


def month_start() -> datetime:
    now = datetime.utcnow()
    return datetime(now.year, now.month, 1)


def can_analyze_user(
    db: Session,
    user_id: Optional[int],
    plan_code: str,
    unlimited: bool = False,
) -> tuple[bool, str]:
    if unlimited:
        return True, ""

    if user_id is None:
        return False, "لا يمكن تنفيذ التحليل بدون جلسة مستخدم صحيحة."

    plan = get_subscription_plan(db, plan_code)

    if not plan:
        return True, ""

    if plan.monthly_analyses <= 0:
        return False, "باقتك الحالية لا تسمح بإجراء تحليلات قانونية."

    used = (
        db.query(Analysis)
        .filter(
            Analysis.user_id == user_id,
            Analysis.created_at >= month_start(),
        )
        .count()
    )

    if used >= plan.monthly_analyses:
        return False, "لقد وصلت إلى حد التحليلات الشهري في باقتك الحالية."

    return True, ""


def can_upload_document_user(
    db: Session,
    user_id: Optional[int],
    plan_code: str,
    unlimited: bool = False,
) -> tuple[bool, str]:
    if unlimited:
        return True, ""

    if user_id is None:
        return False, "لا يمكن تحليل المستند بدون جلسة مستخدم صحيحة."

    plan = get_subscription_plan(db, plan_code)

    if not plan:
        return True, ""

    if not plan.can_upload_documents:
        return False, "باقتك الحالية لا تسمح بتحليل المستندات."

    if plan.monthly_documents <= 0:
        return False, "باقتك الحالية لا تسمح بتحليل المستندات."

    used = (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.created_at >= month_start(),
        )
        .count()
    )

    if used >= plan.monthly_documents:
        return False, "لقد وصلت إلى حد تحليل المستندات الشهري في باقتك الحالية."

    return True, ""


def get_plan_max_file_size_mb(
    db: Session,
    plan_code: str,
    unlimited: bool = False,
) -> int:
    if unlimited:
        return 200

    plan = get_subscription_plan(db, plan_code)

    if not plan:
        return 15

    return int(plan.max_file_size_mb or 15)


def object_to_dict(obj) -> dict:
    if not obj:
        return {}

    result = {}

    for column in obj.__table__.columns:
        value = getattr(obj, column.name)

        if isinstance(value, datetime):
            value = value.isoformat()

        result[column.name] = value

    return result


def get_case_context(
    db: Session,
    user_id: Optional[int],
    case_id: Optional[int],
    user_country_name: str,
):
    if not case_id:
        return None

    if user_id is None:
        raise HTTPException(
            status_code=403,
            detail="وضع الموظف الداخلي لا يدعم ربط التحليل بقضايا المستخدمين.",
        )

    case = (
        db.query(Case)
        .filter(
            Case.id == case_id,
            Case.user_id == user_id,
        )
        .first()
    )

    if not case:
        raise HTTPException(
            status_code=404,
            detail="القضية غير موجودة أو لا تملك صلاحية الوصول إليها.",
        )

    if case.country_name and case.country_name != user_country_name:
        raise HTTPException(
            status_code=403,
            detail="لا يمكن استخدام قضية مرتبطة بدولة مختلفة عن دولة الحساب.",
        )

    notes = (
        db.query(CaseNote)
        .filter(
            CaseNote.case_id == case_id,
            CaseNote.user_id == user_id,
        )
        .order_by(CaseNote.created_at.desc())
        .limit(10)
        .all()
    )

    updates = (
        db.query(CaseUpdate)
        .filter(
            CaseUpdate.case_id == case_id,
            CaseUpdate.user_id == user_id,
        )
        .order_by(CaseUpdate.created_at.desc())
        .limit(10)
        .all()
    )

    analyses = (
        db.query(Analysis)
        .filter(
            Analysis.case_id == case_id,
            Analysis.user_id == user_id,
        )
        .order_by(Analysis.created_at.desc())
        .limit(5)
        .all()
    )

    documents = (
        db.query(Document)
        .filter(
            Document.case_id == case_id,
            Document.user_id == user_id,
        )
        .order_by(Document.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "case": object_to_dict(case),
        "notes": [object_to_dict(item) for item in notes],
        "updates": [object_to_dict(item) for item in updates],
        "analyses": [object_to_dict(item) for item in analyses],
        "documents": [object_to_dict(item) for item in documents],
    }


@router.post("/analyze")
async def analyze_question(
    request: Request,
    payload: LegalQuestionRequest,
):
    user = require_user(request)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="يجب تسجيل الدخول أولًا لاستخدام المساعد القانوني.",
        )

    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    user_id = get_user_id_or_none(user)
    country_name = get_user_country_name(user)
    country_code = get_user_country_code(user)
    plan_code = get_user_plan(user)
    user_role = get_user_role(user)

    question = payload.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="يرجى كتابة السؤال القانوني.")

    selected_case_type = clean_case_type(payload.selected_case_type or payload.case_type)
    conversation_history = clean_conversation_history(payload.conversation_history)

    db = SessionLocal()

    try:
        allowed, msg = can_analyze_user(
            db=db,
            user_id=user_id,
            plan_code=plan_code,
            unlimited=unlimited,
        )

        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

        case_context = None

        if not staff_mode:
            case_context = get_case_context(
                db=db,
                user_id=user_id,
                case_id=payload.case_id,
                user_country_name=country_name,
            )

        legal_sources = search_legal_sources(
            db=db,
            query=question,
            country_code=country_code,
            country_name=country_name,
            limit=8,
            approved_only=True,
            active_only=True,
        )

        legal_sources_context = build_sources_context(legal_sources)
        legal_source_policy = build_legal_source_policy(legal_sources)

        try:
            result = await analyze_legal_question(
                question=question,
                country=country_name,
                case_type=selected_case_type,
                selected_case_type=selected_case_type,
                conversation_history=conversation_history,
                plan=plan_code,
                user_role=user_role,
                criminal_details=payload.criminal_details or {},
                case_context=case_context,
                legal_sources_context=legal_sources_context,
                legal_source_policy=legal_source_policy,
                legal_sources=legal_sources,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            raise HTTPException(
                status_code=500,
                detail="حدث خطأ أثناء التحليل. يرجى المحاولة مرة أخرى بعد قليل.",
            )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode

        # fallback حتى لو ai_service لم يرجعها لسبب ما
        result["selected_case_type"] = result.get("selected_case_type") or selected_case_type
        result["detected_case_type"] = result.get("detected_case_type") or "غير محدد"

        if "case_type_match" not in result:
            result["case_type_match"] = (
                selected_case_type == "غير محدد"
                or result["detected_case_type"] == "غير محدد"
                or selected_case_type == result["detected_case_type"]
            )

        if result.get("case_type_match") is True:
            result["case_type_correction_note"] = result.get("case_type_correction_note") or ""

        if staff_mode:
            result["staff_mode_note"] = "تم تنفيذ هذا التحليل بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."
            return result

        final_case_type = result.get("detected_case_type") or selected_case_type

        analysis = Analysis(
            user_id=user_id,
            case_id=payload.case_id,
            question=question,
            answer_json=json.dumps(result, ensure_ascii=False),
            country_code=country_code,
            country_name=country_name,
            case_type=final_case_type,
            plan_code=plan_code,
            user_role=user_role,
            model_used="gemini",
            sources_json=json.dumps(legal_sources, ensure_ascii=False),
            confidence_level=result.get("confidence_level", ""),
            created_at=datetime.utcnow(),
        )

        db.add(analysis)

        if payload.case_id:
            case = (
                db.query(Case)
                .filter(
                    Case.id == payload.case_id,
                    Case.user_id == user_id,
                )
                .first()
            )

            if case:
                case.updated_at = datetime.utcnow()

        db.commit()

        return result

    finally:
        db.close()


@router.post("/analyze-document")
async def analyze_document(
    request: Request,
    file: UploadFile = File(...),
    country: str = Form(""),
    document_type: str = Form("مستند قانوني"),
    plan: str = Form(""),
    question: str = Form(""),
    case_id: str = Form(""),
    selected_case_type: str = Form("غير محدد"),
):
    user = require_user(request)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="يجب تسجيل الدخول أولًا لتحليل المستندات.",
        )

    staff_mode = is_staff_mode_user(user)
    unlimited = is_unlimited_user(user)

    user_id = get_user_id_or_none(user)
    staff_id = user.get("staff_id")
    country_name = get_user_country_name(user)
    plan_code = get_user_plan(user)
    user_role = get_user_role(user)

    selected_case_type = clean_case_type(selected_case_type)

    db = SessionLocal()

    try:
        allowed, msg = can_upload_document_user(
            db=db,
            user_id=user_id,
            plan_code=plan_code,
            unlimited=unlimited,
        )

        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

        safe_case_id: Optional[int] = None

        if not staff_mode and case_id and str(case_id).strip():
            try:
                safe_case_id = int(case_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="رقم القضية غير صحيح.")

        case_context = None

        if not staff_mode:
            case_context = get_case_context(
                db=db,
                user_id=user_id,
                case_id=safe_case_id,
                user_country_name=country_name,
            )

        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(status_code=400, detail="الملف فارغ.")

        max_size_mb = get_plan_max_file_size_mb(
            db=db,
            plan_code=plan_code,
            unlimited=unlimited,
        )
        max_size = max_size_mb * 1024 * 1024

        if len(file_bytes) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"حجم الملف كبير جدًا. الحد الحالي {max_size_mb}MB.",
            )

        filename = file.filename or "uploaded-file"
        mime_type = file.content_type or "application/octet-stream"

        allowed_mimes = {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if mime_type not in allowed_mimes:
            raise HTTPException(
                status_code=400,
                detail="نوع الملف غير مدعوم. يرجى رفع PDF أو صورة JPG/PNG/WEBP.",
            )

        upload_dir = settings.UPLOAD_DIR or "data/uploads"
        os.makedirs(upload_dir, exist_ok=True)

        safe_filename = filename.replace("/", "_").replace("\\", "_")

        if staff_mode:
            saved_filename = f"staff_{staff_id}_{int(time.time())}_{safe_filename}"
        else:
            saved_filename = f"{user_id}_{int(time.time())}_{safe_filename}"

        saved_path = os.path.join(upload_dir, saved_filename)

        with open(saved_path, "wb") as f:
            f.write(file_bytes)

        try:
            result = await analyze_legal_document(
                file_bytes=file_bytes,
                mime_type=mime_type,
                filename=filename,
                country=country_name,
                document_type=document_type,
                selected_case_type=selected_case_type,
                plan=plan_code,
                user_role=user_role,
                question=question,
                case_context=case_context,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            raise HTTPException(
                status_code=500,
                detail="حدث خطأ أثناء تحليل المستند. يرجى المحاولة مرة أخرى بعد قليل.",
            )

        result["session_mode"] = "staff_unlimited" if staff_mode else "user"
        result["is_staff_mode"] = staff_mode
        result["selected_case_type"] = result.get("selected_case_type") or selected_case_type
        result["detected_case_type"] = result.get("detected_case_type") or "غير محدد"

        if staff_mode:
            result["staff_mode_note"] = "تم تحليل هذا المستند بوضع الموظف الداخلي غير المحدود، ولم يتم احتسابه ضمن استخدامات أي مستخدم."
            return result

        document = Document(
            user_id=user_id,
            case_id=safe_case_id,
            filename=filename,
            stored_filename=saved_filename,
            file_path=saved_path,
            mime_type=mime_type,
            file_size_bytes=len(file_bytes),
            document_type=document_type,
            analysis_json=json.dumps(result, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )

        db.add(document)

        if safe_case_id:
            case = (
                db.query(Case)
                .filter(
                    Case.id == safe_case_id,
                    Case.user_id == user_id,
                )
                .first()
            )

            if case:
                case.updated_at = datetime.utcnow()

        db.commit()

        return result

    finally:
        db.close()