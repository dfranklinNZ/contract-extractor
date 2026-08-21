"""Build evals/golden.json from CUAD's data/master_clauses.csv.

Rerun this any time to regenerate the golden set (e.g. with a different
--sample-size). It only keeps contracts that have a matching PDF under
data/raw/, since those are the only ones the eval suite can actually run.
"""
import argparse
import ast
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

RAW_DIR = Path("data/raw")
CSV_PATH = Path("data/master_clauses.csv")
OUT_PATH = Path(__file__).parent / "golden.json"

# field_name -> CUAD column names. "fallback" columns are used when the
# primary answer is blank (e.g. many contracts leave "Effective Date" blank
# and use "Agreement Date" instead).
FIELD_COLUMNS = {
    "parties": {"answer": "Parties-Answer", "quotes": "Parties"},
    "effective_date": {
        "answer": "Effective Date-Answer", "quotes": "Effective Date",
        "fallback_answer": "Agreement Date-Answer", "fallback_quotes": "Agreement Date",
    },
    "governing_law": {"answer": "Governing Law-Answer", "quotes": "Governing Law"},
    "termination_clause": {"answer": "Termination For Convenience-Answer", "quotes": "Termination For Convenience"},
    "liability_cap": {"answer": "Cap On Liability-Answer", "quotes": "Cap On Liability"},
    "auto_renewal": {"answer": "Renewal Term-Answer", "quotes": "Renewal Term"},
}

def _parse_quote_list(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        parsed = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return []
    return [str(q).strip() for q in parsed if str(q).strip()]

def _clean_party_name(name: str) -> str:
    name = re.sub(r"\([^)]*\)", "", name)  # drop parenthetical aliases like ("Company")
    return name.strip().strip('"').strip()

def _parties(answer: str) -> list[str]:
    return [n for n in (_clean_party_name(p) for p in answer.split(";")) if n]

def build_field(row: dict, field_name: str) -> dict:
    cols = FIELD_COLUMNS[field_name]
    answer = row.get(cols["answer"], "").strip()
    quotes = _parse_quote_list(row.get(cols["quotes"], ""))
    if "fallback_answer" in cols and not answer:
        answer = row.get(cols["fallback_answer"], "").strip()
        quotes = quotes or _parse_quote_list(row.get(cols["fallback_quotes"], ""))

    correct_value = _parties(answer) if field_name == "parties" else answer
    return {
        "field_name": field_name,
        "correct_value": correct_value,
        "acceptable_alternatives": quotes,
    }

def _spread_across_categories(usable: list[dict], pdfs_on_disk: dict, sample_size: int) -> list[dict]:
    by_category = defaultdict(list)
    for row in usable:
        category = pdfs_on_disk[row["Filename"]].parent.name
        by_category[category].append(row)
    for rows in by_category.values():
        rows.sort(key=lambda r: r["Filename"])

    categories = sorted(by_category)
    sample = []
    i = 0
    while len(sample) < sample_size and any(by_category.values()):
        category = categories[i % len(categories)]
        if by_category[category]:
            sample.append(by_category[category].pop(0))
        i += 1
    return sample

def main(sample_size: int, out_path: Path) -> None:
    pdfs_on_disk = {p.name: p for p in RAW_DIR.rglob("*.pdf")}
    with CSV_PATH.open() as f:
        rows = list(csv.DictReader(f))

    usable = [r for r in rows if r["Filename"] in pdfs_on_disk]
    sample = _spread_across_categories(usable, pdfs_on_disk, sample_size)

    golden = {}
    for row in sample:
        contract_id = Path(row["Filename"]).stem
        golden[contract_id] = {
            "pdf_path": pdfs_on_disk[row["Filename"]].relative_to(RAW_DIR).as_posix(),
            "fields": [build_field(row, field_name) for field_name in FIELD_COLUMNS],
        }

    out_path.write_text(json.dumps(golden, indent=2))
    print(f"wrote {len(golden)} contracts to {out_path} (from {len(usable)} usable / {len(rows)} total CUAD rows)")

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = _parse_args()
    main(args.sample_size, args.out)
