from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    description_ar: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description_en: Mapped[str] = mapped_column(Text, nullable=False, default="")

    price_monthly: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")

    monthly_analyses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    can_upload_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_use_case_memory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_export_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_export_word: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_access_advanced_analysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_use_legal_sources: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    # active, cancelled, expired, trial

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    period_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Example: 2026-05

    analyses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cases_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")

    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # pending, paid, failed, refunded

    raw_response: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("payment_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="issued")
    # issued, paid, cancelled

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)