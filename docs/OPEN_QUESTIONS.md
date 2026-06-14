# TaRa Health — Open Questions & Decisions

A running log of design decisions and the questions still open. Update as things
get resolved.

---

## Decisions made

| Decision | Choice | Date |
|----------|--------|------|
| Profiles | **Single profile only** — one user, no family/caregiver support | [Date] |
| Data storage | **Local-first** — data lives on the user's device by default | [Date] |
| License | **Proprietary / All Rights Reserved** for now (may revisit) | [Date] |
| Branding | Product = **TaRa Health**; assistant = **Tara** | [Date] |

---

## Open questions

### 1. Model / provider choice
Hosted frontier model (best quality, but sensitive data leaves the device) vs.
a local/on-device model (privacy-preserving, weaker reasoning) vs. a hybrid
(local for PHI-heavy steps, hosted for general reasoning). The local-first
decision pushes toward keeping as much on-device as feasible — but does the
quality hold up for grounded medical/insurance reasoning?

### 2. Provider portals without a clean public API
Epic on FHIR exists, but production access requires Epic's app review, and
write-back actions (scheduling, messaging) are heavier than read access. Not all
facilities expose a portal. **Question:** do early versions use read-only FHIR +
assisted handoff for scheduling, and defer full automated booking?

### 3. Pharmacy & delivery integrations are gated
- CVS / Walgreens pharmacy APIs require provisioning and may restrict to mobile apps.
- Instacart's public API doesn't place orders directly — it hands off to an Instacart-hosted checkout page.
- Food delivery (DoorDash / Uber Eats) consumer-order APIs are limited.

**Question:** which of these is worth the integration effort vs. starting as a
"Tara prepares it, you tap to confirm on their site" handoff?

### 4. Messages / SMS
iMessage has no official API. **Question:** is SMS via a provider like Twilio
worth it, or are in-app + calendar/email notifications enough for v1?

### 5. Document store location & format (within local-first)
Where exactly do documents and the vector index live on-device, and how are they
encrypted? How does the user back up or migrate their data?

### 6. Liability & disclaimers
What's the right framing and consent flow so Tara's health guidance is clearly
informational, especially if this ever moves from personal project to product?

### 7. Productization triggers
If/when this becomes a product: what changes for HIPAA, multi-user support
(currently out of scope), hosting, and licensing? Worth noting the seams now so
single-profile/local-first decisions don't become expensive to unwind later.
