from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "developer",
    "admin",
]


def can_view_logs(staff) -> bool:
    return bool(staff and staff.role in ALLOWED_ROLES)


def safe_fetch_logs(db, table_name: str, limit: int = 100):
    try:
        rows = db.execute(
            text(
                f"""
                SELECT *
                FROM {table_name}
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(row) for row in rows]

    except Exception:
        return []


def safe_count(db, table_name: str):
    try:
        row = db.execute(
            text(f"SELECT COUNT(*) AS total FROM {table_name}")
        ).mappings().first()

        return int(row["total"] or 0)

    except Exception:
        return 0


@router.get("/internal/logs", response_class=HTMLResponse)
async def internal_logs_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_view_logs(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        log_type = request.query_params.get("type", "staff_access_logs").strip()

        allowed_tables = {
            "staff_access_logs": "سجلات دخول الموظفين",
            "internal_audit_logs": "سجلات التدقيق الداخلي",
            "ai_request_logs": "سجلات طلبات الذكاء الصناعي",
            "legal_search_logs": "سجلات البحث القانوني",
        }

        if log_type not in allowed_tables:
            log_type = "staff_access_logs"

        current_logs = safe_fetch_logs(db, log_type, limit=150)

        stats = {
            "staff_access_logs": safe_count(db, "staff_access_logs"),
            "internal_audit_logs": safe_count(db, "internal_audit_logs"),
            "ai_request_logs": safe_count(db, "ai_request_logs"),
            "legal_search_logs": safe_count(db, "legal_search_logs"),
        }

        return templates.TemplateResponse(
            request=request,
            name="internal/logs.html",
            context={
                "request": request,
                "staff": staff,
                "log_type": log_type,
                "log_title": allowed_tables[log_type],
                "allowed_tables": allowed_tables,
                "logs": current_logs,
                "stats": stats,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()