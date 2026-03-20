# LinkedIn Post Drafts — Oncoteam

> DO NOT publish without explicit user approval

## Post 1: Launch Announcement (Personal Profile)

**When my wife was diagnosed with colorectal cancer, I did what any engineer would do — I built an AI team to help us fight it.**

Oncoteam is your always-ready crew of 18 AI agents that work alongside you to manage cancer treatment. They:

- Read every lab result, pathology report, and imaging study
- Search PubMed and ClinicalTrials.gov for compatible treatments
- Check trial eligibility against YOUR molecular profile
- Track protocols with dose modification rules and toxicity grading
- Prepare you for every oncologist appointment with the right questions
- Apply DeVita textbook and NCCN protocols as a second opinion
- Inform your family with plain-language updates via WhatsApp

Chat with your crew via Claude.ai, ChatGPT (thanks to MCP), or WhatsApp. View everything in a full dashboard. No medical degree required.

Built on the Model Context Protocol — open, interoperable, designed to work with any AI assistant. Your data stays in your Google Drive.

This isn't a theoretical project. Running in production for a real patient since February 2026, tracking real labs, real biomarkers, real treatment decisions.

592 automated tests. 18 agents. 24 tools. GDPR compliant.

Upgrade yourself with an always-ready team to stay in control — even if you're a medicine amateur.

https://oncoteam.cloud

#HealthAI #Oncology #MCP #CancerTreatment #PatientAdvocacy #AI #Claude

---

## Post 2: Technical Deep-Dive (Company Page — instarea)

**How we built a cancer treatment AI with 18 autonomous agents on the Model Context Protocol**

When we needed an AI system to manage real cancer treatment, we chose MCP as the foundation. Here's why — and what we learned.

Two-layer architecture:
- **Oncofiles** (data layer): MCP server bridging Google Drive, Gmail, and Calendar to AI. OCR, metadata, lab parsing. GDrive = single source of truth.
- **Oncoteam** (intelligence layer): 18 autonomous agents + 24 MCP tools. Clinical trial search, lab analysis, protocol tracking, eligibility checking, document processing.

Multi-channel access:
- **Dashboard**: Nuxt 4 bilingual interface — labs, timeline, medications, dictionary, dose tracking, agent observatory
- **Claude.ai / ChatGPT**: Deep analysis and Q&A via MCP protocol
- **WhatsApp**: Proactive safety alerts and family updates
- **Autonomous agents**: 18 scheduled tasks running 24/7

Key technical decisions:
1. MCP over custom APIs — works with Claude, ChatGPT, any MCP-compatible assistant
2. Google Drive as source of truth — patients keep control of their data
3. FastMCP 3.1 server framework — Python async, OpenTelemetry built-in
4. No local database — all persistence through MCP (data sovereignty)
5. Embedded clinical protocol — dose thresholds, toxicity grading, cycle rules in code
6. Full prompt transparency — see every AI decision, prompt, tool call

592 tests. Railway deployment. Real patient, real data, real decisions.

https://oncoteam.cloud

#MCP #ModelContextProtocol #HealthTech #Claude #AI #Python #FastMCP

---

## Post 3: Patient Advocacy Angle (Personal Profile)

**Cancer doesn't wait for your next appointment.**

Between oncology visits, patients and caregivers are left alone with lab results they can't interpret, protocols they struggle to understand, and clinical trials they don't know exist.

The information asymmetry in cancer care is staggering. You get 15 minutes with your oncologist every 2-3 weeks. The rest? Google, forums, and anxiety.

We built Oncoteam to close that gap. It's not a chatbot — it's your always-ready AI team:

- Knows your molecular profile (KRAS, BRAF, MSI, HER2) and which treatments are compatible
- Monitors clinical trials across 14 EU countries matching YOUR biomarkers
- Tracks YOUR lab trends and flags deviations before your doctor sees them
- Applies DeVita textbook standards as a second opinion on YOUR case
- Prepares YOU for every visit with specific, data-backed questions
- Keeps your family informed with plain-language WhatsApp updates

Chat via Claude.ai or ChatGPT. Get alerts on WhatsApp. See everything in a dashboard. Even top-notch medical standards are automatically applied — so you walk in prepared, not overwhelmed.

Every data point traceable. Every recommendation cited. No hallucinations — just your actual medical data, analyzed by 18 AI agents continuously.

Stay in control, even if you're a medicine amateur.

https://oncoteam.cloud

#PatientAdvocacy #CancerCare #Oncology #AI #Caregiver #HealthEquity
