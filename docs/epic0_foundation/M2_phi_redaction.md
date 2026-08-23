# Epic 0 · M2 — phi_redaction

- **Parent:** [Epic 0 — Foundation](README.md) — overview · decisions · build order · global constraints.
- **Seams:** depends on [M1](M1_repo_restructure.md). Supplies `redact_phi()` to two independent consumers: [M3 execution_tracing](M3_execution_tracing.md), which redacts span attributes, and the Epic 1 M4 hosted-egress path per [M4 §3.1](M4_epic1_handoff.md). Neither consumer is a prerequisite for this module.

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Strip protected health information out of any text before it leaves the process, so infrastructure can carry the clinical and cost content without carrying identity.

**Architecture:** One kernel root module, `phi_redaction.py`, wrapping Presidio's analyzer and anonymizer. Two custom recognizers add the insurance member and group identifiers Presidio's stock entity set misses. A recall fixture over realistic benefit-document text measures whether it actually works, because a PHI safeguard whose recall is unmeasured is a claim, not a control.

**Design sections:** [Epic 0 README](README.md) §5 row 1, §6.2

**Tech Stack:** Presidio (analyzer + anonymizer) · spaCy `en_core_web_sm`

**Why this is its own module** (split from the original combined M2 on 2026-08-15):

- `phi_redaction.py` is a **kernel** module; `execution_tracing/` is a **plane** that depends on it. Bundling a kernel module with one of its consumers inverts the layering the project enforces everywhere else.
- It has a **second consumer independent of tracing** — the Epic 1 M4 hosted-egress path. If tracing slips or is reworked, redaction must not be entangled with it.
- It is the **security-critical half**, and it earns its own review gate. The Epic 0 M1 final review demonstrated that security defects hide in the seams between concerns.

## Global Constraints

- See [README.md](README.md#global-constraints). Every task's requirements implicitly include that section.
- **This module is behaviour-neutral for the running app.** Nothing calls `redact_phi()` until M3. The suite must stay at `67 passed, 3 skipped` plus the tests this module adds.
- **Redaction must never be silently disabled.** `phi_redaction_enabled` defaults to `true`; a caller must not have to check it.

## File Structure

| # | Path | Responsibility |
|---|---|---|
| 1 | `backend/src/tara/phi_redaction.py` | Kernel. `redact_phi(text) -> str`. |
| 2 | `backend/tests/test_phi_redaction.py` | Unit tests over synthetic strings. |
| 3 | `backend/tests/fixtures/phi_recall_cases.py` | Labelled recall fixture — realistic document text with the spans that must be caught. |
| 4 | `backend/tests/test_phi_redaction_recall.py` | The recall gate over fixture 3. |

---

### Task 1: Add the Presidio dependencies and redaction settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/tara/config.py`
- Modify: `deployment/local/bootstrap.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: M1's repaired manifest.
- Produces: `Settings.phi_redaction_enabled: bool`, `Settings.phi_redaction_nlp_model: str`. Task 2 reads both; M3 reads neither directly.

**Context an engineer needs:**
- **Presidio needs a spaCy language model at runtime.** Its default is `en_core_web_lg` (~600 MB). This plan pins `en_core_web_sm` (~12 MB), configured explicitly, so a laptop install and a CI runner stay light and deterministic. Accuracy improves with `en_core_web_lg`; swapping is a one-setting change, which is why the model name is configuration.
- The OpenTelemetry dependencies are **not** added here — they belong to [M3](M3_execution_tracing.md) Task 1.

- [ ] **Step 1: Add the dependencies**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    # PHI redaction before any span export or hosted egress
    "presidio-analyzer>=2.2",
    "presidio-anonymizer>=2.2",
```

- [ ] **Step 2: Add the settings**

In `backend/src/tara/config.py`, add inside `class Settings`, after the Timeouts block:

```python
    # ---- PHI redaction (README §6.2) ----
    # On by default: this module exists so infrastructure can carry clinical
    # content without carrying identity. A caller must never have to check it.
    phi_redaction_enabled: bool = True
    # Presidio defaults to en_core_web_lg (~600MB). en_core_web_sm (~12MB) keeps
    # a laptop install and a CI runner light; swap to _lg for better recall.
    phi_redaction_nlp_model: str = "en_core_web_sm"
```

- [ ] **Step 3: Add the spaCy model download to the bootstrap script**

In `deployment/local/bootstrap.sh`, after the install step and before the data-store initialization, insert:

```bash
echo "==> Downloading the spaCy model Presidio needs"
python -m spacy download en_core_web_sm
```

- [ ] **Step 4: Add the same download to the CI test job**

In `.github/workflows/ci.yml`, in the `test` job only, insert before `- run: make test`:

```yaml
      - run: python -m spacy download en_core_web_sm
```

- [ ] **Step 5: Document both settings**

Append to `.env.example`, in the same style as the existing sections:

```bash
# ---- PHI redaction ----
# On by default. Redaction is what makes tracing and hosted egress safe on a
# health corpus; disable it only for local debugging on synthetic data.
TARA_PHI_REDACTION_ENABLED=true
# en_core_web_sm (12MB) keeps installs light; en_core_web_lg (600MB) has better recall.
TARA_PHI_REDACTION_NLP_MODEL=en_core_web_sm
```

- [ ] **Step 6: Install and verify nothing changed**

```bash
uv pip install -e "./backend[dev]" && python -m spacy download en_core_web_sm
cd backend && python -m pytest -q 2>&1 | grep -E "passed|failed" | tail -1
```

Expected: `67 passed, 3 skipped, ...`

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/src/tara/config.py deployment/local/bootstrap.sh .github/workflows/ci.yml .env.example
git commit -m "build: add Presidio dependencies and PHI-redaction settings

Both settings default to the safe position, so this commit changes
nothing observable.

Pins spaCy en_core_web_sm (12MB) over Presidio's en_core_web_lg
default (600MB) so laptop and CI installs stay light; the model name
is a setting, so upgrading recall is a config change."
```

---

### Task 2: Build the PHI redaction module

**Files:**
- Create: `backend/src/tara/phi_redaction.py`
- Test: `backend/tests/test_phi_redaction.py`

**Interfaces:**
- Consumes: `Settings.phi_redaction_enabled`, `Settings.phi_redaction_nlp_model` from Task 1.
- Produces: `redact_phi(text: str) -> str`. Consumed by Task 3's recall gate, by [M3](M3_execution_tracing.md)'s `redact_span_attributes()`, and at Epic 1 M4 by the hosted-egress path.

**Context an engineer needs:**
- This is a **kernel root module**, not a package — it is one concept, and the naming rules forbid one-concept packages.
- Presidio's stock entity set does not cover insurance identifiers. Two custom `PatternRecognizer` instances add member and group numbers, which appear throughout benefits documents.
- The engines are expensive to construct, so both are cached with `lru_cache`.
- Presidio's default anonymizer operator replaces a match with `<ENTITY_TYPE>`, which is exactly what a trace wants: the shape of the value without the value.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_phi_redaction.py`:

```python
"""PHI redaction is what makes tracing safe on a health corpus - test it hard."""
from __future__ import annotations

import pytest

from tara import config
from tara.phi_redaction import redact_phi


@pytest.fixture
def redaction_on(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.integration
def test_person_name_is_removed(redaction_on):
    redacted = redact_phi("Patient Michael Okonkwo was seen on Tuesday.")
    assert "Michael Okonkwo" not in redacted
    assert "<PERSON>" in redacted


@pytest.mark.integration
def test_phone_number_is_removed(redaction_on):
    redacted = redact_phi("Call the office at 617-555-0142 to confirm.")
    assert "617-555-0142" not in redacted


@pytest.mark.integration
def test_insurance_member_id_is_removed(redaction_on):
    redacted = redact_phi("Member ID: XQZ8842190 is active through December.")
    assert "XQZ8842190" not in redacted
    assert "<INSURANCE_MEMBER_ID>" in redacted


@pytest.mark.integration
def test_insurance_group_id_is_removed(redaction_on):
    redacted = redact_phi("Group # 55210 covers the specialist visit.")
    assert "<INSURANCE_GROUP_ID>" in redacted


@pytest.mark.integration
def test_clinical_content_survives_redaction(redaction_on):
    """The point of redaction is to keep the medicine and drop the identity."""
    redacted = redact_phi("Michael Okonkwo has a specialist copay of $40.")
    assert "specialist copay" in redacted
    assert "$40" in redacted


def test_disabled_redaction_passes_text_through(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "false")
    config.get_settings.cache_clear()
    original = "Patient Michael Okonkwo, member ID XQZ8842190."
    assert redact_phi(original) == original
    config.get_settings.cache_clear()


def test_empty_text_is_returned_unchanged(redaction_on):
    assert redact_phi("") == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_phi_redaction.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tara.phi_redaction'`

- [ ] **Step 3: Write the implementation**

Create `backend/src/tara/phi_redaction.py`:

```python
"""Removes protected health information from text before it leaves the process.

Self-hosting the trace backend protects the destination; this module protects
the payload. A redacted span keeps the clinical and cost content a trace exists
to show, while dropping the identity that makes it protected health information.
"""
from __future__ import annotations

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from tara.config import get_settings

# Insurance identifiers Presidio's stock entity set does not cover. They appear
# throughout benefits summaries and explanation-of-benefits documents.
INSURANCE_MEMBER_ID_ENTITY = "INSURANCE_MEMBER_ID"
INSURANCE_GROUP_ID_ENTITY = "INSURANCE_GROUP_ID"

REDACTED_ENTITIES = [
    "PERSON",
    "DATE_TIME",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "US_SSN",
    "LOCATION",
    "MEDICAL_LICENSE",
    INSURANCE_MEMBER_ID_ENTITY,
    INSURANCE_GROUP_ID_ENTITY,
]


def _insurance_member_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_MEMBER_ID_ENTITY,
        patterns=[Pattern(
            name="member_id",
            regex=r"(?:Member|Subscriber)\s*(?:ID|Number|No\.?|#)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{4,}",
            score=0.85,
        )],
    )


def _insurance_group_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_GROUP_ID_ENTITY,
        patterns=[Pattern(
            name="group_id",
            regex=r"(?:Group)\s*(?:ID|Number|No\.?|#)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{3,}",
            score=0.85,
        )],
    )


@lru_cache(maxsize=1)
def _analyzer_engine() -> AnalyzerEngine:
    """Build the analyzer once. Constructing it loads a language model."""
    nlp_engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{
            "lang_code": "en",
            "model_name": get_settings().phi_redaction_nlp_model,
        }],
    }).create_engine()
    analyzer_engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    analyzer_engine.registry.add_recognizer(_insurance_member_id_recognizer())
    analyzer_engine.registry.add_recognizer(_insurance_group_id_recognizer())
    return analyzer_engine


@lru_cache(maxsize=1)
def _anonymizer_engine() -> AnonymizerEngine:
    return AnonymizerEngine()


def redact_phi(text: str) -> str:
    """Return `text` with PHI entities replaced by `<ENTITY_TYPE>` placeholders.

    A no-op when `phi_redaction_enabled` is false or the text is empty, so the
    caller never has to branch.
    """
    if not text or not get_settings().phi_redaction_enabled:
        return text
    analyzer_results = _analyzer_engine().analyze(
        text=text, language="en", entities=REDACTED_ENTITIES,
    )
    if not analyzer_results:
        return text
    return _anonymizer_engine().anonymize(
        text=text, analyzer_results=analyzer_results,
    ).text
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_phi_redaction.py -q`
Expected: `8 passed`

If `test_insurance_group_id_is_removed` fails, check that the group-number regex tolerates the space in `Group # 55210`. Adjust the regex, not the test.

- [ ] **Step 5: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `75 passed, 3 skipped, ...`

- [ ] **Step 6: Commit**

```bash
git add backend/src/tara/phi_redaction.py backend/tests/test_phi_redaction.py
git commit -m "feat: add PHI redaction over Presidio

Kernel root module (one concept, so not a package). Wraps Presidio's
analyzer and anonymizer, adding two custom recognizers for insurance
member and group identifiers that the stock entity set misses.

Keeps clinical and cost content intact while dropping identity - that
separation is what makes tracing a health corpus safe."
```


---

### Task 3: Measure redaction recall against realistic document text

**Files:**
- Create: `backend/tests/fixtures/phi_recall_cases.py`
- Create: `backend/tests/test_phi_redaction_recall.py`

**Interfaces:**
- Consumes: `redact_phi(text)` from Task 2.
- Produces: a recall figure and a gate. No production code.

**Context an engineer needs:**
- **Why this task exists.** Task 2's tests use short synthetic strings — `"Patient Michael Okonkwo was seen on Tuesday."` A real benefits summary or explanation-of-benefits carries identifiers in table cells, headers, and footers, in formats Presidio's stock recognizers may miss entirely. The same standard the project applies to Llama Guard applies here: **trust is earned by a fixture, not by a library's reputation.**
- **This is a measurement task, not a tuning task.** Record the number the fixture produces. If recall is below the gate, the remedy is another custom recognizer — but adding recognizers to chase a number you have not measured is guesswork.
- **The fixture must be synthetic.** Invent names, member numbers, and dates. Never paste real health-document text into the repository.

- [ ] **Step 1: Write the labelled fixture**

Create `backend/tests/fixtures/phi_recall_cases.py`. Each case is a realistic text fragment plus the exact substrings that MUST be removed. Write at least twelve cases spanning the shapes below — the point is coverage of formats, not volume.

```python
"""Labelled PHI-recall cases. All content is synthetic - never paste real
document text into this repository.

Each case pairs a realistic fragment with the substrings redaction MUST
remove. `must_survive` guards the other half of the contract: redaction that
also destroys the clinical or cost content is useless.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhiRecallCase:
    label: str
    text: str
    must_remove: tuple[str, ...]
    must_survive: tuple[str, ...] = field(default=())


PHI_RECALL_CASES: tuple[PhiRecallCase, ...] = (
    PhiRecallCase(
        label="benefits_header_member_and_group",
        text="AETNA CHOICE POS II\nMember: Priya Raghunathan   Member ID: W8842190113\n"
             "Group #: 0847221   Effective: 01/01/2026\nSpecialist office visit: $40 copay",
        must_remove=("Priya Raghunathan", "W8842190113", "0847221"),
        must_survive=("Specialist office visit", "$40"),
    ),
    PhiRecallCase(
        label="eob_table_row",
        text="Patient          Date of Service   Billed    Plan Paid   You Owe\n"
             "Okonkwo, Michael 03/14/2026        $412.00   $329.60     $82.40",
        must_remove=("Okonkwo, Michael",),
        must_survive=("$412.00", "$82.40"),
    ),
    PhiRecallCase(
        label="lab_report_with_dob_and_mrn",
        text="LabCorp Results — Wei Chen, DOB 08/22/1984, MRN 4471902\n"
             "Hemoglobin A1c: 6.1% (ref 4.0-5.6%)",
        must_remove=("Wei Chen", "08/22/1984", "4471902"),
        must_survive=("Hemoglobin A1c", "6.1%"),
    ),
    # Continue to at least twelve cases. Required additional shapes:
    #  - subscriber vs dependent named on the same line
    #  - a phone number in a plan footer
    #  - an address block
    #  - a member ID with no label preceding it, inside a table
    #  - a name in ALL CAPS
    #  - a hyphenated surname and a name with a particle ("van der Berg")
    #  - a prescription label with prescriber and patient both named
    #  - a date written as "March 14, 2026" rather than numerically
    #  - a claim number that must NOT be redacted (it identifies a claim, not a person)
)
```

- [ ] **Step 2: Write the recall gate**

Create `backend/tests/test_phi_redaction_recall.py`:

```python
"""Recall gate for PHI redaction.

A PHI safeguard whose recall is unmeasured is a claim, not a control. This
module reports the number and fails below the gate.
"""
from __future__ import annotations

import pytest

from tara import config
from tara.phi_redaction import redact_phi
from tests.fixtures.phi_recall_cases import PHI_RECALL_CASES

# Every labelled identifier must be removed. This starts at 100% deliberately:
# a miss is a real PHI leak, so the gate should fail loudly and the remedy is a
# new custom recognizer, not a lowered threshold.
REQUIRED_RECALL = 1.0


@pytest.fixture(autouse=True)
def redaction_on(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.parametrize("case", PHI_RECALL_CASES, ids=lambda c: c.label)
def test_every_labelled_identifier_is_removed(case):
    redacted = redact_phi(case.text)
    leaked = [secret for secret in case.must_remove if secret in redacted]
    assert not leaked, f"{case.label}: PHI survived redaction: {leaked}"


@pytest.mark.integration
@pytest.mark.parametrize("case", PHI_RECALL_CASES, ids=lambda c: c.label)
def test_clinical_and_cost_content_survives(case):
    redacted = redact_phi(case.text)
    destroyed = [keep for keep in case.must_survive if keep not in redacted]
    assert not destroyed, f"{case.label}: redaction destroyed needed content: {destroyed}"


@pytest.mark.integration
def test_aggregate_recall_meets_the_gate(capsys):
    """Report the corpus-wide recall figure, then gate on it."""
    total = sum(len(case.must_remove) for case in PHI_RECALL_CASES)
    caught = sum(
        1
        for case in PHI_RECALL_CASES
        for secret in case.must_remove
        if secret not in redact_phi(case.text)
    )
    recall = caught / total
    with capsys.disabled():
        print(f"\nPHI redaction recall: {caught}/{total} = {recall:.1%}")
    assert recall >= REQUIRED_RECALL, f"recall {recall:.1%} below gate {REQUIRED_RECALL:.0%}"
```

- [ ] **Step 3: Run the gate and record the real number**

Run: `cd backend && python -m pytest tests/test_phi_redaction_recall.py -q -s`

- Record the printed recall figure in your report **whatever it is**. This is the module's headline result.
- If any case fails, add a custom `PatternRecognizer` to `phi_redaction.py` for that shape and re-run. Do **not** lower `REQUIRED_RECALL`, and do **not** weaken a fixture case to make it pass.
- If a case cannot be caught without an unacceptable false-positive rate on the `must_survive` assertions, stop and report it — that is a real finding about Presidio's limits on this corpus, and it belongs in the report rather than being tuned away.

- [ ] **Step 4: Verify the full suite**

Run: `cd backend && python -m pytest -q 2>&1 | grep -E "passed|failed" | tail -1`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/phi_recall_cases.py backend/tests/test_phi_redaction_recall.py
git commit -m "test: gate PHI redaction on measured recall

Task 2's tests used short synthetic strings; real benefit documents carry
identifiers in table cells, headers, and footers that stock Presidio
recognizers can miss.

The gate starts at 100% deliberately - a miss is a real PHI leak, so the
remedy is a new recognizer, never a lowered threshold. The paired
must_survive assertions stop over-redaction from passing as success."
```

---

## M2 acceptance

- [ ] `redact_phi()` removes person names, dates, phone numbers, addresses, and insurance member/group identifiers.
- [ ] Clinical and cost content survives redaction — the `must_survive` assertions pass on every fixture case.
- [ ] **The recall figure is recorded**, and the gate passes at 100%.
- [ ] `phi_redaction_enabled=false` returns the input unchanged, so a caller never has to branch.
- [ ] `make lint` and `make typecheck` are clean.
- [ ] No production code outside `backend/src/tara/phi_redaction.py` and `config.py` has changed. Nothing calls `redact_phi()` yet — [M3](M3_execution_tracing.md) wires it in.
