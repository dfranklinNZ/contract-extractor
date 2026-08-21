import time

import anthropic
from dotenv import load_dotenv
from pydantic import ValidationError

from .schema import ContractExtraction ##import class to collect data as objects for the 6 fields

load_dotenv()

client = anthropic.Anthropic()

MODEL_VERSION = "claude-sonnet-5"
PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You are extracting structured fields from a contract.

Read the full contract text and extract these six fields: parties, \
effective_date, termination_clause, liability_cap, auto_renewal, governing_law.

Every field, including parties, is an object with value, source_quote, \
page_number, and confidence — never a bare string.

For each field:
- source_quote must be copied verbatim from the contract text, never paraphrased.
- page_number is the page the source_quote appears on.
- value is null if the field is not present in the contract; never infer or guess.
- confidence is "high", "medium", or "low" based on how directly the text supports value.

For the parties field specifically, set its value to the party names joined by ", "."""

TOOL_NAME = "record_contract_extraction"

_TOOL = {
    "name": TOOL_NAME,
    "description": "Record the six extracted contract fields.",
    "input_schema": ContractExtraction.model_json_schema(), ##returns json schema / dict
}

def extract(contract_text: str) -> ContractExtraction:  ##takes in a string, returns this class for the 6 fields
    result, _usage, _wall_ms = extract_with_usage(contract_text)
    return result

def extract_with_usage(contract_text: str) -> tuple[ContractExtraction, dict, int]:
    """Like extract(), but also returns token usage and call wall-clock time (ms) — used by evals to track cost/latency per run."""
    # occasionally the model nests the whole response in a value/source_quote/...
    # wrapper instead of the 6 top-level fields; one retry clears it up almost always.
    last_error: ValidationError | None = None
    for _attempt in range(2):
        t0 = time.perf_counter()
        msg = client.messages.create(
            model=MODEL_VERSION,
            max_tokens=4000,
            system=SYSTEM_PROMPT,   # rules: quote verbatim, null if absent, never infer
            messages=[{"role": "user", "content": contract_text}],
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": TOOL_NAME}, ## specifies that the tool to be used is the one defined above
        )
        wall_ms = int((time.perf_counter() - t0) * 1000)
        ## so here we create a message and send it to the model with the tool choice, then tool_use below searches the blocks in the returned msg
        tool_use = next(block for block in msg.content if block.type == "tool_use") ## finds the first block in the message content that is of type "tool_use", Next is a built-in function that returns the next item from an iterator, in this case, the first block that matches the condition.
        ## how does the tool get used by the model? isnt that a seperate message sent?
        try:
            result = ContractExtraction.model_validate(tool_use.input) ##pydantic method that validates the input data against the ContractExtraction model, ensuring that it conforms to the expected structure and types. If the input is valid, it returns an instance of ContractExtraction populated with the extracted data.
            ##what is in a block agian? whats tool use block ... input
            ##ok so input is a DICT object, so that means it does actually call a tool, it creates the dict shape
            usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
            return result, usage, wall_ms
        except ValidationError as e:
            last_error = e
    raise last_error 