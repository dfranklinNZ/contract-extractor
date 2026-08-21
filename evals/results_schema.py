from pydantic import BaseModel, Field

class GradeResult(BaseModel):
    verdict: str = Field(description="correct | partial | wrong")
    reasoning: str = Field(description="One or two sentences explaining the verdict")
    confidence: str = Field(description="high | medium | low")
