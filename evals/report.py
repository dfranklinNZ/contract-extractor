"""Generate a static HTML report from eval_contracts.db.

No server, no template engine — just reads the DB and writes plain HTML you
can open directly in a browser. Rerun after every eval run to refresh it.

Three sections:
- Runs summary: one row per run, with a delta-vs-previous-run score column.
- Compare Runs: a pivot of verdict per (contract, field) across the most
  recent runs, so you can see exactly what flipped between two runs.
- Per-run detail: collapsible, one per run, with the full prompt text used
  and the per-field breakdown (now including which grader graded it).
"""
from html import escape
from pathlib import Path
import sqlite3

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "eval_contracts.db"
OUT_PATH = HERE / "report.html"

MAX_RUNS_IN_COMPARISON = 10

_STYLE = """
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; max-width: 1200px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 0.9rem; vertical-align: top; }
th { background: #f4f4f4; }
.correct { color: #1a7f37; font-weight: 600; }
.partial { color: #9a6700; font-weight: 600; }
.wrong { color: #cf222e; font-weight: 600; }
.delta-up { color: #1a7f37; }
.delta-down { color: #cf222e; }
pre { white-space: pre-wrap; background: #f6f8fa; padding: 0.75rem; border-radius: 4px; font-size: 0.85rem; }
details { margin-bottom: 1.5rem; }
summary { cursor: pointer; font-weight: 600; }
</style>
"""

def _cell(value, limit: int = 100) -> str:
    text = "" if value is None else str(value)
    if len(text) > limit:
        text = text[:limit] + "…"
    return escape(text)

def _verdict_cell(verdict: str | None) -> str:
    if not verdict:
        return "–"
    return f'<span class="{escape(verdict)}">{escape(verdict)}</span>'

def _delta_cell(delta: float | None) -> str:
    if delta is None:
        return "—"
    css_class = "delta-up" if delta > 0 else "delta-down" if delta < 0 else ""
    return f'<span class="{css_class}">{delta:+.2f}</span>'

def _fetch_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM runs ORDER BY run_timestamp ASC").fetchall()

def _score_deltas(runs_asc: list[sqlite3.Row]) -> dict[str, float | None]:
    deltas: dict[str, float | None] = {}
    previous_score = None
    for run in runs_asc:
        deltas[run["run_id"]] = None if previous_score is None else run["score"] - previous_score
        previous_score = run["score"]
    return deltas

def _build_runs_summary(runs_asc: list[sqlite3.Row], deltas: dict[str, float | None]) -> list[str]:
    html = ["<h1>Eval Runs</h1>"]
    html.append(
        "<table><tr><th>run_id</th><th>timestamp</th><th>extractor</th>"
        "<th>judge</th><th>score</th><th>Δ score</th><th>tokens</th><th>time</th></tr>"
    )
    for run in reversed(runs_asc):  # newest first for display
        html.append(
            f"<tr><td>{_cell(run['run_id'])}</td><td>{_cell(run['run_timestamp'])}</td>"
            f"<td>{_cell(run['extractor_model_version'])} / {_cell(run['extractor_prompt_version'])}</td>"
            f"<td>{_cell(run['judge_model_version'])} / {_cell(run['judge_prompt_version'])}</td>"
            f"<td>{run['score']:.2f}</td><td>{_delta_cell(deltas[run['run_id']])}</td>"
            f"<td>{run['total_tokens']}</td><td>{run['total_wall_ms'] / 1000:.1f}s</td></tr>"
        )
    html.append("</table>")
    return html

def _build_comparison(conn: sqlite3.Connection, runs_asc: list[sqlite3.Row]) -> list[str]:
    compared_runs = runs_asc[-MAX_RUNS_IN_COMPARISON:]
    run_ids = [r["run_id"] for r in compared_runs]
    if not run_ids:
        return []

    placeholders = ",".join("?" * len(run_ids))
    results = conn.execute(
        f"SELECT contract_id, field_name, grader_type, run_id, verdict "
        f"FROM eval_results WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()

    pivot: dict[tuple[str, str], dict] = {}
    for r in results:
        key = (r["contract_id"], r["field_name"])
        entry = pivot.setdefault(key, {"grader_type": r["grader_type"], "verdicts": {}})
        entry["verdicts"][r["run_id"]] = r["verdict"]

    html = [f"<h1>Compare Runs (last {len(run_ids)})</h1>"]
    header_cells = "".join(f"<th>{_cell(rid, 20)}</th>" for rid in run_ids)
    html.append(f"<table><tr><th>contract</th><th>field</th><th>grader</th>{header_cells}</tr>")
    for (contract_id, field_name), entry in sorted(pivot.items()):
        row_cells = "".join(
            f"<td>{_verdict_cell(entry['verdicts'].get(rid))}</td>" for rid in run_ids
        )
        html.append(
            f"<tr><td>{_cell(contract_id, 60)}</td><td>{_cell(field_name)}</td>"
            f"<td>{_cell(entry['grader_type'])}</td>{row_cells}</tr>"
        )
    html.append("</table>")
    return html

def _build_run_detail(conn: sqlite3.Connection, run: sqlite3.Row) -> list[str]:
    html = [f"<details><summary>{_cell(run['run_id'])} (score {run['score']:.2f})</summary>"]
    html.append(
        f"<p>extractor: {_cell(run['extractor_model_version'])} / {_cell(run['extractor_prompt_version'])} "
        f"&nbsp;|&nbsp; judge: {_cell(run['judge_model_version'])} / {_cell(run['judge_prompt_version'])} "
        f"&nbsp;|&nbsp; tokens: {run['total_tokens']} &nbsp;|&nbsp; time: {run['total_wall_ms'] / 1000:.1f}s</p>"
    )
    html.append(
        f"<details><summary>extractor system prompt</summary>"
        f"<pre>{escape(run['extractor_system_prompt'] or '')}</pre></details>"
    )
    html.append(
        f"<details><summary>judge system prompt</summary>"
        f"<pre>{escape(run['judge_system_prompt'] or '')}</pre></details>"
    )

    html.append(
        "<table><tr><th>contract</th><th>field</th><th>grader</th><th>extracted</th>"
        "<th>golden</th><th>verdict</th><th>reasoning</th></tr>"
    )
    results = conn.execute(
        "SELECT * FROM eval_results WHERE run_id = ? ORDER BY contract_id, field_name",
        (run["run_id"],),
    ).fetchall()
    for r in results:
        html.append(
            f"<tr><td>{_cell(r['contract_id'], 60)}</td><td>{_cell(r['field_name'])}</td>"
            f"<td>{_cell(r['grader_type'])}</td>"
            f"<td>{_cell(r['extracted_value'])}</td><td>{_cell(r['golden_value'])}</td>"
            f"<td>{_verdict_cell(r['verdict'])}</td><td>{_cell(r['reasoning'], 150)}</td></tr>"
        )
    html.append("</table></details>")
    return html

def build_report(conn: sqlite3.Connection) -> str:
    conn.row_factory = sqlite3.Row
    runs_asc = _fetch_runs(conn)
    deltas = _score_deltas(runs_asc)

    html = [f"<html><head><title>Eval Report</title>{_STYLE}</head><body>"]
    html += _build_runs_summary(runs_asc, deltas)
    html += _build_comparison(conn, runs_asc)
    html.append("<h1>Run Detail</h1>")
    for run in reversed(runs_asc):  # newest first
        html += _build_run_detail(conn, run)
    html.append("</body></html>")
    return "\n".join(html)

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    OUT_PATH.write_text(build_report(conn))
    conn.close()
    print(f"wrote {OUT_PATH}")

if __name__ == "__main__":
    main()
