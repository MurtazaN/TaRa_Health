"""Removes protected health information from text before it leaves the process.

Self-hosting the trace backend protects the destination; this module protects
the payload. A redacted span keeps the clinical and cost content a trace exists
to show, while dropping the identity that makes it protected health information.
"""
from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
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
    # HIPAA Safe Harbor identifier (O), 45 CFR 164.514(b)(2)(i)(O). Added
    # for M3: execution_tracing spans carry client and host addresses, and
    # those are exactly what this entity catches. Verified (M2 final
    # review) against every fixture text plus the clinical shapes it could
    # plausibly collide with (ICD-10 codes, an NDC, a section number, a
    # blood-pressure reading, a version string): zero false positives.
    "IP_ADDRESS",
    INSURANCE_MEMBER_ID_ENTITY,
    INSURANCE_GROUP_ID_ENTITY,
    # Deliberately excluded: ORGANIZATION. It fires on ordinary clinical nouns
    # (measured: "Specialist" gets tagged ORGANIZATION), so including it would
    # destroy the clinical content this module exists to preserve.
]

# The set used when text is sent to a model off this device. Identical to
# REDACTED_ENTITIES except that DATE_TIME is excluded, because DATE_TIME does not
# only take calendar dates: M2's measurements record it consuming "2026" in
# "Plan: Gold PPO 2026", the "30-day" in a waiting period, a "daily" dosage
# frequency, and the blood-pressure reading "120/80". Those are the facts an
# answer is made of, and a model that cannot see them cannot answer from them.
# Identity is removed by PERSON, the identifier entities, LOCATION and the rest,
# none of which are relaxed here. Kept beside REDACTED_ENTITIES so the one
# difference between the two lists is visible on one screen.
EGRESS_REDACTED_ENTITIES = [
    entity for entity in REDACTED_ENTITIES if entity != "DATE_TIME"
]

# Presidio defaults `global_regex_flags` to re.I|re.M|re.S. A global IGNORECASE
# makes the label match in any case but also lets the value class match prose,
# so it is dropped and applied inline per-token instead.
_ID_REGEX_FLAGS = re.MULTILINE | re.DOTALL

# Identifiers are defined by EXCLUDING the non-identifier shapes that a label
# is commonly followed by, rather than by guessing a positive shape. Three
# earlier attempts at a positive shape each leaked or over-redacted.
#
# Excluded: a bare 4-digit year, which also covers "2024-2025" and "2024-25"
# because \b matches before the hyphen.
_NOT_A_YEAR = r"(?!\d{4}\b)"
# Excluded: durations, which read like short identifiers after a label
# ("Group: 30-day waiting period").
_NOT_A_DURATION = r"(?!\d{1,3}-(?i:day|days|year|years|month|months|week|weeks)\b)"
# An identifier always carries a digit; an English word does not.
_HAS_A_DIGIT = r"(?=[A-Za-z0-9-]*\d)"
# The value class is case-INSENSITIVE: real documents and OCR output both
# produce lowercase identifiers. The 5-character floor is what excludes bare
# years, which is why the separator below can stay optional.
_ID_VALUE = (
    _NOT_A_YEAR + _NOT_A_DURATION + _HAS_A_DIGIT + r"[A-Za-z0-9][A-Za-z0-9-]{4,}\b"
)
# The separator is OPTIONAL so "Member No. 12345" is covered; the value guards
# above are what prevent prose from matching.
_LABEL_QUALIFIER = r"\s*(?i:ID|Identification|Number|No\.?|#)?\s*[:#]?\s*"


def _insurance_member_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity=INSURANCE_MEMBER_ID_ENTITY,
        name="InsuranceMemberIdRecognizer",
        global_regex_flags=_ID_REGEX_FLAGS,
        patterns=[Pattern(
            name="labelled_member_id",
            regex=(
                r"\b(?i:Member|Subscriber|Insured|Policy|Certificate|Plan|MBI|Medicare)"
                + _LABEL_QUALIFIER + _ID_VALUE
            ),
            score=0.85,
        )],
    )


def _insurance_group_id_recognizer() -> PatternRecognizer:
    # Shares _ID_VALUE with the member recognizer. The previous {2,} vs {3,}
    # split made this pattern strictly more fragile than its sibling for no
    # stated reason.
    return PatternRecognizer(
        supported_entity=INSURANCE_GROUP_ID_ENTITY,
        name="InsuranceGroupIdRecognizer",
        global_regex_flags=_ID_REGEX_FLAGS,
        patterns=[Pattern(
            name="labelled_group_id",
            regex=r"\b(?i:Group)" + _LABEL_QUALIFIER + _ID_VALUE,
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


# Set the first time redact_phi() runs while phi_redaction_enabled is false,
# so the one-time warning below fires once per process rather than once per
# call. Never reset in production; tests that need a fresh warning reset it
# via monkeypatch.
_disabled_warning_emitted = False


def redact_phi(text: str, entities: Sequence[str] | None = None) -> str:
    """Return `text` with PHI entities replaced by `<ENTITY_TYPE>` placeholders.

    `entities` defaults to `REDACTED_ENTITIES`. It exists so a caller can narrow
    the set for its own context: an on-device trace can afford aggressive
    redaction, while the hosted-egress path needs to keep plan years and
    waiting periods that `DATE_TIME` would otherwise strip. Narrowing at the
    call site rather than by editing the constant keeps one consumer's choice
    from silently weakening the other's.

    A no-op when `phi_redaction_enabled` is false or the text is empty, so the
    caller never has to branch - but the disabled case is never SILENT: the
    first call made while disabled emits a one-time `warnings.warn`, because
    this module's Global Constraint is that redaction must never be silently
    disabled. Raises on a non-string input rather than silently passing it
    through, so the `-> str` contract always holds.
    """
    if not isinstance(text, str):
        raise TypeError(f"redact_phi expects str, got {type(text).__name__}")
    if not text:
        return text
    if not get_settings().phi_redaction_enabled:
        global _disabled_warning_emitted
        if not _disabled_warning_emitted:
            warnings.warn(
                "PHI redaction is disabled (phi_redaction_enabled=false); "
                "text is passing through unredacted.",
                stacklevel=2,
            )
            _disabled_warning_emitted = True
        return text
    analyzer_results = _analyzer_engine().analyze(
        text=text,
        language="en",
        entities=list(entities) if entities else REDACTED_ENTITIES,
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
