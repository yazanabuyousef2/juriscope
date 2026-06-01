"""Actor identity utilities.

This module solves a real ownership problem in Mizan:
case/workspace tables are owned by ``users.id`` through a foreign key, while
staff sessions are stored in ``staff_users`` and are exposed to the UI as
``id=None``.  The previous workaround used negative user ids, which correctly
failed once the database enforced foreign keys.

The professional solution is to resolve every actor that creates user-owned
records to a real row in ``public.users``:
- normal users keep their existing ``users.id``;
- staff users get a deterministic shadow user account in ``public.users``;
- local/dev sessions without an id get a deterministic local shadow user.

This keeps database integrity, avoids NULL/negative ids, and lets all existing
case, analysis, document, and workspace queries continue to use ``user_id``.
"""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from typing import Any

import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")


@lru_cache(maxsize=1)
def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL is missing.")
    return url


def _connect():
    return psycopg2.connect(_database_url())


def _get_public_user_columns(cur) -> list[tuple[str, str, str, str | None]]:
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
        ORDER BY ordinal_position
        """
    )
    columns = cur.fetchall()
    if not columns:
        raise RuntimeError("public.users table does not exist.")
    return columns


def _actor_email(user: dict[str, Any]) -> str:
    user_id = user.get("id")
    if user_id is not None:
        # Normal users should already exist; this is only a defensive fallback.
        return str(user.get("email") or f"user-{user_id}@mizan.local").strip().lower()

    staff_id = user.get("staff_id")
    if staff_id is not None:
        return f"staff-{int(staff_id)}@mizan.local"

    return "local-workspace@mizan.local"


def _actor_name(user: dict[str, Any]) -> str:
    return str(user.get("full_name") or user.get("name") or "Mizan Local User").strip()


def _actor_role(user: dict[str, Any]) -> str:
    return str(user.get("user_role") or user.get("staff_role") or "individual").strip()


def _actor_plan(user: dict[str, Any]) -> str:
    return str(user.get("plan_code") or user.get("plan") or "free").strip()


def _value_for_column(column_name: str, data_type: str, user: dict[str, Any], now: datetime):
    name = column_name.lower()

    if "created_at" in name or "updated_at" in name or name in {"created", "updated"}:
        return now
    if name == "email" or "email" in name:
        return _actor_email(user)
    if "username" in name:
        # Keep deterministic and readable.
        return _actor_email(user).split("@")[0].replace(".", "_").replace("-", "_")
    if name in {"full_name", "display_name", "name"} or "full_name" in name:
        return _actor_name(user)
    if "password" in name or "hash" in name:
        return "local-shadow-account-not-for-login"
    if name in {"country", "country_name"} or "country_name" in name:
        return str(user.get("country_name") or user.get("country") or "الأردن")
    if name == "country_code" or "country_code" in name:
        return str(user.get("country_code") or "JO")
    if name == "phone_country_code" or "phone_country_code" in name:
        return str(user.get("phone_country_code") or "+962")
    if name == "phone" or name.endswith("_phone"):
        return str(user.get("phone") or "")
    if name == "phone_verified":
        return True
    if name in {"user_role", "role"}:
        return _actor_role(user)
    if name in {"plan", "plan_code"}:
        return _actor_plan(user)
    if name in {"account_type", "user_type", "type"}:
        return "staff_shadow" if user.get("staff_id") is not None else "local"
    if name == "status" or name.endswith("_status"):
        return "active"
    if name == "is_active":
        return True
    if data_type == "boolean":
        return False
    if data_type in {"integer", "bigint", "smallint"}:
        return 0
    if "timestamp" in data_type or data_type == "date":
        return now
    return ""


def ensure_shadow_user(user: dict[str, Any]) -> int:
    """Return a real ``public.users.id`` for staff/local actors."""
    email = _actor_email(user)
    now = datetime.utcnow()

    conn = _connect()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id FROM public.users WHERE lower(email) = lower(%s) LIMIT 1", (email,))
        existing = cur.fetchone()
        if existing:
            return int(existing[0])

        columns = _get_public_user_columns(cur)
        real_columns = {row[0] for row in columns}
        values_by_column: dict[str, Any] = {}

        for column_name, data_type, is_nullable, column_default in columns:
            name = column_name.lower()

            if name == "id":
                continue

            must_fill = is_nullable == "NO" and column_default is None
            useful_fill = any(
                key in name
                for key in [
                    "email",
                    "username",
                    "full_name",
                    "display_name",
                    "name",
                    "password",
                    "hash",
                    "country",
                    "phone",
                    "role",
                    "plan",
                    "type",
                    "status",
                    "active",
                    "created_at",
                    "updated_at",
                    "created",
                    "updated",
                ]
            )

            if not must_fill and not useful_fill:
                continue

            if column_name in real_columns:
                values_by_column[column_name] = _value_for_column(column_name, data_type, user, now)

        if "email" in real_columns:
            values_by_column["email"] = email

        if not values_by_column:
            raise RuntimeError("Unable to build a valid users insert payload.")

        insert_columns = list(values_by_column.keys())
        insert_values = [values_by_column[col] for col in insert_columns]
        quoted_columns = ", ".join([f'"{col}"' for col in insert_columns])
        placeholders = ", ".join(["%s"] * len(insert_values))

        cur.execute(
            f"""
            INSERT INTO public.users ({quoted_columns})
            VALUES ({placeholders})
            RETURNING id
            """,
            insert_values,
        )
        user_id = int(cur.fetchone()[0])
        conn.commit()
        return user_id

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def get_effective_user_id(user: dict[str, Any]) -> int:
    """Return the real database owner id for the current actor.

    This function deliberately never returns NULL, 0, or a negative id.
    """
    if not user:
        raise RuntimeError("Authenticated user is required.")

    raw_user_id = user.get("id")
    if raw_user_id is not None:
        return int(raw_user_id)

    return ensure_shadow_user(user)
