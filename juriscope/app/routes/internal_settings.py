from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


OWNER_ALLOWED_ROLES = [
    "superadmin",
    "developer",
    "admin",
]


DEFAULT_SETTINGS = {
    "system_name": {
        "label": "اسم النظام",
        "value": "Mizan",
        "type": "text",
        "description": "الاسم الظاهر للنظام داخليًا وفي بعض الواجهات.",
    },
    "maintenance_mode": {
        "label": "وضع الصيانة",
        "value": "off",
        "type": "select",
        "description": "عند التفعيل يمكن لاحقًا منع دخول المستخدمين مؤقتًا.",
    },
    "maintenance_message": {
        "label": "رسالة الصيانة",
        "value": "النظام قيد الصيانة حاليًا. يرجى المحاولة لاحقًا.",
        "type": "textarea",
        "description": "الرسالة التي تظهر للمستخدمين أثناء الصيانة.",
    },
    "default_ai_model": {
        "label": "موديل الذكاء الصناعي الافتراضي",
        "value": "gemini-2.5-flash",
        "type": "text",
        "description": "اسم الموديل الافتراضي المستخدم في التحليل.",
    },
    "fallback_ai_model": {
        "label": "موديل الذكاء الصناعي الاحتياطي",
        "value": "gemini-2.0-flash",
        "type": "text",
        "description": "يستخدم عند وجود ضغط أو مشكلة في الموديل الأساسي.",
    },
    "global_max_file_size_mb": {
        "label": "أقصى حجم عام للملفات MB",
        "value": "50",
        "type": "number",
        "description": "حد عام يمكن استخدامه لاحقًا فوق حدود الباقات.",
    },
    "legal_disclaimer": {
        "label": "التنبيه القانوني العام",
        "value": "هذا التحليل أولي ومساعد ولا يُعد استشارة قانونية نهائية. يجب مراجعة محامٍ مرخص قبل اتخاذ أي إجراء قانوني.",
        "type": "textarea",
        "description": "النص العام للتنبيه القانوني في نتائج التحليل.",
    },
    "staff_unlimited_mode": {
        "label": "وضع الموظف غير المحدود",
        "value": "on",
        "type": "select",
        "description": "يسمح للموظفين باستخدام واجهة المستخدم بدون حدود باقات.",
    },
}


def can_manage_settings(staff) -> bool:
    return bool(staff and staff.role in OWNER_ALLOWED_ROLES)


def ensure_settings_table(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                id SERIAL PRIMARY KEY
            )
            """
        )
    )

    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS setting_key VARCHAR(150)"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS setting_value TEXT"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS setting_type VARCHAR(50)"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS label VARCHAR(255)"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS description TEXT"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS updated_by_staff_id INTEGER NULL"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
    db.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))

    db.execute(
        text(
            """
            UPDATE system_settings
            SET setting_type = 'text'
            WHERE setting_type IS NULL
            """
        )
    )

    db.execute(
        text(
            """
            UPDATE system_settings
            SET created_at = NOW()
            WHERE created_at IS NULL
            """
        )
    )

    db.execute(
        text(
            """
            UPDATE system_settings
            SET updated_at = NOW()
            WHERE updated_at IS NULL
            """
        )
    )

    db.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'system_settings_setting_key_unique'
                ) THEN
                    ALTER TABLE system_settings
                    ADD CONSTRAINT system_settings_setting_key_unique UNIQUE (setting_key);
                END IF;
            END $$;
            """
        )
    )

    db.commit()


def seed_default_settings(db):
    for key, data in DEFAULT_SETTINGS.items():
        existing = db.execute(
            text(
                """
                SELECT id
                FROM system_settings
                WHERE setting_key = :setting_key
                """
            ),
            {"setting_key": key},
        ).first()

        if existing:
            db.execute(
                text(
                    """
                    UPDATE system_settings
                    SET
                        setting_type = COALESCE(setting_type, :setting_type),
                        label = COALESCE(label, :label),
                        description = COALESCE(description, :description),
                        updated_at = COALESCE(updated_at, :updated_at),
                        created_at = COALESCE(created_at, :created_at)
                    WHERE setting_key = :setting_key
                    """
                ),
                {
                    "setting_key": key,
                    "setting_type": data["type"],
                    "label": data["label"],
                    "description": data["description"],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            )
            continue

        db.execute(
            text(
                """
                INSERT INTO system_settings (
                    setting_key,
                    setting_value,
                    setting_type,
                    label,
                    description,
                    created_at,
                    updated_at
                )
                VALUES (
                    :setting_key,
                    :setting_value,
                    :setting_type,
                    :label,
                    :description,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "setting_key": key,
                "setting_value": data["value"],
                "setting_type": data["type"],
                "label": data["label"],
                "description": data["description"],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )

    db.commit()


def get_all_settings(db):
    rows = db.execute(
        text(
            """
            SELECT
                id,
                setting_key,
                setting_value,
                setting_type,
                label,
                description,
                updated_by_staff_id,
                created_at,
                updated_at
            FROM system_settings
            ORDER BY id ASC
            """
        )
    ).mappings().all()

    return [dict(row) for row in rows]


@router.get("/internal/settings", response_class=HTMLResponse)
async def internal_settings_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_settings(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        ensure_settings_table(db)
        seed_default_settings(db)
        settings = get_all_settings(db)

        return templates.TemplateResponse(
            request=request,
            name="internal/settings.html",
            context={
                "request": request,
                "staff": staff,
                "settings": settings,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/settings/update")
async def internal_settings_update(
    request: Request,
    setting_key: str = Form(...),
    setting_value: str = Form(""),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_settings(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    setting_key = setting_key.strip()
    setting_value = setting_value.strip()

    db = SessionLocal()

    try:
        ensure_settings_table(db)

        existing = db.execute(
            text(
                """
                SELECT id
                FROM system_settings
                WHERE setting_key = :setting_key
                """
            ),
            {"setting_key": setting_key},
        ).first()

        if not existing:
            return RedirectResponse(url="/internal/settings?error=setting_not_found", status_code=303)

        db.execute(
            text(
                """
                UPDATE system_settings
                SET
                    setting_value = :setting_value,
                    updated_by_staff_id = :updated_by_staff_id,
                    updated_at = :updated_at
                WHERE setting_key = :setting_key
                """
            ),
            {
                "setting_key": setting_key,
                "setting_value": setting_value,
                "updated_by_staff_id": staff.id,
                "updated_at": datetime.utcnow(),
            },
        )

        db.commit()

        return RedirectResponse(url="/internal/settings?success=updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/settings/reset-defaults")
async def internal_settings_reset_defaults(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if staff.role != "superadmin":
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        ensure_settings_table(db)

        for key, data in DEFAULT_SETTINGS.items():
            existing = db.execute(
                text(
                    """
                    SELECT id
                    FROM system_settings
                    WHERE setting_key = :setting_key
                    """
                ),
                {"setting_key": key},
            ).first()

            if existing:
                db.execute(
                    text(
                        """
                        UPDATE system_settings
                        SET
                            setting_value = :setting_value,
                            setting_type = :setting_type,
                            label = :label,
                            description = :description,
                            updated_by_staff_id = :updated_by_staff_id,
                            updated_at = :updated_at
                        WHERE setting_key = :setting_key
                        """
                    ),
                    {
                        "setting_key": key,
                        "setting_value": data["value"],
                        "setting_type": data["type"],
                        "label": data["label"],
                        "description": data["description"],
                        "updated_by_staff_id": staff.id,
                        "updated_at": datetime.utcnow(),
                    },
                )
            else:
                db.execute(
                    text(
                        """
                        INSERT INTO system_settings (
                            setting_key,
                            setting_value,
                            setting_type,
                            label,
                            description,
                            updated_by_staff_id,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            :setting_key,
                            :setting_value,
                            :setting_type,
                            :label,
                            :description,
                            :updated_by_staff_id,
                            :created_at,
                            :updated_at
                        )
                        """
                    ),
                    {
                        "setting_key": key,
                        "setting_value": data["value"],
                        "setting_type": data["type"],
                        "label": data["label"],
                        "description": data["description"],
                        "updated_by_staff_id": staff.id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    },
                )

        db.commit()

        return RedirectResponse(url="/internal/settings?success=reset", status_code=303)

    finally:
        db.close()