"""Run the contract-extraction eval suite.

For each contract in golden.json: parse the PDF, extract the 6 fields with
the real pipeline (src.extract), grade each field against the golden
reference, and write one row per field into eval_contracts.db.

Usage:
    python -m evals.run
    python -m evals.run --contracts CreditcardscomInc_..., CybergyHoldingsInc_...
"""
import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from src import extract, parse

from .graders import FIELD_GRADERS, JUDGE_MODEL_VERSION, JUDGE_PROMPT_VERSION, JUDGE_SYSTEM_PROMPT, grade_field

HERE = Path(__file__).parent
GOLDEN_PATH = HERE / "golden.json"
RAW_DIR = Path("data/raw")
DB_PATH = HERE / "data" / "eval_contracts.db"
FAILURE_LOG = HERE / "data" / "failure-log.md"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    run_timestamp TEXT,
    extractor_model_version TEXT,
    extractor_prompt_version TEXT,
    judge_model_version TEXT,
    judge_prompt_version TEXT,
    score REAL,
    total_tokens INTEGER,
    total_wall_ms INTEGER,
    extractor_system_prompt TEXT,
    judge_system_prompt TEXT
);

CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    grader_type TEXT,
    extracted_value TEXT,
    extracted_source_quote TEXT,
    extracted_page_number INTEGER,
    extracted_confidence TEXT,
    golden_value TEXT,
    verdict TEXT,
    reasoning TEXT,
    extraction_tokens INTEGER,
    extraction_wall_ms INTEGER,
    judge_tokens INTEGER,
    judge_wall_ms INTEGER
);
"""

def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn

def load_golden(contract_filter: list[str] | None) -> dict:
    golden = json.loads(GOLDEN_PATH.read_text())
    if contract_filter:
        golden = {k: v for k, v in golden.items() if k in contract_filter}
    return golden

def run(contract_filter: list[str] | None, run_id: str | None) -> None:
    golden = load_golden(contract_filter) ## load golden above, takes a list of contract IDs, 
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") #set run id or use timestamp
    run_timestamp = datetime.now(timezone.utc).isoformat()
    conn = init_db(DB_PATH)
    run_t0 = time.perf_counter()

    verdict_counts = {"correct": 0, "partial": 0, "wrong": 0}
    rows = []
    total_tokens = 0

    failed = 0
    for contract_id, entry in golden.items(): #double loop > goes through each 'entry' for each contract id
        try: ## individual try / exception block for each PDF contract 
            pdf_path = RAW_DIR / entry["pdf_path"] 
            pages = parse.pdf_to_pages(str(pdf_path)) #runs the normal parsing that returns list of dicts
            contract_text = "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in pages) #joins all the text back up to send to claude
            result, extraction_usage, extraction_wall_ms = extract.extract_with_usage(contract_text) ##get the extraction done from main code module
            extraction_tokens = extraction_usage["input_tokens"] + extraction_usage["output_tokens"]
            total_tokens += extraction_tokens ##measure me tokens used, for effeciency and what not.... 

            golden_by_field = {f["field_name"]: f for f in entry["fields"]} #so entry is ... , this ...
            for field_name, clause in result.fields(): ##each result is a contract (dict), with field dicts; loops field name, then clause
                golden_field = golden_by_field.get(field_name)
                if golden_field is None:
                    continue ##dunno what this does if field in none??
                verdict, reasoning, judge_tokens, judge_wall_ms = grade_field(field_name, clause, golden_field) ## GRADING
                #sends to graders.py, grade field, uses FIELD Graders json to decide the TYPE of grading:
                #e.g.  "parties": "set","effective_date": "exact","termination_clause": "judge"
                total_tokens += judge_tokens ##token counting.... 
                verdict_counts[verdict] += 1
                rows.append({ ##the row data below for saving to sql lite db
                    "run_id": run_id,
                    "contract_id": contract_id,
                    "field_name": field_name,
                    "grader_type": FIELD_GRADERS[field_name],
                    "extracted_value": clause.value,
                    "extracted_source_quote": clause.source_quote,
                    "extracted_page_number": clause.page_number,
                    "extracted_confidence": clause.confidence,
                    "golden_value": json.dumps(golden_field["correct_value"]),
                    "verdict": verdict,
                    "reasoning": reasoning,
                    "extraction_tokens": extraction_tokens,
                    "extraction_wall_ms": extraction_wall_ms,
                    "judge_tokens": judge_tokens,
                    "judge_wall_ms": judge_wall_ms,
                })
                print(f"  {contract_id} / {field_name}: {verdict}", flush=True)
        except Exception as e:
            failed += 1
            FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with FAILURE_LOG.open("a") as f:
                f.write(f"- {run_timestamp} | {contract_id} | {e!r}\n")
            print(f"  {contract_id}: FAILED ({e})", flush=True)

    conn.executemany(. ##database connection CONN, runs SQL below to insert these values dynamically
        """
        INSERT INTO eval_results (
            run_id, contract_id, field_name, grader_type, extracted_value, extracted_source_quote,
            extracted_page_number, extracted_confidence, golden_value, verdict, reasoning,
            extraction_tokens, extraction_wall_ms, judge_tokens, judge_wall_ms
        ) VALUES (
            :run_id, :contract_id, :field_name, :grader_type, :extracted_value, :extracted_source_quote,
            :extracted_page_number, :extracted_confidence, :golden_value, :verdict, :reasoning,
            :extraction_tokens, :extraction_wall_ms, :judge_tokens, :judge_wall_ms
        )
        """,
        rows,
    )

    total = sum(verdict_counts.values()) or 1
    score = (verdict_counts["correct"] + 0.5 * verdict_counts["partial"]) / total
    total_wall_ms = int((time.perf_counter() - run_t0) * 1000)
    conn.execute(
        """
        INSERT INTO runs (
            run_id, run_timestamp, extractor_model_version, extractor_prompt_version,
            judge_model_version, judge_prompt_version, score, total_tokens, total_wall_ms,
            extractor_system_prompt, judge_system_prompt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, run_timestamp, extract.MODEL_VERSION, extract.PROMPT_VERSION,
         JUDGE_MODEL_VERSION, JUDGE_PROMPT_VERSION, score, total_tokens, total_wall_ms,
         extract.SYSTEM_PROMPT, JUDGE_SYSTEM_PROMPT),
    )
    conn.commit()
    conn.close()

    print(f"\nrun {run_id}: {verdict_counts} score={score:.2f} "
          f"tokens={total_tokens} time={total_wall_ms / 1000:.1f}s ({failed} contracts failed)")

def _parse_args(argv=None):  ##takes in the args from command line, size of eval (contracts) 
    parser = argparse.ArgumentParser(description="Run the contract-extraction eval suite.")
    parser.add_argument("--contracts", help="Comma-separated contract_ids to run (default: all in golden.json)")
    parser.add_argument("--run-id", help="Override the run id (default: a timestamp)")
    return parser.parse_args(argv) ##example on command line: python -m evals.run --contracts CreditcardscomInc_2020-01-01, CybergyHoldingsInc_2021-05-15 --run-id my_custom_run_id

def main(argv=None) -> None:  #takes in ARGV from command line
    args = _parse_args(argv) #parses the ARGuments ^^ above
    contract_filter = args.contracts.split(",") if args.contracts else None
    run(contract_filter, args.run_id)

if __name__ == "__main__":
    main()
