# TaRa Health — Open Questions

The design questions still open. Update as they get resolved — when a question is
settled, **remove it here and record the decision in its canonical doc** (product
decisions in [PRD.md](PRD.md), technical decisions in the phase technical-design
docs, license in `LICENSE`). This file is not a decision log; it only tracks what's
undecided.

---

## 1. Local-model quality for grounded medical/insurance reasoning
The provider *mechanism* is settled (a `local` / `hosted` / `hybrid` config switch,
default `local` — see the technical design). What's still open is empirical: does
the on-device model hold up for grounded medical/insurance reasoning, or do we need
to default to `hybrid`/`hosted` for acceptable quality? **Resolve via the eval
harness** (technical design §8 / build step 7) — measure citation correctness and
honesty for `local` vs `hosted` on the fixture set, then pick the default with
evidence.

## 2. Liability & disclaimers — consent flow
Framing is already decided (the README carries a disclaimer and `safety/framing.py`
enforces "general information, not a diagnosis" on every answer). **Still open:** the
explicit consent flow — what the user agrees to, and when — especially if this ever
moves from personal project to product. (Proactive-feature consent is designed in
[PHASE_4_TECHNICAL_DESIGN.md](PHASE_4_TECHNICAL_DESIGN.md) §3.5; the broader
product-level consent flow remains open.)

## 3. Productization triggers
If/when this becomes a product: what changes for HIPAA, multi-user support
(currently out of scope), hosting, and licensing? Worth noting the seams now so the
single-profile / local-first decisions don't become expensive to unwind later.
