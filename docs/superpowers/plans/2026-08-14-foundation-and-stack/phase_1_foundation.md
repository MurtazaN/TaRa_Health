# Phase 1 — Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Restructure the repository into a `backend/` + `frontend/` + `deployment/` monorepo and add the CI, container, and task-runner layer — with zero change to product behaviour.

**Architecture:** The Python package moves wholesale from `src/tara/` to `backend/src/tara/`; the two user-interface files move out of the package into `frontend/`. Only two code paths assume the old layout and both become configuration. Everything else is new files that did not exist before.

**Spec:** [../../specs/2026-08-14-foundation-and-stack-design.md](../../specs/2026-08-14-foundation-and-stack-design.md) §4, §8

**Tech Stack:** git · uv · Docker Compose · GitHub Actions · GNU make

## Global Constraints

- See [README.md](README.md#global-constraints). Every task's requirements implicitly include that section.
- **Phase 1 is behaviour-neutral.** The proof is that the test suite reports exactly `67 passed, 3 skipped` before and after.

## File Structure

| # | Path | Responsibility |
|---|---|---|
| 1 | `backend/src/tara/` | The Python package, moved verbatim |
| 2 | `backend/tests/` | Test suite, moved verbatim |
| 3 | `backend/scripts/` | `initialize_data_stores.py`, moved verbatim |
| 4 | `backend/pyproject.toml` | Moved; dependency list repaired |
| 5 | `frontend/index.html`, `frontend/app.js` | Moved out of `src/tara/web_ui/` |
| 6 | `deployment/docker/Dockerfile.backend` | Backend image |
| 7 | `deployment/docker/compose.yaml` | Service definitions |
| 8 | `deployment/local/bootstrap.sh` | One-command dev setup |
| 9 | `.github/workflows/ci.yml` | Lint, typecheck, test, build |
| 10 | `Makefile` | Task entry points, run from repo root |

---

### Task 1: Move the tree and fix the two path assumptions

**Files:**
- Move: `src/` → `backend/src/`, `tests/` → `backend/tests/`, `scripts/` → `backend/scripts/`, `pyproject.toml` → `backend/pyproject.toml`
- Move: `src/tara/web_ui/templates/index.html` → `frontend/index.html`, `src/tara/web_ui/static/app.js` → `frontend/app.js`
- Modify: `backend/src/tara/config.py` (add `frontend_dir`, fix `env_file`)
- Modify: `backend/src/tara/web_app.py:44-46`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.frontend_dir: Path` — phase 2 and the container both read it.

**Context an engineer needs:**
- Only two places in the codebase assume the current layout: `web_app.py:44` (`_web_dir = Path(__file__).parent / "web_ui"`) and `conftest.py:21` (`Path(__file__).parent / "fixtures"`).
- `conftest.py` needs no change — its path is relative to `tests/`, which moves as a unit.
- `index.html:24` references `/static/app.js`, so mounting `StaticFiles` at `/static` pointing at `frontend/` keeps that URL working with both files in one directory.
- `pydantic-settings` resolves `env_file=".env"` relative to the **current working directory**. Once `pyproject.toml` lives in `backend/`, running `pytest` from `backend/` would look for `backend/.env` and silently find nothing. The fix is an explicit repo-root path with a CWD-relative fallback.
- From `backend/src/tara/config.py`, `Path(__file__).resolve().parents[3]` is the repository root (`[0]`=`tara`, `[1]`=`src`, `[2]`=`backend`, `[3]`=root).

- [ ] **Step 1: Record the baseline test result**

Run: `python -m pytest -q 2>&1 | tail -1`
Expected: `67 passed, 3 skipped, 6 warnings in ...`

Write the number down. It is the acceptance criterion for this task.

- [ ] **Step 2: Create the new directories and move the files**

```bash
mkdir -p backend frontend deployment/docker deployment/local .github/workflows
git mv src/tara/web_ui/templates/index.html frontend/index.html
git mv src/tara/web_ui/static/app.js frontend/app.js
rmdir src/tara/web_ui/templates src/tara/web_ui/static src/tara/web_ui
git mv src backend/src
git mv tests backend/tests
git mv scripts backend/scripts
git mv pyproject.toml backend/pyproject.toml
```

- [ ] **Step 3: Add `frontend_dir` and fix `env_file` in config.py**

In `backend/src/tara/config.py`, replace the `model_config` line inside `class Settings` and add the new setting.

Replace:

```python
    model_config = SettingsConfigDict(env_prefix="TARA_", env_file=".env", extra="ignore")
```

With:

```python
    # `.env` lives at the repository root, but commands may run from `backend/`.
    # Name both so the file is found either way; the CWD-relative entry wins when
    # both exist, and the container supplies plain env vars instead of a file.
    model_config = SettingsConfigDict(
        env_prefix="TARA_",
        env_file=(_REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )
```

Add above `class Settings` (after the `LocalLLMBackend` alias):

```python
# backend/src/tara/config.py -> parents: [0]=tara, [1]=src, [2]=backend, [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
```

Add inside `class Settings`, in the Storage block beneath `db_key`:

```python
    # The user interface lives outside the Python package (monorepo layout), so
    # its location is configuration — the container mounts it elsewhere.
    frontend_dir: Path = Field(default=_REPO_ROOT / "frontend")
```

- [ ] **Step 4: Point web_app.py at the new frontend location**

In `backend/src/tara/web_app.py`, replace lines 44-46:

```python
_web_dir = Path(__file__).parent / "web_ui"
templates = Jinja2Templates(directory=str(_web_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(_web_dir / "static")), name="static")
```

With:

```python
# Templates and static assets share one directory in the monorepo layout;
# index.html references "/static/app.js", so the mount keeps that URL working.
_frontend_dir = get_settings().frontend_dir
templates = Jinja2Templates(directory=str(_frontend_dir))
app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")
```

Add to the imports at the top of `web_app.py`:

```python
from tara.config import get_settings
```

Remove the now-unused `from pathlib import Path` import if nothing else in the file uses `Path`.

- [ ] **Step 5: Reinstall the package from its new location**

The editable install still points at the old path.

```bash
uv pip install -e "./backend[dev]"
```

- [ ] **Step 6: Verify the suite is unchanged**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `67 passed, 3 skipped, 6 warnings in ...` — identical to step 1.

If the count differs, stop. A behaviour-neutral move that changes the test count has broken something.

- [ ] **Step 7: Verify the app still serves the UI**

```bash
cd backend && python -c "
from fastapi.testclient import TestClient
from tara.web_app import app
r = TestClient(app).get('/')
print(r.status_code, '/static/app.js' in r.text)
"
```

Expected: `200 True`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: restructure into backend/frontend/deployment monorepo

Moves src/, tests/, scripts/, and pyproject.toml under backend/, and
lifts the two UI files out of the Python package into frontend/.

Two path assumptions become configuration: Settings.frontend_dir, and
an explicit repo-root .env path so pydantic-settings finds the file
regardless of which directory a command runs from.

No behaviour change: 67 passed, 3 skipped before and after."
```

---

### Task 2: Repair the dependency manifest

**Files:**
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: a dependency list matching what the code imports; phases 2 and 3 add to it.

**Context an engineer needs:**
- Four declared dependencies are not imported anywhere in `backend/src/`. Verified 2026-08-14.
- `sentence-transformers` is also currently unimported, but it is **retained deliberately** — phase 3 uses its `CrossEncoder` class to run the reranker. Do not remove it.
- The `[tool.pytest.ini_options]` comment references a vendored `ECC/` tree that no longer exists. The `testpaths` setting is still correct and stays; only the stale comment goes.

- [ ] **Step 1: Confirm the four dependencies really are unused**

```bash
cd backend && grep -rn "pymupdf4llm\|import docling\|from docling\|import anthropic\|from anthropic" src/ || echo "CONFIRMED: none imported"
```

Expected: `CONFIRMED: none imported`

- [ ] **Step 2: Edit the dependency list**

In `backend/pyproject.toml`, remove these three lines from `dependencies`:

```toml
    "pymupdf4llm>=0.0.17",       # fast path for clean digital PDFs
    "docling>=2.0",              # layout-aware parsing + OCR (primary)
    "anthropic>=0.34",           # swap/extend for whichever hosted provider you choose
```

Add `pymupdf` explicitly, because `text_extraction.py` imports it directly and it was only arriving transitively:

```toml
    "pymupdf>=1.24",             # native-text PDF extraction with word positions (M1)
```

Update the `sentence-transformers` comment to record why it stays:

```toml
    "sentence-transformers>=3.0", # CrossEncoder runtime for the M3 reranker
```

Add an optional group for the deferred OCR dependency:

```toml
ocr = ["docling>=2.0"]           # layout-aware parsing + OCR; pulled in at M6
```

- [ ] **Step 3: Remove the stale pytest comment**

In `backend/pyproject.toml`, replace:

```toml
[tool.pytest.ini_options]
# Only collect the project's own tests. The vendored ECC/ tree ships its own
# conftest.py + test packages, which otherwise clash during collection.
testpaths = ["tests"]
```

With:

```toml
[tool.pytest.ini_options]
# Collect only this package's tests; keeps collection deterministic.
testpaths = ["tests"]
```

- [ ] **Step 4: Reinstall and verify nothing broke**

```bash
uv pip install -e "./backend[dev]" && cd backend && python -m pytest -q 2>&1 | tail -1
```

Expected: `67 passed, 3 skipped, 6 warnings in ...`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build: repair dependency manifest

Removes pymupdf4llm, docling, and anthropic — none imported anywhere in
src/. Declares pymupdf explicitly since text_extraction.py imports it
directly. Moves docling to an [ocr] extra for M6. Retains
sentence-transformers, which becomes the M3 reranker runtime."
```

---

### Task 3: Add the Makefile and the local bootstrap script

**Files:**
- Create: `Makefile`
- Create: `deployment/local/bootstrap.sh`

**Interfaces:**
- Consumes: `backend/pyproject.toml` from Task 2.
- Produces: `make lint`, `make typecheck`, `make test`, `make eval`, `make up`, `make down`, `make run`. CI (Task 5) calls the same targets so local and pipeline behaviour cannot drift.

**Context an engineer needs:**
- Every target runs from the repository root; the ones that need `backend/` as their working directory `cd` there themselves.
- `make eval` is deliberately **not** wired into CI. The DeepEval judge is the local LM Studio model, which a GitHub Actions runner does not have. See spec §8.3.
- The `eval` target will fail until phase 3 builds the harness; it is defined now so the interface is stable.

- [ ] **Step 1: Create the Makefile**

```makefile
.PHONY: install lint typecheck test eval run up down logs clean

BACKEND := backend
COMPOSE := docker compose -f deployment/docker/compose.yaml

install:  ## Install the backend with dev tooling
	uv pip install -e "./$(BACKEND)[dev]"

lint:  ## Static lint
	ruff check $(BACKEND)/src $(BACKEND)/tests

typecheck:  ## Static type check
	cd $(BACKEND) && mypy

test:  ## Unit and integration tests (excludes behavior_evals)
	cd $(BACKEND) && python -m pytest -q --ignore=tests/behavior_evals

eval:  ## DeepEval quality gate. LOCAL ONLY - needs LM Studio running.
	cd $(BACKEND) && python -m pytest tests/behavior_evals -v

run:  ## Run the local server on the host
	cd $(BACKEND) && python -m tara.web_app

up:  ## Start the containerized stack
	$(COMPOSE) up -d

down:  ## Stop the containerized stack
	$(COMPOSE) down

logs:  ## Tail container logs
	$(COMPOSE) logs -f

clean:  ## Remove caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
```

- [ ] **Step 2: Create the bootstrap script**

Create `deployment/local/bootstrap.sh`:

```bash
#!/usr/bin/env bash
# One-command dev setup. Idempotent - safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> Creating virtualenv (if absent)"
[ -d .venv ] || uv venv

echo "==> Installing backend with dev extras"
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
```

- [ ] **Step 3: Make it executable and verify the targets resolve**

```bash
chmod +x deployment/local/bootstrap.sh
make lint && make test
```

Expected: ruff reports no errors; pytest reports `67 passed, 3 skipped`.

- [ ] **Step 4: Commit**

```bash
git add Makefile deployment/local/bootstrap.sh
git commit -m "build: add Makefile and local bootstrap script

Single entry point for lint, typecheck, test, eval, run, and the
container stack. CI calls the same targets so local and pipeline
behaviour cannot drift.

make eval is intentionally excluded from CI: the DeepEval judge is the
local LM Studio model, which a hosted runner does not have."
```

---

### Task 4: Add the backend image and Compose file

**Files:**
- Create: `deployment/docker/Dockerfile.backend`
- Create: `deployment/docker/compose.yaml`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `Settings.frontend_dir` from Task 1; `make up` / `make down` from Task 3.
- Produces: a `tara-backend` service on port 8000. Phase 2 adds the `phoenix` service to the same file.

**Context an engineer needs:**
- **LM Studio stays on the host.** It needs direct graphics-hardware access and cannot usefully run in this container. The backend reaches it through `host.docker.internal`, which Docker Desktop provides on macOS and which the `extra_hosts` entry provides on Linux.
- The container has no `.env` file; Compose passes plain environment variables, which `pydantic-settings` reads with higher precedence anyway.
- `TARA_FRONTEND_DIR` must be set in the container, because the repo-root-relative default computed in `config.py` is wrong once the package is installed into site-packages.
- The build context is the repository root, not `deployment/docker/`, because the image needs both `backend/` and `frontend/`.

- [ ] **Step 1: Create the Dockerfile**

Create `deployment/docker/Dockerfile.backend`:

```dockerfile
# Build context is the REPOSITORY ROOT (see compose.yaml), because the image
# needs both backend/ and frontend/.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# uv resolves and installs far faster than pip on this dependency set.
RUN pip install --no-cache-dir uv

# Dependency layer first, so source edits do not invalidate the install.
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src/tara/__init__.py /app/backend/src/tara/__init__.py
RUN uv pip install --system -e "/app/backend"

COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# The repo-root-relative default in config.py is wrong once installed.
ENV TARA_FRONTEND_DIR=/app/frontend \
    TARA_DATA_DIR=/data

RUN mkdir -p /data && chmod 700 /data
VOLUME ["/data"]

EXPOSE 8000
WORKDIR /app/backend
CMD ["python", "-m", "tara.web_app"]
```

- [ ] **Step 2: Create the Compose file**

Create `deployment/docker/compose.yaml`:

```yaml
# Two services. LM Studio deliberately stays on the HOST - it needs direct
# graphics-hardware access - and the backend reaches it via host.docker.internal.
services:
  tara-backend:
    build:
      context: ../..
      dockerfile: deployment/docker/Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      TARA_LMSTUDIO_HOST: "http://host.docker.internal:1234"
      TARA_OLLAMA_HOST: "http://host.docker.internal:11434"
      TARA_MODEL_MODE: "local"
      TARA_DATA_DIR: "/data"
      TARA_FRONTEND_DIR: "/app/frontend"
    volumes:
      - tara-data:/data
    extra_hosts:
      # Docker Desktop supplies this on macOS; the mapping is needed on Linux.
      - "host.docker.internal:host-gateway"

volumes:
  tara-data:
```

- [ ] **Step 3: Create the .dockerignore**

Create `.dockerignore` at the repository root:

```
.git/
.venv/
venv/
.env
.tara_data/
**/__pycache__/
**/*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
docs/
graphify-out/
.claude/
```

- [ ] **Step 4: Build and verify the container serves the UI**

```bash
make up
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: `200`

- [ ] **Step 5: Tear down**

```bash
make down
```

- [ ] **Step 6: Commit**

```bash
git add deployment/docker/ .dockerignore
git commit -m "build: containerize the backend

Adds Dockerfile.backend and compose.yaml. Build context is the repo root
because the image needs backend/ and frontend/ together.

LM Studio stays on the host by design - it needs graphics-hardware
access - so the container reaches it via host.docker.internal.
TARA_FRONTEND_DIR is set explicitly because the repo-root-relative
default is wrong once the package is installed to site-packages."
```

---

### Task 5: Add the CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the `make` targets from Task 3.
- Produces: a required status check on every push and pull request.

**Context an engineer needs:**
- The pipeline calls the same `make` targets a developer runs locally, so the two cannot diverge.
- **The evaluation gate is deliberately absent.** See spec §8.3 — the DeepEval judge is a local model that a hosted runner does not have. Do not add it here.
- Jobs run in parallel; `build` does not depend on `test`, because a Docker build failure and a test failure are independent signals.

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

env:
  PYTHON_VERSION: "3.12"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: uv pip install --system -e "./backend[dev]"
      - run: make lint

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: uv pip install --system -e "./backend[dev]"
      - run: make typecheck

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: uv pip install --system -e "./backend[dev]"
      # No LM Studio on a hosted runner; the suite is offline by design
      # (conftest replaces the embedder with a deterministic fake).
      - run: make test

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f deployment/docker/Dockerfile.backend -t tara-backend:ci .
```

- [ ] **Step 2: Verify the workflow parses**

```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('valid YAML')"
```

Expected: `valid YAML`

- [ ] **Step 3: Verify each job's command succeeds locally**

```bash
make lint && make typecheck && make test
```

Expected: no lint errors, no type errors, `67 passed, 3 skipped`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline

Four parallel jobs - lint, typecheck, test, build - each calling the
same make targets a developer runs locally, so the two cannot drift.

The DeepEval gate is deliberately excluded: its judge is the local
LM Studio model, which a hosted runner does not have. It runs via
make eval before merge instead."
```

---

### Task 6: Update the documentation to match the new layout

**Files:**
- Modify: `CLAUDE.md` (Commands section, Architecture section, repository layout)
- Modify: `docs/epic1_grounded_qa/README.md` (Repository layout section, ~lines 167-198)
- Modify: `docs/Epic2_first_actions.md` (Repository layout deltas, ~lines 302-315)
- Modify: `README.md` (quickstart commands)

**Interfaces:**
- Consumes: the final layout from Tasks 1-5.
- Produces: documentation an engineer can follow without hitting a stale path.

**Context an engineer needs:**
- Every design document states the repository layout as settled fact. Leaving them stale means the next contributor — human or agent — is told to create files in directories that no longer exist.
- Keep the bulleted format; these files follow the project's no-prose rule.
- Epics 3 and 4 do not restate the layout, so they need no change. Verify with the grep in step 1.

- [ ] **Step 1: Find every stale path reference**

```bash
grep -rn "src/tara\|pip install -e\|python scripts/\|web_ui" CLAUDE.md README.md docs/*.md docs/epic1_grounded_qa/*.md | grep -v superpowers
```

Every hit is a line to update or confirm.

- [ ] **Step 2: Update the CLAUDE.md Commands block**

Replace the commands block with:

```bash
./deployment/local/bootstrap.sh   # one-command setup (venv, install, .env, data stores)
make install                      # install backend with dev tools
make test                         # run tests
make lint                         # ruff
make typecheck                    # mypy
make run                          # local server at http://127.0.0.1:8000
make up / make down               # containerized stack
make eval                         # DeepEval gate (local only; needs LM Studio)

cd backend && python -m pytest tests/safety_checks/test_emergency_triage.py   # single file
```

- [ ] **Step 3: Update the layout tree in `docs/epic1_grounded_qa/README.md`**

Replace the `tara-health/` tree so the package sits under `backend/src/tara/`, the UI under `frontend/`, and add `deployment/`, `.github/workflows/`, and `Makefile`. Keep every existing per-directory comment — they describe module responsibilities, which have not changed. Remove the `web_ui/` line from the package tree and note the UI now lives at the repository root.

- [ ] **Step 4: Update the layout delta in `docs/Epic2_first_actions.md`**

Prefix the `agent_orchestration/` and `agent_tools/` paths with `backend/src/tara/`.

- [ ] **Step 5: Update the README quickstart**

Replace the install and run commands with the `make` targets from step 2.

- [ ] **Step 6: Verify no stale references remain**

```bash
grep -rn "src/tara" CLAUDE.md README.md docs/*.md docs/epic1_grounded_qa/*.md | grep -v "backend/src/tara" | grep -v superpowers || echo "CLEAN"
```

Expected: `CLEAN`

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md README.md docs/
git commit -m "docs: update repository layout for the monorepo restructure

Every design doc stated the old src/tara/ layout as settled fact.
Updates CLAUDE.md, the Epic 1 README layout tree, the Epic 2 layout
delta, and the root README quickstart. Epics 3 and 4 do not restate
the layout and need no change."
```

---

## Phase 1 acceptance

- [ ] `make test` reports `67 passed, 3 skipped` — identical to the pre-restructure baseline.
- [ ] `make lint` and `make typecheck` are clean.
- [ ] `make up` then `curl http://127.0.0.1:8000/` returns `200`.
- [ ] `grep -rn "src/tara" CLAUDE.md README.md docs/*.md docs/epic1_grounded_qa/*.md | grep -v "backend/src/tara"` is empty.
- [ ] No file under `backend/src/tara/` has changed except `config.py` and `web_app.py`.
