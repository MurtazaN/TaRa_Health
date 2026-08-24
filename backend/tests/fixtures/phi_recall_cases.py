"""Labelled PHI-recall cases. All content is synthetic - never paste real
document text into this repository.

Each case pairs a realistic fragment with the substrings redaction MUST
remove. `must_survive` guards the other half of the contract: redaction that
also destroys the clinical or cost content is useless.

Three rounds of ad-hoc probing already established which shapes redact_phi()
handles and which it does not. This module is the single measured record of
both halves, not just the successes: `RECALL_GAP_REASONS` and
`SURVIVAL_GAP_REASONS` name every case that is known, today, to fail one of
the two contracts, and why. test_phi_redaction_recall.py reads those two maps
to keep the gate honest - it reports the true corpus-wide recall including
the gaps, and gates only on the cases that are not already known to fail.

`must_remove` holds INDIVIDUAL name tokens, never a joined multi-word name.
A joined check ("Okonkwo, Michael") passes as long as the substring is gone
from the redacted text - including when only "Michael" was actually redacted
and the surname "Okonkwo" leaked in full. Surname-only leakage is the exact
failure that forced this module from en_core_web_sm to en_core_web_lg, so a
gate that cannot see it is measuring the wrong thing. Every multi-token name
below is split into its constituent tokens for that reason (found during the
M2 final review, tracked as C1 in the fix report).
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
    # --- Pinned: already redacting correctly (three fix rounds' evidence) ---
    # Each is its own case so a future regression on any single format shows
    # up as a single named failure rather than being buried in a combined one.
    PhiRecallCase(
        label="pinned_member_id_mixed_case",
        text="Member ID: XQZ8842190",
        must_remove=("XQZ8842190",),
    ),
    PhiRecallCase(
        label="pinned_member_id_all_caps",
        text="MEMBER ID: XQZ8842190",
        must_remove=("XQZ8842190",),
    ),
    PhiRecallCase(
        label="pinned_member_id_lowercase_value",
        text="Member ID: xqz8842190",
        must_remove=("xqz8842190",),
    ),
    PhiRecallCase(
        label="pinned_member_bare_label",
        text="Member: W8842190113",
        must_remove=("W8842190113",),
    ),
    PhiRecallCase(
        label="pinned_plan_id_hyphenated",
        text="Plan ID: HMO-2210",
        must_remove=("HMO-2210",),
    ),
    PhiRecallCase(
        label="pinned_mbi_hyphenated",
        text="MBI: 1EG4-TE5-MK73",
        must_remove=("1EG4-TE5-MK73",),
    ),
    PhiRecallCase(
        label="pinned_policy_hash_separator",
        text="Policy #: 8842190113",
        must_remove=("8842190113",),
    ),
    PhiRecallCase(
        label="pinned_certificate_number_label",
        text="Certificate Number: 88421901",
        must_remove=("88421901",),
    ),
    PhiRecallCase(
        label="pinned_member_no_dot_separator",
        text="Member No. 12345",
        must_remove=("12345",),
    ),
    PhiRecallCase(
        label="pinned_group_colon",
        text="Group: 55210",
        must_remove=("55210",),
    ),
    PhiRecallCase(
        label="pinned_group_hash_space",
        text="Group # 55210",
        must_remove=("55210",),
    ),
    PhiRecallCase(
        label="pinned_group_all_caps_hash_colon",
        text="GROUP #: 0847221",
        must_remove=("0847221",),
    ),
    PhiRecallCase(
        label="pinned_group_no_dot_separator",
        text="Group No. 45678",
        must_remove=("45678",),
    ),
    # --- Pinned: already surviving correctly ---
    # Measured independently against the current code rather than trusted
    # from the prior rounds' notes. Two entries below turned out to only
    # partially survive under direct measurement, both to the same DATE_TIME
    # defect as the dedicated gap cases further down; they carry their full,
    # un-narrowed must_survive content and are listed in SURVIVAL_GAP_REASONS
    # so they report as xfail rather than passing on a shrunk assertion.
    PhiRecallCase(
        label="pinned_member_id_prose_survives",
        text="Your Member ID cards are mailed within ten business days.",
        must_remove=(),
        # Full expected survival, not narrowed to the part that happens to
        # pass: "ten business days" is destroyed by DATE_TIME (same parked
        # ruling as the dedicated DATE_TIME gap cases below), so this is
        # listed in SURVIVAL_GAP_REASONS and reports as xfail rather than
        # silently passing on a shrunk assertion.
        must_survive=("Your Member ID cards are mailed within ten business days.",),
    ),
    PhiRecallCase(
        label="pinned_group_number_prose_survives",
        text="The Group Number assigned to your employer appears below.",
        must_remove=(),
        must_survive=("assigned to your employer",),
    ),
    PhiRecallCase(
        label="pinned_plan_2024_benefit_changes_survives",
        text="Plan: 2024 benefit changes",
        must_remove=(),
        must_survive=("2024", "benefit changes"),
    ),
    PhiRecallCase(
        label="pinned_mbi_bare_2024_survives",
        text="MBI: 2024",
        must_remove=(),
        must_survive=("2024",),
    ),
    PhiRecallCase(
        label="pinned_plan_gold_ppo_2026_survives",
        text="Plan: Gold PPO 2026",
        must_remove=(),
        # Full expected survival, not narrowed: "2026" is destroyed by
        # DATE_TIME (confirmed deterministic; "Plan: Silver HMO 2026" survives
        # unchanged, so this is a token-sequence-specific spaCy quirk, not a
        # blanket "year after Plan:" rule). Listed in SURVIVAL_GAP_REASONS so
        # it reports as xfail rather than silently passing on a shrunk
        # assertion.
        must_survive=("Plan: Gold PPO 2026",),
    ),
    PhiRecallCase(
        label="pinned_certificate_see_page_survives",
        text="Certificate: see page 4",
        must_remove=(),
        must_survive=("see page 4",),
    ),
    PhiRecallCase(
        label="pinned_member_see_enclosed_card_survives",
        text="Member: see enclosed card",
        must_remove=(),
        must_survive=("see enclosed card",),
    ),
    PhiRecallCase(
        label="pinned_specialist_copay_survives",
        text="Specialist office visit: $40 copay",
        must_remove=(),
        must_survive=("Specialist office visit", "$40 copay"),
    ),
    PhiRecallCase(
        label="pinned_diagnosis_e119_survives",
        text="Diagnosis: E11.9",
        must_remove=(),
        must_survive=("E11.9",),
    ),
    PhiRecallCase(
        label="pinned_icd10_j45909_survives",
        text="J45.909",
        must_remove=(),
        must_survive=("J45.909",),
    ),
    PhiRecallCase(
        label="pinned_icd10_i10_survives",
        text="ICD10 I10",
        must_remove=(),
        must_survive=("I10",),
    ),
    # --- Required shapes: currently passing ---
    PhiRecallCase(
        label="subscriber_and_dependent_same_line",
        text="Subscriber: Wei Chen   Dependent: Lily Chen (daughter)",
        # Split into individual name tokens (C1): a joined-substring check
        # would pass even if only the given name were redacted and the
        # shared surname "Chen" leaked from either mention.
        must_remove=("Wei", "Chen", "Lily", "Chen"),
        must_survive=("(daughter)",),
    ),
    PhiRecallCase(
        label="phone_number_in_plan_footer",
        text="Questions? Call Member Services at (800) 555-0199, Mon-Fri 8am-6pm.",
        must_remove=("(800) 555-0199",),
        must_survive=("Member Services",),
    ),
    PhiRecallCase(
        label="all_caps_name_in_header",
        text="MEMBER NAME: DEREK THOMPSON",
        # Split into individual name tokens (C1): see the module docstring
        # note on why a joined-substring check is a blind spot.
        must_remove=("DEREK", "THOMPSON"),
        must_survive=("MEMBER NAME",),
    ),
    PhiRecallCase(
        label="name_with_particle",
        text="Insured: Willem van der Berg, effective 01/01/2026",
        # Split into individual name tokens (C1).
        must_remove=("Willem", "van", "der", "Berg"),
        must_survive=("Insured",),
    ),
    PhiRecallCase(
        label="prescription_label_prescriber_and_patient",
        text="Prescriber: Dr. Sandra Kowalski   Patient: Marcus Ellison   Rx: Lisinopril 10mg",
        # Split into individual name tokens (C1).
        must_remove=("Sandra", "Kowalski", "Marcus", "Ellison"),
        must_survive=("Lisinopril 10mg",),
    ),
    PhiRecallCase(
        label="date_written_in_long_form",
        text="Effective date: March 14, 2026",
        must_remove=("March 14, 2026",),
        must_survive=("Effective date",),
    ),
    # --- Known gaps: identifiers that leak (expected to FAIL) ---
    # Do not fix these here - see the M2 Task 3 brief and report. Each is
    # keyed in RECALL_GAP_REASONS below so the test module can xfail it and
    # exclude it from the recall gate while still reporting the true number.
    PhiRecallCase(
        label="unlabelled_member_id_alone_on_line",
        text="W8842190113",
        must_remove=("W8842190113",),
    ),
    PhiRecallCase(
        label="unlabelled_member_id_in_table_row",
        text="Okonkwo, Michael | W8842190113 | $412.00",
        # Split into individual name tokens (C1) - this is the exact case
        # that exposed the joined-substring blind spot: the old joined
        # check ("Okonkwo, Michael") passed even though only "Michael" was
        # redacted and "Okonkwo" leaked in full.
        must_remove=("Okonkwo", "Michael", "W8842190113"),
        must_survive=("$412.00",),
    ),
    PhiRecallCase(
        label="uncovered_label_formats_leak",
        text=(
            "Reference #: HX99887766\n"
            "Claim Number: CL8837719945\n"
            "Authorization Number: AUTH99001122\n"
            "Rx Number: RX7788990011\n"
            "Account Number: ACCT445566778\n"
            "MRN: 4482910\n"
            "Medical Record Number: 4482910\n"
            "Patient ID: P8842190\n"
            "HICN: 123456789A\n"
            "Enrollee ID: EN8842190\n"
            "Cardholder ID: CH8842190\n"
            "ID: W8842910113"
        ),
        must_remove=(
            "HX99887766",
            "CL8837719945",
            "AUTH99001122",
            "RX7788990011",
            "ACCT445566778",
            # I4: the medical record number is the primary patient
            # identifier in clinical documents and an explicit HIPAA Safe
            # Harbor item; these seven labels are as uncovered as the five
            # above but were absent from this case until the M2 final
            # review (see RECALL_GAP_REASONS).
            "4482910",
            "4482910",
            "P8842190",
            "123456789A",
            "EN8842190",
            "CH8842190",
            "W8842910113",
        ),
    ),
    PhiRecallCase(
        label="ocr_noised_member_id_leaks",
        # Cyrillic "г" in place of Latin "r", and a letter O in place of a
        # zero - the shapes the Epic 1 M6 OCR path actually produces.
        text="Membeг ID: W884219O113",
        must_remove=("W884219O113",),
    ),
    PhiRecallCase(
        label="hyphenated_surname_after_label_leaks",
        text=(
            "Patient: Aisha Nwosu-Okafor\n"
            "MEMBER NAME: AISHA NWOSU-OKAFOR\n"
            "Member Name\n"
            "JAMAL WASHINGTON"
        ),
        # "Aisha Nwosu-Okafor" is kept joined: the whole name leaks (both
        # tokens), so splitting it would not change what the check reveals.
        # The two additional identifiers (I3) are split per the C1
        # convention, since each is a genuinely new multi-token name.
        must_remove=("Aisha Nwosu-Okafor", "AISHA", "NWOSU-OKAFOR", "JAMAL", "WASHINGTON"),
    ),
    PhiRecallCase(
        label="address_block_partial_leak",
        text="123 Maple Street, Apt 4B\nSpringfield, IL 62704",
        must_remove=("123 Maple Street", "62704"),
    ),
    PhiRecallCase(
        label="spaced_identifier_after_covered_label_leaks",
        # C2: the label IS covered by the alternation in each line below -
        # this is not an "uncovered label" gap. The value class is
        # [A-Za-z0-9-], so when the run right after the label carries no
        # digit ("XQZ", "ABC", "55", "884"), the digit lookahead fails at
        # the value's start and the whole match aborts before the
        # digit-bearing group later in the string is ever evaluated.
        text=(
            "Member ID: XQZ 884 2190\n"
            "Subscriber ID: ABC 123456\n"
            "Group: 55 210\n"
            "Policy No: 884/2190/11\n"
            "Member ID: 884.2190.11"
        ),
        must_remove=(
            "XQZ 884 2190",
            "ABC 123456",
            "55 210",
            "884/2190/11",
            "884.2190.11",
        ),
    ),
    PhiRecallCase(
        label="short_identifier_after_covered_label_leaks",
        # I1: direct cost of the round-3 length floor (_ID_VALUE requires a
        # first character plus at least four more, i.e. length >= 5) that
        # exists to exclude bare 4-digit years. Four-digit group numbers and
        # short plan/member IDs are real and are not years.
        text=(
            "Group: 5521\n"
            "Group #: 0842\n"
            "Member ID: 1234\n"
            "Plan ID: A123"
        ),
        must_remove=("5521", "0842", "1234", "A123"),
    ),
    PhiRecallCase(
        label="ip_address_in_access_log_line_is_removed",
        # I2: IP_ADDRESS is a HIPAA Safe Harbor identifier (O),
        # 45 CFR 164.514(b)(2)(i)(O), and M3 is a tracing plane where
        # client and host addresses are exactly what span attributes carry.
        text="Portal accessed from 10.1.2.3\nsource_ip=172.16.4.9",
        must_remove=("10.1.2.3", "172.16.4.9"),
    ),
    # --- Known gaps: DATE_TIME over-redaction (expected to FAIL) ---
    # Parked with a ruling: this is a precision problem, not a recall
    # problem, and the durable fix is context-dependent entity sets at
    # M3/M4, not an M2 patch. Encoded as must_survive so the number is on
    # record; keyed in SURVIVAL_GAP_REASONS below.
    PhiRecallCase(
        label="policy_date_range_destroyed_by_date_time",
        text="Policy: 2024-2025 renewal",
        must_remove=(),
        must_survive=("2024-2025",),
    ),
    PhiRecallCase(
        label="group_duration_destroyed_by_date_time",
        text="Group: 30-day waiting period",
        must_remove=(),
        must_survive=("30-day",),
    ),
    PhiRecallCase(
        label="blood_pressure_destroyed_by_date_time",
        text="Blood pressure 120/80 mmHg.",
        must_remove=(),
        must_survive=("120/80",),
    ),
    PhiRecallCase(
        label="dosage_frequency_destroyed_by_date_time",
        text="Dosage: 500 mg twice daily",
        must_remove=(),
        must_survive=("twice daily",),
    ),
    # --- Known gap: plan-name destruction, mis-attributable to DATE_TIME ---
    PhiRecallCase(
        label="plan_name_destroyed_by_custom_id_regex",
        # I7: firing recognizer is INSURANCE_MEMBER_ID, NOT DATE_TIME. Do
        # not change the regex - see RECALL_GAP_REASONS / SURVIVAL_GAP_REASONS
        # and the M2 final-fix brief: this is a precision defect in the
        # exclusion-based value class, not a DATE_TIME interaction, and a
        # fourth regex-correction round is exactly the failure mode being
        # avoided.
        text=(
            "Plan: HDHP3000 deductible is $3,000\n"
            "Plan: PPO2500 network only\n"
            "Policy: FY2024-2025 renewal notice"
        ),
        must_remove=(),
        must_survive=(
            "Plan: HDHP3000 deductible is $3,000",
            "Plan: PPO2500 network only",
            "Policy: FY2024-2025 renewal notice",
        ),
    ),
)

# Cases in PHI_RECALL_CASES whose must_remove assertion is known, today, to
# fail - keyed by label so the test module can xfail them individually and
# exclude them from the gated recall denominator while the aggregate test
# still reports the true corpus-wide number including them.
RECALL_GAP_REASONS: dict[str, str] = {
    "unlabelled_member_id_alone_on_line": (
        "No label precedes the identifier, so neither custom recognizer "
        "fires; US_DRIVER_LICENSE would have caught this shape but was "
        "deliberately excluded because its pattern also matches ICD-10 codes."
    ),
    "unlabelled_member_id_in_table_row": (
        "The ID has no preceding label token inside the table cell, same "
        "root cause as the bare-identifier case. Separately, and newly "
        "visible now that must_remove checks individual name tokens (see "
        "the module docstring): spaCy tags only the given name in a "
        "'Surname, GivenName' table-cell fragment, so 'Okonkwo' leaks "
        "while 'Michael' is correctly redacted - a second, independent "
        "leak in this one case."
    ),
    "uncovered_label_formats_leak": (
        "Reference #, Claim Number, Authorization Number, Rx Number, "
        "Account Number, MRN, Medical Record Number, Patient ID, HICN, "
        "Enrollee ID, Cardholder ID, and bare ID are not in either custom "
        "recognizer's label alternation (Member/Subscriber/Insured/Policy/"
        "Certificate/Plan/MBI/Medicare for the member recognizer, Group "
        "for the group recognizer), so their values are never evaluated as "
        "candidates. The medical record number (MRN) is the primary "
        "patient identifier in clinical documents and an explicit HIPAA "
        "Safe Harbor item (I4); it was added to this case during the M2 "
        "final review alongside its close peers."
    ),
    "ocr_noised_member_id_leaks": (
        "OCR noise (Cyrillic 'г' for Latin 'r', letter O for zero) breaks "
        "the literal 'Member' label match, so the custom recognizer never "
        "fires against the garbled label token."
    ),
    "hyphenated_surname_after_label_leaks": (
        "NOT a hyphen-after-colon-label shape defect - that generalization "
        "was measured and found false: five other hyphenated surnames "
        "directly after a colon-terminated label redact correctly ('Attn: "
        "Deshawn Jefferson-Brooks', 'Spouse: Ellen McAllister-Reyes', "
        "'Beneficiary: Fatima Al-Rashid', 'MEMBER: GARCIA-LOPEZ, MARIA', "
        "'Insured: Jean-Luc Moreau'). The real cause: statistical "
        "named-entity recognition is unreliable per-NAME on "
        "out-of-vocabulary tokens in low-context lines - an unbounded, "
        "unenumerable failure mode, confirmed here by two further named "
        "leaks that share no shape with the original ('AISHA NWOSU-OKAFOR' "
        "leaks entirely in an ALL-CAPS header; 'JAMAL' leaks on its own "
        "line while 'WASHINGTON' is coincidentally caught, but only "
        "because it is mistagged LOCATION, not PERSON). PERSON recall is "
        "NAME-dependent, not SHAPE-dependent: no fixture, however large, "
        "bounds it, so this gap must not be read as 'hyphenated surnames "
        "after a label' - that scope is too narrow for what is actually "
        "unbounded."
    ),
    "address_block_partial_leak": (
        "Newly discovered during this measurement, not on the M2 audit's "
        "original gap list: Presidio's LOCATION recognizer tags only the "
        "city token ('Springfield'); the street address and ZIP code are "
        "left untouched."
    ),
    "spaced_identifier_after_covered_label_leaks": (
        "C2: the label IS covered by the custom recognizer's alternation - "
        "do not read this as a 'label not covered' gap like the ones "
        "above. The value class is [A-Za-z0-9-], so when the token run "
        "immediately after the label carries no digit ('XQZ', 'ABC', '55', "
        "'884'), the digit lookahead (_HAS_A_DIGIT) fails at the very "
        "start of the value and the whole match aborts - the digit-bearing "
        "group later in the same string (e.g. '2190' after 'XQZ 884') is "
        "never reached or evaluated as a candidate. Not fixed here: the "
        "regexes are out of scope for this review (see the M2 final-fix "
        "brief)."
    ),
    "short_identifier_after_covered_label_leaks": (
        "I1: direct cost of the round-3 length floor. _ID_VALUE requires "
        "a first character plus at least four more (effectively length "
        ">= 5), specifically to exclude a bare 4-digit year. Four-digit "
        "group numbers ('5521', '0842') and short member/plan IDs "
        "('1234', 'A123') are real identifiers, not years, and this floor "
        "excludes them too. Do NOT lower the floor to fix this - rounds 1 "
        "through 3 already show that chasing one shape with the regex "
        "reliably breaks another; the floor's tradeoff is accepted and "
        "documented here instead."
    ),
}

# Cases in PHI_RECALL_CASES whose must_survive assertion is known, today, to
# fail - same purpose as RECALL_GAP_REASONS but for the over-redaction side
# of the contract.
SURVIVAL_GAP_REASONS: dict[str, str] = {
    "policy_date_range_destroyed_by_date_time": (
        "DATE_TIME consumes the year range following the label. Parked: a "
        "spec decision (DATE_TIME is in the entity list), a precision "
        "problem rather than a recall problem, fixed by context-dependent "
        "entity sets at M3/M4, not an M2 patch."
    ),
    "group_duration_destroyed_by_date_time": (
        "DATE_TIME consumes the day-count duration following the label. "
        "Same parked ruling as the policy date-range case."
    ),
    "blood_pressure_destroyed_by_date_time": (
        "DATE_TIME consumes the '120/80' reading when it ends the "
        "sentence. Same parked ruling as the policy date-range case."
    ),
    "dosage_frequency_destroyed_by_date_time": (
        "DATE_TIME consumes the 'daily' dosage frequency. Same parked "
        "ruling as the policy date-range case."
    ),
    "pinned_member_id_prose_survives": (
        "DATE_TIME consumes 'ten business days', leaving 'Your Member ID "
        "cards are mailed within <DATE_TIME>.' Same parked ruling as the "
        "policy date-range case; previously disclosed only via a narrowed "
        "must_survive tuple and a comment, which a reader skimming green CI "
        "would never see - restored to the full expected content and "
        "surfaced here instead."
    ),
    "pinned_plan_gold_ppo_2026_survives": (
        "DATE_TIME consumes '2026', leaving 'Plan: Gold PPO <DATE_TIME>' "
        "(confirmed deterministic; 'Plan: Silver HMO 2026' survives "
        "unchanged, so this is a token-sequence-specific spaCy quirk rather "
        "than a blanket rule). Same parked ruling as the policy date-range "
        "case; previously disclosed only via a narrowed must_survive tuple "
        "and a comment - restored to the full expected content and surfaced "
        "here instead."
    ),
    "plan_name_destroyed_by_custom_id_regex": (
        "I7: the firing recognizer is INSURANCE_MEMBER_ID, NOT DATE_TIME - "
        "do not attribute this to the DATE_TIME interaction documented "
        "above, that is a real but separate finding. _NOT_A_YEAR is "
        "anchored at the value's start, so any prefix defeats it: "
        "'HDHP3000' and 'PPO2500' carry a digit run that is not itself a "
        "bare year, and 'FY2024-2025' passes the guard that a bare "
        "'2024-2025' fails, because the guard only inspects the first four "
        "characters after the label. Plan-name tokens are exactly the "
        "field an M4 coverage question needs, and the label is consumed "
        "along with them. Not fixed here: the regexes are out of scope for "
        "this review (see the M2 final-fix brief) - this is a precision "
        "problem in the exclusion-based design, not a recall problem, and "
        "a fourth regex-correction round is exactly the failure mode being "
        "avoided."
    ),
}
