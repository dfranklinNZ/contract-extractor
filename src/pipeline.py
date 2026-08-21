import argparse
from datetime import datetime, timezone
from pathlib import Path

from . import extract, parse
from .db import init_db, insert_extractions

FAILURE_LOG = Path("notes/failure-log.md")

def _parse_args(argv=None): ## purpose of the function is to parse command-line arguments for the script. It defines the expected arguments, their types, and help messages, and then returns the parsed arguments as an object.
    #NOTE: ARGV captures the command line arguments as a list of strings. 
    parser = argparse.ArgumentParser(description="Extract contract fields from PDFs into SQLite.") ##intialise the parser 
    parser.add_argument("input_dir", help="Directory to search for PDFs (recursively).") ## add a POSITIONAL argument for the INPUT DIRECTOR 
    parser.add_argument("--limit", type=int, default=None, help="Max number of PDFs to process.") ##add an OPTIONAL argument for the LIMIT of PDFs to process, with a default value of None (no limit).
    parser.add_argument("--db", default="data/contracts.db", help="Path to the SQLite database file.") ##add an OPTIONAL argument for the database path, with a default value of "data/contracts.db".
    return parser.parse_args(argv) ##example of using this in command line: UV run python script.py /path/to/input_dir --limit 10 --db /path/to/database.db

def _log_failure(contract_id: str, error: Exception, timestamp: str) -> None:
    FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FAILURE_LOG.open("a") as f:
        f.write(f"- {timestamp} | {contract_id} | {error!r}\n")

def _rows_for_contract(contract_id: str, pages: list[dict], result, model_version: str,
                        prompt_version: str, run_timestamp: str) -> list[dict]:
    pages_by_number = {p["page"]: p["text"] for p in pages} ##creates a dict (translating list[dict] to just dict) that maps page numbers to their corresponding text content. This allows for quick lookup of the text of a specific page by its number.
    rows = [] ##empty rows list 
    for field_name, clause in result.fields(): ## iterates over the fields of the ContractExtraction object (result) firstly by fieldname, then by clause. .fields() is from schema and is the fields(self) function  returning: list[tuple[str, ClauseExtraction]]. (tuple is an immutable list).
        ## so like list["parties", clauseextraction{clause fields}, then "governing_law"...]
        ## below adds a dictionary to rows list for each field in the contract. thus search all fields by contract ID
        rows.append({
            "contract_id": contract_id,
            "field_name": field_name,
            "value": clause.value,
            "source_quote": clause.source_quote,
            "page_number": clause.page_number,
            "confidence": clause.confidence,
            "quote_verified": int(quote_verified),
            "model_version": model_version,
            "prompt_version": prompt_version,
            "run_timestamp": run_timestamp,
        })
    return rows

def run(input_dir: str, limit: int | None, db_path: str) -> None:  ##takes in the input directory, and limit (or NONE), and databse path 
    root = Path(input_dir) ##sets variable root to the path of input directory (full path)
    pdf_paths = sorted(root.rglob("*.pdf")) ## create pdf_paths variable and creates a list: searches for all PDF files in the input directory and its subdirectories, returning a sorted list of Path objects representing the PDF file paths.
    if limit is not None:  ##if limit passed in
        pdf_paths = pdf_paths[:limit] ## then take the pdf_paths list and slice it down to the first limit number of items. This allows the user to process only a subset of the PDFs if desired.

    run_timestamp = datetime.now(timezone.utc).isoformat()
    conn = init_db(db_path) ## initailise a connection object with the database passed in

    all_rows = [] ##empty list to hold all the rows that will be inserted into the database
    processed = 0
    failed = 0

    for pdf_path in pdf_paths:  ##for loop to iterate over pdf paths list 
        contract_id = pdf_path 
        try: ##try block  
            pages = parse.pdf_to_pages(str(pdf_path))  ## creates list[dict] pages variable (FOR THIS LOOP ROUND) - called parse module and pdf to pages function giving it thre path. Returns list of objects/dicts: [{"page": i + 1, "text": p.get_text()},...]
            contract_text = "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in pages) ##creates a contract text string variable that loops through pages list and joins the text to a single string, [page] text 
            result = extract.extract(contract_text) ##creates ContractExtraction results variable that calls the extract module and extract function, passing in the contract text to the message call to LLM.  Returns a ContractExtraction object with the extracted fields. each field is a ClauseExtraction object
            all_rows.extend(_rows_for_contract( ## adds to the variable ABOVE the loop, using the rows for contact function and passing in the id, full pages sting, result objects, then some model variables etc. rows for contract returns a rows: list[dict] so it can be used in db module
                contract_id, pages, result,
                extract.MODEL_VERSION, extract.PROMPT_VERSION, run_timestamp,
            ))
            processed += 1 ##adds to processed counter above the loop 
        except Exception as e: ##if exception found in ANY of above, log the failure 
            _log_failure(contract_id, e, run_timestamp)
            failed += 1 ##add to failed counter above

    insert_extractions(conn, all_rows) ## once loop is complete insert from db module, with database connection and all rows list: rows: list[dict] 
    conn.close()

    print(f"{processed} processed, {failed} failed, {len(all_rows)} rows written to {db_path}")

def main(argv=None) -> None: ## takes argv optional argument, which is a list of command-line arguments. If not provided, it defaults to None, and argparse will use sys.argv by default. The function parses the command-line arguments, and then calls the run function with the parsed arguments.
    args = _parse_args(argv)
    run(args.input_dir, args.limit, args.db)

if __name__ == "__main__":
    main()
