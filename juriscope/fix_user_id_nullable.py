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

# السماح بإنشاء قضية بدون user_id أثناء التشغيل المحلي
cur.execute("""
ALTER TABLE cases
ALTER COLUMN user_id DROP NOT NULL
""")

# احتياطًا: السماح للجداول المرتبطة بالقضية أن تقبل user_id فارغ محليًا
cur.execute("""
ALTER TABLE case_messages
ALTER COLUMN user_id DROP NOT NULL
""")

cur.execute("""
ALTER TABLE case_documents
ALTER COLUMN user_id DROP NOT NULL
""")

conn.commit()
cur.close()
conn.close()

print("USER_ID FIX OK - تم السماح بتجربة القضايا محليًا بدون user_id")
