# scripts/download_cuad.py
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="theatticusproject/cuad",
    repo_type="dataset",              # default is "model" — wrong repo namespace without this
    allow_patterns=["CUAD_v1/full_contract_pdf/*", "CUAD_v1/master_clauses.csv"],
    local_dir="data/cuad",            # files land here, mirroring the repo's folder structure
)