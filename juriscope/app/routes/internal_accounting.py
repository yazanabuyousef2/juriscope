from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.db.session import SessionLocal
from app.internal_dependencies import get_current_staff_optional


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


ALLOWED_ROLES = [
    "superadmin",
    "admin",
    "developer",
    "accountant",
]


def can_manage_accounting(staff) -> bool:
    return bool(staff and staff.role in ALLOWED_ROLES)


def money(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.000")


def calculate_invoice_totals(
    quantity,
    unit_price,
    discount_amount,
    tax_rate,
    is_taxable,
):
    quantity = money(quantity)
    unit_price = money(unit_price)
    discount_amount = money(discount_amount)
    tax_rate = money(tax_rate)

    subtotal = (quantity * unit_price).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    if discount_amount > subtotal:
        discount_amount = subtotal

    taxable_amount = subtotal - discount_amount

    if is_taxable:
        tax_amount = (taxable_amount * tax_rate / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    else:
        tax_amount = Decimal("0.000")

    total_amount = (taxable_amount + tax_amount).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "taxable_amount": taxable_amount,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
    }


def ensure_accounting_tables(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS accounting_settings (
                id SERIAL PRIMARY KEY,
                setting_key VARCHAR(150) UNIQUE NOT NULL,
                setting_value TEXT NOT NULL,
                label VARCHAR(255),
                description TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS accounting_customers (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(100),
                tax_number VARCHAR(100),
                address TEXT,
                user_id INTEGER NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS accounting_invoices (
                id SERIAL PRIMARY KEY,
                invoice_number VARCHAR(100) UNIQUE NOT NULL,
                customer_id INTEGER NULL,
                customer_name VARCHAR(255) NOT NULL,
                customer_email VARCHAR(255),
                customer_phone VARCHAR(100),
                customer_tax_number VARCHAR(100),
                invoice_type VARCHAR(100) NOT NULL DEFAULT 'subscription',
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                currency VARCHAR(10) NOT NULL DEFAULT 'JOD',
                issue_date DATE NOT NULL DEFAULT CURRENT_DATE,
                due_date DATE NULL,
                subtotal NUMERIC(12,3) NOT NULL DEFAULT 0,
                discount_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                taxable_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                sales_tax_rate NUMERIC(6,3) NOT NULL DEFAULT 16,
                sales_tax_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                total_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                paid_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                balance_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                is_taxable BOOLEAN NOT NULL DEFAULT TRUE,
                tax_note TEXT,
                notes TEXT,
                created_by_staff_id INTEGER NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS accounting_invoice_items (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES accounting_invoices(id) ON DELETE CASCADE,
                item_name VARCHAR(255) NOT NULL,
                description TEXT,
                quantity NUMERIC(12,3) NOT NULL DEFAULT 1,
                unit_price NUMERIC(12,3) NOT NULL DEFAULT 0,
                line_total NUMERIC(12,3) NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS accounting_payments (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER NOT NULL REFERENCES accounting_invoices(id) ON DELETE CASCADE,
                amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                payment_method VARCHAR(100) NOT NULL DEFAULT 'cash',
                payment_reference VARCHAR(255),
                paid_at TIMESTAMP NOT NULL DEFAULT NOW(),
                notes TEXT,
                created_by_staff_id INTEGER NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS accounting_expenses (
                id SERIAL PRIMARY KEY,
                expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
                category VARCHAR(150) NOT NULL,
                vendor_name VARCHAR(255),
                description TEXT,
                amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                sales_tax_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                total_amount NUMERIC(12,3) NOT NULL DEFAULT 0,
                payment_method VARCHAR(100) NOT NULL DEFAULT 'cash',
                receipt_number VARCHAR(255),
                created_by_staff_id INTEGER NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    db.commit()


def seed_accounting_settings(db):
    defaults = {
        "default_sales_tax_rate": {
            "value": "16",
            "label": "نسبة ضريبة المبيعات الافتراضية",
            "description": "النسبة الافتراضية لضريبة المبيعات الأردنية. يمكن تعديلها إذا كان النشاط أو الخدمة يخضع لنسبة مختلفة.",
        },
        "default_currency": {
            "value": "JOD",
            "label": "العملة الافتراضية",
            "description": "العملة المستخدمة في الفواتير والتقارير.",
        },
        "invoice_prefix": {
            "value": "MZN",
            "label": "بادئة رقم الفاتورة",
            "description": "تظهر قبل رقم الفاتورة، مثل MZN-000001.",
        },
    }

    for key, data in defaults.items():
        existing = db.execute(
            text("SELECT id FROM accounting_settings WHERE setting_key = :key"),
            {"key": key},
        ).first()

        if existing:
            continue

        db.execute(
            text(
                """
                INSERT INTO accounting_settings (
                    setting_key,
                    setting_value,
                    label,
                    description,
                    created_at,
                    updated_at
                )
                VALUES (
                    :key,
                    :value,
                    :label,
                    :description,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "key": key,
                "value": data["value"],
                "label": data["label"],
                "description": data["description"],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )

    db.commit()


def get_setting(db, key: str, fallback: str = "") -> str:
    row = db.execute(
        text(
            """
            SELECT setting_value
            FROM accounting_settings
            WHERE setting_key = :key
            """
        ),
        {"key": key},
    ).mappings().first()

    if not row:
        return fallback

    return str(row["setting_value"])


def generate_invoice_number(db) -> str:
    prefix = get_setting(db, "invoice_prefix", "MZN")

    row = db.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM accounting_invoices
            """
        )
    ).mappings().first()

    next_number = int(row["total"] or 0) + 1

    return f"{prefix}-{next_number:06d}"


def refresh_invoice_payment_status(db, invoice_id: int):
    paid_row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(amount), 0) AS paid
            FROM accounting_payments
            WHERE invoice_id = :invoice_id
            """
        ),
        {"invoice_id": invoice_id},
    ).mappings().first()

    invoice = db.execute(
        text(
            """
            SELECT total_amount
            FROM accounting_invoices
            WHERE id = :invoice_id
            """
        ),
        {"invoice_id": invoice_id},
    ).mappings().first()

    if not invoice:
        return

    paid_amount = money(paid_row["paid"])
    total_amount = money(invoice["total_amount"])
    balance_amount = total_amount - paid_amount

    if balance_amount <= 0:
        status = "paid"
        balance_amount = Decimal("0.000")
    elif paid_amount > 0:
        status = "partial"
    else:
        status = "unpaid"

    db.execute(
        text(
            """
            UPDATE accounting_invoices
            SET
                paid_amount = :paid_amount,
                balance_amount = :balance_amount,
                status = :status,
                updated_at = :updated_at
            WHERE id = :invoice_id
            """
        ),
        {
            "invoice_id": invoice_id,
            "paid_amount": paid_amount,
            "balance_amount": balance_amount,
            "status": status,
            "updated_at": datetime.utcnow(),
        },
    )


def get_dashboard_stats(db):
    row = db.execute(
        text(
            """
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_sales,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(balance_amount), 0) AS total_unpaid,
                COALESCE(SUM(sales_tax_amount), 0) AS total_sales_tax,
                COUNT(*) AS invoices_count
            FROM accounting_invoices
            """
        )
    ).mappings().first()

    expenses = db.execute(
        text(
            """
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_expenses,
                COUNT(*) AS expenses_count
            FROM accounting_expenses
            """
        )
    ).mappings().first()

    total_sales = money(row["total_sales"])
    total_expenses = money(expenses["total_expenses"])

    return {
        "total_sales": total_sales,
        "total_paid": money(row["total_paid"]),
        "total_unpaid": money(row["total_unpaid"]),
        "total_sales_tax": money(row["total_sales_tax"]),
        "invoices_count": int(row["invoices_count"] or 0),
        "total_expenses": total_expenses,
        "expenses_count": int(expenses["expenses_count"] or 0),
        "net_profit": total_sales - total_expenses,
    }


@router.get("/internal/accounting", response_class=HTMLResponse)
async def accounting_dashboard(request: Request):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_accounting(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        ensure_accounting_tables(db)
        seed_accounting_settings(db)

        stats = get_dashboard_stats(db)

        invoices = db.execute(
            text(
                """
                SELECT *
                FROM accounting_invoices
                ORDER BY created_at DESC
                LIMIT 20
                """
            )
        ).mappings().all()

        expenses = db.execute(
            text(
                """
                SELECT *
                FROM accounting_expenses
                ORDER BY created_at DESC
                LIMIT 20
                """
            )
        ).mappings().all()

        default_tax_rate = get_setting(db, "default_sales_tax_rate", "16")
        default_currency = get_setting(db, "default_currency", "JOD")

        return templates.TemplateResponse(
            request=request,
            name="internal/accounting.html",
            context={
                "request": request,
                "staff": staff,
                "stats": stats,
                "invoices": [dict(item) for item in invoices],
                "expenses": [dict(item) for item in expenses],
                "default_tax_rate": default_tax_rate,
                "default_currency": default_currency,
                "error": request.query_params.get("error", ""),
                "success": request.query_params.get("success", ""),
            },
        )

    finally:
        db.close()


@router.post("/internal/accounting/settings/update")
async def accounting_settings_update(
    request: Request,
    default_sales_tax_rate: str = Form("16"),
    default_currency: str = Form("JOD"),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_accounting(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    db = SessionLocal()

    try:
        ensure_accounting_tables(db)
        seed_accounting_settings(db)

        db.execute(
            text(
                """
                UPDATE accounting_settings
                SET setting_value = :value, updated_at = :updated_at
                WHERE setting_key = 'default_sales_tax_rate'
                """
            ),
            {
                "value": str(money(default_sales_tax_rate)),
                "updated_at": datetime.utcnow(),
            },
        )

        db.execute(
            text(
                """
                UPDATE accounting_settings
                SET setting_value = :value, updated_at = :updated_at
                WHERE setting_key = 'default_currency'
                """
            ),
            {
                "value": default_currency.strip() or "JOD",
                "updated_at": datetime.utcnow(),
            },
        )

        db.commit()

        return RedirectResponse(url="/internal/accounting?success=settings_updated", status_code=303)

    finally:
        db.close()


@router.post("/internal/accounting/invoices/create")
async def accounting_invoice_create(
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(""),
    customer_phone: str = Form(""),
    customer_tax_number: str = Form(""),
    invoice_type: str = Form("subscription"),
    item_name: str = Form(...),
    item_description: str = Form(""),
    quantity: str = Form("1"),
    unit_price: str = Form("0"),
    discount_amount: str = Form("0"),
    is_taxable: str = Form("yes"),
    sales_tax_rate: str = Form("16"),
    payment_amount: str = Form("0"),
    payment_method: str = Form("cash"),
    notes: str = Form(""),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_accounting(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    customer_name = customer_name.strip()
    item_name = item_name.strip()

    if not customer_name or not item_name:
        return RedirectResponse(url="/internal/accounting?error=missing_invoice_data", status_code=303)

    db = SessionLocal()

    try:
        ensure_accounting_tables(db)
        seed_accounting_settings(db)

        taxable = is_taxable == "yes"

        totals = calculate_invoice_totals(
            quantity=quantity,
            unit_price=unit_price,
            discount_amount=discount_amount,
            tax_rate=sales_tax_rate,
            is_taxable=taxable,
        )

        invoice_number = generate_invoice_number(db)

        db.execute(
            text(
                """
                INSERT INTO accounting_invoices (
                    invoice_number,
                    customer_name,
                    customer_email,
                    customer_phone,
                    customer_tax_number,
                    invoice_type,
                    status,
                    currency,
                    subtotal,
                    discount_amount,
                    taxable_amount,
                    sales_tax_rate,
                    sales_tax_amount,
                    total_amount,
                    paid_amount,
                    balance_amount,
                    is_taxable,
                    tax_note,
                    notes,
                    created_by_staff_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    :invoice_number,
                    :customer_name,
                    :customer_email,
                    :customer_phone,
                    :customer_tax_number,
                    :invoice_type,
                    'unpaid',
                    :currency,
                    :subtotal,
                    :discount_amount,
                    :taxable_amount,
                    :sales_tax_rate,
                    :sales_tax_amount,
                    :total_amount,
                    0,
                    :total_amount,
                    :is_taxable,
                    :tax_note,
                    :notes,
                    :created_by_staff_id,
                    :created_at,
                    :updated_at
                )
                RETURNING id
                """
            ),
            {
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "customer_email": customer_email.strip(),
                "customer_phone": customer_phone.strip(),
                "customer_tax_number": customer_tax_number.strip(),
                "invoice_type": invoice_type.strip() or "subscription",
                "currency": get_setting(db, "default_currency", "JOD"),
                "subtotal": totals["subtotal"],
                "discount_amount": totals["discount_amount"],
                "taxable_amount": totals["taxable_amount"],
                "sales_tax_rate": money(sales_tax_rate),
                "sales_tax_amount": totals["tax_amount"],
                "total_amount": totals["total_amount"],
                "is_taxable": taxable,
                "tax_note": "ضريبة مبيعات أردنية محسوبة حسب النسبة المدخلة. النسبة الافتراضية 16% قابلة للتعديل حسب الحالة الضريبية.",
                "notes": notes.strip(),
                "created_by_staff_id": staff.id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )

        invoice_id = db.execute(text("SELECT currval(pg_get_serial_sequence('accounting_invoices','id')) AS id")).mappings().first()["id"]

        line_total = (money(quantity) * money(unit_price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        db.execute(
            text(
                """
                INSERT INTO accounting_invoice_items (
                    invoice_id,
                    item_name,
                    description,
                    quantity,
                    unit_price,
                    line_total,
                    created_at
                )
                VALUES (
                    :invoice_id,
                    :item_name,
                    :description,
                    :quantity,
                    :unit_price,
                    :line_total,
                    :created_at
                )
                """
            ),
            {
                "invoice_id": invoice_id,
                "item_name": item_name,
                "description": item_description.strip(),
                "quantity": money(quantity),
                "unit_price": money(unit_price),
                "line_total": line_total,
                "created_at": datetime.utcnow(),
            },
        )

        payment = money(payment_amount)

        if payment > 0:
            db.execute(
                text(
                    """
                    INSERT INTO accounting_payments (
                        invoice_id,
                        amount,
                        payment_method,
                        paid_at,
                        notes,
                        created_by_staff_id,
                        created_at
                    )
                    VALUES (
                        :invoice_id,
                        :amount,
                        :payment_method,
                        :paid_at,
                        :notes,
                        :created_by_staff_id,
                        :created_at
                    )
                    """
                ),
                {
                    "invoice_id": invoice_id,
                    "amount": payment,
                    "payment_method": payment_method.strip() or "cash",
                    "paid_at": datetime.utcnow(),
                    "notes": "دفعة مسجلة عند إنشاء الفاتورة.",
                    "created_by_staff_id": staff.id,
                    "created_at": datetime.utcnow(),
                },
            )

            refresh_invoice_payment_status(db, invoice_id)

        db.commit()

        return RedirectResponse(url="/internal/accounting?success=invoice_created", status_code=303)

    finally:
        db.close()


@router.post("/internal/accounting/payments/create")
async def accounting_payment_create(
    request: Request,
    invoice_id: int = Form(...),
    amount: str = Form(...),
    payment_method: str = Form("cash"),
    payment_reference: str = Form(""),
    notes: str = Form(""),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_accounting(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    payment_amount = money(amount)

    if payment_amount <= 0:
        return RedirectResponse(url="/internal/accounting?error=invalid_payment", status_code=303)

    db = SessionLocal()

    try:
        ensure_accounting_tables(db)

        invoice = db.execute(
            text(
                """
                SELECT id
                FROM accounting_invoices
                WHERE id = :invoice_id
                """
            ),
            {"invoice_id": invoice_id},
        ).first()

        if not invoice:
            return RedirectResponse(url="/internal/accounting?error=invoice_not_found", status_code=303)

        db.execute(
            text(
                """
                INSERT INTO accounting_payments (
                    invoice_id,
                    amount,
                    payment_method,
                    payment_reference,
                    paid_at,
                    notes,
                    created_by_staff_id,
                    created_at
                )
                VALUES (
                    :invoice_id,
                    :amount,
                    :payment_method,
                    :payment_reference,
                    :paid_at,
                    :notes,
                    :created_by_staff_id,
                    :created_at
                )
                """
            ),
            {
                "invoice_id": invoice_id,
                "amount": payment_amount,
                "payment_method": payment_method.strip() or "cash",
                "payment_reference": payment_reference.strip(),
                "paid_at": datetime.utcnow(),
                "notes": notes.strip(),
                "created_by_staff_id": staff.id,
                "created_at": datetime.utcnow(),
            },
        )

        refresh_invoice_payment_status(db, invoice_id)

        db.commit()

        return RedirectResponse(url="/internal/accounting?success=payment_created", status_code=303)

    finally:
        db.close()


@router.post("/internal/accounting/expenses/create")
async def accounting_expense_create(
    request: Request,
    category: str = Form(...),
    vendor_name: str = Form(""),
    description: str = Form(""),
    amount: str = Form("0"),
    sales_tax_amount: str = Form("0"),
    payment_method: str = Form("cash"),
    receipt_number: str = Form(""),
):
    staff = get_current_staff_optional(request)

    if not staff:
        return RedirectResponse(url="/internal/login", status_code=303)

    if not can_manage_accounting(staff):
        return RedirectResponse(url="/internal/dashboard?error=not_allowed", status_code=303)

    base_amount = money(amount)
    tax_amount = money(sales_tax_amount)
    total_amount = base_amount + tax_amount

    if not category.strip() or total_amount <= 0:
        return RedirectResponse(url="/internal/accounting?error=invalid_expense", status_code=303)

    db = SessionLocal()

    try:
        ensure_accounting_tables(db)

        db.execute(
            text(
                """
                INSERT INTO accounting_expenses (
                    expense_date,
                    category,
                    vendor_name,
                    description,
                    amount,
                    sales_tax_amount,
                    total_amount,
                    payment_method,
                    receipt_number,
                    created_by_staff_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    CURRENT_DATE,
                    :category,
                    :vendor_name,
                    :description,
                    :amount,
                    :sales_tax_amount,
                    :total_amount,
                    :payment_method,
                    :receipt_number,
                    :created_by_staff_id,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "category": category.strip(),
                "vendor_name": vendor_name.strip(),
                "description": description.strip(),
                "amount": base_amount,
                "sales_tax_amount": tax_amount,
                "total_amount": total_amount,
                "payment_method": payment_method.strip() or "cash",
                "receipt_number": receipt_number.strip(),
                "created_by_staff_id": staff.id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )

        db.commit()

        return RedirectResponse(url="/internal/accounting?success=expense_created", status_code=303)

    finally:
        db.close()