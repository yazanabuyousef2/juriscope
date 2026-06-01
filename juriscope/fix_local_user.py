import os
from datetime import datetime
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

cur.execute("""
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position
""")

columns = cur.fetchall()

if not columns:
    raise RuntimeError("جدول users غير موجود")

cur.execute("SELECT id FROM users WHERE id = -1")
existing = cur.fetchone()

if existing:
    print("LOCAL USER EXISTS - المستخدم المحلي موجود مسبقًا")
else:
    now = datetime.utcnow()

    values_by_column = {}

    for column_name, data_type, is_nullable, column_default in columns:
        name = column_name.lower()

        if name == "id":
            values_by_column[column_name] = -1
            continue

        must_fill = is_nullable == "NO" and column_default is None

        useful_fill = any(key in name for key in [
            "email",
            "username",
            "full_name",
            "display_name",
            "name",
            "password",
            "hash",
            "role",
            "type",
            "status",
            "created_at",
            "updated_at",
            "created",
            "updated",
        ])

        if not must_fill and not useful_fill:
            continue

        if "created_at" in name or "updated_at" in name or name in ["created", "updated"]:
            values_by_column[column_name] = now
        elif "email" in name:
            values_by_column[column_name] = "local@mizan.test"
        elif "username" in name:
            values_by_column[column_name] = "local_mizan_user"
        elif "full_name" in name or "display_name" in name or name == "name":
            values_by_column[column_name] = "Local Mizan User"
        elif "password" in name or "hash" in name:
            values_by_column[column_name] = "local-dev-password"
        elif "role" in name:
            values_by_column[column_name] = "staff"
        elif "type" in name:
            values_by_column[column_name] = "local"
        elif "status" in name:
            values_by_column[column_name] = "active"
        elif data_type in ("integer", "bigint", "smallint"):
            values_by_column[column_name] = 0
        elif data_type == "boolean":
            values_by_column[column_name] = False
        elif "timestamp" in data_type or data_type == "date":
            values_by_column[column_name] = now
        else:
            values_by_column[column_name] = "local"

    insert_columns = list(values_by_column.keys())
    insert_values = [values_by_column[col] for col in insert_columns]

    placeholders = ", ".join(["%s"] * len(insert_values))
    quoted_columns = ", ".join([f'"{col}"' for col in insert_columns])

    sql = f"""
    INSERT INTO users ({quoted_columns})
    OVERRIDING SYSTEM VALUE
    VALUES ({placeholders})
    """

    cur.execute(sql, insert_values)
    conn.commit()

    print("LOCAL USER CREATED - تم إنشاء مستخدم محلي id=-1")

# اربط أي قضايا قديمة بدون user_id بالمستخدم المحلي
cur.execute("""
UPDATE cases
SET user_id = -1
WHERE user_id IS NULL
""")

conn.commit()

cur.close()
conn.close()

print("LOCAL USER FIX OK")
