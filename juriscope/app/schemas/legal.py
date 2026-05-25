from pydantic import BaseModel
from typing import List


class AnalyzeRequest(BaseModel):
    question: str


class SimilarCase(BaseModel):
    title: str
    similarity: str
    principle: str
    why_relevant: str


class AnalyzeResponse(BaseModel):
    short_answer: str
    case_understanding: str
    legal_classification: str
    key_risks: List[str]
    relevant_documents: List[str]
    similar_cases: List[SimilarCase]
    next_steps: List[str]
    lawyer_summary: str
    disclaimer: str
