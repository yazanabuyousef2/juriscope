from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.legal import AnalyzeRequest, AnalyzeResponse, DocumentAnalysisResponse
from app.services.ai_service import analyze_legal_document, analyze_legal_question

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return await analyze_legal_question(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze-document", response_model=DocumentAnalysisResponse)
async def analyze_document(
    file: UploadFile = File(...),
    country: str = Form("الأردن"),
    document_type: str = Form("مستند قانوني"),
    plan: str = Form("المجانية"),
    question: str = Form(""),
) -> DocumentAnalysisResponse:
    try:
        file_bytes = await file.read()
        return await analyze_legal_document(
            file_bytes=file_bytes,
            filename=file.filename or "uploaded_document",
            content_type=file.content_type or "application/octet-stream",
            country=country,
            document_type=document_type,
            plan=plan,
            question=question,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
