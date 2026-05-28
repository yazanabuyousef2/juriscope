from datetime import datetime
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.staff import StaffSession, StaffUser


settings = get_settings()


def get_current_staff_by_token(db: Session, token: str) -> Optional[StaffUser]:
    if not token:
        return None

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

    return session.staff_user


def get_current_staff_optional(request: Request) -> Optional[StaffUser]:
    token = request.cookies.get(settings.STAFF_SESSION_COOKIE_NAME, "")

    if not token:
        return None

    db = SessionLocal()

    try:
        return get_current_staff_by_token(db, token)
    finally:
        db.close()


def require_staff(request: Request) -> Optional[StaffUser]:
    return get_current_staff_optional(request)


def staff_has_role(staff: Optional[StaffUser], allowed_roles: list[str]) -> bool:
    if not staff:
        return False

    if staff.role == "superadmin":
        return True

    return staff.role in allowed_roles


def require_internal_permission(staff: Optional[StaffUser], allowed_roles: list[str]) -> bool:
    return staff_has_role(staff, allowed_roles)