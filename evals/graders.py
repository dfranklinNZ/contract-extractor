"""Grading building blocks for the eval suite.

Three kinds of graders, matching how "correct" is defined per field:
- exact_match: deterministic, for fields with one right answer (dates, jurisdictions).
- set_gradable: precision/recall over a set, for fields that are a list (parties).
- llm_judge: an LLM judges free-text against reference material, for fields
  where "correct" is a matter of judgment (clause summaries).

Every grader returns (verdict, reasoning, tokens, wall_ms) where verdict is
one of CORRECT / PARTIAL / WRONG. exact_match and set_gradable are local and
always report 0 tokens / 0 ms; llm_judge makes an API call and reports real
usage, used by the eval run to track cost/latency.
"""
import re
import time
from datetime import datetime

import anthropic
from dotenv import load_dotenv

from .results_schema import GradeResult

load_dotenv()

CORRECT, PARTIAL, WRONG = "correct", "partial", "wrong"

JUDGE_MODEL_VERSION = "claude-sonnet-5"
JUDGE_PROMPT_VERSION = "v1"

_DATE_FORMATS = ["%m/%d/%y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y"]

def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()

def _try_parse_date(s: str):
    s = (s or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def exact_match(extracted_value: str | None, golden: dict) -> tuple[str, str, int, int]:
    if not extracted_value:
        return WRONG, "no value extracted", 0, 0

    candidates = [golden["correct_value"], *golden.get("acceptable_alternatives", [])]
    extracted_date = _try_parse_date(extracted_value)
    for candidate in candidates:
        if not candidate:
            continue
        norm_candidate, norm_extracted = _normalize_text(candidate), _normalize_text(extracted_value)
        if norm_candidate == norm_extracted:
            return CORRECT, "", 0, 0
        candidate_date = _try_parse_date(candidate)
        if extracted_date and candidate_date and extracted_date == candidate_date:
            return CORRECT, "", 0, 0
        # loose containment handles e.g. "State of Delaware" vs "Delaware"
        if norm_candidate in norm_extracted or norm_extracted in norm_candidate:
            return CORRECT, "", 0, 0
    return WRONG, f"expected {golden['correct_value']!r}, got {extracted_value!r}", 0, 0

def set_gradable(extracted_value: str | None, golden: dict) -> tuple[str, str, int, int]:
    extracted_names = [_normalize_text(n) for n in re.split(r",|;", extracted_value or "") if n.strip()]
    golden_names = [_normalize_text(n) for n in golden["correct_value"] if n.strip()]
    if not golden_names:
        return WRONG, "no golden parties to compare against", 0, 0

    def matched(golden_name: str) -> bool:
        return any(golden_name in e or e in golden_name for e in extracted_names)

    missing = [g for g in golden_names if not matched(g)]
    if not missing:
        return CORRECT, "", 0, 0
    if len(missing) == len(golden_names):
        return WRONG, f"missing all of {golden_names}", 0, 0
    return PARTIAL, f"missing {missing}", 0, 0

JUDGE_SYSTEM_PROMPT = """You are grading whether an extracted contract field is correct.

You will be given the field being extracted, the value and supporting quote the \
extraction produced, and reference material (a known answer and/or supporting \
quotes from the same contract). The reference quotes may use different wording \
or cover a narrower legal category than the field itself — treat them as \
supporting evidence, not a required exact match.

verdict is "correct" if the extracted value is well-supported by the reference \
material, "partial" if it's roughly right but incomplete or overstated, "wrong" \
if it contradicts or is unsupported by the reference material."""

TOOL_NAME = "record_grade"

_TOOL = {
    "name": TOOL_NAME,
    "description": "Record the grading verdict for an extracted contract field.",
    "input_schema": GradeResult.model_json_schema(),
}

def llm_judge(extracted_value: str | None, extracted_quote: str, field_name: str, golden: dict) -> tuple[str, str, int, int]:
    client = anthropic.Anthropic()
    user_content = (
        f"Field: {field_name}\n\n"
        f"Extracted value: {extracted_value!r}\n"
        f"Extracted supporting quote: {extracted_quote!r}\n\n"
        f"Reference answer: {golden['correct_value']!r}\n"
        f"Reference supporting quotes: {golden.get('acceptable_alternatives', [])}\n\n"
        "Record your verdict with the tool."
    )
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=JUDGE_MODEL_VERSION,
        max_tokens=1000,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )
    wall_ms = int((time.perf_counter() - t0) * 1000)
    tool_use = next(block for block in msg.content if block.type == "tool_use")
    grade = GradeResult.model_validate(tool_use.input)
    tokens = msg.usage.input_tokens + msg.usage.output_tokens
    return grade.verdict, grade.reasoning, tokens, wall_ms

# field_name -> which grader to use.
FIELD_GRADERS = {
    "parties": "set",
    "effective_date": "exact",
    "governing_law": "exact",
    "termination_clause": "judge",
    "liability_cap": "judge",
    "auto_renewal": "judge",
}

def grade_field(field_name: str, clause, golden: dict) -> tuple[str, str, int, int]:
    grader_type = FIELD_GRADERS[field_name]
    if grader_type == "exact":
        return exact_match(clause.value, golden)
    if grader_type == "set":
        return set_gradable(clause.value, golden)
    if grader_type == "judge":
        return llm_judge(clause.value, clause.source_quote, field_name, golden)
    raise ValueError(f"unknown grader type {grader_type!r} for field {field_name!r}")
