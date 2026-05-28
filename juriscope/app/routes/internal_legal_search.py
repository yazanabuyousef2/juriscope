from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional, staff_has_role
from app.models.country import Country
from app.services.legal_retrieval_service import build_sources_context, search_legal_sources


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "legal_reviewer",
    "data_entry",
    "developer",
]


def can_test_legal_search(staff) -> bool:
    return staff_has_role(staff, ALLOWED_ROLES)


@router.get("/internal/legal-search-test", response_class=HTMLResponse)
async def legal_search_test_page(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_test_legal_search(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        countries = (
            db.query(Country)
            .filter(Country.is_active == True)
            .order_by(Country.name_ar.asc())
            .all()
        )

        return templates.TemplateResponse(
            request=request,
            name="internal/legal_search_test.html",
            context={
                "request": request,
                "staff": staff,
                "countries": countries,
                "query": "",
                "selected_country_id": "",
                "approved_only": True,
                "active_only": True,
                "sources": [],
                "sources_context": "",
            },
        )

    finally:
        db.close()


@router.post("/internal/legal-search-test", response_class=HTMLResponse)
async def legal_search_test(
    request: Request,
    query: str = Form(...),
    country_id: int = Form(...),
    approved_only: str = Form("yes"),
    active_only: str = Form("yes"),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/login", status_code=303)

    if not can_test_legal_search(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        countries = (
            db.query(Country)
            .filter(Country.is_active == True)
            .order_by(Country.name_ar.asc())
            .all()
        )

        use_approved_only = approved_only == "yes"
        use_active_only = active_only == "yes"

        sources = search_legal_sources(
            db=db,
            query=query,
            country_id=country_id,
            limit=10,
            approved_only=use_approved_only,
            active_only=use_active_only,
        )

        sources_context = build_sources_context(sources)

        return templates.TemplateResponse(
            request=request,
            name="internal/legal_search_test.html",
            context={
                "request": request,
                "staff": staff,
                "countries": countries,
                "query": query,
                "selected_country_id": country_id,
                "approved_only": use_approved_only,
                "active_only": use_active_only,
                "sources": sources,
                "sources_context": sources_context,
            },
        )

    finally:
        db.close()