from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth.dependencies import is_staff_mode_user, require_user
from app.database import execute


router = APIRouter()


# الباقات هنا اشتراكات فقط، وليست نوع مستخدم.
# نوع المستخدم يبقى في user_role ويؤثر على أسلوب الرد فقط.
# الاشتراك يؤثر على الحدود والصلاحيات.
ALLOWED_PLANS = {
    "free": "المجانية",
    "basic": "Basic",
    "pro": "Pro",
    "premium": "Premium",
    "enterprise": "Enterprise",
}


@router.get("/pricing/select-plan")
async def select_plan_get():
    return RedirectResponse(url="/pricing", status_code=303)


@router.get("/profile/plan")
async def update_plan_get():
    return RedirectResponse(url="/profile", status_code=303)


def normalize_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()
    return plan if plan in ALLOWED_PLANS else ""


def update_user_plan(user_id: int, plan_code: str):
    # ندعم النسخ القديمة التي فيها plan، والنسخ الجديدة التي فيها plan_code.
    # إذا لم يكن أحد العمودين موجودًا، نتجاهل الخطأ حتى لا تتعطل الصفحة.
    try:
        execute("UPDATE users SET plan_code = ? WHERE id = ?", (plan_code, user_id))
    except Exception:
        pass

    try:
        execute("UPDATE users SET plan = ? WHERE id = ?", (plan_code, user_id))
    except Exception:
        pass


@router.post("/profile/plan")
async def update_plan(
    request: Request,
    plan: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if is_staff_mode_user(user):
        return RedirectResponse(url="/assistant", status_code=303)

    plan_code = normalize_plan(plan)

    if not plan_code:
        return RedirectResponse(url="/profile?error=invalid_plan", status_code=303)

    update_user_plan(int(user["id"]), plan_code)

    return RedirectResponse(url="/profile?plan_updated=1", status_code=303)


@router.post("/pricing/select-plan")
async def select_plan_from_pricing(
    request: Request,
    plan: str = Form(...),
):
    user = require_user(request)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if is_staff_mode_user(user):
        return RedirectResponse(url="/assistant", status_code=303)

    plan_code = normalize_plan(plan)

    if not plan_code:
        return RedirectResponse(url="/pricing?error=invalid_plan", status_code=303)

    update_user_plan(int(user["id"]), plan_code)

    return RedirectResponse(url="/profile?plan_updated=1", status_code=303)
