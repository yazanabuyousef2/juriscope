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

# الأعمدة التي يستخدمها كود النسخة الجديدة عند إنشاء قضية
new_insert_columns = {
    "user_id",
    "title",
    "country",
    "case_type",
    "opponent_name",
    "court_name",
    "case_number",
    "status",
    "summary",
    "created_at",
    "updated_at",
}

# تأكد من وجود الأعمدة الجديدة المطلوبة
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS country TEXT DEFAULT ''")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_type TEXT DEFAULT ''")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS opponent_name TEXT DEFAULT ''")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS court_name TEXT DEFAULT ''")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_number TEXT DEFAULT ''")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'مفتوحة'")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT ''")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
cur.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")

# إصلاح country_code القديم إن كان موجودًا
cur.execute("""
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'cases'
  AND column_name = 'country_code'
""")

if cur.fetchone():
    cur.execute("UPDATE cases SET country_code = 'JO' WHERE country_code IS NULL")
    cur.execute("ALTER TABLE cases ALTER COLUMN country_code SET DEFAULT 'JO'")
    cur.execute("ALTER TABLE cases ALTER COLUMN country_code DROP NOT NULL")

# السماح بتجربة محلية بدون user_id
cur.execute("""
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'cases'
  AND column_name = 'user_id'
""")

if cur.fetchone():
    cur.execute("ALTER TABLE cases ALTER COLUMN user_id DROP NOT NULL")

# أي عمود قديم إجباري ولا يدخل في INSERT الجديد نخليه قابل للفراغ حتى لا يكسر التشغيل المحلي
cur.execute("""
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'cases'
  AND is_nullable = 'NO'
  AND column_default IS NULL
""")

required_columns_without_defaults = [row[0] for row in cur.fetchall()]

for column in required_columns_without_defaults:
    if column not in new_insert_columns and column != "id":
        print(f"Dropping NOT NULL from legacy column: {column}")
        cur.execute(f'ALTER TABLE cases ALTER COLUMN "{column}" DROP NOT NULL')

# تأكد من جداول الـ Workspace وClaude
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

print("CASES LEGACY FIX OK - تم إصلاح جدول القضايا القديم بنجاح")
