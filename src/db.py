import sqlite3 ## code for sql lite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value TEXT,
    source_quote TEXT,
    page_number INTEGER,
    confidence TEXT,
    quote_verified INTEGER,
    model_version TEXT,
    prompt_version TEXT,
    run_timestamp TEXT
)
""" ## table schema - only creates if nothing exists. table name "extractions" 

def init_db(path: str) -> sqlite3.Connection:  ## takes in a path, returns a connection to the database
    conn = sqlite3.connect(path) ## creates a connection to the database at the given path
    conn.execute(_SCHEMA)  ## executes the schema to create the table if it doesn't exist
    conn.commit() ## commits the changes to the database
    return conn ## returns the connection object

def insert_extractions(conn: sqlite3.Connection, rows: list[dict]) -> None: ## takes in a connection and a list of dicts "the ROWs", inserts the data into the database
    conn.executemany( 
        """
        INSERT INTO extractions (
            contract_id, field_name, value, source_quote, page_number,
            confidence, quote_verified, model_version, prompt_version, run_timestamp
        ) VALUES (
            :contract_id, :field_name, :value, :source_quote, :page_number,
            :confidence, :quote_verified, :model_version, :prompt_version, :run_timestamp
        )
        """,
        rows, ## the list of dicts to be inserted into the database, assume this maps to the :column name
    )
    conn.commit() ##commits the change to the database

    ##write a function to query the database and return all rows for a given contract_id
def get_extractions_by_contract_id(conn: sqlite3.Connection, contract_id: str) -> list[dict]: ## takes in a connection and a contract_id, returns a list of dicts
    cursor = conn.execute(
        """
        SELECT * FROM extractions WHERE contract_id = ?
        """,
        (contract_id,),
    )
    rows = cursor.fetchall() ## fetches all rows that match the contract_id
    return [dict(row) for row in rows] ## returns a list of dicts, each dict represents a row in the database


##sqlite3 data/contracts.db "select contract_id, field_name, value, page_number, confidence, quote_verified from extractions order by contract_id, field_name;" -header -column
