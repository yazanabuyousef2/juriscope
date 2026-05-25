from fastapi import APIRouter, HTTPException
from app.schemas.legal import AnalyzeRequest, AnalyzeResponse
from app.services.ai_service import analyze_legal_question

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return await analyze_legal_question(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
