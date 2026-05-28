from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "legal_reviewer",
    "customer_service",
]


def can_view_sensitive_cases(staff) -> bool:
    return bool(staff and staff.role in ALLOWED_ROLES)


def ensure_sensitive_access_log_table(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sensitive_case_access_logs (
                id SERIAL PRIMARY KEY,
                staff_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                access_reason TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.commit()


def safe_case_row_to_dict(row):
    return dict(row) if row else None


@router.get("/internal/sensitive-cases", response_class=HTMLResponse)
async def sensitive_cases_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_view_sensitive_cases(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    search = request.query_params.get("search", "").strip()
    status = request.query_params.get("status", "").strip()
    case_type = request.query_params.get("case_type", "").strip()

    db = SessionLocal()

    try:
        ensure_sensitive_access_log_table(db)

        where_parts = []
        params = {}

        if search:
            where_parts.append("(CAST(id AS TEXT) ILIKE :search OR title ILIKE :search)")
            params["search"] = f"%{search}%"

        if status:
            where_parts.append("status = :status")
            params["status"] = status

        if case_type:
            where_parts.append("case_type = :case_type")
            params["case_type"] = case_type

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        cases = db.execute(
            text(
                f"""
                SELECT *
                FROM cases
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT 200
                """
            ),
            params,
        ).mappings().all()

        recent_logs = db.execute(
            text(
                """
                SELECT
                    l.id,
                    l.staff_id,
                    l.case_id,
                    l.access_reason,
                    l.created_at,
                    s.full_name AS staff_name,
                    s.email AS staff_email
                FROM sensitive_case_access_logs l
                LEFT JOIN staff_users s ON s.id = l.staff_id
                ORDER BY l.created_at DESC
                LIMIT 50
                """
            )
        ).mappings().all()

        stats = {
            "total_cases": db.execute(text("SELECT COUNT(*) AS total FROM cases")).mappings().first()["total"],
            "shown_cases": len(cases),
            "access_logs": db.execute(text("SELECT COUNT(*) AS total FROM sensitive_case_access_logs")).mappings().first()["total"],
        }

        return templates.TemplateResponse(
            request=request,
            name="internal/sensitive_cases.html",
            context={
                "request": request,
                "staff": staff,
                "cases": [dict(item) for item in cases],
                "recent_logs": [dict(item) for item in recent_logs],
                "selected_case": None,
                "search": search,
                "status": status,
                "case_type": case_type,
                "stats": stats,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/sensitive-cases/view", response_class=HTMLResponse)
async def sensitive_case_view(
    request: Request,
    case_id: int = Form(...),
    access_reason: str = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_view_sensitive_cases(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    access_reason = access_reason.strip()

    if len(access_reason) < 10:
        return RedirectResponse(url="/internal/sensitive-cases?error=reason_required", status_code=303)

    db = SessionLocal()

    try:
        ensure_sensitive_access_log_table(db)

        selected_case = db.execute(
            text(
                """
                SELECT *
                FROM cases
                WHERE id = :case_id
                """
            ),
            {"case_id": case_id},
        ).mappings().first()

        if not selected_case:
            return RedirectResponse(url="/internal/sensitive-cases?error=case_not_found", status_code=303)

        db.execute(
            text(
                """
                INSERT INTO sensitive_case_access_logs (
                    staff_id,
                    case_id,
                    access_reason,
                    created_at
                )
                VALUES (
                    :staff_id,
                    :case_id,
                    :access_reason,
                    :created_at
                )
                """
            ),
            {
                "staff_id": staff.id,
                "case_id": case_id,
                "access_reason": access_reason,
                "created_at": datetime.utcnow(),
            },
        )

        db.commit()

        notes = db.execute(
            text(
                """
                SELECT *
                FROM case_notes
                WHERE case_id = :case_id
                ORDER BY created_at DESC
                LIMIT 50
                """
            ),
            {"case_id": case_id},
        ).mappings().all()

        updates = db.execute(
            text(
                """
                SELECT *
                FROM case_updates
                WHERE case_id = :case_id
                ORDER BY created_at DESC
                LIMIT 50
                """
            ),
            {"case_id": case_id},
        ).mappings().all()

        analyses = db.execute(
            text(
                """
                SELECT *
                FROM analyses
                WHERE case_id = :case_id
                ORDER BY created_at DESC
                LIMIT 20
                """
            ),
            {"case_id": case_id},
        ).mappings().all()

        documents = db.execute(
            text(
                """
                SELECT *
                FROM documents
                WHERE case_id = :case_id
                ORDER BY created_at DESC
                LIMIT 20
                """
            ),
            {"case_id": case_id},
        ).mappings().all()

        recent_logs = db.execute(
            text(
                """
                SELECT
                    l.id,
                    l.staff_id,
                    l.case_id,
                    l.access_reason,
                    l.created_at,
                    s.full_name AS staff_name,
                    s.email AS staff_email
                FROM sensitive_case_access_logs l
                LEFT JOIN staff_users s ON s.id = l.staff_id
                ORDER BY l.created_at DESC
                LIMIT 50
                """
            )
        ).mappings().all()

        cases = db.execute(
            text(
                """
                SELECT *
                FROM cases
                ORDER BY updated_at DESC
                LIMIT 200
                """
            )
        ).mappings().all()

        stats = {
            "total_cases": db.execute(text("SELECT COUNT(*) AS total FROM cases")).mappings().first()["total"],
            "shown_cases": len(cases),
            "access_logs": db.execute(text("SELECT COUNT(*) AS total FROM sensitive_case_access_logs")).mappings().first()["total"],
        }

        return templates.TemplateResponse(
            request=request,
            name="internal/sensitive_cases.html",
            context={
                "request": request,
                "staff": staff,
                "cases": [dict(item) for item in cases],
                "recent_logs": [dict(item) for item in recent_logs],
                "selected_case": dict(selected_case),
                "notes": [dict(item) for item in notes],
                "updates": [dict(item) for item in updates],
                "analyses": [dict(item) for item in analyses],
                "documents": [dict(item) for item in documents],
                "search": "",
                "status": "",
                "case_type": "",
                "stats": stats,
                "error": "",
                "success": "access_logged",
            },
        )

    finally:
        db.close()