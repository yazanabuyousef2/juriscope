from app.db.session import Base

# Import all models here so Alembic can detect them.
from app.models.user import User, UserSession
from app.models.staff import StaffUser, StaffSession, StaffPermission
from app.models.country import Country, Jurisdiction
from app.models.case import Case, CaseNote, CaseUpdate, Analysis, Document
from app.models.legal import (
    LegalDocument,
    LegalArticle,
    LegalArticleVersion,
    LegalTopic,
    LegalArticleTopic,
    LegalArticleKeyword,
    LegalImportJob,
)
from app.models.subscription import (
    SubscriptionPlan,
    UserSubscription,
    PaymentTransaction,
    Invoice,
    UsageCounter,
)
from app.models.support import SupportTicket, SupportMessage
from app.models.audit import (
    InternalAuditLog,
    AIRequestLog,
    LegalSearchLog,
    StaffAccessLog,
    SystemSetting,
)