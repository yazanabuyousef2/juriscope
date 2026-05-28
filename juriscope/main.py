import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes.pages import router as pages_router
from app.routes.api import router as api_router
from app.routes.auth import router as auth_router
from app.routes.cases import router as cases_router


app = FastAPI(
    title="Mizan",
    description="AI Legal Assistant",
)

# Create database tables on startup
init_db()

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )