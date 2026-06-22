# TaRa Health — Open Questions

The design questions still open. Update as they get resolved — when a question is
settled, **remove it here and record the decision in its canonical doc** (product
decisions in [PRD.md](PRD.md), technical decisions in
[PHASE_1_TECHNICAL_DESIGN.md](PHASE_1_TECHNICAL_DESIGN.md), license in `LICENSE`).
This file is not a decision log; it only tracks what's undecided.

---

## 1. Local-model quality for grounded medical/insurance reasoning
The provider *mechanism* is settled (a `local` / `hosted` / `hybrid` config switch,
default `local` — see the technical design). What's still open is empirical: does
the on-device model hold up for grounded medical/insurance reasoning, or do we need
to default to `hybrid`/`hosted` for acceptable quality? **Resolve via the eval
harness** (technical design §8 / build step 7) — measure citation correctness and
honesty for `local` vs `hosted` on the fixture set, then pick the default with
evidence.

## 2. Provider portals without a clean public API
Epic on FHIR exists, but production access requires Epic's app review, and
write-back actions (scheduling, messaging) are heavier than read access. Not all
facilities expose a portal. **Question:** do early versions use read-only FHIR +
assisted handoff for scheduling, and defer full automated booking? *(Phase 2+.)*

## 3. Pharmacy & delivery integrations are gated
- CVS / Walgreens pharmacy APIs require provisioning and may restrict to mobile apps.
- Instacart's public API doesn't place orders directly — it hands off to an Instacart-hosted checkout page.
- Food delivery (DoorDash / Uber Eats) consumer-order APIs are limited.

**Question:** which of these is worth the integration effort vs. starting as a
"Tara prepares it, you tap to confirm on their site" handoff? *(Phase 2+.)*

## 4. Messages / SMS
iMessage has no official API. **Question:** is SMS via a provider like Twilio
worth it, or are in-app + calendar/email notifications enough for v1? *(Phase 2+.)*

## 5. Liability & disclaimers — consent flow
Framing is already decided (the README carries a disclaimer and `safety/framing.py`
enforces "general information, not a diagnosis" on every answer). **Still open:** the
explicit consent flow — what the user agrees to, and when — especially if this ever
moves from personal project to product.

## 6. Productization triggers
If/when this becomes a product: what changes for HIPAA, multi-user support
(currently out of scope), hosting, and licensing? Worth noting the seams now so the
single-profile / local-first decisions don't become expensive to unwind later.
