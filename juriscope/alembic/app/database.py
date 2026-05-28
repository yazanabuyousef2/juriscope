import os
import sqlite3
import secrets
from datetime import datetime, timedelta


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "mizan.db")


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute(query: str, params: tuple = ()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id


def fetch_one(query: str, params: tuple = ()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row


def fetch_all(query: str, params: tuple = ()):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    # توافق مع النسخ القديمة والجديدة:
    # plan/plan_code = الاشتراك
    # user_role = نوع المستخدم فقط
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN plan_code TEXT NOT NULL DEFAULT 'free'")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN user_role TEXT NOT NULL DEFAULT 'individual'")
    except Exception:
        pass

    try:
        cursor.execute("UPDATE users SET plan_code = plan WHERE (plan_code IS NULL OR plan_code = '')")
    except Exception:
        pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        country TEXT DEFAULT '',
        case_type TEXT DEFAULT '',
        opponent_name TEXT DEFAULT '',
        court_name TEXT DEFAULT '',
        case_number TEXT DEFAULT '',
        status TEXT DEFAULT 'مفتوحة',
        summary TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        case_id INTEGER,
        question TEXT NOT NULL,
        answer_json TEXT NOT NULL,
        country TEXT DEFAULT '',
        case_type TEXT DEFAULT '',
        plan TEXT DEFAULT 'free',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        case_id INTEGER,
        filename TEXT NOT NULL,
        document_type TEXT DEFAULT '',
        analysis_json TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        case_id INTEGER NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        case_id INTEGER NOT NULL,
        update_text TEXT NOT NULL,
        hearing_date TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER,
        user_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER,
        user_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        stored_path TEXT DEFAULT '',
        content_type TEXT DEFAULT '',
        analysis_json TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )
    """)

    conn.commit()
    conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    created_at = now_iso()
    expires_at = (datetime.utcnow() + timedelta(days=14)).isoformat()

    execute(
        """
        INSERT INTO sessions (user_id, token, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, token, created_at, expires_at),
    )

    return token


def delete_session(token: str):
    if token:
        execute(
            "DELETE FROM sessions WHERE token = ?",
            (token,),
        )


def get_user_by_session(token: str):
    if not token:
        return None

    return fetch_one(
        """
        SELECT users.*
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        AND sessions.expires_at > ?
        AND users.is_active = 1
        """,
        (token, now_iso()),
    )


def user_limits(plan: str = "free") -> dict:
    """
    الاشتراك يحدد الحدود والصلاحيات. نوع المستخدم لا علاقة له بالحدود.
    نحاول قراءة الحدود من subscription_plans إن كانت موجودة، وإلا نستخدم defaults.
    """
    plan = (plan or "free").strip().lower()

    defaults = {
        "free": {"monthly_analyses": 3, "monthly_documents": 1, "cases": 1},
        "basic": {"monthly_analyses": 50, "monthly_documents": 20, "cases": 5},
        "pro": {"monthly_analyses": 200, "monthly_documents": 100, "cases": 20},
        "premium": {"monthly_analyses": 500, "monthly_documents": 300, "cases": 100},
        "enterprise": {"monthly_analyses": 999999, "monthly_documents": 999999, "cases": 999999},
        "staff_unlimited": {"monthly_analyses": 999999, "monthly_documents": 999999, "cases": 999999},
    }

    try:
        row = fetch_one(
            """
            SELECT monthly_analyses, monthly_documents, max_cases
            FROM subscription_plans
            WHERE code = ? AND is_active = 1
            """,
            (plan,),
        )

        if row:
            return {
                "monthly_analyses": int(row["monthly_analyses"] or 0),
                "monthly_documents": int(row["monthly_documents"] or 0),
                "cases": int(row["max_cases"] or 0),
            }
    except Exception:
        pass

    return defaults.get(plan, defaults["free"])

def user_usage(user_id: int) -> dict:
    """
    Returns current usage statistics for the user.
    """

    analyses_row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM analyses
        WHERE user_id = ?
        AND substr(created_at, 1, 7) = substr(?, 1, 7)
        """,
        (user_id, now_iso()),
    )

    documents_row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM documents
        WHERE user_id = ?
        AND substr(created_at, 1, 7) = substr(?, 1, 7)
        """,
        (user_id, now_iso()),
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
        "monthly_analyses": analyses_row["count"] if analyses_row else 0,
        "monthly_documents": documents_row["count"] if documents_row else 0,
        "cases": cases_row["count"] if cases_row else 0,
    }


def can_analyze(user_id: int, plan: str = "free") -> tuple[bool, str]:
    limits = user_limits(plan)

    if limits["monthly_analyses"] >= 999999:
        return True, ""

    usage = user_usage(user_id)

    if usage["monthly_analyses"] >= limits["monthly_analyses"]:
        return False, "لقد وصلت إلى حد التحليلات الشهري في باقتك الحالية."

    return True, ""

def can_upload_document(user_id: int, plan: str = "free") -> tuple[bool, str]:
    limits = user_limits(plan)

    if limits["monthly_documents"] >= 999999:
        return True, ""

    usage = user_usage(user_id)

    if usage["monthly_documents"] >= limits["monthly_documents"]:
        return False, "لقد وصلت إلى حد المستندات الشهري في باقتك الحالية."

    return True, ""

def can_create_case(user_id: int, plan: str = "free") -> tuple[bool, str]:
    """
    Development mode:
    يسمح بإنشاء جميع القضايا بدون حد.
    """

    return True, ""