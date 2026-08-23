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
uv pip install -e "./backend[dev]"

echo "==> Downloading the spaCy model Presidio needs"
# en_core_web_lg (~427MB): the smaller models miss names in benefits-document
# formats (ALL-CAPS headers, label:value fragments) - see config.py.
python -m spacy download en_core_web_lg

echo "==> Seeding .env (if absent)"
[ -f .env ] || cp .env.example .env

echo "==> Initializing local data stores"
cd backend && python scripts/initialize_data_stores.py

echo
echo "Done. Next:"
echo "  1. Start LM Studio and load the model named in TARA_LOCAL_MODEL"
echo "  2. make test    # verify the install"
echo "  3. make run     # serve on http://127.0.0.1:8000"
