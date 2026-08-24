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

echo
echo "Done. Next:"
echo "  1. Start LM Studio and load the model named in TARA_LOCAL_MODEL"
echo "  2. make test    # verify the install"
echo "  3. make run     # serve on http://127.0.0.1:8000"
