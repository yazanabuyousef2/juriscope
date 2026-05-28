from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.database import get_user_by_session

SESSION_COOKIE_NAME = "mizan_session"


def get_current_user_optional(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    return get_user_by_session(token)


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
