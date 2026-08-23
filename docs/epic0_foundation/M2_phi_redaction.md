# Epic 0 · M2 — phi_redaction

- **Parent:** [Epic 0 — Foundation](README.md) — overview · decisions · build order · global constraints.
- **Seams:** depends on [M1](M1_repo_restructure.md). Supplies `redact_phi()` to two independent consumers: [M3 execution_tracing](M3_execution_tracing.md), which redacts span attributes, and the Epic 1 M4 hosted-egress path per [M4 §3.1](M4_epic1_handoff.md). Neither consumer is a prerequisite for this module.

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Strip protected health information out of any text before it leaves the process, so infrastructure can carry the clinical and cost content without carrying identity.

**Architecture:** One kernel root module, `phi_redaction.py`, wrapping Presidio's analyzer and anonymizer. Two custom recognizers add the insurance member and group identifiers Presidio's stock entity set misses. A recall fixture over realistic benefit-document text measures whether it actually works, because a PHI safeguard whose recall is unmeasured is a claim, not a control.

**Design sections:** [Epic 0 README](README.md) §5 row 1, §6.2

**Tech Stack:** Presidio (analyzer + anonymizer) · spaCy `en_core_web_lg`

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
- Modify: `.env.example`

**Interfaces:**
- Consumes: M1's repaired manifest.
- Produces: `Settings.phi_redaction_enabled: bool`, `Settings.phi_redaction_nlp_model: str`. Task 2 reads both; M3 reads neither directly.

**Context an engineer needs:**
- **Presidio needs a spaCy language model at runtime.** This plan pins `en_core_web_lg` (~427 MB on disk), configured explicitly. An earlier revision of this plan pinned `en_core_web_sm` (~12 MB) to keep laptop installs and CI runners light; Task 2's testing measured that `en_core_web_sm` returns **zero** entities for `"Member: Priya Raghunathan"` and leaks the given name in `"MEMBER NAME: JAMAL WASHINGTON"`, and that `en_core_web_md` still misses ALL-CAPS names — both formats are standard in benefits documents, so the smaller models fail this module's only job. Size is noise next to the local model this app already runs. The model name stays a setting, so it remains a one-line change if a future model changes the tradeoff again.
- **The model is a pinned wheel dependency, not a `spacy download` step.** An earlier revision downloaded the model separately in `bootstrap.sh` and CI — but the container's `Dockerfile.backend` installs Presidio and never ran that download, so the first `redact_phi()` call inside a container raised `OSError [E050] Can't find model`. Pinning `en_core_web_lg` as a wheel URL in `pyproject.toml`'s `dependencies` fixes the container, CI, and a local venv in one move, and pins the exact model version so nothing drifts against whatever `spacy download` would resolve to.
- The OpenTelemetry dependencies are **not** added here — they belong to [M3](M3_execution_tracing.md) Task 1.

- [ ] **Step 1: Add the dependencies**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    # PHI redaction before any span export or hosted egress
    "presidio-analyzer>=2.2",
    "presidio-anonymizer>=2.2",
    # The spaCy model is a pinned wheel, not a `spacy download`, so the
    # container, CI, and a local venv all get the SAME model version. A
    # `download` resolves to whatever matches the installed spaCy, which would
    # leave the recall tests pinned against a moving target.
    "en_core_web_lg @ https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl",
```

- [ ] **Step 2: Add the settings**

In `backend/src/tara/config.py`, add inside `class Settings`, after the Timeouts block:

```python
    # ---- PHI redaction (README §6.2) ----
    # On by default: this module exists so infrastructure can carry clinical
    # content without carrying identity. A caller must never have to check it.
    phi_redaction_enabled: bool = True
    # en_core_web_lg (~427MB on disk) rather than the smaller models: measured
    # 2026-08-15, en_core_web_sm returns ZERO entities for "Member: Priya
    # Raghunathan" and leaks the given name in "MEMBER NAME: JAMAL WASHINGTON",
    # while en_core_web_md still misses ALL-CAPS names. Both formats are
    # standard in benefits documents, so the smaller models fail this module's
    # only job. Size is noise next to the local model this app already runs.
    phi_redaction_nlp_model: str = "en_core_web_lg"
```

- [ ] **Step 3: Document the enabled flag only — not the model name**

Append to `.env.example`, in the same style as the existing sections:

```bash
# ---- PHI redaction ----
# On by default. Redaction is what makes tracing and hosted egress safe on a
# health corpus; disable it only for local debugging on synthetic data.
TARA_PHI_REDACTION_ENABLED=true
# The spaCy model is pinned as a wheel dependency in pyproject.toml, not an
# env knob: bootstrap copies this file only when .env is absent, so anyone
# who bootstrapped earlier would keep a stale value here and an env var
# beats the config.py default - re-introducing exactly the recall gap that
# was measured and fixed. config.py is the single source of truth.
```

Do **not** add a `TARA_PHI_REDACTION_NLP_MODEL` line — see the comment above for why.

- [ ] **Step 4: Install and verify nothing changed**

```bash
uv pip install -e "./backend[dev]"
cd backend && python -m pytest -q 2>&1 | grep -E "passed|failed" | tail -1
```

The wheel dependency in Step 1 installs the model — no separate `spacy download` is needed in bootstrap, CI, or here.

Expected: `67 passed, 3 skipped, ...`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/tara/config.py .env.example
git commit -m "build: add Presidio dependencies and PHI-redaction settings

Both settings default to the safe position, so this commit changes
nothing observable.

Pins spaCy en_core_web_lg (~427MB) as a wheel dependency rather than
a spacy download step, so the container, CI, and a local venv all
get the same model version with no separate download step to forget.
Task 2's testing found the smaller models miss names in
benefits-document formats (ALL-CAPS headers, label:value fragments),
which is this module's only job. The model name stays a setting, so
a future tradeoff change is a one-line edit, not a redesign."
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
- **The NLP model backing the analyzer matters more than it looks.** `en_core_web_sm` returns zero PERSON entities for label:value fragments like `"Member: Priya Raghunathan"` and leaks the given name in ALL-CAPS headers like `"MEMBER NAME: JAMAL WASHINGTON"` — both formats are standard in benefits documents. `en_core_web_md` still misses the ALL-CAPS case. This plan pins `en_core_web_lg`; do not downgrade the model to chase install size without re-running the cases in Step 4's regression tests below.
- **The two custom regexes went through two correction rounds — the current version in Step 3 is the one to trust.** Round 1 required a label token (`Member ID`, `Group Number`, …), which leaked every unlabelled or partial format (`Group: 55210`, `MBI: 1EG4-TE5-MK73`). Round 2 fixed that by making the label token optional and requiring a digit in the value, but dropped `IGNORECASE` *globally* to stop the digit-guard from matching lowercase prose — which broke the ALL-CAPS labels standard on insurance cards, over-redacted bare plan years (`"Plan 2024"`) once the label alternation widened, and (via `US_DRIVER_LICENSE`) started destroying ICD-10 codes like `E11.9`. The version below fixes all three: `(?i:...)` scopes case-insensitivity to the label only (the value stays case-sensitive), the `[:#]` separator is mandatory (excluding bare-word plan-year prose), and `US_DRIVER_LICENSE` is removed from `REDACTED_ENTITIES` entirely. If you are re-deriving these regexes from scratch, re-run every case in Step 4's tests — each round's fix silently broke something the previous round had just fixed.

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


@pytest.mark.integration
def test_name_in_label_value_format_is_removed(redaction_on):
    """Benefits documents are label:value, not prose - the format that broke
    en_core_web_sm entirely."""
    redacted = redact_phi("Member: Priya Raghunathan  Specialist copay: $40")
    assert "Priya" not in redacted
    assert "Raghunathan" not in redacted
    assert "$40" in redacted


@pytest.mark.integration
def test_all_caps_name_is_removed(redaction_on):
    """Insurance cards and EOB headers print names in caps."""
    redacted = redact_phi("MEMBER NAME: JAMAL WASHINGTON")
    assert "JAMAL" not in redacted
    assert "WASHINGTON" not in redacted
    # Guards against total destruction: a redactor that nukes the whole
    # string to "" would also make the two asserts above pass.
    assert "<PERSON>" in redacted
    assert "MEMBER NAME" in redacted


@pytest.mark.integration
def test_given_name_alone_is_not_left_behind(redaction_on):
    """en_core_web_sm caught only the surname here, leaving the given name."""
    redacted = redact_phi("Patient Priya Raghunathan was seen on Tuesday.")
    assert "Priya" not in redacted
    # Guards against total destruction: an empty string would also satisfy
    # the assert above without proving anything was actually redacted.
    assert "<PERSON>" in redacted
    assert "was seen on" in redacted


@pytest.mark.integration
def test_prose_mentioning_member_id_survives(redaction_on):
    """Presidio's PatternRecognizer defaults global_regex_flags to include
    IGNORECASE, which would make [A-Z0-9] match lowercase prose words -
    destroying sentences that merely mention the label."""
    redacted = redact_phi("Your Member ID cards are mailed within ten business days.")
    assert "cards are mailed" in redacted
    assert "<INSURANCE_MEMBER_ID>" not in redacted


@pytest.mark.integration
def test_prose_mentioning_group_number_survives(redaction_on):
    redacted = redact_phi("The Group Number assigned to your employer appears below.")
    assert "assigned to your employer" in redacted
    assert "<INSURANCE_GROUP_ID>" not in redacted


@pytest.mark.integration
def test_unlabelled_member_id_formats_are_removed(redaction_on):
    """The label token used to be required, so common card formats without
    the word ID/Number leaked entirely."""
    for text, must_remove in [
        ("Group: 55210", "55210"),
        ("Member: W8842190113", "W8842190113"),
        ("Plan ID: HMO-2210", "HMO-2210"),
        ("MBI: 1EG4-TE5-MK73", "1EG4-TE5-MK73"),
    ]:
        redacted = redact_phi(text)
        assert must_remove not in redacted, f"{must_remove!r} leaked in {redacted!r}"


@pytest.mark.integration
def test_all_caps_and_mixed_case_labels_are_removed(redaction_on):
    """Dropping IGNORECASE globally (to stop lowercase prose over-matching)
    must not break ALL-CAPS or mixed-case labels - both are standard on
    insurance cards and EOB headers."""
    for text, must_remove in [
        ("MEMBER ID: XQZ8842190 is active through your plan year.", "XQZ8842190"),
        ("PLAN ID: HMO-2210", "HMO-2210"),
        ("Member Id: XQZ8842190", "XQZ8842190"),
    ]:
        redacted = redact_phi(text)
        assert must_remove not in redacted, f"{must_remove!r} leaked in {redacted!r}"


@pytest.mark.integration
def test_plan_year_prose_survives(redaction_on):
    """Widening the label alternation to include bare "Plan"/"Policy"/
    "Medicare" must not over-redact a plan year mentioned in prose - only a
    labelled identifier with a mandatory :/# separator should match.

    All three cases confirm the regex fix: INSURANCE_MEMBER_ID never fires on
    a bare year. One case (documented below) still loses its bare "2024" to
    spaCy's own DATE_TIME recognizer - a pre-existing, unrelated behaviour
    (DATE_TIME has been in REDACTED_ENTITIES since this module's first
    version, and this module treats a bare date as PHI-adjacent everywhere
    else, e.g. test_person_name_is_removed's "Tuesday" -> <DATE_TIME>). That
    is not a defect this round's regex fix introduced or is scoped to fix.
    """
    cases = [
        ("Please review Plan 2024 benefit changes.", "2024", "benefit changes"),
        ("Medicare 2024 Plan Summary of Benefits.", "2024", "Summary of Benefits"),
    ]
    for text, must_survive_number, must_survive_phrase in cases:
        redacted = redact_phi(text)
        assert must_survive_number in redacted, f"{text!r} -> {redacted!r}"
        assert must_survive_phrase in redacted, f"{text!r} -> {redacted!r}"
        assert "<INSURANCE_MEMBER_ID>" not in redacted, f"{text!r} -> {redacted!r}"

    # spaCy's own DATE_TIME recognizer (not either custom ID regex) tags the
    # bare "2024" here - see the docstring. The regex fix itself is still
    # verified: INSURANCE_MEMBER_ID does not fire, and the surrounding prose
    # survives.
    redacted = redact_phi("This Policy 2024 renewal notice is important.")
    assert "renewal notice" in redacted
    assert "<INSURANCE_MEMBER_ID>" not in redacted


@pytest.mark.integration
def test_icd10_diagnosis_codes_survive(redaction_on):
    """US_DRIVER_LICENSE's pattern matches ICD-10 diagnosis codes, which would
    destroy the clinical content this module exists to preserve."""
    cases = [
        ("Diagnosis: E11.9 (Type 2 diabetes)", "E11.9"),
        ("Primary dx code J45.909 for asthma.", "J45.909"),
        ("CPT 99214, ICD10 I10 for hypertension.", "I10"),
    ]
    for text, must_survive in cases:
        redacted = redact_phi(text)
        assert must_survive in redacted, f"{text!r} -> {redacted!r}"


@pytest.mark.integration
def test_every_redacted_entity_is_actually_supported(redaction_on):
    """Presidio logs a warning and SKIPS an unknown entity name rather than
    failing, so a typo or an upstream rename would silently stop redacting a
    whole category while every other test still passed."""
    from tara.phi_redaction import REDACTED_ENTITIES, _analyzer_engine

    supported = set(_analyzer_engine().get_supported_entities(language="en"))
    unsupported = sorted(set(REDACTED_ENTITIES) - supported)
    assert not unsupported, f"not recognised by Presidio: {unsupported}"


def test_non_string_input_is_rejected(redaction_on):
    """redact_phi is annotated -> str; a non-string input must raise rather
    than silently pass through and violate that contract."""
    with pytest.raises(TypeError):
        redact_phi(None)  # type: ignore[arg-type]


def test_disabled_redaction_passes_text_through(monkeypatch):
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "false")
    config.get_settings.cache_clear()
    original = "Patient Michael Okonkwo, member ID XQZ8842190."
    assert redact_phi(original) == original
    config.get_settings.cache_clear()


def test_empty_text_is_returned_unchanged(redaction_on):
    assert redact_phi("") == ""
```

The three name-recall tests pin the cases `en_core_web_lg` fixes that `en_core_web_sm`
and `en_core_web_md` do not — see the model-choice bullet above. The two prose-survival
and the unlabelled-format tests pin the F3/F4 regex fixes below: dropping global
`IGNORECASE` and requiring a digit in the value. The ALL-CAPS/mixed-case,
plan-year-prose, and ICD-10 tests pin the corrected version of that same fix — the
first attempt at F3/F4 broke ALL-CAPS labels, over-redacted plan years, and (via
`US_DRIVER_LICENSE`) destroyed ICD-10 codes; see the label/value guards below.
`test_every_redacted_entity_is_actually_supported` guards against a silent
Presidio-side rename or typo, since Presidio skips an unsupported entity name with a
warning rather than raising. All of them exist so a future regression — a model
downgrade, a regex rewrite, an entity-list typo — cannot pass review silently.

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

import re
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
    # US_DRIVER_LICENSE deliberately NOT included: its pattern matches ICD-10
    # diagnosis codes (E11.9, J45.909, I10), destroying the clinical content
    # this module exists to preserve. The unlabelled-identifier gap it would
    # have closed is a Task 3 measurement, not a guess.
    "US_PASSPORT",
    "US_ITIN",
    # HIPAA counts account and payment numbers as identifiers; premium-autopay
    # and EOB payment sections carry them.
    "CREDIT_CARD",
    "US_BANK_NUMBER",
    "IBAN_CODE",
    # EOB portal links routinely embed a member token in the query string.
    "URL",
    INSURANCE_MEMBER_ID_ENTITY,
    INSURANCE_GROUP_ID_ENTITY,
    # Deliberately excluded: ORGANIZATION. It fires on ordinary clinical nouns
    # (measured: "Specialist" gets tagged ORGANIZATION), so including it would
    # destroy the clinical content this module exists to preserve.
]

# Presidio defaults `global_regex_flags` to re.I|re.M|re.S. A global IGNORECASE
# makes `[A-Z0-9]` match lowercase prose, so it is dropped here and applied
# inline to the LABEL only via `(?i:...)`. Labels appear in any case on real
# cards ("MEMBER ID:", "Member Id:"); identifier values do not.
_ID_REGEX_FLAGS = re.MULTILINE | re.DOTALL

# Two guards together. The value must contain a digit, which excludes ordinary
# words. And the `[:#]` separator is MANDATORY, which excludes plan-year prose
# like "Plan 2024" while keeping every real card format.
_HAS_A_DIGIT = r"(?=[A-Z0-9-]*\d)"
_LABEL_QUALIFIER = r"\s*(?i:ID|Identification|Number|No\.?|#)?\s*[:#]\s*"


def _insurance_member_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_MEMBER_ID_ENTITY,
        name="InsuranceMemberIdRecognizer",
        global_regex_flags=_ID_REGEX_FLAGS,
        patterns=[Pattern(
            name="labelled_member_id",
            regex=(
                r"\b(?i:Member|Subscriber|Insured|Policy|Certificate|Plan|MBI|Medicare)"
                + _LABEL_QUALIFIER + _HAS_A_DIGIT + r"[A-Z0-9][A-Z0-9-]{3,}\b"
            ),
            score=0.85,
        )],
    )


def _insurance_group_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_GROUP_ID_ENTITY,
        name="InsuranceGroupIdRecognizer",
        global_regex_flags=_ID_REGEX_FLAGS,
        patterns=[Pattern(
            name="labelled_group_id",
            regex=(
                r"\b(?i:Group)" + _LABEL_QUALIFIER
                + _HAS_A_DIGIT + r"[A-Z0-9][A-Z0-9-]{2,}\b"
            ),
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
    caller never has to branch. Raises on a non-string input rather than
    silently passing it through, so the `-> str` contract always holds.
    """
    if not isinstance(text, str):
        raise TypeError(f"redact_phi expects str, got {type(text).__name__}")
    if not text or not get_settings().phi_redaction_enabled:
        return text
    analyzer_results = _analyzer_engine().analyze(
        text=text, language="en", entities=REDACTED_ENTITIES,
    )
    if not analyzer_results:
        return text
    # presidio_analyzer.RecognizerResult and presidio_anonymizer's own
    # RecognizerResult are structurally identical but nominally distinct
    # types; the anonymizer accepts the analyzer's results at runtime.
    return _anonymizer_engine().anonymize(
        text=text,
        analyzer_results=analyzer_results,  # type: ignore[arg-type]
    ).text
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_phi_redaction.py -q`
Expected: `18 passed`

If `test_insurance_group_id_is_removed` fails, check that the group-number regex tolerates the space in `Group # 55210`. Adjust the regex, not the test. If any of the name-recall or regex-fix regression tests fail, stop and report it — do not add a custom PERSON recognizer to force a pass; that is a Task 3 finding, to be measured before it is patched. Do not lower `score` to force a match.

Note: a bare year adjacent to a label word (e.g. `"This Policy 2024 renewal notice is important."`) may still lose the year to spaCy's own `DATE_TIME` recognizer — unrelated to either custom regex, and not a defect this module's ID recognizers are scoped to fix (DATE_TIME has been in `REDACTED_ENTITIES` since this module's first version, and a bare date is treated as PHI-adjacent everywhere else in this suite).

- [ ] **Step 5: Verify the full suite still passes**

Run: `cd backend && python -m pytest -q 2>&1 | tail -1`
Expected: `85 passed, 3 skipped, ...`

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
