from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.user import User, UserSession
from app.internal_dependencies import get_current_staff_optional


settings = get_settings()


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,

        # aliases for old code compatibility
        "country": user.country_name,
        "country_code": user.country_code,
        "country_name": user.country_name,

        "phone": user.phone,
        "phone_country_code": user.phone_country_code,
        "phone_verified": user.phone_verified,

        "user_role": user.user_role,

        # old code expects user["plan"]
        "plan": user.plan_code,
        "plan_code": user.plan_code,

        "is_active": user.is_active,
        "created_at": user.created_at,

        # session mode
        "is_staff_mode": False,
        "staff_id": None,
        "staff_role": None,
        "is_unlimited": False,
    }


def staff_to_user_mode_dict(staff) -> dict:
    """
    هذا يحوّل حساب الموظف إلى شكل يشبه user dict
    حتى يستطيع دخول واجهة المستخدم بدون إنشاء حساب مستخدم عادي.
    """

    return {
        # لا تستخدم هذا كـ user_id حقيقي داخل جداول المستخدمين
        "id": None,

        "full_name": staff.full_name,
        "email": staff.email,

        # الدولة الافتراضية لوضع الموظف الداخلي
        "country": "الأردن",
        "country_code": "JO",
        "country_name": "الأردن",

        "phone": "",
        "phone_country_code": "",
        "phone_verified": True,

        # شخصية الرد الافتراضية للموظف
        "user_role": "legal_researcher",

        # وضع داخلي غير محدود وليس باقة تجارية
        "plan": "staff_unlimited",
        "plan_code": "staff_unlimited",

        "is_active": staff.is_active,
        "created_at": staff.created_at,

        # staff mode flags
        "is_staff_mode": True,
        "staff_id": staff.id,
        "staff_role": staff.role,
        "is_unlimited": True,
    }


def get_current_user_by_token(db: Session, token: str) -> Optional[dict]:
    if not token:
        return None

    session = (
        db.query(UserSession)
        .join(User, User.id == UserSession.user_id)
        .filter(
            UserSession.token == token,
            UserSession.expires_at > datetime.utcnow(),
            User.is_active == True,
        )
        .first()
    )

    if not session:
        return None

    return user_to_dict(session.user)


def get_current_user_optional(request: Request):
    """
    يحاول أولًا قراءة جلسة المستخدم العادي.
    إذا لم يجد مستخدمًا، يحاول قراءة جلسة الموظف.
    """

    token = request.cookies.get(settings.SESSION_COOKIE_NAME, "")

    if token:
        db = SessionLocal()

        try:
            user = get_current_user_by_token(db, token)

            if user:
                return user
        finally:
            db.close()

    staff = get_current_staff_optional(request)

    if staff and staff.is_active:
        return staff_to_user_mode_dict(staff)

    return None


def require_user(request: Request):
    return get_current_user_optional(request)


def is_staff_mode_user(user: Optional[dict]) -> bool:
    return bool(user and user.get("is_staff_mode") is True)


def is_unlimited_user(user: Optional[dict]) -> bool:
    return bool(user and user.get("is_unlimited") is True)