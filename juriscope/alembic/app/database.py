import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv


load_dotenv(dotenv_path=".env", override=False)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

LEGAL_UPLOAD_DIR = os.path.join(DATA_DIR, "legal_uploads")
os.makedirs(LEGAL_UPLOAD_DIR, exist_ok=True)


def clean_database_url(raw_url: str | None) -> str:
    url = (raw_url or "").strip().strip('"').strip("'")

    if url.startswith("DATABASE_URL="):
        url = url.replace("DATABASE_URL=", "", 1).strip().strip('"').strip("'")

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


DATABASE_URL = clean_database_url(os.getenv("DATABASE_URL", ""))


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


def require_database_url():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is missing. Please add PostgreSQL DATABASE_URL to your .env or Render environment variables."
        )


def get_connection():
    require_database_url()

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def normalize_legacy_sql(query: str) -> str:
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


def normalize_query(query: str) -> str:
    query = normalize_legacy_sql(query)
    return query.replace("?", "%s")


def add_returning_id_if_needed(query: str) -> str:
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
    conn = get_connection()
    cursor = conn.cursor()

    try:
        final_query = normalize_query(query)
        final_query = add_returning_id_if_needed(final_query)

        cursor.execute(final_query, params)

        last_id = None

        if cursor.description:
            row = cursor.fetchone()
            if row and "id" in row:
                last_id = row["id"]

        conn.commit()
        return last_id

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


def fetch_one(query: str, params: tuple = ()):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(normalize_query(query), params)
        return cursor.fetchone()

    finally:
        cursor.close()
        conn.close()


def fetch_all(query: str, params: tuple = ()):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(normalize_query(query), params)
        return cursor.fetchall()

    finally:
        cursor.close()
        conn.close()


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = %s
        AND column_name = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def add_column_if_missing(cursor, table_name: str, column_name: str, definition: str):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def seed_countries(cursor):
    countries = [
        ("JO", "الأردن", "Jordan", "+962", "JOD", True),
        ("SA", "السعودية", "Saudi Arabia", "+966", "SAR", True),
        ("AE", "الإمارات", "United Arab Emirates", "+971", "AED", True),
        ("EG", "مصر", "Egypt", "+20", "EGP", True),
        ("IQ", "العراق", "Iraq", "+964", "IQD", True),
        ("QA", "قطر", "Qatar", "+974", "QAR", True),
        ("KW", "الكويت", "Kuwait", "+965", "KWD", True),
        ("BH", "البحرين", "Bahrain", "+973", "BHD", True),
        ("OM", "عُمان", "Oman", "+968", "OMR", True),
    ]

    for code, name_ar, name_en, phone_code, currency, is_active in countries:
        cursor.execute(
            """
            INSERT INTO countries (
                code,
                name_ar,
                name_en,
                phone_code,
                currency,
                is_active,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (code) DO UPDATE SET
                name_ar = EXCLUDED.name_ar,
                name_en = EXCLUDED.name_en,
                phone_code = EXCLUDED.phone_code,
                currency = EXCLUDED.currency,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            """,
            (code, name_ar, name_en, phone_code, currency, is_active),
        )


def seed_subscription_plans(cursor):
    plans = [
        {
            "code": "free",
            "name_ar": "Free",
            "name_en": "Free",
            "description_ar": "خطة مجانية للتجربة",
            "description_en": "Free trial plan",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 15,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": False,
            "can_export_word": False,
            "can_access_advanced_analysis": False,
            "can_use_legal_sources": True,
            "is_active": True,
        },
        {
            "code": "basic",
            "name_ar": "Basic",
            "name_en": "Basic",
            "description_ar": "خطة أساسية",
            "description_en": "Basic plan",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 15,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": False,
            "can_export_word": False,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
            "is_active": True,
        },
        {
            "code": "pro",
            "name_ar": "Pro",
            "name_en": "Pro",
            "description_ar": "خطة احترافية",
            "description_en": "Professional plan",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 20,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": True,
            "can_export_word": True,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
            "is_active": True,
        },
        {
            "code": "premium",
            "name_ar": "Premium",
            "name_en": "Premium",
            "description_ar": "خطة مميزة",
            "description_en": "Premium plan",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 30,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": True,
            "can_export_word": True,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
            "is_active": True,
        },
        {
            "code": "enterprise",
            "name_ar": "Enterprise",
            "name_en": "Enterprise",
            "description_ar": "خطة المؤسسات",
            "description_en": "Enterprise plan",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 50,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": True,
            "can_export_word": True,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
            "is_active": True,
        },
    ]

    for plan in plans:
        cursor.execute(
            """
            INSERT INTO subscription_plans (
                code,
                name_ar,
                name_en,
                description_ar,
                description_en,
                price_monthly,
                currency,
                monthly_analyses,
                monthly_documents,
                max_cases,
                max_file_size_mb,
                can_upload_documents,
                can_use_case_memory,
                can_export_pdf,
                can_export_word,
                can_access_advanced_analysis,
                can_use_legal_sources,
                is_active,
                created_at,
                updated_at
            )
            VALUES (
                %(code)s,
                %(name_ar)s,
                %(name_en)s,
                %(description_ar)s,
                %(description_en)s,
                %(price_monthly)s,
                %(currency)s,
                %(monthly_analyses)s,
                %(monthly_documents)s,
                %(max_cases)s,
                %(max_file_size_mb)s,
                %(can_upload_documents)s,
                %(can_use_case_memory)s,
                %(can_export_pdf)s,
                %(can_export_word)s,
                %(can_access_advanced_analysis)s,
                %(can_use_legal_sources)s,
                %(is_active)s,
                NOW(),
                NOW()
            )
            ON CONFLICT (code) DO UPDATE SET
                name_ar = EXCLUDED.name_ar,
                name_en = EXCLUDED.name_en,
                description_ar = EXCLUDED.description_ar,
                description_en = EXCLUDED.description_en,
                price_monthly = EXCLUDED.price_monthly,
                currency = EXCLUDED.currency,
                monthly_analyses = EXCLUDED.monthly_analyses,
                monthly_documents = EXCLUDED.monthly_documents,
                max_cases = EXCLUDED.max_cases,
                max_file_size_mb = EXCLUDED.max_file_size_mb,
                can_upload_documents = EXCLUDED.can_upload_documents,
                can_use_case_memory = EXCLUDED.can_use_case_memory,
                can_export_pdf = EXCLUDED.can_export_pdf,
                can_export_word = EXCLUDED.can_export_word,
                can_access_advanced_analysis = EXCLUDED.can_access_advanced_analysis,
                can_use_legal_sources = EXCLUDED.can_use_legal_sources,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            """,
            plan,
        )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS countries (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name_ar TEXT NOT NULL,
                name_en TEXT DEFAULT '',
                phone_code TEXT DEFAULT '',
                currency TEXT DEFAULT '',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                plan_code TEXT DEFAULT 'free',
                country TEXT NOT NULL DEFAULT 'الأردن',
                country_code TEXT DEFAULT 'JO',
                country_name TEXT DEFAULT 'الأردن',
                phone TEXT NOT NULL DEFAULT '',
                phone_country_code TEXT DEFAULT '+962',
                phone_verified BOOLEAN NOT NULL DEFAULT TRUE,
                user_role TEXT NOT NULL DEFAULT 'individual',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                accepted_terms_at TIMESTAMP NULL,
                accepted_privacy_at TIMESTAMP NULL,
                legal_disclaimer_accepted_at TIMESTAMP NULL,
                marketing_consent BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        add_column_if_missing(cursor, "users", "plan", "TEXT NOT NULL DEFAULT 'free'")
        add_column_if_missing(cursor, "users", "plan_code", "TEXT DEFAULT 'free'")
        add_column_if_missing(cursor, "users", "country", "TEXT NOT NULL DEFAULT 'الأردن'")
        add_column_if_missing(cursor, "users", "country_code", "TEXT DEFAULT 'JO'")
        add_column_if_missing(cursor, "users", "country_name", "TEXT DEFAULT 'الأردن'")
        add_column_if_missing(cursor, "users", "phone", "TEXT NOT NULL DEFAULT ''")
        add_column_if_missing(cursor, "users", "phone_country_code", "TEXT DEFAULT '+962'")
        add_column_if_missing(cursor, "users", "phone_verified", "BOOLEAN NOT NULL DEFAULT TRUE")
        add_column_if_missing(cursor, "users", "user_role", "TEXT NOT NULL DEFAULT 'individual'")
        add_column_if_missing(cursor, "users", "is_active", "BOOLEAN NOT NULL DEFAULT TRUE")
        add_column_if_missing(cursor, "users", "accepted_terms_at", "TIMESTAMP NULL")
        add_column_if_missing(cursor, "users", "accepted_privacy_at", "TIMESTAMP NULL")
        add_column_if_missing(cursor, "users", "legal_disclaimer_accepted_at", "TIMESTAMP NULL")
        add_column_if_missing(cursor, "users", "marketing_consent", "BOOLEAN NOT NULL DEFAULT FALSE")
        add_column_if_missing(cursor, "users", "updated_at", "TIMESTAMP NOT NULL DEFAULT NOW()")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                country TEXT DEFAULT '',
                case_type TEXT DEFAULT '',
                opponent_name TEXT DEFAULT '',
                court_name TEXT DEFAULT '',
                case_number TEXT DEFAULT '',
                status TEXT DEFAULT 'مفتوحة',
                summary TEXT DEFAULT '',
                sensitivity_level TEXT DEFAULT 'normal',
                staff_access_requires_reason BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
                question TEXT NOT NULL,
                answer_json TEXT NOT NULL,
                country TEXT DEFAULT '',
                case_type TEXT DEFAULT '',
                plan TEXT DEFAULT 'free',
                user_role TEXT DEFAULT '',
                model_used TEXT DEFAULT '',
                sources_json TEXT DEFAULT '',
                confidence_level TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
                filename TEXT NOT NULL,
                stored_filename TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                mime_type TEXT DEFAULT '',
                file_size_bytes INTEGER DEFAULT 0,
                document_type TEXT DEFAULT '',
                analysis_json TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS case_notes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
                note TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS case_updates (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
                update_text TEXT NOT NULL,
                hearing_date TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jurisdictions (
                id SERIAL PRIMARY KEY,
                country_id INTEGER REFERENCES countries(id) ON DELETE CASCADE,
                name_ar TEXT NOT NULL,
                name_en TEXT DEFAULT '',
                jurisdiction_type TEXT DEFAULT '',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'customer_service',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER,
                last_login_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_sessions (
                id SERIAL PRIMARY KEY,
                staff_user_id INTEGER NOT NULL REFERENCES staff_users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_permissions (
                id SERIAL PRIMARY KEY,
                role TEXT NOT NULL,
                permission_key TEXT NOT NULL,
                is_allowed BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(role, permission_key)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_documents (
                id SERIAL PRIMARY KEY,
                country_id INTEGER REFERENCES countries(id) ON DELETE SET NULL,
                jurisdiction_id INTEGER REFERENCES jurisdictions(id) ON DELETE SET NULL,
                title_ar TEXT NOT NULL,
                title_en TEXT DEFAULT '',
                document_type TEXT NOT NULL DEFAULT 'law',
                source_name TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                official_reference TEXT DEFAULT '',
                issue_date TEXT DEFAULT '',
                effective_date TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                review_status TEXT NOT NULL DEFAULT 'draft',
                source_confidence TEXT DEFAULT 'medium',
                uploaded_file_path TEXT DEFAULT '',
                created_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                reviewed_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_articles (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES legal_documents(id) ON DELETE CASCADE,
                country_id INTEGER REFERENCES countries(id) ON DELETE SET NULL,
                article_number TEXT NOT NULL,
                article_title TEXT DEFAULT '',
                article_text TEXT NOT NULL,
                article_text_clean TEXT DEFAULT '',
                chapter TEXT DEFAULT '',
                section TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                review_status TEXT NOT NULL DEFAULT 'draft',
                effective_date TEXT DEFAULT '',
                repealed_date TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                source_confidence TEXT DEFAULT 'medium',
                last_verified_at TIMESTAMP NULL,
                created_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                updated_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                reviewed_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_article_relations (
                id SERIAL PRIMARY KEY,
                article_id INTEGER NOT NULL REFERENCES legal_articles(id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL DEFAULT 'link',
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                reference_text TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                source_name TEXT DEFAULT 'ديوان التشريع والرأي',
                official_reference TEXT DEFAULT '',
                related_document_id INTEGER REFERENCES legal_documents(id) ON DELETE SET NULL,
                related_article_id INTEGER REFERENCES legal_articles(id) ON DELETE SET NULL,
                court_name TEXT DEFAULT '',
                case_number TEXT DEFAULT '',
                decision_date TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                source_confidence TEXT DEFAULT 'official',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_article_versions (
                id SERIAL PRIMARY KEY,
                article_id INTEGER REFERENCES legal_articles(id) ON DELETE CASCADE,
                version_number INTEGER NOT NULL DEFAULT 1,
                article_text TEXT NOT NULL,
                article_text_clean TEXT DEFAULT '',
                change_reason TEXT DEFAULT '',
                status TEXT DEFAULT 'archived',
                effective_date TEXT DEFAULT '',
                created_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_topics (
                id SERIAL PRIMARY KEY,
                name_ar TEXT NOT NULL,
                name_en TEXT DEFAULT '',
                parent_id INTEGER REFERENCES legal_topics(id) ON DELETE SET NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_article_topics (
                id SERIAL PRIMARY KEY,
                article_id INTEGER REFERENCES legal_articles(id) ON DELETE CASCADE,
                topic_id INTEGER REFERENCES legal_topics(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(article_id, topic_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_article_keywords (
                id SERIAL PRIMARY KEY,
                article_id INTEGER REFERENCES legal_articles(id) ON DELETE CASCADE,
                keyword TEXT NOT NULL,
                keyword_type TEXT DEFAULT 'general',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_import_jobs (
                id SERIAL PRIMARY KEY,
                country_id INTEGER REFERENCES countries(id) ON DELETE SET NULL,
                staff_user_id INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result_json TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_plans (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name_ar TEXT NOT NULL,
                name_en TEXT DEFAULT '',
                description_ar TEXT DEFAULT '',
                description_en TEXT DEFAULT '',
                price_monthly NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                monthly_analyses INTEGER DEFAULT 0,
                monthly_documents INTEGER DEFAULT 0,
                max_cases INTEGER DEFAULT 0,
                max_file_size_mb INTEGER DEFAULT 15,
                can_upload_documents BOOLEAN DEFAULT TRUE,
                can_use_case_memory BOOLEAN DEFAULT TRUE,
                can_export_pdf BOOLEAN DEFAULT FALSE,
                can_export_word BOOLEAN DEFAULT FALSE,
                can_access_advanced_analysis BOOLEAN DEFAULT FALSE,
                can_use_legal_sources BOOLEAN DEFAULT TRUE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                plan_code TEXT NOT NULL DEFAULT 'free',
                status TEXT NOT NULL DEFAULT 'active',
                started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                ends_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                plan_code TEXT DEFAULT '',
                amount NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                provider TEXT DEFAULT '',
                provider_reference TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                raw_response TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                transaction_id INTEGER REFERENCES payment_transactions(id) ON DELETE SET NULL,
                invoice_number TEXT UNIQUE,
                amount NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                status TEXT DEFAULT 'issued',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounting_invoices (
                id SERIAL PRIMARY KEY,
                invoice_number TEXT UNIQUE,
                customer_name TEXT DEFAULT '',
                customer_email TEXT DEFAULT '',
                customer_phone TEXT DEFAULT '',
                description TEXT DEFAULT '',
                amount NUMERIC DEFAULT 0,
                tax_amount NUMERIC DEFAULT 0,
                total_amount NUMERIC DEFAULT 0,
                subtotal_amount NUMERIC DEFAULT 0,
                sales_tax_amount NUMERIC DEFAULT 0,
                discount_amount NUMERIC DEFAULT 0,
                paid_amount NUMERIC DEFAULT 0,
                balance_amount NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'JOD',
                status TEXT DEFAULT 'draft',
                due_date TIMESTAMP NULL,
                notes TEXT DEFAULT '',
                payment_method TEXT DEFAULT '',
                reference_number TEXT DEFAULT '',
                issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
                paid_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        add_column_if_missing(cursor, "accounting_invoices", "subtotal_amount", "NUMERIC DEFAULT 0")
        add_column_if_missing(cursor, "accounting_invoices", "sales_tax_amount", "NUMERIC DEFAULT 0")
        add_column_if_missing(cursor, "accounting_invoices", "discount_amount", "NUMERIC DEFAULT 0")
        add_column_if_missing(cursor, "accounting_invoices", "paid_amount", "NUMERIC DEFAULT 0")
        add_column_if_missing(cursor, "accounting_invoices", "balance_amount", "NUMERIC DEFAULT 0")
        add_column_if_missing(cursor, "accounting_invoices", "due_date", "TIMESTAMP NULL")
        add_column_if_missing(cursor, "accounting_invoices", "notes", "TEXT DEFAULT ''")
        add_column_if_missing(cursor, "accounting_invoices", "payment_method", "TEXT DEFAULT ''")
        add_column_if_missing(cursor, "accounting_invoices", "reference_number", "TEXT DEFAULT ''")
        add_column_if_missing(cursor, "accounting_invoices", "updated_at", "TIMESTAMP NOT NULL DEFAULT NOW()")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounting_expenses (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                amount NUMERIC DEFAULT 0,
                tax_amount NUMERIC DEFAULT 0,
                total_amount NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'JOD',
                category TEXT DEFAULT '',
                expense_date TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                assigned_to INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                assigned_to_id INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
                subject TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT DEFAULT 'normal',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS support_messages (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
                sender_type TEXT NOT NULL DEFAULT 'user',
                sender_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                sender_staff_id INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS internal_audit_logs (
                id SERIAL PRIMARY KEY,
                staff_user_id INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity_type TEXT DEFAULT '',
                entity_id TEXT DEFAULT '',
                before_json TEXT DEFAULT '',
                after_json TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                ip_address TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_request_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
                country TEXT DEFAULT '',
                user_role TEXT DEFAULT '',
                plan TEXT DEFAULT '',
                model_used TEXT DEFAULT '',
                request_type TEXT DEFAULT '',
                input_size INTEGER DEFAULT 0,
                status TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_search_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
                country_id INTEGER REFERENCES countries(id) ON DELETE SET NULL,
                query_text TEXT NOT NULL,
                result_count INTEGER DEFAULT 0,
                sources_json TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                id SERIAL PRIMARY KEY,
                setting_key TEXT NOT NULL UNIQUE,
                setting_value TEXT DEFAULT '',
                setting_type TEXT DEFAULT 'text',
                updated_by INTEGER REFERENCES staff_users(id) ON DELETE SET NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_analyses_case_id ON analyses(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_staff_email ON staff_users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_staff_sessions_token ON staff_sessions(token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_legal_documents_country ON legal_documents(country_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_legal_articles_country ON legal_articles(country_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_legal_articles_document ON legal_articles(document_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_legal_articles_number ON legal_articles(article_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_legal_article_relations_article ON legal_article_relations(article_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_user ON support_tickets(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_user ON ai_request_logs(user_id)")

        seed_countries(cursor)
        seed_subscription_plans(cursor)

        conn.commit()

        try:
            from app.production_schema import ensure_production_schema
            ensure_production_schema()
        except Exception:
            pass

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


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


def user_limits(plan: str = "free") -> dict:
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
        "monthly_analyses": int(row["monthly_analyses"]),
        "monthly_documents": int(row["monthly_documents"]),
        "cases": int(row["max_cases"]),
        "max_file_size_mb": int(row["max_file_size_mb"]),
        "can_upload_documents": bool(row["can_upload_documents"]),
        "can_use_case_memory": bool(row["can_use_case_memory"]),
        "can_export_pdf": bool(row["can_export_pdf"]),
        "can_export_word": bool(row["can_export_word"]),
        "can_access_advanced_analysis": bool(row["can_access_advanced_analysis"]),
        "can_use_legal_sources": bool(row["can_use_legal_sources"]),
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
        "monthly_analyses": analyses_row["count"] if analyses_row else 0,
        "monthly_documents": documents_row["count"] if documents_row else 0,
        "cases": cases_row["count"] if cases_row else 0,
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