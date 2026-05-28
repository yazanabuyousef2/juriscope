from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="JO")
    country_name: Mapped[str] = mapped_column(String(100), nullable=False, default="الأردن")

    phone_country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="+962")
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user_role: Mapped[str] = mapped_column(String(50), nullable=False, default="individual")
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="free")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    accepted_terms_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_privacy_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    legal_disclaimer_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    cases: Mapped[list["Case"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(days=14),
    )

    user: Mapped["User"] = relationship(back_populates="sessions")