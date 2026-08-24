"""Recall gate for PHI redaction.

A PHI safeguard whose recall is unmeasured is a claim, not a control. This
module reports the number and fails below the gate.

Three rounds of ad-hoc probing on individual strings kept substituting for a
systematic measurement. This is that measurement: a labelled fixture
(tests/fixtures/phi_recall_cases.py) states, per case, exactly which
substrings must disappear and which must survive, and this module runs the
whole corpus through redact_phi() and reports the true result - including
the cases that are known, today, to fail either half of that contract.
Those known-failing cases are marked `xfail` (not deleted, not weakened) and
excluded from the gated recall denominator; the aggregate test still prints
the true corpus-wide number with them included.
"""
from __future__ import annotations

import pytest

from tara import config
from tara.phi_redaction import redact_phi
from tests.fixtures.phi_recall_cases import (
    PHI_RECALL_CASES,
    RECALL_GAP_REASONS,
    SURVIVAL_GAP_REASONS,
)

# Every labelled identifier must be removed. This starts at 100% deliberately:
# a miss is a real PHI leak, so the gate should fail loudly and the remedy is a
# new custom recognizer, not a lowered threshold. The gate is computed only
# over cases NOT already named in RECALL_GAP_REASONS - see
# test_aggregate_recall_meets_the_gate for the true, ungated number.
REQUIRED_RECALL = 1.0

# Freezing these LABEL SETS (not counts) is what stops the gate being passed
# dishonestly. A count-only freeze lets a genuine failure be swapped for a
# gap that was actually fixed - removing the fixed one and adding the new one
# keeps len() unchanged, so the guard passes silently while nothing is safer.
# Freezing identity closes that: swapping any single label, in either
# direction, changes the set and fails loudly, naming exactly what was added
# and what was removed. Raising the set is a deliberate act that has to be
# justified in review.
EXPECTED_RECALL_GAP_LABELS = frozenset({
    "unlabelled_member_id_alone_on_line",
    "unlabelled_member_id_in_table_row",
    "uncovered_label_formats_leak",
    "ocr_noised_member_id_leaks",
    "hyphenated_surname_after_label_leaks",
    "address_block_partial_leak",
    "spaced_identifier_after_covered_label_leaks",
    "short_identifier_after_covered_label_leaks",
})
EXPECTED_SURVIVAL_GAP_LABELS = frozenset({
    "policy_date_range_destroyed_by_date_time",
    "group_duration_destroyed_by_date_time",
    "blood_pressure_destroyed_by_date_time",
    "dosage_frequency_destroyed_by_date_time",
    "pinned_member_id_prose_survives",
    "pinned_plan_gold_ppo_2026_survives",
    "plan_name_destroyed_by_custom_id_regex",
})


@pytest.fixture(autouse=True)
def redaction_on(monkeypatch):
    """Force redaction on for every case in this module.

    Only `get_settings` is cleared here, not `_analyzer_engine`. The engine
    cache holds a ~427MB spaCy model; clearing it forces a ~0.9s rebuild on
    the NEXT call, and this fixture ran on every single test in this module
    (~80 of them), which is where most of the suite's wall-clock went for no
    correctness benefit - no case in this module changes
    `TARA_PHI_REDACTION_NLP_MODEL`, so the engine this fixture was rebuilding
    was never stale to begin with. The engine cache must still be cleared by
    any fixture that DOES change the model setting - clear it there, not
    here.
    """
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _parametrize_cases(gap_reasons: dict[str, str]) -> list:
    """Wrap each fixture case in `pytest.param`, xfailing the ones named in
    `gap_reasons` so a known gap reports as XFAIL rather than FAILED, without
    hiding it from the test run.
    """
    params = []
    for case in PHI_RECALL_CASES:
        reason = gap_reasons.get(case.label)
        marks = [pytest.mark.xfail(reason=reason, strict=True)] if reason else []
        params.append(pytest.param(case, id=case.label, marks=marks))
    return params


@pytest.mark.integration
@pytest.mark.parametrize("case", _parametrize_cases(RECALL_GAP_REASONS))
def test_every_labelled_identifier_is_removed(case):
    redacted = redact_phi(case.text)
    leaked = [secret for secret in case.must_remove if secret in redacted]
    assert not leaked, f"{case.label}: PHI survived redaction: {leaked}"


@pytest.mark.integration
@pytest.mark.parametrize("case", _parametrize_cases(SURVIVAL_GAP_REASONS))
def test_clinical_and_cost_content_survives(case):
    redacted = redact_phi(case.text)
    destroyed = [keep for keep in case.must_survive if keep not in redacted]
    assert not destroyed, f"{case.label}: redaction destroyed needed content: {destroyed}"


@pytest.mark.integration
def test_aggregate_recall_meets_the_gate(capsys):
    """Report the corpus-wide recall figure - true and gated - then gate on
    the gated figure.

    "True" recall counts every labelled identifier in the fixture, including
    the ones in RECALL_GAP_REASONS that are known today not to be caught.
    "Gated" recall excludes those - it measures only the shapes this module
    currently claims to handle, which is what REQUIRED_RECALL actually holds
    the line on. Reporting only the gated figure would hide the known gaps
    inside a passing number; reporting only the true figure would make the
    gate impossible to hold at 100% while gaps remain parked. Both are
    printed so neither happens.
    """
    total_true = 0
    caught_true = 0
    total_gated = 0
    caught_gated = 0
    for case in PHI_RECALL_CASES:
        if not case.must_remove:
            continue
        redacted = redact_phi(case.text)
        case_total = len(case.must_remove)
        case_caught = sum(1 for secret in case.must_remove if secret not in redacted)
        total_true += case_total
        caught_true += case_caught
        if case.label not in RECALL_GAP_REASONS:
            total_gated += case_total
            caught_gated += case_caught

    recall_true = caught_true / total_true if total_true else 1.0
    recall_gated = caught_gated / total_gated if total_gated else 1.0

    with capsys.disabled():
        print(f"\nPHI redaction recall (true, all cases):   {caught_true}/{total_true} = {recall_true:.1%}")
        print(f"PHI redaction recall (gated, known gaps excluded): {caught_gated}/{total_gated} = {recall_gated:.1%}")
        print("\nCases excluded from the gate (known gaps, not fixed - see RECALL_GAP_REASONS):")
        for label, reason in RECALL_GAP_REASONS.items():
            print(f"  - {label}: {reason}")

    assert recall_gated >= REQUIRED_RECALL, (
        f"gated recall {recall_gated:.1%} below gate {REQUIRED_RECALL:.0%} "
        "on cases NOT already listed in RECALL_GAP_REASONS"
    )


def test_gap_lists_are_frozen():
    """A new gap must be an explicit, visible decision - never a quiet edit.

    Freezes on LABEL IDENTITY, not len(). A count-only freeze lets a real
    regression swap places with a gap that was actually fixed - remove the
    fixed label, add the new one, and len() never moves, so the guard would
    pass silently while nothing got safer. Comparing sets instead means any
    single substitution changes both EXPECTED_*_GAP_LABELS - EXPECTED (added)
    and EXPECTED_*_GAP_LABELS - actual (removed), and the failure message
    names both, so a swap cannot hide behind an unchanged count.
    """
    actual_recall_labels = frozenset(RECALL_GAP_REASONS)
    added_recall = sorted(actual_recall_labels - EXPECTED_RECALL_GAP_LABELS)
    removed_recall = sorted(EXPECTED_RECALL_GAP_LABELS - actual_recall_labels)
    assert not added_recall and not removed_recall, (
        "Recall-gap labels changed - "
        f"added: {added_recall}, removed: {removed_recall}. "
        "If you are adding a gap, update EXPECTED_RECALL_GAP_LABELS "
        "deliberately and say why in the reason string. If you FIXED one, "
        "remove its label from EXPECTED_RECALL_GAP_LABELS - and thank you."
    )

    actual_survival_labels = frozenset(SURVIVAL_GAP_REASONS)
    added_survival = sorted(actual_survival_labels - EXPECTED_SURVIVAL_GAP_LABELS)
    removed_survival = sorted(EXPECTED_SURVIVAL_GAP_LABELS - actual_survival_labels)
    assert not added_survival and not removed_survival, (
        "Survival-gap labels changed - "
        f"added: {added_survival}, removed: {removed_survival}. "
        "Same rule as above."
    )


@pytest.mark.integration
def test_disabled_redaction_is_a_true_control(monkeypatch):
    """A harness self-check: with redaction disabled, every fixture case must
    come back byte-identical.

    Without this, a perfect recall figure above could mean either that
    redaction works, or that it is silently disabled - the fixture alone
    cannot tell those apart. This proves the ON/OFF switch actually gates
    behaviour across the whole corpus before the recall number is trusted.
    """
    monkeypatch.setenv("TARA_PHI_REDACTION_ENABLED", "false")
    config.get_settings.cache_clear()
    try:
        changed = [
            case.label for case in PHI_RECALL_CASES if redact_phi(case.text) != case.text
        ]
    finally:
        config.get_settings.cache_clear()
    assert not changed, f"redaction fired while TARA_PHI_REDACTION_ENABLED=false for: {changed}"
