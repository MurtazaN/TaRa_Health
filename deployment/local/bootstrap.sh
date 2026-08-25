#!/usr/bin/env bash
# One-command dev setup. Idempotent - safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> Creating virtualenv (if absent)"
[ -d .venv ] || uv venv

# Later steps (initialize_data_stores.py) need the venv's interpreter and
# installed packages, not the system python; `uv pip install` alone does not
# put .venv/bin first on PATH.
source .venv/bin/activate

echo "==> Installing backend with dev extras"
# The spaCy model (en_core_web_lg) installs as a pinned wheel dependency of
# the backend package itself, not a separate `spacy download` - see
# pyproject.toml. That keeps the container, CI, and this venv on one version.
uv pip install -e "./backend[dev]"

echo "==> Seeding .env (if absent)"
[ -f .env ] || cp .env.example .env

echo "==> Initializing local data stores"
cd backend && python scripts/initialize_data_stores.py

cd "$REPO_ROOT"
echo "==> Pre-fetching the pinned embedding model (~1.2 GB, one time)"
python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('Qwen/Qwen3-Embedding-0.6B', \
                    revision='97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3')"

echo
echo "Done. Next:"
echo "  1. Embeddings run in-process — no model server needed for ingestion or search."
echo "  2. For local ANSWERING, start LM Studio and load the model named in TARA_LOCAL_MODEL."
echo "  3. For Agent Platform answering, set TARA_GCP_PROJECT and run:"
echo "       gcloud auth application-default login"
echo "       gcloud auth application-default set-quota-project <PROJECT_ID>"
