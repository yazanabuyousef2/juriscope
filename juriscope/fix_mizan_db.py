import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

database_url = os.getenv("DATABASE_URL", "").strip()

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if not database_url:
    raise RuntimeError("DATABASE_URL غير موجود داخل ملف .env")

conn = psycopg2.connect(database_url)
cur = conn.cursor()

# إصلاح جدول القضايا القديم
case_columns = [
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS country TEXT DEFAULT ''",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_type TEXT DEFAULT ''",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS opponent_name TEXT DEFAULT ''",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS court_name TEXT DEFAULT ''",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_number TEXT DEFAULT ''",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'مفتوحة'",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT ''",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS sensitivity_level TEXT DEFAULT 'normal'",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS staff_access_requires_reason BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
    "ALTER TABLE cases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
]

for sql in case_columns:
    cur.execute(sql)

# جداول سجل التحليلات والتقييم
cur.execute("""
CREATE TABLE IF NOT EXISTS analysis_feedback (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER,
    user_id INTEGER,
    feedback TEXT NOT NULL,
    comment TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS analysis_exports (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER,
    user_id INTEGER,
    export_type TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
""")

# جداول ربط القضية بالـ Workspace
cur.execute("""
CREATE TABLE IF NOT EXISTS case_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    case_id INTEGER,
    question TEXT DEFAULT '',
    answer_json TEXT DEFAULT '',
    assistant_mode TEXT DEFAULT '',
    audience_mode TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS case_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    case_id INTEGER,
    title TEXT DEFAULT '',
    document_type TEXT DEFAULT '',
    status TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
""")

conn.commit()
cur.close()
conn.close()

print("DB MIGRATION OK - تم إصلاح قاعدة البيانات بنجاح")
