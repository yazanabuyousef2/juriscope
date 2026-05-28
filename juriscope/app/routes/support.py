from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import require_user, is_staff_mode_user
from app.db.session import SessionLocal
from app.models.staff import StaffUser
from app.models.support import SupportMessage, SupportTicket


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


TICKET_STATUSES = {
    "open": "مفتوحة",
    "pending": "بانتظار المتابعة",
    "resolved": "تم الحل",
    "closed": "مغلقة",
}


TICKET_PRIORITIES = {
    "low": "منخفضة",
    "normal": "عادية",
    "high": "عالية",
    "urgent": "عاجلة",
}


@router.get("/support", response_class=HTMLResponse)
async def support_page(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Staff Mode لا يستخدم صفحة دعم المستخدم العادي
    if is_staff_mode_user(user):
        return RedirectResponse(url="/internal/support-tickets", status_code=303)

    user_id = int(user["id"])

    db = SessionLocal()

    try:
        tickets = (
            db.query(SupportTicket)
            .filter(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.updated_at.desc())
            .all()
        )

        staff_users = db.query(StaffUser).all()
        staff_map = {staff.id: staff for staff in staff_users}

        return templates.TemplateResponse(
            request=request,
            name="support.html",
            context={
                "request": request,
                "user": user,
                "tickets": tickets,
                "staff_map": staff_map,
                "statuses": TICKET_STATUSES,
                "priorities": TICKET_PRIORITIES,
                "is_staff_mode": False,
                "is_unlimited_user": False,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/support/create")
async def support_create(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if is_staff_mode_user(user):
        return RedirectResponse(url="/internal/support-tickets", status_code=303)

    user_id = int(user["id"])

    subject = subject.strip()
    message = message.strip()

    if not subject:
        return RedirectResponse(url="/support?error=missing_subject", status_code=303)

    if not message:
        return RedirectResponse(url="/support?error=missing_message", status_code=303)

    db = SessionLocal()

    try:
        ticket = SupportTicket(
            user_id=user_id,
            assigned_to_id=None,
            case_id=None,
            subject=subject,
            status="open",
            priority="normal",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(ticket)
        db.flush()

        first_message = SupportMessage(
            ticket_id=ticket.id,
            sender_type="user",
            sender_user_id=user_id,
            sender_staff_id=None,
            message=message,
            created_at=datetime.utcnow(),
        )

        db.add(first_message)
        db.commit()

        return RedirectResponse(url="/support?success=created", status_code=303)

    finally:
        db.close()


@router.post("/support/reply")
async def support_reply(
    request: Request,
    ticket_id: int = Form(...),
    message: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if is_staff_mode_user(user):
        return RedirectResponse(url="/internal/support-tickets", status_code=303)

    user_id = int(user["id"])
    message = message.strip()

    if not message:
        return RedirectResponse(url="/support?error=missing_message", status_code=303)

    db = SessionLocal()

    try:
        ticket = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.id == ticket_id,
                SupportTicket.user_id == user_id,
            )
            .first()
        )

        if not ticket:
            return RedirectResponse(url="/support?error=ticket_not_found", status_code=303)

        if ticket.status == "closed":
            return RedirectResponse(url="/support?error=ticket_closed", status_code=303)

        reply = SupportMessage(
            ticket_id=ticket.id,
            sender_type="user",
            sender_user_id=user_id,
            sender_staff_id=None,
            message=message,
            created_at=datetime.utcnow(),
        )

        ticket.status = "open"
        ticket.updated_at = datetime.utcnow()

        db.add(reply)
        db.commit()

        return RedirectResponse(url="/support?success=replied", status_code=303)

    finally:
        db.close()


@router.post("/support/close")
async def support_close(
    request: Request,
    ticket_id: int = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if is_staff_mode_user(user):
        return RedirectResponse(url="/internal/support-tickets", status_code=303)

    user_id = int(user["id"])

    db = SessionLocal()

    try:
        ticket = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.id == ticket_id,
                SupportTicket.user_id == user_id,
            )
            .first()
        )

        if not ticket:
            return RedirectResponse(url="/support?error=ticket_not_found", status_code=303)

        ticket.status = "closed"
        ticket.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/support?success=closed", status_code=303)

    finally:
        db.close()