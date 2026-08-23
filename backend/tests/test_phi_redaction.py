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
