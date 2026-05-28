from datetime import datetime

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.db.session import SessionLocal
from app.models.country import Country
from app.models.staff import StaffUser
from app.models.subscription import SubscriptionPlan


def seed_countries(db: Session):
    countries = [
        {
            "code": "JO",
            "name_ar": "الأردن",
            "name_en": "Jordan",
            "phone_code": "+962",
            "currency": "JOD",
        },
        {
            "code": "SA",
            "name_ar": "السعودية",
            "name_en": "Saudi Arabia",
            "phone_code": "+966",
            "currency": "SAR",
        },
        {
            "code": "AE",
            "name_ar": "الإمارات",
            "name_en": "United Arab Emirates",
            "phone_code": "+971",
            "currency": "AED",
        },
        {
            "code": "EG",
            "name_ar": "مصر",
            "name_en": "Egypt",
            "phone_code": "+20",
            "currency": "EGP",
        },
        {
            "code": "IQ",
            "name_ar": "العراق",
            "name_en": "Iraq",
            "phone_code": "+964",
            "currency": "IQD",
        },
        {
            "code": "QA",
            "name_ar": "قطر",
            "name_en": "Qatar",
            "phone_code": "+974",
            "currency": "QAR",
        },
        {
            "code": "KW",
            "name_ar": "الكويت",
            "name_en": "Kuwait",
            "phone_code": "+965",
            "currency": "KWD",
        },
        {
            "code": "BH",
            "name_ar": "البحرين",
            "name_en": "Bahrain",
            "phone_code": "+973",
            "currency": "BHD",
        },
        {
            "code": "OM",
            "name_ar": "عُمان",
            "name_en": "Oman",
            "phone_code": "+968",
            "currency": "OMR",
        },
    ]

    for item in countries:
        existing = db.query(Country).filter(Country.code == item["code"]).first()

        if existing:
            existing.name_ar = item["name_ar"]
            existing.name_en = item["name_en"]
            existing.phone_code = item["phone_code"]
            existing.currency = item["currency"]
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
        else:
            db.add(Country(**item, is_active=True))


def seed_subscription_plans(db: Session):
    plans = [
        {
            "code": "free",
            "name_ar": "Free",
            "name_en": "Free",
            "description_ar": "باقة مجانية للتجربة الأولية.",
            "description_en": "Free trial plan.",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 15,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": False,
            "can_export_word": False,
            "can_access_advanced_analysis": False,
            "can_use_legal_sources": True,
        },
        {
            "code": "basic",
            "name_ar": "Basic",
            "name_en": "Basic",
            "description_ar": "باقة أساسية بتحليل أوضح ومنظم.",
            "description_en": "Basic structured analysis plan.",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 15,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": False,
            "can_export_word": False,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
        },
        {
            "code": "pro",
            "name_ar": "Pro",
            "name_en": "Pro",
            "description_ar": "باقة احترافية بتحليل أعمق.",
            "description_en": "Professional deeper analysis plan.",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 20,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": True,
            "can_export_word": True,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
        },
        {
            "code": "premium",
            "name_ar": "Premium",
            "name_en": "Premium",
            "description_ar": "باقة متقدمة بتحليل موسع واستراتيجية.",
            "description_en": "Advanced strategic analysis plan.",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 30,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": True,
            "can_export_word": True,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
        },
        {
            "code": "enterprise",
            "name_ar": "Enterprise",
            "name_en": "Enterprise",
            "description_ar": "باقة مؤسساتية للشركات والمكاتب والفرق.",
            "description_en": "Enterprise plan for teams and organizations.",
            "price_monthly": 0,
            "currency": "USD",
            "monthly_analyses": 999999,
            "monthly_documents": 999999,
            "max_cases": 999999,
            "max_file_size_mb": 50,
            "can_upload_documents": True,
            "can_use_case_memory": True,
            "can_export_pdf": True,
            "can_export_word": True,
            "can_access_advanced_analysis": True,
            "can_use_legal_sources": True,
        },
    ]

    for item in plans:
        existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == item["code"]).first()

        if existing:
            for key, value in item.items():
                setattr(existing, key, value)

            existing.is_active = True
            existing.updated_at = datetime.utcnow()
        else:
            db.add(SubscriptionPlan(**item, is_active=True))

def seed_superadmin(db: Session):
    email = "yazanabuyousef2@gmail.com"

    existing = db.query(StaffUser).filter(StaffUser.email == email).first()

    if existing:
        existing.full_name = "Yazan Abu Yousef"
        existing.password_hash = hash_password("Y1911@m1876")
        existing.role = "superadmin"
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        return

    superadmin = StaffUser(
        full_name="Yazan Abu Yousef",
        email=email,
        password_hash=hash_password("Y1911@m1876"),
        role="superadmin",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(superadmin)


def run_seed():
    db = SessionLocal()

    try:
        seed_countries(db)
        seed_subscription_plans(db)
        seed_superadmin(db)

        db.commit()

        print("Seed completed successfully.")
        print("Super Admin:")
        print("Email: yazanabuyousef2@gmail.com")
        print("Password: Y1911@m1876")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    run_seed()