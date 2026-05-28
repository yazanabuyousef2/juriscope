from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import SESSION_COOKIE_NAME, get_current_user_optional
from app.auth.security import hash_password, verify_password
from app.database import create_session, delete_session, execute, fetch_one, now_iso

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = get_current_user_optional(request)

    if user:
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
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "user": None,
                "error": "يرجى إدخال الاسم الكامل.",
            },
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "user": None,
                "error": "كلمتا المرور غير متطابقتين.",
            },
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "user": None,
                "error": "كلمة المرور يجب أن تكون 8 أحرف على الأقل.",
            },
        )

    existing = fetch_one("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "user": None,
                "error": "هذا البريد الإلكتروني مستخدم بالفعل.",
            },
        )

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
        return RedirectResponse(url="/profile", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "error": "",
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()

    db_user = fetch_one(
        "SELECT * FROM users WHERE email = ? AND is_active = 1",
        (email,),
    )

    if not db_user or not verify_password(password, db_user["password_hash"]):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "error": "بيانات الدخول غير صحيحة.",
            },
        )

    token = create_session(db_user["id"])

    response = RedirectResponse(url="/profile", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    return response


@router.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    delete_session(token)

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response