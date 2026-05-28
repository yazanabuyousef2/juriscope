import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.staff import StaffSession, StaffUser
from app.models.user import User, UserSession


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()


USER_ROLES = {
    "individual",
    "lawyer",
    "company",
    "judge",
    "law_student",
    "legal_researcher",
    "government_employee",
}


COUNTRY_MAP = {
    "الأردن": {"code": "JO", "phone": "+962"},
    "السعودية": {"code": "SA", "phone": "+966"},
    "الإمارات": {"code": "AE", "phone": "+971"},
    "مصر": {"code": "EG", "phone": "+20"},
    "العراق": {"code": "IQ", "phone": "+964"},
    "قطر": {"code": "QA", "phone": "+974"},
    "الكويت": {"code": "KW", "phone": "+965"},
    "البحرين": {"code": "BH", "phone": "+973"},
    "عُمان": {"code": "OM", "phone": "+968"},
}


def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False

    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    has_symbol = any(not ch.isalnum() for ch in password)

    return has_upper and has_lower and has_digit and has_symbol


def create_user_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)

    session = UserSession(
        user_id=user_id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=14),
    )

    db.add(session)
    db.commit()

    return token


def create_staff_session(db: Session, staff_user_id: int) -> str:
    token = secrets.token_urlsafe(32)

    session = StaffSession(
        staff_user_id=staff_user_id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )

    db.add(session)
    db.commit()

    return token


def delete_user_session(db: Session, token: str):
    if not token:
        return

    session = db.query(UserSession).filter(UserSession.token == token).first()

    if session:
        db.delete(session)
        db.commit()


def delete_staff_session(db: Session, token: str):
    if not token:
        return

    session = db.query(StaffSession).filter(StaffSession.token == token).first()

    if session:
        db.delete(session)
        db.commit()


def get_staff_by_token(db: Session, token: str):
    if not token:
        return None

    session = (
        db.query(StaffSession)
        .join(StaffUser, StaffUser.id == StaffSession.staff_user_id)
        .filter(
            StaffSession.token == token,
            StaffSession.expires_at > datetime.utcnow(),
            StaffUser.is_active == True,
        )
        .first()
    )

    if not session:
        return None

    return session.staff_user


def get_user_by_token(db: Session, token: str):
    if not token:
        return None

    session = (
        db.query(UserSession)
        .join(User, User.id == UserSession.user_id)
        .filter(
            UserSession.token == token,
            UserSession.expires_at > datetime.utcnow(),
            User.is_active == True,
        )
        .first()
    )

    if not session:
        return None

    return session.user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    db = SessionLocal()

    try:
        staff_token = request.cookies.get(settings.STAFF_SESSION_COOKIE_NAME, "")
        user_token = request.cookies.get(settings.SESSION_COOKIE_NAME, "")

        staff = get_staff_by_token(db, staff_token)
        if staff:
            return RedirectResponse(url="/internal/dashboard", status_code=303)

        user = get_user_by_token(db, user_token)
        if user:
            return RedirectResponse(url="/assistant", status_code=303)

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "",
            },
        )

    finally:
        db.close()


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()

    try:
        email = email.strip().lower()

        # 1) Check staff first
        staff = (
            db.query(StaffUser)
            .filter(
                StaffUser.email == email,
                StaffUser.is_active == True,
            )
            .first()
        )

        if staff and verify_password(password, staff.password_hash):
            token = create_staff_session(db, staff.id)

            staff.last_login_at = datetime.utcnow()
            staff.updated_at = datetime.utcnow()
            db.commit()

            response = RedirectResponse(url="/internal/dashboard", status_code=303)

            response.set_cookie(
                settings.STAFF_SESSION_COOKIE_NAME,
                token,
                httponly=True,
                samesite="lax",
                secure=settings.is_production,
                max_age=60 * 60 * 8,
            )

            response.delete_cookie(settings.SESSION_COOKIE_NAME)
            return response

        # 2) Check normal user
        user = (
            db.query(User)
            .filter(
                User.email == email,
                User.is_active == True,
            )
            .first()
        )

        if user and verify_password(password, user.password_hash):
            token = create_user_session(db, user.id)

            response = RedirectResponse(url="/assistant", status_code=303)

            response.set_cookie(
                settings.SESSION_COOKIE_NAME,
                token,
                httponly=True,
                samesite="lax",
                secure=settings.is_production,
                max_age=60 * 60 * 24 * 14,
            )

            response.delete_cookie(settings.STAFF_SESSION_COOKIE_NAME)
            return response

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "بيانات الدخول غير صحيحة.",
            },
        )

    finally:
        db.close()


@router.get("/logout")
async def logout(request: Request):
    user_token = request.cookies.get(settings.SESSION_COOKIE_NAME, "")
    staff_token = request.cookies.get(settings.STAFF_SESSION_COOKIE_NAME, "")

    db = SessionLocal()

    try:
        delete_user_session(db, user_token)
        delete_staff_session(db, staff_token)
    finally:
        db.close()

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    response.delete_cookie(settings.STAFF_SESSION_COOKIE_NAME)

    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "request": request,
            "error": "",
        },
    )


@router.post("/register", response_class=HTMLResponse)
async def register(request: Request):
    form = await request.form()

    full_name = str(form.get("full_name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    confirm_password = str(form.get("confirm_password", form.get("password_confirm", "")))

    country_name = str(form.get("country", "الأردن")).strip() or "الأردن"
    country_data = COUNTRY_MAP.get(country_name, COUNTRY_MAP["الأردن"])
    country_code = country_data["code"]

    phone_country_code = str(form.get("phone_country_code", country_data["phone"])).strip()
    phone = str(form.get("phone", "")).strip()

    user_role = str(form.get("user_role", "individual")).strip()
    if user_role not in USER_ROLES:
        user_role = "individual"

    if not full_name or not email or not password:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "request": request,
                "error": "يرجى تعبئة جميع الحقول المطلوبة.",
            },
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "request": request,
                "error": "كلمة المرور وتأكيدها غير متطابقين.",
            },
        )

    if not is_strong_password(password):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "request": request,
                "error": "كلمة المرور ضعيفة. يجب أن تحتوي على 8 أحرف على الأقل، حرف كبير، حرف صغير، رقم، ورمز خاص.",
            },
        )

    db = SessionLocal()

    try:
        existing_user = db.query(User).filter(User.email == email).first()
        existing_staff = db.query(StaffUser).filter(StaffUser.email == email).first()

        if existing_user or existing_staff:
            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={
                    "request": request,
                    "error": "هذا البريد الإلكتروني مستخدم مسبقًا.",
                },
            )

        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            country_code=country_code,
            country_name=country_name,
            phone_country_code=phone_country_code,
            phone=phone,
            phone_verified=True,
            user_role=user_role,
            plan_code="free",
            is_active=True,
            accepted_terms_at=datetime.utcnow(),
            accepted_privacy_at=datetime.utcnow(),
            legal_disclaimer_accepted_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_user_session(db, user.id)

        response = RedirectResponse(url="/assistant", status_code=303)
        response.set_cookie(
            settings.SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
            max_age=60 * 60 * 24 * 14,
        )

        return response

    finally:
        db.close()


@router.post("/profile/update")
async def update_profile(request: Request):
    user_token = request.cookies.get(settings.SESSION_COOKIE_NAME, "")

    form = await request.form()

    full_name = str(form.get("full_name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    phone_country_code = str(form.get("phone_country_code", "")).strip()
    phone = str(form.get("phone", "")).strip()
    user_role = str(form.get("user_role", "individual")).strip()

    if user_role not in USER_ROLES:
        return RedirectResponse(url="/profile?error=invalid_user_role", status_code=303)

    db = SessionLocal()

    try:
        user = get_user_by_token(db, user_token)

        if not user:
            return RedirectResponse(url="/login", status_code=303)

        email_exists = (
            db.query(User)
            .filter(
                User.email == email,
                User.id != user.id,
            )
            .first()
        )

        staff_email_exists = db.query(StaffUser).filter(StaffUser.email == email).first()

        if email_exists or staff_email_exists:
            return RedirectResponse(url="/profile?error=email_exists", status_code=303)

        user.full_name = full_name
        user.email = email
        user.phone_country_code = phone_country_code
        user.phone = phone
        user.user_role = user_role
        user.phone_verified = True
        user.updated_at = datetime.utcnow()

        db.commit()

        return RedirectResponse(url="/profile?updated=1", status_code=303)

    finally:
        db.close()


@router.post("/profile/password")
async def update_password(request: Request):
    user_token = request.cookies.get(settings.SESSION_COOKIE_NAME, "")

    form = await request.form()

    current_password = str(form.get("current_password", ""))
    new_password = str(form.get("new_password", ""))
    confirm_password = str(form.get("confirm_password", ""))

    db = SessionLocal()

    try:
        user = get_user_by_token(db, user_token)

        if not user:
            return RedirectResponse(url="/login", status_code=303)

        if not verify_password(current_password, user.password_hash):
            return RedirectResponse(url="/profile?error=wrong_password", status_code=303)

        if new_password != confirm_password:
            return RedirectResponse(url="/profile?error=password_mismatch", status_code=303)

        if not is_strong_password(new_password):
            return RedirectResponse(url="/profile?error=weak_password", status_code=303)

        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()
        db.commit()

        return RedirectResponse(url="/profile?password_updated=1", status_code=303)

    finally:
        db.close()