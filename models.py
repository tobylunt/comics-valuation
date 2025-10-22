from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ConditionGrade(str, Enum):
    """Comic book condition grades based on industry standard"""
    MINT = "10.0"
    NEAR_MINT_PLUS = "9.8"
    NEAR_MINT = "9.6"
    NEAR_MINT_MINUS = "9.2"
    NEAR_MINT_LOW = "9.0"  # Added for Gemini compatibility
    VERY_FINE_PLUS = "8.5"
    VERY_FINE = "8.0"
    VERY_FINE_MINUS = "7.5"
    FINE_VERY_FINE = "7.0"  # Added for Gemini compatibility
    FINE_PLUS = "6.5"
    FINE = "6.0"
    FINE_MINUS = "5.5"
    VERY_GOOD_PLUS = "4.5"
    VERY_GOOD = "4.0"
    VERY_GOOD_MINUS = "3.5"
    GOOD_PLUS = "2.5"
    GOOD = "2.0"
    FAIR = "1.5"
    POOR = "1.0"


class ValuationEstimate(BaseModel):
    """Price estimates for different scenarios"""
    model_config = ConfigDict(extra='forbid')

    low_estimate: float = Field(..., description="Pessimistic/low-end estimate")
    best_estimate: float = Field(..., description="Most likely value given condition")
    high_estimate: float = Field(..., description="Optimistic/high-end estimate")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in estimates (0-1)")


class ComicValuation(BaseModel):
    """Complete comic book valuation data"""
    model_config = ConfigDict(extra='forbid')

    # Basic identification
    series: str = Field(..., description="Comic book series name")
    title: str = Field(..., description="Specific issue title")
    issue_number: str = Field(..., description="Issue number (including variants)")
    publisher: str = Field(..., description="Publishing company")
    publication_date: str = Field(..., description="Publication date (YYYY-MM or YYYY), use 'Unknown' if not determinable")

    # Condition assessment
    estimated_grade: ConditionGrade
    condition_notes: List[str] = Field(..., description="Specific condition issues, use empty list if none observed")

    # Market factors
    key_issue: bool = Field(..., description="Whether this is a key/significant issue")
    key_issue_notes: str = Field(..., description="Why this is a key issue, or 'Not a key issue' if not significant")
    rarity_notes: str = Field(..., description="Rarity or print run information, or 'Unknown' if not determinable")

    # Valuation
    valuation: ValuationEstimate

    # Metadata
    image_filename: str = Field(..., description="Source image filename")
    analysis_date: str = Field(..., description="When analysis was performed (ISO format)")
    llm_provider: str = Field(..., description="Which LLM was used for analysis")

    # Quality indicators
    identification_confidence: float = Field(..., ge=0, le=1, description="Confidence in comic identification")
    analysis_notes: str = Field(..., description="Additional analysis notes or observations")

    # Grounding metadata (Gemini-specific)
    grounding_metadata: Optional[dict] = Field(None, description="Google Search grounding data with queries and source URLs")


class ProcessingResult(BaseModel):
    """Result of processing a single image"""
    model_config = ConfigDict(extra='forbid')

    image_filename: str
    success: bool
    valuation: Optional[ComicValuation] = None
    error_message: Optional[str] = None
    processing_time: float = 0.0


class BatchResults(BaseModel):
    """Results from processing multiple images"""
    model_config = ConfigDict(extra='forbid')

    total_processed: int
    successful: int
    failed: int
    results: List[ProcessingResult]
    batch_start_time: datetime
    batch_end_time: datetime
    total_processing_time: float
