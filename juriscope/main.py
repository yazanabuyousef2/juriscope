import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db

from app.routes.pages import router as pages_router
from app.routes.api import router as api_router
from app.routes.auth import router as auth_router
from app.routes.cases import router as cases_router
from app.routes.plans import router as plans_router
from app.routes.support import router as support_router

from app.routes.internal_auth import router as internal_auth_router
from app.routes.internal_staff import router as internal_staff_router
from app.routes.internal_legal import router as internal_legal_router
from app.routes.internal_legal_articles import router as internal_legal_articles_router
from app.routes.internal_legal_search import router as internal_legal_search_router
from app.routes.internal_review import router as internal_review_router
from app.routes.internal_users import router as internal_users_router
from app.routes.internal_plans import router as internal_plans_router
from app.routes.internal_support import router as internal_support_router
from app.routes.internal_settings import router as internal_settings_router
from app.routes.internal_logs import router as internal_logs_router
from app.routes.internal_sensitive_cases import router as internal_sensitive_cases_router
from app.routes.internal_accounting import router as internal_accounting_router


app = FastAPI(
    title="Mizan",
    description="AI Legal Assistant",
)


@app.on_event("startup")
async def startup_tasks():
    """
    Production startup initialization.

    This uses DATABASE_URL from the environment.
    It creates all required PostgreSQL tables if they do not exist,
    and seeds default countries and subscription plans.
    """
    init_db()


app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Public website routes
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(plans_router)
app.include_router(support_router)


# Internal dashboard routes
app.include_router(internal_auth_router)
app.include_router(internal_staff_router)
app.include_router(internal_legal_router)
app.include_router(internal_legal_articles_router)
app.include_router(internal_legal_search_router)
app.include_router(internal_review_router)
app.include_router(internal_users_router)
app.include_router(internal_plans_router)
app.include_router(internal_support_router)
app.include_router(internal_settings_router)
app.include_router(internal_logs_router)
app.include_router(internal_sensitive_cases_router)
app.include_router(internal_accounting_router)


# API routes
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )