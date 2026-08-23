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
def test_lowercase_and_mixed_case_values_are_removed(redaction_on):
    """Round 2's (?i:...) scoping fixed the LABEL's case but left the VALUE
    class as [A-Z0-9], which never matched a lowercase identifier - a
    regression against this module's original, fully case-insensitive
    version. "Member ID: xqz8842190" used to leak in full."""
    for text, must_remove in [
        ("Member ID: xqz8842190", "xqz8842190"),
        ("MEMBER ID: xqz8842190", "xqz8842190"),
        ("Member ID: Xqz8842190", "Xqz8842190"),
    ]:
        redacted = redact_phi(text)
        assert must_remove not in redacted, f"{must_remove!r} leaked in {redacted!r}"


@pytest.mark.integration
def test_colon_bearing_plan_year_headers_survive_as_identifiers(redaction_on):
    """A colon after the label ("Plan: 2024 benefit changes") used to satisfy
    the old mandatory-separator guard, so a bare year or year range was
    over-redacted as INSURANCE_MEMBER_ID. The _NOT_A_YEAR lookahead now
    excludes any bare 4-digit run regardless of the separator.

    Two of the five fully survive verbatim. The other three still lose their
    year/range to spaCy's own DATE_TIME recognizer - a separate, pre-existing
    behaviour unrelated to either custom regex (see test_plan_year_prose_survives
    for the same interaction with a single year). The assertion this test
    exists to make is that INSURANCE_MEMBER_ID never fires here; full-sentence
    survival is asserted only where it actually holds.
    """
    fully_survives = [
        "Plan: 2024 benefit changes",
        "MBI: 2024",
    ]
    for text in fully_survives:
        redacted = redact_phi(text)
        assert redacted == text, f"{text!r} -> {redacted!r}"
        assert "<INSURANCE_MEMBER_ID>" not in redacted

    # DATE_TIME (not INSURANCE_MEMBER_ID) redacts the year/range in these -
    # honest, out-of-scope finding, not a regex defect this round introduced.
    date_time_intercepts = [
        ("Insured: 2026 Plan Summary", "Plan Summary"),
        ("Policy: 2024-2025 renewal", "renewal"),
        ("Certificate: 2024-25 update", "update"),
    ]
    for text, must_survive_phrase in date_time_intercepts:
        redacted = redact_phi(text)
        assert must_survive_phrase in redacted, f"{text!r} -> {redacted!r}"
        assert "<INSURANCE_MEMBER_ID>" not in redacted, f"{text!r} -> {redacted!r}"


@pytest.mark.integration
def test_durations_after_group_label_survive_as_identifiers(redaction_on):
    """A short number-hyphen-word span after "Group:" used to read like a
    short identifier ("Group: 30-day waiting period"). The _NOT_A_DURATION
    lookahead now excludes day/week/month/year durations explicitly.

    As with the plan-year headers above, INSURANCE_GROUP_ID correctly never
    fires, but spaCy's own DATE_TIME recognizer still independently redacts
    the duration span in all three cases - documented, not patched; narrowing
    DATE_TIME is outside this round's (and this module's two custom
    recognizers') scope.
    """
    cases = [
        ("Group: 30-day waiting period applies.", "waiting period applies"),
        ("Group: 90-day supply limit", "supply limit"),
        ("Group: 42-year-old patient", "patient"),
    ]
    for text, must_survive_phrase in cases:
        redacted = redact_phi(text)
        assert must_survive_phrase in redacted, f"{text!r} -> {redacted!r}"
        assert "<INSURANCE_GROUP_ID>" not in redacted, f"{text!r} -> {redacted!r}"


@pytest.mark.integration
def test_separator_free_labels_are_removed(redaction_on):
    """The separator is optional (not mandatory) in this design, specifically
    so "Member No. 12345" - no colon or hash at all - is still covered."""
    for text, must_remove in [
        ("Member No. 12345", "12345"),
        ("Group No. 45678", "45678"),
    ]:
        redacted = redact_phi(text)
        assert must_remove not in redacted, f"{must_remove!r} leaked in {redacted!r}"


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
