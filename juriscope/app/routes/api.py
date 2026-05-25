from fastapi import APIRouter
from app.schemas.legal import AnalyzeRequest, AnalyzeResponse
from app.services.ai_service import analyze_legal_question

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return await analyze_legal_question(request.question)
