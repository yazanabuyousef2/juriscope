from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class StaffUser(Base):
    __tablename__ = "staff_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    role: Mapped[str] = mapped_column(String(50), nullable=False, default="customer_service")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    sessions: Mapped[list["StaffSession"]] = relationship(
        back_populates="staff_user",
        cascade="all, delete-orphan",
    )


class StaffSession(Base):
    __tablename__ = "staff_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    staff_user_id: Mapped[int] = mapped_column(
        ForeignKey("staff_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(hours=8),
    )

    staff_user: Mapped["StaffUser"] = relationship(back_populates="sessions")


class StaffPermission(Base):
    __tablename__ = "staff_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    role: Mapped[str] = mapped_column(String(50), nullable=False)
    permission_key: Mapped[str] = mapped_column(String(100), nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("role", "permission_key", name="uq_staff_role_permission"),
    )