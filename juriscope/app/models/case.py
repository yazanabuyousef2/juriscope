from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="JO")
    country_name: Mapped[str] = mapped_column(String(100), nullable=False, default="الأردن")

    case_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    opponent_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    court_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    case_number: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    sensitivity_level: Mapped[str] = mapped_column(String(50), nullable=False, default="normal")
    staff_access_requires_reason: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="cases")

    notes: Mapped[list["CaseNote"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )

    updates: Mapped[list["CaseUpdate"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    case: Mapped["Case"] = relationship(back_populates="notes")


class CaseUpdate(Base):
    __tablename__ = "case_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    update_text: Mapped[str] = mapped_column(Text, nullable=False)
    hearing_date: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    case: Mapped["Case"] = relationship(back_populates="updates")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_json: Mapped[str] = mapped_column(Text, nullable=False)

    country_code: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    country_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    case_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    user_role: Mapped[str] = mapped_column(String(50), nullable=False, default="individual")

    model_used: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence_level: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    case: Mapped[Optional["Case"]] = relationship(back_populates="analyses")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    analysis_json: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    case: Mapped[Optional["Case"]] = relationship(back_populates="documents")