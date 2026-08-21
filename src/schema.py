from pydantic import BaseModel, Field

class ClauseExtraction(BaseModel): ## represents the extraction of a specific clause from a contract
    value: str | None = Field(description="Extracted text, null if absent")
    source_quote: str = Field(description="Verbatim snippet supporting this")
    page_number: int | None
    confidence: str = Field(description="high | medium | low")

class ContractExtraction(BaseModel): ## parent object of 6 fields, each represented by clauseextraction classes
    parties: ClauseExtraction
    effective_date: ClauseExtraction
    termination_clause: ClauseExtraction
    liability_cap: ClauseExtraction
    auto_renewal: ClauseExtraction
    governing_law: ClauseExtraction

    def fields(self) -> list[tuple[str, ClauseExtraction]]: ## part of class - returns a list of tuples, each containing the field name and its corresponding ClauseExtraction object
        return [
            ("parties", self.parties),
            ("effective_date", self.effective_date),
            ("termination_clause", self.termination_clause),
            ("liability_cap", self.liability_cap),
            ("auto_renewal", self.auto_renewal),
            ("governing_law", self.governing_law),
        ]
