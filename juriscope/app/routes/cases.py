from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import require_user
from app.database import (
    can_create_case,
    execute,
    fetch_all,
    fetch_one,
    now_iso,
    user_limits,
    user_usage,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def build_context(request: Request, user, extra: dict | None = None):
    raw_usage = user_usage(user["id"])
    raw_limits = user_limits(user["plan"])

    data = {
        "request": request,
        "user": user,
        "usage": {
            "analyses": raw_usage.get("monthly_analyses", 0),
            "documents": raw_usage.get("monthly_documents", 0),
            "cases": raw_usage.get("cases", 0),
        },
        "limits": {
            "analyses_per_month": raw_limits.get("monthly_analyses", 3),
            "documents_per_month": raw_limits.get("monthly_documents", 1),
            "cases": raw_limits.get("cases", 1),
        },
    }

    if extra:
        data.update(extra)

    return data


@router.get("/cases", response_class=HTMLResponse)
async def cases_list(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    cases = fetch_all(
        """
        SELECT id, title, country, case_type, opponent_name, court_name, case_number, status, updated_at
        FROM cases
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (user["id"],),
    )

    return templates.TemplateResponse(
        request=request,
        name="cases.html",
        context=build_context(
            request,
            user,
            {
                "cases": cases,
            },
        ),
    )


@router.get("/cases/new", response_class=HTMLResponse)
async def new_case_page(request: Request):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    allowed, msg = can_create_case(user["id"], user["plan"])

    return templates.TemplateResponse(
        request=request,
        name="case_new.html",
        context=build_context(
            request,
            user,
            {
                "allowed": allowed,
                "error": msg if not allowed else "",
            },
        ),
    )


@router.post("/cases/new", response_class=HTMLResponse)
async def create_case(
    request: Request,
    title: str = Form(...),
    country: str = Form(""),
    case_type: str = Form(""),
    opponent_name: str = Form(""),
    court_name: str = Form(""),
    case_number: str = Form(""),
    status: str = Form("مفتوحة"),
    summary: str = Form(""),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    allowed, msg = can_create_case(user["id"], user["plan"])

    if not allowed:
        return templates.TemplateResponse(
            request=request,
            name="case_new.html",
            context=build_context(
                request,
                user,
                {
                    "allowed": False,
                    "error": msg,
                },
            ),
        )

    now = now_iso()

    case_id = execute(
        """
        INSERT INTO cases (
            user_id, title, country, case_type, opponent_name, court_name,
            case_number, status, summary, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"],
            title.strip(),
            country.strip(),
            case_type.strip(),
            opponent_name.strip(),
            court_name.strip(),
            case_number.strip(),
            status.strip(),
            summary.strip(),
            now,
            now,
        ),
    )

    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)


@router.get("/cases/{case_id}", response_class=HTMLResponse)
async def case_detail(request: Request, case_id: int):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    case = fetch_one(
        """
        SELECT *
        FROM cases
        WHERE id = ?
        AND user_id = ?
        """,
        (case_id, user["id"]),
    )

    if not case:
        return RedirectResponse(url="/cases", status_code=303)

    analyses = fetch_all(
        """
        SELECT *
        FROM analyses
        WHERE case_id = ?
        AND user_id = ?
        ORDER BY created_at DESC
        """,
        (case_id, user["id"]),
    )

    documents = fetch_all(
        """
        SELECT *
        FROM documents
        WHERE case_id = ?
        AND user_id = ?
        ORDER BY created_at DESC
        """,
        (case_id, user["id"]),
    )

    notes = fetch_all(
        """
        SELECT *
        FROM case_notes
        WHERE case_id = ?
        AND user_id = ?
        ORDER BY created_at DESC
        """,
        (case_id, user["id"]),
    )

    updates = fetch_all(
        """
        SELECT *
        FROM case_updates
        WHERE case_id = ?
        AND user_id = ?
        ORDER BY created_at DESC
        """,
        (case_id, user["id"]),
    )

    return templates.TemplateResponse(
        request=request,
        name="case_detail.html",
        context=build_context(
            request,
            user,
            {
                "case": case,
                "analyses": analyses,
                "documents": documents,
                "notes": notes,
                "updates": updates,
            },
        ),
    )


@router.post("/cases/{case_id}/notes")
async def add_case_note(
    request: Request,
    case_id: int,
    note: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    case = fetch_one(
        "SELECT id FROM cases WHERE id = ? AND user_id = ?",
        (case_id, user["id"]),
    )

    if not case:
        return RedirectResponse(url="/cases", status_code=303)

    execute(
        """
        INSERT INTO case_notes (user_id, case_id, note, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user["id"], case_id, note.strip(), now_iso()),
    )

    execute(
        "UPDATE cases SET updated_at = ? WHERE id = ? AND user_id = ?",
        (now_iso(), case_id, user["id"]),
    )

    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)


@router.post("/cases/{case_id}/updates")
async def add_case_update(
    request: Request,
    case_id: int,
    update_text: str = Form(...),
    hearing_date: str = Form(""),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    case = fetch_one(
        "SELECT id FROM cases WHERE id = ? AND user_id = ?",
        (case_id, user["id"]),
    )

    if not case:
        return RedirectResponse(url="/cases", status_code=303)

    execute(
        """
        INSERT INTO case_updates (user_id, case_id, update_text, hearing_date, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user["id"], case_id, update_text.strip(), hearing_date.strip(), now_iso()),
    )

    execute(
        "UPDATE cases SET updated_at = ? WHERE id = ? AND user_id = ?",
        (now_iso(), case_id, user["id"]),
    )

    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)