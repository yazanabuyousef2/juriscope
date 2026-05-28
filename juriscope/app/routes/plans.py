from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth.dependencies import require_user
from app.database import execute


router = APIRouter()


ALLOWED_PLANS = {
    "free": "المجانية",
    "individual": "الأفراد",
    "business": "الأعمال والشركات",
    "lawyer": "المحامين",
}


@router.get("/pricing/select-plan")
async def select_plan_get():
    return RedirectResponse(url="/pricing", status_code=303)


@router.get("/profile/plan")
async def update_plan_get():
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/plan")
async def update_plan(
    request: Request,
    plan: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if plan not in ALLOWED_PLANS:
        return RedirectResponse(url="/profile?error=invalid_plan", status_code=303)

    execute(
        "UPDATE users SET plan = ? WHERE id = ?",
        (plan, user["id"]),
    )

    return RedirectResponse(url="/profile?plan_updated=1", status_code=303)


@router.post("/pricing/select-plan")
async def select_plan_from_pricing(
    request: Request,
    plan: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if plan not in ALLOWED_PLANS:
        return RedirectResponse(url="/pricing?error=invalid_plan", status_code=303)

    execute(
        "UPDATE users SET plan = ? WHERE id = ?",
        (plan, user["id"]),
    )

    return RedirectResponse(url="/profile?plan_updated=1", status_code=303)