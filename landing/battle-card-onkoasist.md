# Oncoteam vs OnkoAsist — Battle Card

> **Purpose:** Source of truth for NCZI outreach letters, press Q&A, LinkedIn talking points.
> **Audience:** Internal only. Not served publicly. Updated: 2026-04-16 (Sprint 89).
> **Full analysis:** see `memory/reference_metais-onkoasist-deep-dive.md`.

## Core framing

> **OnkoAsist and Oncoteam cover opposite halves of the cancer journey. We don't compete — we complement.**

- **OnkoAsist** = state backbone for the pre-treatment pathway (symptom → diagnosis → start of treatment). National infrastructure, planned.
- **Oncoteam** = patient-facing layer for during-treatment and beyond (cycles, dose mods, research, family communication). Working product, live since Feb 2026.

The scope overlap is near-zero by design. OnkoAsist's feasibility study explicitly ends at treatment initiation — exactly where Oncoteam's value begins.

## One-line positioning

**"Oncoteam is the intelligence layer for the time between oncology visits — the part national eHealth doesn't cover."**

## Quick-reference comparison

| Dimension | OnkoAsist (NCZI) | Oncoteam |
|---|---|---|
| Scope in journey | Pre-diagnosis → start of treatment | Active treatment → survivorship |
| Status (2026-04) | Tender open since 01/2023 — unawarded | In production, 3 patients, live |
| Realistic go-live | 2027-2028 (if procurement clears) | Already shipping weekly |
| Architecture | Classical SOA on eZdravie, on-prem NCZI | MCP multi-agent, cloud-native (Railway) |
| Patient channels | eID web portal | WhatsApp, dashboard, Claude.ai MCP, voice, photo |
| Data source | National register (law 153/2013), eLab, eZdravie | Patient-owned Google Drive, OCR of paper |
| Clinical depth | Appointment booking, pre-diagnosis triage, decision support to start of treatment | Pre-cycle safety, dose mods, cumulative dose, biomarker-aware trial matching, PubMed funnel |
| Funding | €10.93M tender ceiling, EU-funded | Open-source, free during active treatment |
| Pilot diagnoses | 3 (C34 lung, C18-20 CRC, C50 breast) | Any oncology diagnosis + general health |
| Legal authority | ISVS, NOR feed, mandatory reporting | Advisory-only patient tool |

## Talking points (LinkedIn, press, NCZI)

### When someone asks "isn't there already a Slovak eHealth oncology project?"

> "Yes — OnkoAsist at NCZI. It's meant to solve a different problem: making sure a patient gets from first symptom to start of treatment within 60 days instead of 160. We think that's an important project. Oncoteam starts where OnkoAsist ends — from the moment treatment begins, through every chemo cycle, every lab result, every trial that might match. Different scope, different user, different cadence. We're happy to see the state investing in the first half of the journey."

### When someone asks "why build this if the state is building it?"

> "They're not building what we build. OnkoAsist is a pre-treatment pathway manager — appointment booking, referral routing, pre-diagnosis triage. It ends at treatment initiation. Oncoteam is a during-treatment clinical companion — it reads lab results after every cycle, flags when ANC drops below threshold, searches clinical trials when a biomarker profile changes. These are complementary layers."

### When someone asks "would you bid on a NCZI tender?"

> "No. Our cadence is weekly; NCZI's procurement cadence is multi-year. We'd be the wrong partner for a €10M tender. But we'd love to feed patient-reported outcomes into any national system that eventually captures them — that's the pitch we'd bring to an NCZI conversation."

### If asked about OnkoAsist delays or adoption risk

Stay neutral. Do not criticize. Say:

> "Government IT projects at this scale have their own rhythm. We respect that. Our job is to help the patients who are in active treatment right now."

## Red flags validating Oncoteam's approach (from Slovensko.Digital Red Flags review)

Use these for policy audiences (parliament, ministry, ÚVZ), **not** for general LinkedIn.

- eZdravie modules (eObjednanie, eVyšetrenie, eLab) described as "practically unused" despite years of investment.
- Only 101 of 275,000 generated electronic referrals were actually accessed (H1 2021 data — NCZI own metric).
- eLab promised for 01/2025 — still non-operational per STVR reporting, June 2025.
- Physicians lack native GUI; depend on third-party EHR vendors.

**Conclusion:** Top-down state-led digitization in SK healthcare has a strong under-adoption pattern. Patient-facing bottom-up tools (Oncoteam via WhatsApp) bypass the adoption problem by meeting patients where they already are.

## Gaps in our offering (we should acknowledge these honestly)

- No eID authentication (we use phone + Google OAuth).
- No FHIR R4 / HL7 interoperability (we use MCP).
- No ISVS registration (legal prerequisite for national data reads).
- Not a medical device / clinical decision support system (and we intentionally stay advisory-only to avoid MDR Class IIa regulation).
- No appointment booking, no inter-provider data exchange.

These are the things OnkoAsist (or a future version of it) is right to build.

## Integration we would welcome

If OnkoAsist eventually ships, the high-value handoff is:

1. **OnkoAsist marks patient as "treatment initiated"** → webhook provisions an Oncoteam profile pre-populated with diagnosis, staging, biomarkers. Eliminates manual onboarding.
2. **Oncoteam collects WhatsApp-based PROs** (symptoms, toxicity, quality-of-life) → feeds OnkoAsist's clinical data module. Solves OnkoAsist's likely physician-input adoption problem.

Both directions require FHIR R4 + eID on our side. 2-3 sprints of work. Not on roadmap unless NCZI engagement materializes.

## What NOT to do

- Do not bid on OnkoAsist or any NCZI tender.
- Do not position as "cheaper alternative to OnkoAsist." That's a fight we can't win and shouldn't try.
- Do not claim "medical device" or "clinical decision support system."
- Do not assume OnkoAsist ships on its announced timeline — plan as if it's 2028+ or not at all.
- Do not criticize NCZI publicly. Humble tone per project convention.

## Sources

- Slovensko.Digital Red Flags — https://redflags.slovensko.digital/projekty/8255/hodnotenie-pripravy
- JOSEPHINE tender #35645 — https://josephine.proebiz.com/sk/tender/35645/summary
- NCZI public consultation page — https://www.nczisk.sk/Aktuality/Pages/Verejne-pripomienkovanie-studie-uskutocnitelnosti-Onkoasist.aspx
- Full analysis — `memory/reference_metais-onkoasist-deep-dive.md`
