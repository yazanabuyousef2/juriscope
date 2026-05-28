from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.database import get_user_by_session
from app.db.session import SessionLocal
from app.models.staff import StaffSession, StaffUser


settings = get_settings()
SESSION_COOKIE_NAME = settings.SESSION_COOKIE_NAME


def staff_to_user_dict(staff: StaffUser) -> dict:
    return {
        "id": None,
        "staff_id": staff.id,
        "full_name": staff.full_name,
        "email": staff.email,
        "country": "الأردن",
        "country_code": "JO",
        "country_name": "الأردن",
        "phone": "",
        "phone_country_code": "+962",
        "phone_verified": True,
        "user_role": "lawyer" if staff.role in ["superadmin", "admin", "legal_reviewer", "developer"] else "individual",
        "plan": "staff_unlimited",
        "plan_code": "staff_unlimited",
        "is_active": True,
        "is_staff_mode": True,
        "session_mode": "staff_unlimited",
        "staff_role": staff.role,
        "created_at": staff.created_at,
    }


def get_current_staff_as_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(settings.STAFF_SESSION_COOKIE_NAME, "")

    if not token:
        return None

    db = SessionLocal()

    try:
        session = (
            db.query(StaffSession)
            .join(StaffUser, StaffUser.id == StaffSession.staff_user_id)
            .filter(
                StaffSession.token == token,
                StaffSession.expires_at > datetime.utcnow(),
                StaffUser.is_active == True,
            )
            .first()
        )

        if not session:
            return None

        return staff_to_user_dict(session.staff_user)

    finally:
        db.close()


def normalize_user_dict(user_row) -> dict:
    data = dict(user_row)

    # توافق بين قواعد البيانات القديمة والجديدة.
    plan_code = data.get("plan_code") or data.get("plan") or "free"
    data["plan"] = plan_code
    data["plan_code"] = plan_code

    data["user_role"] = data.get("user_role") or "individual"
    data["country"] = data.get("country_name") or data.get("country") or "الأردن"
    data["country_name"] = data.get("country_name") or data.get("country") or "الأردن"
    data["country_code"] = data.get("country_code") or "JO"

    return data


def get_current_user_optional(request: Request) -> Optional[dict]:
    # أولًا المستخدم العادي.
    token = request.cookies.get(SESSION_COOKIE_NAME, "")

    user = get_user_by_session(token)
    if user:
        return normalize_user_dict(user)

    # إذا لا توجد جلسة مستخدم، نسمح للموظف باستخدام واجهة المستخدم بصلاحية Staff Unlimited.
    return get_current_staff_as_user(request)


def require_user(request: Request) -> dict:
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="يرجى تسجيل الدخول لاستخدام هذه الخدمة.")
    return user


def redirect_if_not_logged_in(request: Request):
    user = get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return None


def is_staff_mode_user(user: dict | None) -> bool:
    if not user:
        return False
    return bool(user.get("is_staff_mode") or user.get("session_mode") == "staff_unlimited" or user.get("plan") == "staff_unlimited")


def is_unlimited_user(user: dict | None) -> bool:
    if not user:
        return False
    if is_staff_mode_user(user):
        return True
    return (user.get("plan") or user.get("plan_code") or "") in ["enterprise", "staff_unlimited"]
