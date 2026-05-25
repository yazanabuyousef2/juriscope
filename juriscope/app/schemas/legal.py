from typing import List, Optional
from pydantic import BaseModel, Field


class CriminalDetails(BaseModel):
    alleged_crime: Optional[str] = ""
    has_prior_record: Optional[str] = "غير معروف"
    prior_count: Optional[str] = ""
    confession: Optional[str] = "غير معروف"
    witnesses: Optional[str] = "غير معروف"
    harm: Optional[str] = "غير معروف"
    mitigating_factors: Optional[str] = ""
    aggravating_factors: Optional[str] = ""


class AnalyzeRequest(BaseModel):
    question: str
    country: str = "الأردن"
    case_type: str = "أخرى"
    plan: str = "المجانية"
    criminal_details: Optional[CriminalDetails] = None


class SimilarCase(BaseModel):
    title: str = ""
    similarity: str = ""
    principle: str = ""
    why_relevant: str = ""


class CriminalPenaltyEstimate(BaseModel):
    show: bool = False
    alleged_crime: str = ""
    possible_penalty_range: str = ""
    factors_that_may_increase_penalty: List[str] = Field(default_factory=list)
    factors_that_may_reduce_penalty: List[str] = Field(default_factory=list)
    important_warning: str = ""


class AnalyzeResponse(BaseModel):
    short_answer: str = ""
    country_context: str = ""
    case_understanding: str = ""
    legal_classification: str = ""
    key_risks: List[str] = Field(default_factory=list)
    relevant_documents: List[str] = Field(default_factory=list)
    similar_cases: List[SimilarCase] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    lawyer_summary: str = ""
    criminal_penalty_estimate: CriminalPenaltyEstimate = Field(default_factory=CriminalPenaltyEstimate)
    disclaimer: str = ""


class DocumentAnalysisResponse(BaseModel):
    document_type: str = ""
    country_context: str = ""
    summary: str = ""
    parties: List[str] = Field(default_factory=list)
    main_obligations: List[str] = Field(default_factory=list)
    risky_clauses: List[str] = Field(default_factory=list)
    legal_gaps: List[str] = Field(default_factory=list)
    missing_clauses: List[str] = Field(default_factory=list)
    suggested_edits: List[str] = Field(default_factory=list)
    risk_level: str = ""
    lawyer_summary: str = ""
    disclaimer: str = ""
