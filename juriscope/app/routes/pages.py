from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


@router.get("/assistant", response_class=HTMLResponse)
async def assistant(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="assistant.html"
    )


@router.get("/features", response_class=HTMLResponse)
async def features(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="features.html"
    )


@router.get("/use-cases", response_class=HTMLResponse)
async def use_cases(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="use_cases.html"
    )