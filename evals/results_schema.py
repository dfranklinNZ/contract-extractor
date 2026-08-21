from pydantic import BaseModel, Field

## this is just a class for storing my grade results in memory in a nice data structure. 

class GradeResult(BaseModel):
    verdict: str = Field(description="correct | partial | wrong")
    reasoning: str = Field(description="One or two sentences explaining the verdict")
    confidence: str = Field(description="high | medium | low")
