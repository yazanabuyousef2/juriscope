import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(dotenv_path=".env")

from app.db.session import Base, SessionLocal, engine

try:
    import app.db.base  # noqa: F401
except Exception:
    pass


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

LEGAL_UPLOAD_DIR = os.path.join(DATA_DIR, "legal_uploads")
os.makedirs(LEGAL_UPLOAD_DIR, exist_ok=True)


BOOLEAN_COLUMNS = [
    "is_active",
    "phone_verified",
    "marketing_consent",
    "staff_access_requires_reason",
    "is_allowed",
    "can_upload_documents",
    "can_use_case_memory",
    "can_export_pdf",
    "can_export_word",
    "can_access_advanced_analysis",
    "can_use_legal_sources",
]


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def init_db():
    """
    Initializes database tables using SQLAlchemy models and ensures the
    production Supabase/PostgreSQL schema is complete.
    """
    Base.metadata.create_all(bind=engine)

    from app.production_schema import ensure_production_schema

    ensure_production_schema()


def _normalize_legacy_sql(query: str) -> str:
    """
    Convert old SQLite-style SQL into PostgreSQL-safe SQL.
    """
    final_query = query

    for column in BOOLEAN_COLUMNS:
        final_query = re.sub(
            rf"\b{column}\s*=\s*1\b",
            f"{column} = true",
            final_query,
            flags=re.IGNORECASE,
        )
        final_query = re.sub(
            rf"\b{column}\s*=\s*0\b",
            f"{column} = false",
            final_query,
            flags=re.IGNORECASE,
        )
        final_query = re.sub(
            rf"\b{column}\s*!=\s*1\b",
            f"{column} != true",
            final_query,
            flags=re.IGNORECASE,
        )
        final_query = re.sub(
            rf"\b{column}\s*!=\s*0\b",
            f"{column} != false",
            final_query,
            flags=re.IGNORECASE,
        )

    return final_query


def _convert_question_marks(query: str, params: tuple = ()):  # SQLite style ? -> SQLAlchemy binds
    final_query = _normalize_legacy_sql(query)
    bind_params = {}

    for index, value in enumerate(params or ()): 
        key = f"p{index}"
        final_query = final_query.replace("?", f":{key}", 1)
        bind_params[key] = value

    return final_query, bind_params


def _add_returning_id_if_needed(query: str) -> str:
    stripped = query.strip()
    lower = stripped.lower()

    if not lower.startswith("insert"):
        return query

    if " returning " in lower:
        return query

    if stripped.endswith(";"):
        stripped = stripped[:-1]

    return stripped + " RETURNING id"


def execute(query: str, params: tuple = ()): 
    db = SessionLocal()

    try:
        final_query, bind_params = _convert_question_marks(query, params)
        final_query = _add_returning_id_if_needed(final_query)

        result = db.execute(text(final_query), bind_params)
        inserted_id = None

        if result.returns_rows:
            row = result.fetchone()
            if row:
                mapping = row._mapping
                if "id" in mapping:
                    inserted_id = mapping["id"]

        db.commit()
        return inserted_id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def fetch_one(query: str, params: tuple = ()): 
    db = SessionLocal()

    try:
        final_query, bind_params = _convert_question_marks(query, params)
        result = db.execute(text(final_query), bind_params)
        row = result.fetchone()

        if not row:
            return None

        return dict(row._mapping)

    finally:
        db.close()


def fetch_all(query: str, params: tuple = ()): 
    db = SessionLocal()

    try:
        final_query, bind_params = _convert_question_marks(query, params)
        result = db.execute(text(final_query), bind_params)
        return [dict(row._mapping) for row in result.fetchall()]

    finally:
        db.close()


# =========================
# User Sessions
# =========================


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    created_at = datetime.utcnow()
    expires_at = datetime.utcnow() + timedelta(days=14)

    execute(
        """
        INSERT INTO sessions (user_id, token, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, token, created_at, expires_at),
    )

    try:
        execute(
            """
            INSERT INTO user_sessions (user_id, token, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, token, created_at, expires_at),
        )
    except Exception:
        pass

    return token


def delete_session(token: str):
    if not token:
        return

    try:
        execute("DELETE FROM sessions WHERE token = ?", (token,))
    except Exception:
        pass

    try:
        execute("DELETE FROM user_sessions WHERE token = ?", (token,))
    except Exception:
        pass


def get_user_by_session(token: str):
    if not token:
        return None

    user = fetch_one(
        """
        SELECT users.*
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        AND sessions.expires_at > ?
        AND users.is_active = 1
        """,
        (token, datetime.utcnow()),
    )

    if user:
        return user

    return fetch_one(
        """
        SELECT users.*
        FROM user_sessions
        JOIN users ON users.id = user_sessions.user_id
        WHERE user_sessions.token = ?
        AND user_sessions.expires_at > ?
        AND users.is_active = 1
        """,
        (token, datetime.utcnow()),
    )


# =========================
# Staff Sessions
# =========================


def create_staff_session(staff_user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    created_at = datetime.utcnow()
    expires_at = datetime.utcnow() + timedelta(hours=8)

    execute(
        """
        INSERT INTO staff_sessions (staff_user_id, token, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (staff_user_id, token, created_at, expires_at),
    )

    return token


def delete_staff_session(token: str):
    if token:
        execute("DELETE FROM staff_sessions WHERE token = ?", (token,))


def get_staff_by_session(token: str):
    if not token:
        return None

    return fetch_one(
        """
        SELECT staff_users.*
        FROM staff_sessions
        JOIN staff_users ON staff_users.id = staff_sessions.staff_user_id
        WHERE staff_sessions.token = ?
        AND staff_sessions.expires_at > ?
        AND staff_users.is_active = 1
        """,
        (token, datetime.utcnow()),
    )


# =========================
# Plans / Limits
# =========================


def user_limits(plan: str = "free") -> dict:
    plan = plan or "free"

    row = fetch_one(
        """
        SELECT *
        FROM subscription_plans
        WHERE code = ?
        AND is_active = 1
        """,
        (plan,),
    )

    if not row:
        row = fetch_one(
            """
            SELECT *
            FROM subscription_plans
            WHERE code = 'free'
            """
        )

    if not row:
        return {
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "cases": 999999,
            "max_file_size_mb": 15,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": False,
            "can_export_word": False,
            "can_access_advanced_analysis": False,
            "can_use_legal_sources": True,
        }

    return {
        "monthly_analyses": int(row.get("monthly_analyses") or 0),
        "monthly_documents": int(row.get("monthly_documents") or 0),
        "cases": int(row.get("max_cases") or 0),
        "max_file_size_mb": int(row.get("max_file_size_mb") or 15),
        "can_upload_documents": bool(row.get("can_upload_documents")),
        "can_use_case_memory": bool(row.get("can_use_case_memory")),
        "can_export_pdf": bool(row.get("can_export_pdf")),
        "can_export_word": bool(row.get("can_export_word")),
        "can_access_advanced_analysis": bool(row.get("can_access_advanced_analysis")),
        "can_use_legal_sources": bool(row.get("can_use_legal_sources")),
    }


def user_usage(user_id: int) -> dict:
    month_key = datetime.utcnow().strftime("%Y-%m")

    analyses_row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM analyses
        WHERE user_id = ?
        AND to_char(created_at, 'YYYY-MM') = ?
        """,
        (user_id, month_key),
    )

    documents_row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM documents
        WHERE user_id = ?
        AND to_char(created_at, 'YYYY-MM') = ?
        """,
        (user_id, month_key),
    )

    cases_row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM cases
        WHERE user_id = ?
        """,
        (user_id,),
    )

    return {
        "monthly_analyses": int(analyses_row["count"]) if analyses_row else 0,
        "monthly_documents": int(documents_row["count"]) if documents_row else 0,
        "cases": int(cases_row["count"]) if cases_row else 0,
    }


def can_analyze(user_id: int, plan: str = "free") -> tuple[bool, str]:
    limits = user_limits(plan)
    usage = user_usage(user_id)

    if usage["monthly_analyses"] >= limits["monthly_analyses"]:
        return False, "لقد وصلت إلى حد التحليلات الشهري في باقتك الحالية."

    return True, ""


def can_upload_document(user_id: int, plan: str = "free") -> tuple[bool, str]:
    limits = user_limits(plan)
    usage = user_usage(user_id)

    if not limits["can_upload_documents"]:
        return False, "باقتك الحالية لا تسمح بتحليل المستندات."

    if usage["monthly_documents"] >= limits["monthly_documents"]:
        return False, "لقد وصلت إلى حد تحليل المستندات الشهري في باقتك الحالية."

    return True, ""


def can_create_case(user_id: int, plan: str = "free") -> tuple[bool, str]:
    limits = user_limits(plan)
    usage = user_usage(user_id)

    if usage["cases"] >= limits["cases"]:
        return False, "لقد وصلت إلى حد إنشاء القضايا في باقتك الحالية."

    return True, ""


# =========================
# Logs
# =========================


def log_internal_action(
    staff_user_id: Optional[int],
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    before_json: str = "",
    after_json: str = "",
    reason: str = "",
    ip_address: str = "",
):
    execute(
        """
        INSERT INTO internal_audit_logs (
            staff_user_id,
            action,
            entity_type,
            entity_id,
            before_json,
            after_json,
            reason,
            ip_address,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            staff_user_id,
            action,
            entity_type,
            entity_id,
            before_json,
            after_json,
            reason,
            ip_address,
            datetime.utcnow(),
        ),
    )


def log_ai_request(
    user_id: Optional[int],
    case_id: Optional[int],
    country: str,
    user_role: str,
    plan: str,
    model_used: str,
    request_type: str,
    input_size: int,
    status: str,
    error_message: str = "",
):
    execute(
        """
        INSERT INTO ai_request_logs (
            user_id,
            case_id,
            country,
            user_role,
            plan,
            model_used,
            request_type,
            input_size,
            status,
            error_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            case_id,
            country,
            user_role,
            plan,
            model_used,
            request_type,
            input_size,
            status,
            error_message,
            datetime.utcnow(),
        ),
    )
