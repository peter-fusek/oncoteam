# Oncoteam

**Your AI Ally in Cancer Treatment**

> When someone you love has cancer, you become their advocate. Oncoteam helps you understand the treatment, ask the right questions, find clinical trials, and make sure nothing gets overlooked — all from your phone.

[![Tests](https://img.shields.io/badge/tests-620%20passing-brightgreen)](https://github.com/peter-fusek/oncoteam)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Open Source](https://img.shields.io/badge/open%20source-used%20in%20active%20treatment-orange)](https://oncoteam.cloud)

---

## The Reality You're Facing

None of this is anyone's fault. It's just the reality of modern oncology:

- **Hundreds of patients, one doctor** — your oncologist is excellent, but they care for hundreds of patients. Fifteen minutes per appointment isn't enough to cover everything.
- **New trials published every day** — clinical trials matching your molecular profile open every week across Europe and the US. No human can systematically search them all.
- **An avalanche of medical data** — lab results, CT scans, pathology reports, genetic tests, treatment protocols. Understanding what it all means is a full-time job.
- **Treatment evolves, questions multiply** — new side effects, dose adjustments, shifting biomarkers. You need answers now, not in three weeks.

## What Oncoteam Does

| Feature | Description |
|---------|-------------|
| **Lab Analysis** | Understand every number — trends, safety thresholds, inflammation indices, cycle-over-cycle comparisons. Plain language or medical terminology, one click apart. |
| **Appointment Prep** | Personalized questions before every oncologist visit based on latest labs, treatment stage, and changes since last appointment. |
| **Clinical Trial Search** | Searches ClinicalTrials.gov and EU registries across 14 European countries. AI classifies each trial into a funnel — from excluded to action needed. |
| **Treatment Trends** | Visual trends of tumor markers, blood counts, and inflammation indices across every cycle. See the trajectory — is treatment working? |
| **Second Opinion** | Cross-references treatment with medical textbooks (DeVita), NCCN protocols, and latest PubMed research. Not to question your doctor — to make sure no option is missed. |
| **WhatsApp Access** | Chat anytime — ask about a lab value, check the next cycle date, or get a quick summary. Available wherever you are. |
| **Medical Dictionary** | Every medical term, abbreviation, and lab value explained. Switch between plain language and clinical terminology with one click. |
| **Family Updates** | Clear, compassionate treatment summaries for family members. Share via WhatsApp or print — no medical degree required. |

## Who It's For

- **Cancer patients** who want to understand and track their own treatment
- **Family advocates** — spouses, children, siblings coordinating care
- **Care providers** bridging between doctors, family, and the patient
- Anyone who needs a second opinion backed by medical literature — not to replace the doctor, but because even the best oncologist has hundreds of patients and fifteen minutes per visit

## Access

| Channel | URL | Description |
|---------|-----|-------------|
| **Website** | [oncoteam.cloud](https://oncoteam.cloud) | Landing page with features, story, and get-started guide |
| **Dashboard** | [dashboard.oncoteam.cloud](https://dashboard.oncoteam.cloud) | Treatment overview, lab trends, timelines, trial funnel |
| **WhatsApp** | Chat anytime | Quick answers, summaries, alerts, and onboarding |
| **Claude.ai** | MCP connector | Deep analysis and Q&A via Model Context Protocol |

## Get Started in 5 Steps

1. **Create your account** at [oncofiles.com](https://oncofiles.com) — your data foundation
2. **Connect Google Drive** — Oncofiles reads and organizes your medical documents automatically
3. **Upload documents** — lab results, pathology reports, CT scans, genetic tests
4. **Connect AI connectors** — add Oncoteam + Oncofiles in [Claude.ai Settings > Connectors](https://claude.ai/settings/connectors)
5. **Start using** — open the dashboard or message on WhatsApp

> **Free. Period.** 200 medical documents, 500 AI queries/month, 100 autonomous agent runs/month. No credit card required. These limits are yours and we won't reduce them.

## Architecture

```
+------------------+     +------------------+     +------------------+
|                  |     |                  |     |                  |
|   Google Drive   |---->|   Oncofiles      |---->|   Oncoteam       |
|   (your data)    |     |   (data layer)   |     |   (intelligence) |
|                  |     |                  |     |                  |
+------------------+     +------------------+     +------------------+
                                                         |
                                              +----------+----------+
                                              |          |          |
                                           Dashboard  WhatsApp  Claude.ai
```

**Two products, one mission:**

- **[Oncofiles](https://github.com/peter-fusek/oncofiles)** — the data layer. Organizes medical documents from Google Drive: lab results, pathology, CT scans, genetic tests. Structured, connected, searchable.
- **Oncoteam** — the intelligence layer. Turns organized data into understanding. Lab trends, trial matching, appointment prep, family updates — powered by AI, controlled by you.

### Tech Stack

- **Backend**: Python 3.12+, FastMCP 3.0+, Pydantic, httpx
- **Dashboard**: Nuxt 4 (SSR), TypeScript
- **Landing**: Static HTML/CSS, bilingual (EN/SK)
- **Protocol**: Model Context Protocol (MCP) — open standard for AI tool integration
- **Data**: Patient-owned Google Drive (no local database) — GDPR compliant
- **Deployment**: Railway (zero-downtime deploys)

### Integrations

| Service | Purpose |
|---------|---------|
| Claude AI | Autonomous agent loop, deep analysis |
| PubMed | Medical research search (NCBI E-utilities) |
| ClinicalTrials.gov | US clinical trial registry (API v2) |
| EU Clinical Trials | European trial registries |
| WhatsApp (Twilio) | Patient communication, onboarding, alerts |
| Google Drive | Patient document storage (via Oncofiles) |
| MCP Protocol | AI tool integration standard |

## Development

```bash
# Setup
uv sync --extra dev

# Run tests
uv run pytest              # 620 tests, ~2.3s

# Lint
uv run ruff check --fix

# Run MCP server (stdio)
uv run oncoteam-mcp

# Run MCP server (HTTP)
MCP_TRANSPORT=streamable-http uv run oncoteam-mcp

# Dashboard dev
cd dashboard && pnpm dev
```

### Stats

| Metric | Value |
|--------|-------|
| MCP Tools | 24 |
| Dashboard API routes | 21 |
| Autonomous agents | 18 |
| Tests | 630 passing |
| Python LOC | ~10,700 |

## Privacy & Security

- **GDPR compliant** — all patient data processed per EU regulations, encrypted at rest and in transit
- **Your Google Drive** — medical documents stay in your own storage. Oncoteam reads but never stores originals outside your control. Revoke access anytime.
- **Multi-layer security** — Google OAuth, API authentication, bearer tokens, encrypted connections
- **Full transparency** — every data access and AI decision is logged. See exactly what was read, analyzed, and recommended.
- **Open source** — inspect every line of code that touches your data

## The Story

Oncoteam was built by **Peter Fusek** — an entrepreneur and technology enthusiast, not a doctor — when his wife Erika was diagnosed with metastatic colorectal cancer. Buried in lab results, genetic reports, and treatment protocols he didn't understand, he built what he needed: a tool to keep up with a situation that moves faster than any one person can track.

Not as a replacement for their oncologist, but as a tool to help him understand the numbers, prepare the right questions, track what's changing, and search for clinical trials that no single doctor has time to systematically monitor.

> *This is not a replacement for your oncologist. It's a tool that helps you — the patient, the spouse, the son, the daughter — keep up with a situation that moves faster than any one person can track.*

## Links

- **Website**: [oncoteam.cloud](https://oncoteam.cloud)
- **Dashboard**: [dashboard.oncoteam.cloud](https://dashboard.oncoteam.cloud)
- **Oncofiles**: [github.com/peter-fusek/oncofiles](https://github.com/peter-fusek/oncofiles)
- **Author**: [Peter Fusek](https://www.linkedin.com/in/peterfusek/) — Entrepreneur & Founder
- **Company**: [Instarea](https://www.instarea.com)

---

## Who's Behind This

### The People

<table>
<tr>
<td width="50%">

**Peter Fusek** — CEO & Founder

Serial entrepreneur and AI strategist. 4 years at Tatra banka. Co-founded marketlocator (exit to Deutsche Telekom). Advisor to VÚB Bank CEO. 18+ years building technology products.

Built Oncoteam from personal need — when his wife was diagnosed with metastatic colorectal cancer, he needed a tool to keep up with a situation that moves faster than any one person can track.

[LinkedIn](https://www.linkedin.com/in/peterfusek/) · peter.fusek@instarea.com

</td>
<td width="50%">

**Peter Čapkovič** — CTO & Co-founder

Senior IT architect with 20+ years in enterprise banking (VÚB). Expert in .NET, Python, SQL, and systems architecture. Led architecture across all Instarea products.

Architecture, development, operations — everything under one roof.

[LinkedIn](https://www.linkedin.com/in/peter-capkovic/)

</td>
</tr>
</table>

### The Company

**[Instarea](https://www.instarea.com)** — 18 years, 23 products shipped. From telecom analytics and enterprise clients (Callinspector) to mobile-first fintech (InventButton), big data exits (marketlocator → Deutsche Telekom), IoT platforms, and AI-first products (PulseShape, ReplicaCity, HomeGrif).

Oncoteam and [Oncofiles](https://github.com/peter-fusek/oncofiles) are Instarea's latest — built with the same engineering discipline that delivered enterprise-grade products for banking, telecom, and data industries.

10+ verified, synchronized team members available across front-end, back-end, integration, data science, UX/UI, marketing, and cloud ops.

> *"We take it personally, with our own faces, like family and at work."*

---

*Oncoteam is an AI-powered decision support tool. It does not replace professional medical advice. Always consult your oncologist for treatment decisions.*

*Built by a patient advocate, for patient advocates.*
