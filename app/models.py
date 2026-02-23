from pydantic import BaseModel, Field, HttpUrl


class TextAnalysisRequest(BaseModel):
    text: str = Field(
        ..., min_length=1, max_length=50000, description="Text content to analyze"
    )


class URLAnalysisRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL to fetch and analyze")


class AIGeneratedPrediction(BaseModel):
    probability: float = Field(
        ..., ge=0.0, le=1.0,
        description="Probability 0.0 to 1.0 that content is AI-generated",
    )
    label: str = Field(
        ..., description="One of: ai_generated, human_generated, uncertain"
    )
    reasoning: str = Field(
        ..., description="Explanation of why this label was assigned"
    )


class ViralityScore(BaseModel):
    score: int = Field(
        ..., ge=0, le=100, description="Virality score from 0 to 100"
    )
    reasoning: str = Field(..., description="Explanation of virality potential")


class AudienceSegment(BaseModel):
    audience: str = Field(
        ..., description="Name of the audience or community"
    )
    resonance_reason: str = Field(
        ..., description="Why this content resonates with this audience"
    )


class DistributionAnalysis(BaseModel):
    segments: list[AudienceSegment] = Field(
        ..., description="List of audiences this content would resonate with"
    )


class JudgeResult(BaseModel):
    content_type: str = Field(
        ..., description="Type of content analyzed: text, image, or video"
    )
    ai_generated: AIGeneratedPrediction
    virality: ViralityScore
    distribution: DistributionAnalysis
    summary: str = Field(
        ..., description="Concise overall explanation of all judgments"
    )


class AnalysisResponse(BaseModel):
    status: str = Field(default="success")
    result: JudgeResult


class ErrorResponse(BaseModel):
    status: str = Field(default="error")
    detail: str
