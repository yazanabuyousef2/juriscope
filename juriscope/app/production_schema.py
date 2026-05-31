import os
from dotenv import load_dotenv
import psycopg2


load_dotenv(dotenv_path=".env")


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if not url:
        raise RuntimeError("DATABASE_URL is missing.")

    return url


def ensure_production_schema():
    """
    Ensures required production PostgreSQL tables exist.
    This completes the production schema on Supabase/PostgreSQL.
    """

    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()

    try:
        # =========================
        # Countries
        # =========================
        cur.execute(
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

        # =========================
        # Users
        # =========================
        cur.execute(
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

        # =========================
        # User Sessions
        # =========================
        cur.execute(
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

        # Compatibility table for old code if needed
        cur.execute(
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

        # =========================
        # Cases
        # =========================
        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        # =========================
        # Staff / Internal System
        # =========================
        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        # =========================
        # Legal Data
        # =========================
        cur.execute(
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

        cur.execute(
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

        cur.execute(
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


        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_article_relations (
                id SERIAL PRIMARY KEY,
                article_id INTEGER NOT NULL REFERENCES legal_articles(id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                reference_text TEXT DEFAULT '',
                source_name TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        # =========================
        # Subscriptions / Payments
        # =========================
        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        # =========================
        # Accounting
        # =========================
        cur.execute(
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
                currency TEXT DEFAULT 'JOD',
                status TEXT DEFAULT 'draft',
                issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
                paid_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        cur.execute(
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

        # =========================
        # Support
        # =========================
        cur.execute(
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

        cur.execute(
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

        # =========================
        # Logs / Settings
        # =========================
        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        cur.execute(
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

        # =========================
        # Indexes
        # =========================
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_staff_users_email ON staff_users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_staff_sessions_token ON staff_sessions(token)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id ON support_tickets(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_legal_articles_document_id ON legal_articles(document_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_legal_articles_country_id ON legal_articles(country_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_legal_article_relations_article_id ON legal_article_relations(article_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_legal_article_relations_type ON legal_article_relations(relation_type)")

        seed_defaults(cur)

        conn.commit()
        print("✅ Production schema ensured.")

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def seed_defaults(cur):
    countries = [
        ("JO", "الأردن", "Jordan", "+962", "JOD"),
        ("SA", "السعودية", "Saudi Arabia", "+966", "SAR"),
        ("AE", "الإمارات", "United Arab Emirates", "+971", "AED"),
        ("EG", "مصر", "Egypt", "+20", "EGP"),
        ("IQ", "العراق", "Iraq", "+964", "IQD"),
        ("QA", "قطر", "Qatar", "+974", "QAR"),
        ("KW", "الكويت", "Kuwait", "+965", "KWD"),
        ("BH", "البحرين", "Bahrain", "+973", "BHD"),
        ("OM", "عُمان", "Oman", "+968", "OMR"),
    ]

    for code, name_ar, name_en, phone_code, currency in countries:
        cur.execute(
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
            VALUES (
                %s, %s, %s, %s, %s,
                TRUE,
                NOW(),
                NOW()
            )
            ON CONFLICT (code) DO UPDATE SET
                name_ar = EXCLUDED.name_ar,
                name_en = EXCLUDED.name_en,
                phone_code = EXCLUDED.phone_code,
                currency = EXCLUDED.currency,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            """
            ,
            (code, name_ar, name_en, phone_code, currency),
        )

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
        },
    ]

    for plan in plans:
        cur.execute(
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
                TRUE,
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
                is_active = TRUE,
                updated_at = NOW()
            """
            ,
            plan,
        )