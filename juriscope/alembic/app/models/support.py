from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    case_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    subject: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    # open, pending, resolved, closed

    priority: Mapped[str] = mapped_column(String(50), nullable=False, default="normal")
    # low, normal, high, urgent

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    messages: Mapped[list["SupportMessage"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender_type: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    # user, staff, system

    sender_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    sender_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")