# Oncoteam — Competitive Landscape

> Compiled 2026-04-16. EU / CEE primary focus. Revisit when: any listed platform changes status, a new AI-native EU entrant launches, OnkoAsist finally awards its tender, or a major pharma/payer acquires a patient-app competitor.

## Summary

Oncoteam sits at an unusual intersection: **AI-native (LLM agents, not chatbot widgets) + multi-channel (WhatsApp + voice + dashboard) + patient-advocate (multi-patient mode) + open-source + multi-lingual (SK + EN) + during-treatment focus**. No other surveyed platform covers all six dimensions. The closest functional overlap is **Belong.Life** (AI mentor "Dave", community, multi-lingual) and **Outcomes4Me + Mika** (US-origin platform that acquired Germany's Mika in 2025 for EU entry, breast + lung focus). Everything national (OnkoAsist SK, KSO Poland, OncoAppstore NL, EESZT Hungary, Czech Patient Portal, MyHealth@EU) is physician-oriented or classical SOA on national eID with no AI agents and multi-year procurement cycles. Among **AI-native European start-ups**, most are either pharma-funded DTx point solutions (Moovcare, Resilience PRO — both CE-marked IIa medical devices) or research chatbots (Wefight Vik, Mika pre-acquisition). Two platforms overlap OnkoAsist/oncoteam's ambitions but from opposite ends: **Elekta Kaiku Health** (Finnish ePRO, enterprise-deployed at hospitals, not patient-driven) and **Careology** (UK consumer-facing cancer app, shipping at NHS trusts in 2025, no AI agents, no multi-lingual). The most striking asymmetry: **OnkoAsist SK has burned €7.2M CAPEX over 4 years with zero live patients; oncoteam has shipped 89 sprints on €0 and has 3 live patients** — and this pattern (slow, expensive, unadopted national eHealth vs fast, cheap, patient-driven bottom-up) repeats across the EU.

## Comparison table

| Platform | Country | Status (2026-04) | AI | Budget / Model | Patient-facing | Link |
|---|---|---|---|---|---|---|
| **oncoteam** | SK/EU | Live, 3 patients, v0.80.0 | **LLM agents (21 Claude)** | Bootstrapped, open-source | Yes (advocate-first) | [oncoteam.cloud](https://oncoteam.cloud) |
| OnkoAsist (NCZI) | SK | In procurement since 2023; **0 patients** | No (rule-based) | €7.2M CAPEX EU funds | Portal (planned) | [metais.slovensko.sk](https://metais.slovensko.sk) |
| KSO + Nat'l Oncology Portal | PL | Live 04/2025 | No | Gov funded | Portal | [onkologia.pacjent.gov.pl](https://onkologia.pacjent.gov.pl) |
| Czech Patient Portal | CZ | Launching 2026 | No | Gov funded | Mobile + web | [pacient.mzcr.cz](https://www.expats.cz/czech-news/article/electronic-healthcare-appointments-and-patient-records-to-begin-in-czechia-from-2026) |
| EESZT + EgészségAblak | HU | Live | No | Gov funded | Mobile (general health, not onco-specific) | [eeszt.gov.hu](https://e-egeszsegugy.gov.hu) |
| OncoAppstore | NL | 2025 pilot | No (curation) | Gov + research | Curated app catalog | [iknl.nl](https://iknl.nl) |
| Belong.Life ("Dave") | IL/global | Live | **LLM mentor** | VC, freemium | Yes | [belong.life](https://belong.life) |
| Outcomes4Me (+ Mika) | US→EU (DE) | Live, 280k + 100k users | **AI-driven** | $21M Series 2025 | Yes | [outcomes4me.com](https://outcomes4me.com) |
| Kaiku Health (Elekta ONE) | FI/global | Live | ePRO analytics (no LLM) | Elekta-owned enterprise | Via hospital | [kaikuhealth.com](https://kaikuhealth.com) |
| Noona (Varian / Siemens) | FI→US/global | Live | ePRO (no LLM) | Siemens Healthineers | Via hospital | [varian.com/noona](https://www.varian.com/) |
| Careology | UK | Live, NHS deployments 2025 | No LLM | VC + NHS pilots | Yes | [careology.health](https://www.careology.health) |
| Resilience PRO | FR/BE | Live, reimbursed 10/2023 | ePRO + AI | VC | Yes (MDR IIa) | [resilience.care](https://www.resilience.care) |
| Moovcare Poumon (Sivan) | FR | Live, LPPR 2020 | Alert algorithm | Reimbursed | Yes (MDR) | Sivan Innovation |
| Wefight Vik | FR | Live (mature chatbot era) | NLP chatbot | VC | Yes, free | vik.ai |
| Jasper Health | US | Live, $31.8M raised | AI-driven nav | VC | Yes (caregivers) | [hellojasper.com](https://www.hellojasper.com) |
| Color Health Cancer Copilot | US | Live, OpenAI-built | **LLM (GPT)** | Color-funded | Hybrid (clinician-first) | [color.com/cancer](https://www.color.com/cancer) |
| Sidekick Health (onco) | IS | Live | DTx + AI | €35M EIB 2025 | Yes (DTx) | [sidekickhealth.com](https://www.sidekickhealth.com) |
| OpenMRS Oncology Module | global (OSS) | Live in LMICs | No | OSS / grants | Clinician-facing | [github.com/openmrs](https://github.com/openmrs/openmrs-module-oncology) |
| OpenClinica | global (OSS) | Live | No | OSS + commercial | Researcher-facing | [openclinica.com](https://www.openclinica.com) |
| OnkoInfo.sk | SK | Live (since 2019) | No | NGO | Portal (info only, no records) | [onkoinfo.sk](https://onkoinfo.sk) |

## National eHealth oncology (CEE)

### Slovakia — OnkoAsist (NCZI)
One-line: Classical SOA pre-treatment pathway manager built on eZdravie; **€7.2M CAPEX / €10.93M tender ceiling**, tender launched 01/2023, still **unawarded 04/2026**, zero live patients. Pilot diagnoses: lung (C34), CRC (C18-C20), breast (C50). Scope ends at treatment start — covers exactly the segment oncoteam doesn't cover.
Full deep-dive: `reference_metais-onkoasist-deep-dive.md` (private memory).

### Czech Republic — Patient Portal (Portál pacienta)
Launch: 2026 (delayed from 2025). **Not oncology-specific** — general patient portal for e-requests, e-booking, and record access. Czech National Cancer Control Plan 2022-2030 references "telemedicine in oncology" but no dedicated oncology patient module is in public flight. No AI features reported. Gov-funded under multi-year national digital health strategy 2016-2026. eHealth Act in force 01/2026.

### Poland — Krajowa Sieć Onkologiczna (KSO) + Narodowy Portal Onkologiczny
Launch: **01/04/2025** nationwide. KSO is a network organizational model (patient pathways, coordinator-driven referrals, standardized treatment). Digital components: **e-DiLO card** (mandatory 01/2026) and the **National Oncological Portal** (onkologia.gov.pl) for patient information. Care is coordinator-mediated — "the coordinator, not the patient, finds the appropriate center." Gov-funded (Fundusze Europejskie dla Zdrowia). No AI features; informational portal + organizational re-orchestration rather than personal advocate.

### Hungary — EESZT + EgészségAblak
Live. EESZT is the national eHealth backbone; EgészségAblak is the mobile app (Client Gate+ or Digital Citizenship Mobile App login as of 01/2025). A **national oncology IT system in 19 county + 4 regional centres** was scoped but as of 2025 public sources don't show a dedicated patient-facing oncology module. No AI features. Hungarian-only.

### Slovenia — CRPD
The Central Registry of Patient Data is Slovenia's national EHR storage/exchange platform. Strong data infrastructure (cited by WHO/OECD as exemplar alongside Austria, Belgium, Finland for cancer data). No onco-specific patient-facing app identified. Slovene-only.

### Croatia, Romania, Baltics
Croatia: EU Country Cancer Profile 2025 published; no dedicated oncology patient platform identified. Romania: Participating in **RO-MI-LR-DR** (EU4Health, starts 2026, medical images + lab results + discharge reports) and **TRANSiTION** project on oncology digital skills. ICON operates a molecular-profiling tumour board EHR for breast cancer. Baltics: Joined **MyHealth@EU** in 2025; no onco-specific patient apps identified.

## National eHealth oncology (broader EU)

### Germany — Nationale Dekade gegen Krebs + DKFZ
National Decade Against Cancer (co-chaired by DKFZ) is a research + policy programme, not a patient platform. DKFZ runs **Krebsinformationsdienst (KID)** — cancer information service (phone + web, human experts), no AI. **European Cancer Hub Germany** launched 11/2025. No unified national onco patient app identified; fragmented via hospital portals + Mika (now Outcomes4Me-owned, see below).

### France — Moovcare, Resilience PRO, Continuum+
France has the **most developed ePRO-for-oncology reimbursement pathway** in EU. Moovcare Poumon (lung) — LPPR reimbursement since 2020, algorithm detects relapse signals from symptom reports. **Resilience PRO** — first and only digital health oncology solution with branded-line reimbursement (10/2023), MDR Class IIa, used at 33 cancer centres (FR + BE). **Continuum+ Connect** — denied LATM access 07/2023. All three are physician-prescribed, not self-enroll.

### Netherlands — OncoAppstore (IKNL + PALGA)
Pilot study 2025. A **curated catalog** of vetted cancer self-management apps (not a single app itself) developed by IKNL (Netherlands Comprehensive Cancer Organisation). Linked to the **Netherlands Cancer Registry (NCR)** for outcome tracking. Dutch-only. Research/implementation phase. **Oncokompas** — older IKNL self-management eHealth app for survivors (HRQoL improvement, published Acta Oncologica 2020).

### Nordics (DK/SE/NO/FI)
No dedicated national oncology patient app. **Sundhed.dk** (Denmark's general eHealth portal) has Europe's largest patient-portal footprint; Swedish equivalents have the best availability of functionalities but lower usage. **NORDCAN** = cancer statistics database (not patient-facing). NORDeHEALTH project benchmarks patient-facing eHealth across Nordic + Estonia. **Helseplattformen** (Norway) held up as interoperability exemplar.

### Italy, Spain
Italy: National Oncology Plan 2023-2027 commits to digital transition and home telemedicine; no unified patient-facing oncology app identified as live. Spain: Active in EU TRANSiTION project for oncology digital skills; region-level EHR portals but no unified national onco patient app. **ONCOassist** (decision support app, clinician-facing, deployed in UK/IE/FR/IT/ES/PT) is the closest cross-market European tool — but it's for clinicians, not patients.

## Private oncology patient platforms (EU)

### Belong.Life (IL, global)
AI mentor "Dave" (conversational) + "Dave Pro" (long-term memory, document review, reminders). **Free + Pro tier.** Multi-lingual communities (ES, FR, RU, ZH, HE, EN — UI in EN). Features: support groups, clinical-trial matching (ML), document organization, personalized content, direct expert chats. Scale: global patient community. Closest functional overlap with oncoteam's conversational + trial-matching dimensions.

### Outcomes4Me (US → EU via Mika acquisition)
Boston-based. **280k+ users** (breast + lung cancer). AI-driven patient empowerment platform: clinical guidelines + genomics + trial matching + symptom tracking. **$21M Series 2025**. **Acquired German Mika Health (Fosanis GmbH) in 06/2025** — Mika is MDR IIa, 100k+ patients, clinically-validated DTx with daily symptom monitoring + AI coaching. Combined: largest EU-reach AI-native oncology patient platform.

### Kaiku Health (Elekta ONE Patient Companion)
Finnish origin (Helsinki, piloted at Docrates 2012), acquired by Elekta. Now **Elekta ONE Patient Companion** — enterprise ePRO deployed via hospital contracts (not self-enroll). Finnish bank-ID login supported. Strategic partnership with **H2O (Health Outcomes Observatory)** announced 10/2025 for EU-wide standardized real-world outcome capture. Rule-based alerting, no LLM.

### Noona (Varian → Siemens Healthineers)
Finnish origin, acquired by Varian 2018, now under Siemens Healthineers. Hospital-deployed ePRO + symptom tracking + scheduled-appointment views + lab results. 99% activation at CancerCare Manitoba. **Not self-enroll.** Rule-based, no LLM.

### Careology (UK)
UK consumer-facing cancer app. Live at **The Royal Marsden, Guy's and St Thomas', Airedale NHS FT (02/2025)** via West Yorkshire & Harrogate Cancer Alliance. UKONS traffic-light symptom logging, wearable integration (steps/HR/SpO2/BP), My Network + Caregivers sharing, Boots Macmillan pharmacist connection. Partners with Boots pharmacy. **No LLM agents, English-only**, NHS-deployment-driven.

### Resilience PRO (FR/BE)
Covered above under France. CE-marked IIa, reimbursed. 33 cancer centres. Patient mobile + web + HCP interface with EHR integration.

### Wefight Vik (FR)
Early AI chatbot (Vik Breast at CES 2019). NLP-based (pre-LLM architecture). Free, multi-disease (asthma, depression, headache + cancer). Mature product but now overshadowed by LLM-powered successors.

### Jasper Health (US)
$31.8M raised (Series A 02/2022, no 2025 round identified). Cancer care navigation + caregiver support. **1-on-1 virtual support**, AI-driven features. US-only.

### Color Health Cancer Copilot (US)
Built with OpenAI. **Clinician-first** (orders workup, screening plans) with patient-facing Color Assistant (screening + mental health). Not primarily a patient-advocate tool; it's a clinician AI augmented by patient-facing modules.

### Sidekick Health (IS, global)
Icelandic DTx company, oncology programme is one of several verticals (also CV, metabolic, inflammatory). Pharma-partnered deployments. **€35M EIB venture debt 2025** for AI + global expansion. Not a self-enroll consumer app in most markets.

### LivingWith (Pfizer Oncology, US)
Free app from Pfizer. Not Janssen (despite common confusion). General life-with-cancer management. US-centric.

## Open-source / research platforms

### OpenMRS Oncology Module
Open-source EMR extension for chemotherapy management. Developed with IBM + Partners In Health + Uganda Cancer Institute + UNC. Clinician-facing, targeted at LMICs (low-and-middle-income countries). Not patient-facing.

### OpenClinica
Open-source EDC/CDM platform for clinical trials — including oncology trials (used at Oxford Oncology). Researcher-facing, not patient-facing.

### LabKey
Research data platform; used by some cancer centers for biospecimen/molecular data. Researcher-facing.

### Oncio
Free-tier oncology app (details limited from public search); likely patient-facing but low visibility in EU market compared to above.

### OnkoInfo.sk
Slovak NGO patient-information portal since 2019. Static content (diagnoses, nutrition, mental health, legal help), not a personal advocate app. Often cited as the Slovak patient reference but **no record management, no AI, no personalization**.

## AI-native oncology patient tools

Filtered to LLM/agent-based tools, not ePRO-with-algorithm:

| Tool | AI architecture | Patient-channel | Unique angle |
|---|---|---|---|
| **oncoteam** | 21 Claude agents with extended thinking, MCP multi-server | WhatsApp + voice + dashboard | Open-source, multi-patient advocate mode, during-treatment clinical intelligence |
| Belong.Life "Dave" / "Dave Pro" | LLM mentor + ML trial matching | Mobile app | Established community + expert chats + free tier |
| Outcomes4Me + Mika | AI-driven (stack not public) + Mika ML | Mobile app | MDR IIa (Mika), pharma partnerships, now EU-ready via 2025 acquisition |
| Color Health Cancer Copilot | OpenAI LLM | Clinician-first with patient modules | Guideline-grounded RAG, virtual cancer clinic |
| Mika (pre-acquisition) | ML + content | Mobile (DE primary) | DTx, CE-certified, now part of Outcomes4Me |
| Wefight Vik | NLP chatbot (pre-LLM) | Messenger + web | Free, mature chatbot — now stale-tech relative to LLM-era |
| Academic LLM projects (Cancer Core Europe) | GPT-4 + RAG (breast cancer German pilot 2025) | Research prototypes | Not productized |

Outside EU: **BotMD** (Singapore, WhatsApp oncology automation for clinics — closest architectural neighbor, but clinic-facing not patient-advocate) and **Meeval** (India AI, 2026 grant, symptom logging in EN/Malayalam — WhatsApp not yet live).

## Where oncoteam uniquely sits

Dimensions matrix (✓ = present, ~ = partial):

| Dimension | oncoteam | OnkoAsist | Belong | Outcomes4Me+Mika | Kaiku | Noona | Careology | Moovcare/Resilience |
|---|---|---|---|---|---|---|---|---|
| LLM agents (not just chatbot) | ✓ | | ✓ | ✓ | | | | |
| WhatsApp / voice channel | ✓ | | | | | | | |
| Open-source | ✓ | | | | | | | |
| Multi-patient advocate mode | ✓ | | | | | | | |
| Multi-lingual (SK+EN baseline) | ✓ | ~ (SK) | ✓ (communities) | ~ (DE via Mika) | ~ (FI+EN) | ~ | | ~ (FR) |
| During-treatment clinical intelligence (pre-cycle, dose mods, cumulative dose) | ✓ | | | ~ | ~ | ~ | ~ | ~ |
| Tumor-marker trend analysis (CEA, CA19-9) | ✓ | | | | | | | |
| Biomarker-aware therapy exclusion (KRAS/NRAS/BRAF/MSI) | ✓ | | | | | | | |
| Clinical-trial matching | ✓ | | ✓ | ✓ | | | | |
| PubMed / literature ingestion | ✓ | | | | | | | |
| Family-translator narrative | ✓ | | | | | | | |
| Handwritten chemo-sheet OCR (Sonnet) | ✓ | | | | | | | |
| Self-enroll (no hospital gate) | ✓ | | ✓ | ✓ | | | | |
| National EHR integration / NOR feed | | ✓ | | | ~ (HIS) | ~ | ~ (NHS) | ~ |

**Uniquely at oncoteam (no other surveyed platform covers):** LLM-agent-native + WhatsApp + open-source + multi-patient + multi-lingual + during-treatment clinical-protocol depth.

## DIRECT competitors (same user, same job-to-be-done)

Narrowest overlap = "I am a patient or caregiver and I want an AI helper for my specific cancer journey, outside of what the hospital hands me":

1. **Belong.Life + Dave Pro** — closest behavioral analogue (free AI mentor, document review, trial matching). Wins on scale + community. Oncoteam wins on during-treatment depth + open-source + SK language.
2. **Outcomes4Me + Mika (post-acquisition)** — closest functional analogue. Wins on MDR certification + VC-scale + US/DE reach. Oncoteam wins on open-source + multi-patient + SK + biomarker-aware exclusion depth.
3. **Careology** — closest consumer-cancer-app analogue but UK-only, no AI agents. Wins on NHS-channel distribution. Oncoteam wins on everything AI-native + multi-lingual.

## ADJACENT / COMPLEMENTARY

- **OnkoAsist** (SK) — covers pre-treatment pathway, oncoteam covers during-treatment. Explicit complement. See full deep-dive memory.
- **Kaiku Health / Noona** — enterprise ePRO for hospitals. oncoteam is patient-driven self-enroll. Complementary if a hospital adopts Kaiku and a patient independently uses oncoteam.
- **Moovcare / Resilience PRO** — prescribed DTx. oncoteam is advocate-layer. Complementary.
- **OnkoInfo.sk** — static info portal. Complementary (oncoteam could link out to OnkoInfo for content).

## OBSOLETE / SLOW / UNADOPTED

- **OnkoAsist tender** — 3+ years in procurement with zero patients. Pattern repeats across SK eHealth (eObjednanie, eLab per Slovensko.Digital Red Flags). Validates bottom-up over top-down.
- **Wefight Vik** — pre-LLM NLP chatbot; still live but architecturally superseded.
- **Continuum+ Connect** — denied French reimbursement 07/2023.
- **Czech + Hungarian patient portals** — general eHealth, no onco-specific module despite years of investment.

## Asymmetry notes (for battle card)

- **€7.2M CAPEX OnkoAsist vs €0 oncoteam** — OnkoAsist has been in procurement since 01/2023 with zero live patients; oncoteam has 3 live patients and ships weekly on bootstrap budget.
- **Decade+ in planning vs 1 year of shipping** — Czech eHealth national strategy spans 2016-2026 (still rolling out patient portal in 2026); OnkoAsist feasibility study 2022, still unawarded 2026. oncoteam: Feb 2026 launch → 89 sprints by 04/2026.
- **Classical SOA (no AI) vs LLM-agent-native** — Every national eHealth platform surveyed (OnkoAsist, KSO, EESZT, Czech Patient Portal, Slovenian CRPD) uses rule-based decision logic at best. oncoteam runs **21 autonomous Claude agents** (Sonnet + Haiku) with extended thinking, scheduled jobs, cost controls, per-patient circuit breakers.
- **Enterprise-gated ePRO vs self-enroll** — Kaiku (Elekta) + Noona (Siemens) + Moovcare + Resilience PRO all require a hospital/oncologist to enroll you. oncoteam requires a WhatsApp number.
- **English or single-national-language only vs SK + EN baseline** — Careology (EN), Sidekick (EN), Jasper (EN), Mika (DE), Vik (FR). oncoteam is Slovak-first, English-ready, architected for more.
- **DTx closed-source CE-marked vs advocate-tool open-source** — Resilience PRO and Mika are MDR IIa medical devices (strengths: reimbursement, weakness: slow iteration, closed feature set). oncoteam stays advisory-only → no medical-device regulatory lock-in → weekly sprints.
- **One-patient-per-account vs multi-patient advocate mode** — Every surveyed consumer cancer app is one-patient-per-login. oncoteam's role-based model (Peter tracking Erika + q1b + e5g + sgu) is **not found in any other surveyed platform**.
- **Community-of-patients (Belong) vs personalized clinical intelligence (oncoteam)** — Belong is patients-help-patients scaled by LLM; oncoteam is personal-clinical-brain scaled by LLM. Different primary job.

## Recommended TOP 6-8 platforms for compact landing-page comparison

Picked for (a) highest public-awareness, (b) most meaningful overlap, and (c) cleanest asymmetry story:

1. **OnkoAsist (SK)** — show the national project asymmetry (€7.2M, 0 patients, 3+ years in tender)
2. **Belong.Life (Dave)** — global AI-mentor competitor; closest behavioral overlap
3. **Outcomes4Me + Mika** — EU AI-native competitor with scale (280k + 100k users)
4. **Kaiku Health (Elekta ONE)** — EU enterprise ePRO standard-bearer
5. **Noona (Siemens)** — second EU/global enterprise ePRO
6. **Careology (UK)** — closest EU consumer-cancer-app analogue
7. **Resilience PRO (FR)** — reimbursed-DTx benchmark in EU
8. **KSO + National Oncology Portal (PL)** — second national eHealth example to contrast with OnkoAsist

Drop for the landing-page table: Noona if space is tight (overlaps with Kaiku's enterprise-ePRO story), and Resilience PRO (overlaps with Kaiku on "hospital-gated, CE-marked" story). That gives a crisp **6-row table: oncoteam + OnkoAsist + Belong + Outcomes4Me + Kaiku + Careology + KSO**.

## Sources

### National eHealth (CEE)
- [Slovensko.Digital Red Flags: OnkoAsist](https://redflags.slovensko.digital/projekty/8255/hodnotenie-pripravy)
- [JOSEPHINE tender #35645 (OnkoAsist)](https://josephine.proebiz.com/sk/tender/35645/summary)
- [Polish KSO official — onkologia.pacjent.gov.pl](https://onkologia.pacjent.gov.pl/pl/narodowa-strategia-onkologiczna/krajowa-siec-onkologiczna)
- [KSO 2025 rollout — rp.pl](https://www.rp.pl/zdrowie/art39748621-krajowa-siec-onkologiczna-rok-pozniej)
- [Czech Patient Portal 2026 — expats.cz](https://www.expats.cz/czech-news/article/electronic-healthcare-appointments-and-patient-records-to-begin-in-czechia-from-2026)
- [Czech National Cancer Control Plan 2022-2030 (PDF)](https://mzd.gov.cz/wp-content/uploads/2022/07/2207_MZCR_NOPL_CR_2030_EN_v03.pdf)
- [eHealth in Czech Republic — gnius.esante.gouv.fr](https://gnius.esante.gouv.fr/en/international-digital-health-systems/ehealth-in-czech-republic)
- [EESZT Information Portal (Hungary)](https://e-egeszsegugy.gov.hu/en/web/eeszt-information-portal/home)
- [EU Country Cancer Profiles 2025 — ECIR](https://cancer-inequalities.jrc.ec.europa.eu/country-cancer-profiles-2025)
- [eCAN Policy Mapping Slovenia Factsheet (PDF)](https://ecanja.eu/downloads/eCAN_WP4_Policy_Mapping_Country_Factsheet_SI_reviewed_final.pdf)
- [EU Country Cancer Profile: Croatia 2025 (PDF)](https://www.oecd.org/content/dam/oecd/en/publications/reports/2025/02/eu-country-cancer-profile-croatia-2025_dc412e98/46c5e70c-en.pdf)
- [EU4Health 2024 Work Programme — HaDEA](https://hadea.ec.europa.eu/news/2024-eu4health-work-programme-new-projects-advancing-digital-healthcare-across-eu-2025-12-03_en)
- [Good practice Romanian breast cancer molecular tumour board](https://digital-strategy.ec.europa.eu/en/news/good-practice-b2g-data-sharing-romanian-breast-cancer-molecular-profiling-tumour-board)
- [European Cancer Hub Germany launch 11/2025](https://www.dekade-gegen-krebs.de/de/wir-ueber-uns/aktuelles-aus-der-dekade/_documents/european-cancer-hub-germany.html)
- [Italy National Oncology Plan 2023-2027](https://eurohealthobservatory.who.int/monitors/health-systems-monitor/analyses/hspm/italy-2023/the-national-oncology-plan-2023-2027)
- [NORDCAN — IARC](https://nordcan.iarc.fr/en/about)
- [Nordic eHealth Benchmarking — Nordforsk](https://www.nordforsk.org/projects/nordic-ehealth-patients-benchmarking-and-developing-future)
- [Dutch OncoAppstore study protocol 2025 — Supportive Care in Cancer](https://link.springer.com/article/10.1007/s00520-025-09720-2)
- [IKNL (Netherlands Comprehensive Cancer Organisation)](https://iknl.nl/en)

### Private platforms
- [Belong.Life](https://belong.life/) and [Belong cancer FAQ](https://cancer.belong.life/frequently-asked-questions/)
- [BelongAI Dave AI mentor](https://belong.life/belong-ai-cancer-mentor-app/)
- [Outcomes4Me](https://outcomes4me.com/) and [$21M funding May 2025](https://outcomes4me.com/press-release/outcomes4me-secures-21m-in-funding-to-accelerate-ai-driven-innovation-and-drive-global-expansion-to-transform-cancer-care/)
- [Outcomes4Me + Mika acquisition 06/2025](https://outcomes4me.com/press-release/outcomes4me-acquires-germanys-mika-health-app-to-accelerate-ai-driven-patient-empowerment-globally/)
- [Elekta Kaiku Health](https://www.elekta.com/products/life-sciences/elekta-kaiku/)
- [Elekta Kaiku + H2O partnership 10/2025](https://health-outcomes-observatory.eu/2025/10/03/h2o-and-elekta-kaiku-enter-strategic-partnership-to-capture-and-standardise-real-world-outcomes-of-cancer-patients-in-the-eu/)
- [Siemens Healthineers Noona](https://cancercare.siemens-healthineers.com/products/software/patient-engagement/noona)
- [Careology Health](https://www.careology.health/)
- [Careology at Airedale NHS FT 02/2025 — Digital Health](https://www.digitalhealth.net/2025/02/airedale-nhs-ft-rolls-out-careology-app-to-support-cancer-patients/)
- [Resilience Oncology](https://www.resilience.care/us/healthcare-providers/oncology)
- [Resilience PRO France reimbursement — Simon-Kucher](https://www.simon-kucher.com/en/insights/pr-brief-evolution-digital-health-market-access-france)
- [33 centres FR+BE Resilience real-world — Lancet Regional Health Europe](https://www.thelancet.com/journals/lanepe/article/PIIS2666-7762(24)00172-8/fulltext)
- [Moovcare Poumon feasibility — Pubmed](https://pubmed.ncbi.nlm.nih.gov/40850860/)
- [Wefight Vik CES 2019](https://www.itnonline.com/content/wefight-unveils-vik-breast-chatbot-ces-2019)
- [Vik chatbot JMIR Cancer study](https://cancer.jmir.org/2019/1/e12856)
- [Jasper Health $25M Series A 2022](https://www.prnewswire.com/news-releases/jasper-health-raises-25-million-in-series-a-funding-to-increase-access-to-comprehensive-cancer-experience-and-care-navigation-platform-301471245.html)
- [Color Health AI for cancer](https://www.color.com/ai-for-cancer)
- [Color + OpenAI Cancer Copilot](https://www.fiercehealthcare.com/health-tech/color-health-openai-work-together-ai-generated-screening-plans-cancer-patients)
- [Sidekick Health €35M EIB venture debt 2025](https://www.eib.org/en/press/all/2025-196-sidekick-health-secures-eur35-million-venture-debt-from-eib-to-accelerate-rd-and-global-expansion)
- [OnkoInfo.sk](https://onkoinfo.sk/)
- [Temedica](https://temedica.com/)
- [Breast cancer German chatbot GPT-4 pilot 2025 — JMIR Cancer](https://cancer.jmir.org/2025/1/e68426)

### Open-source
- [OpenMRS Oncology Module — GitHub](https://github.com/openmrs/openmrs-module-oncology)
- [OpenMRS chemotherapy paper — PubMed](https://pubmed.ncbi.nlm.nih.gov/31438001/)
- [OpenClinica Oncology Clinical Trials](https://www.openclinica.com/oncology-clinical-trials/)
- [OpenClinica GitHub](https://github.com/OpenClinica/OpenClinica)

### AI / agent landscape
- [oncoteam — GitHub](https://github.com/peter-fusek/oncoteam)
- [oncoteam.cloud](https://oncoteam.cloud)
- [Patient Empowerment Through Software Agents — Liebert AI in Precision Oncology](https://www.liebertpub.com/doi/10.1089/aipo.2024.0027)
- [AI agents in cancer research and oncology — Nature Reviews Cancer](https://www.nature.com/articles/s41568-025-00900-0)
- [Collaborative framework on responsible AI in LLM-driven CDSS — npj Precision Oncology](https://www.nature.com/articles/s41698-025-01180-5)
- [Medical accuracy of AI chatbots in oncology — The Oncologist](https://academic.oup.com/oncolo/article/30/4/oyaf038/8120372)
