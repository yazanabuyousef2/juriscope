import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user_optional, is_staff_mode_user
from app.auth.security import hash_password, verify_password
from app.core.config import get_settings
from app.database import create_session, delete_session, execute, fetch_one, now_iso
from app.db.session import SessionLocal
from app.models.staff import StaffSession, StaffUser


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = get_current_user_optional(request)

    if user:
        if is_staff_mode_user(user):
            return RedirectResponse(url="/internal/dashboard", status_code=303)
        return RedirectResponse(url="/profile", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "user": None,
            "error": "",
        },
    )


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    full_name = full_name.strip()
    email = email.strip().lower()

    if len(full_name) < 2:
        return templates.TemplateResponse(request=request, name="register.html", context={"user": None, "error": "يرجى إدخال الاسم الكامل."})

    if password != confirm_password:
        return templates.TemplateResponse(request=request, name="register.html", context={"user": None, "error": "كلمتا المرور غير متطابقتين."})

    if len(password) < 8:
        return templates.TemplateResponse(request=request, name="register.html", context={"user": None, "error": "كلمة المرور يجب أن تكون 8 أحرف على الأقل."})

    existing = fetch_one("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        return templates.TemplateResponse(request=request, name="register.html", context={"user": None, "error": "هذا البريد الإلكتروني مستخدم بالفعل."})

    user_id = execute(
        "INSERT INTO users (full_name, email, password_hash, plan, created_at) VALUES (?, ?, ?, 'free', ?)",
        (full_name, email, hash_password(password), now_iso()),
    )

    token = create_session(user_id)

    response = RedirectResponse(url="/profile", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user_optional(request)

    if user:
        if is_staff_mode_user(user):
            return RedirectResponse(url="/internal/dashboard", status_code=303)
        return RedirectResponse(url="/profile", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "error": "",
            "next": request.query_params.get("next", ""),
        },
    )


def try_staff_login(email: str, password: str):
    db = SessionLocal()

    try:
        staff = (
            db.query(StaffUser)
            .filter(StaffUser.email == email, StaffUser.is_active == True)
            .first()
        )

        if not staff or not verify_password(password, staff.password_hash):
            return None

        token = secrets.token_urlsafe(32)

        session = StaffSession(
            staff_user_id=staff.id,
            token=token,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=8),
        )

        staff.last_login_at = datetime.utcnow()

        db.add(session)
        db.commit()

        return token

    finally:
        db.close()


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()

    # شاشة تسجيل دخول موحدة:
    # الموظف / السوبر أدمن له أولوية دائمًا.
    # إذا كان نفس البريد موجودًا في users و staff_users، يدخل كموظف وليس كمستخدم عادي.
    staff_token = try_staff_login(email, password)

    if staff_token:
        response = RedirectResponse(url="/internal/dashboard", status_code=303)
        response.set_cookie(
            settings.STAFF_SESSION_COOKIE_NAME,
            staff_token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 8,
        )
        # نزيل جلسة المستخدم العادي حتى لا تختلط الجلسات.
        response.delete_cookie(SESSION_COOKIE_NAME)
        return response

    db_user = fetch_one(
        "SELECT * FROM users WHERE email = ? AND is_active = 1",
        (email,),
    )

    if db_user and verify_password(password, db_user["password_hash"]):
        token = create_session(db_user["id"])
        next_url = request.query_params.get("next") or "/profile"

        response = RedirectResponse(url=next_url, status_code=303)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 14,
        )
        response.delete_cookie(settings.STAFF_SESSION_COOKIE_NAME)
        return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "error": "بيانات الدخول غير صحيحة.",
            "next": request.query_params.get("next", ""),
        },
    )


@router.get("/logout")
async def logout(request: Request):
    user_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    staff_token = request.cookies.get(settings.STAFF_SESSION_COOKIE_NAME, "")

    delete_session(user_token)

    if staff_token:
        db = SessionLocal()
        try:
            db.query(StaffSession).filter(StaffSession.token == staff_token).delete()
            db.commit()
        finally:
            db.close()

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(settings.STAFF_SESSION_COOKIE_NAME)
    return response
