from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.staff import StaffUser
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "customer_service",
]


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


def can_manage_support(staff) -> bool:
    return staff_has_role(staff, ALLOWED_ROLES)


@router.get("/internal/support-tickets", response_class=HTMLResponse)
async def support_tickets_index(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_support(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    status_filter = request.query_params.get("status", "").strip()
    priority_filter = request.query_params.get("priority", "").strip()
    search = request.query_params.get("search", "").strip()

    db = SessionLocal()

    try:
        query = db.query(SupportTicket)

        if status_filter:
            query = query.filter(SupportTicket.status == status_filter)

        if priority_filter:
            query = query.filter(SupportTicket.priority == priority_filter)

        if search:
            like_value = f"%{search}%"
            query = query.filter(SupportTicket.subject.ilike(like_value))

        tickets = (
            query
            .order_by(SupportTicket.updated_at.desc())
            .limit(300)
            .all()
        )

        users = db.query(User).all()
        staff_users = db.query(StaffUser).all()

        user_map = {user.id: user for user in users}
        staff_map = {staff_user.id: staff_user for staff_user in staff_users}

        stats = {
            "open": db.query(SupportTicket).filter(SupportTicket.status == "open").count(),
            "pending": db.query(SupportTicket).filter(SupportTicket.status == "pending").count(),
            "resolved": db.query(SupportTicket).filter(SupportTicket.status == "resolved").count(),
            "closed": db.query(SupportTicket).filter(SupportTicket.status == "closed").count(),
            "urgent": db.query(SupportTicket).filter(SupportTicket.priority == "urgent").count(),
        }

        return templates.TemplateResponse(
            request=request,
            name="internal/support_tickets.html",
            context={
                "request": request,
                "staff": staff,
                "tickets": tickets,
                "user_map": user_map,
                "staff_map": staff_map,
                "statuses": TICKET_STATUSES,
                "priorities": TICKET_PRIORITIES,
                "status_filter": status_filter,
                "priority_filter": priority_filter,
                "search": search,
                "stats": stats,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/support-tickets/update")
async def support_ticket_update(
    request: Request,
    ticket_id: int = Form(...),
    status: str = Form(...),
    priority: str = Form(...),
    assigned_to_me: str = Form("no"),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_support(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    status = status.strip()
    priority = priority.strip()

    if status not in TICKET_STATUSES:
        return RedirectResponse(url="/internal/support-tickets?error=invalid_status", status_code=303)

    if priority not in TICKET_PRIORITIES:
        return RedirectResponse(url="/internal/support-tickets?error=invalid_priority", status_code=303)

    db = SessionLocal()

    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            return RedirectResponse(url="/internal/support-tickets?error=ticket_not_found", status_code=303)

        ticket.status = status
        ticket.priority = priority
        ticket.updated_at = datetime.utcnow()

        if assigned_to_me == "yes":
            ticket.assigned_to_id = staff.id

        db.commit()

        return RedirectResponse(url="/internal/support-tickets?success=updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/support-tickets/reply")
async def support_ticket_reply(
    request: Request,
    ticket_id: int = Form(...),
    message: str = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_support(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    message = message.strip()

    if not message:
        return RedirectResponse(url="/internal/support-tickets?error=empty_message", status_code=303)

    db = SessionLocal()

    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            return RedirectResponse(url="/internal/support-tickets?error=ticket_not_found", status_code=303)

        reply = SupportMessage(
            ticket_id=ticket.id,
            sender_type="staff",
            sender_staff_id=staff.id,
            sender_user_id=None,
            message=message,
            created_at=datetime.utcnow(),
        )

        ticket.assigned_to_id = staff.id
        ticket.status = "pending" if ticket.status == "open" else ticket.status
        ticket.updated_at = datetime.utcnow()

        db.add(reply)
        db.commit()

        return RedirectResponse(url="/internal/support-tickets?success=replied", status_code=303)

    finally:
        db.close()


@router.post("/internal/support-tickets/close")
async def support_ticket_close(
    request: Request,
    ticket_id: int = Form(...),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_manage_support(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()

        if not ticket:
            return RedirectResponse(url="/internal/support-tickets?error=ticket_not_found", status_code=303)

        ticket.status = "closed"
        ticket.assigned_to_id = staff.id
        ticket.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/internal/support-tickets?success=closed", status_code=303)

    finally:
        db.close()