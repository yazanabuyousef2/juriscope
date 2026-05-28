from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InternalAuditLog(Base):
    __tablename__ = "internal_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    staff_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(255), nullable=False)

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    before_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    after_json: Mapped[str] = mapped_column(Text, nullable=False, default="")

    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ip_address: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class StaffAccessLog(Base):
    __tablename__ = "staff_access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    staff_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    access_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ip_address: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AIRequestLog(Base):
    __tablename__ = "ai_request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    country_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    user_role: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    model_used: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    request_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    input_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class LegalSearchLog(Base):
    __tablename__ = "legal_search_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    country_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    setting_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    setting_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    setting_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")

    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)