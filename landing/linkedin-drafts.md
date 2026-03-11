# LinkedIn Post Drafts — Oncoteam Launch

## Post 1: Launch Announcement (Personal Profile)

**When my wife was diagnosed with colorectal cancer, I did what any engineer would do — I built an AI system to help us fight it.**

Oncoteam is a persistent AI agent that manages cancer treatment alongside the patient and caregiver. It:

- Reads every lab result, pathology report, and imaging study
- Tracks treatment protocols with dose modification rules
- Searches PubMed and ClinicalTrials.gov for relevant research
- Checks clinical trial eligibility against the patient's molecular profile
- Prepares pre-cycle checklists and questions for the oncologist
- Runs autonomously — scanning new documents and flagging anything critical

Built on Anthropic's Model Context Protocol (MCP), it's designed to be open and interoperable — not a locked-in platform.

This isn't a theoretical project. It's been running in production for a real patient since February 2026, tracking real labs, real biomarkers, and real treatment decisions.

435 automated tests. 18 MCP tools. Bilingual dashboard. Security-audited. GDPR compliant.

If you're working in health AI, oncology informatics, or patient advocacy — I'd love to connect.

oncoteam.ai

#HealthAI #Oncology #MCP #CancerTreatment #PatientAdvocacy #AI #OpenSource

---

## Post 2: Technical Deep-Dive (Company Page — instarea)

**How we built a cancer treatment management AI on the Model Context Protocol**

When we needed an AI system to help manage real cancer treatment, we chose MCP (Model Context Protocol) as the foundation. Here's why — and what we learned.

Architecture:
- Oncofiles (data layer): MCP server bridging Google Drive patient documents to AI tools. OCR, metadata extraction, lab parsing.
- Oncoteam (intelligence layer): 18 MCP tools for clinical trial search, lab analysis, protocol tracking, eligibility checking.
- Dashboard: Nuxt.js bilingual interface with 13 pages of treatment data visualization.
- Autonomous agent: Claude API with extended thinking for document scanning and data extraction.

Key technical decisions:
1. MCP over custom APIs — interoperability with any AI assistant
2. Google Drive as source of truth — patients keep control of their data
3. FastMCP 3.1 for server framework — Python async, OpenTelemetry built-in
4. No local database — all persistence through MCP tools (data sovereignty)
5. Embedded clinical protocol — dose thresholds, toxicity grading, cycle rules in code

Security: Bearer-only auth, fail-safe startup (no auth = no start), no hardcoded production URLs, GDPR audit trail on every data access.

435 tests. Railway + Render deployment. Real patient, real data, real decisions.

The full stack is at github.com/instarea-sk.

#MCP #ModelContextProtocol #HealthTech #Claude #AI #Python #FastMCP

---

## Post 3: Patient Advocacy Angle (Personal Profile)

**Cancer doesn't wait for your next appointment.**

Between oncology visits, patients and caregivers are left alone with lab results they can't fully interpret, treatment protocols they struggle to understand, and clinical trial options they don't know exist.

The information asymmetry in cancer care is staggering. The patient has 15 minutes with their oncologist every 2-3 weeks. The rest of the time? Google, forums, and anxiety.

We built Oncoteam to close that gap.

It's not a chatbot. It's a persistent AI agent that:
- Understands your specific molecular profile (KRAS, BRAF, MSI, HER2)
- Knows which treatments are contraindicated for YOU
- Monitors clinical trials in your region matching YOUR biomarkers
- Tracks YOUR lab trends and flags deviations before your doctor sees them
- Prepares YOU for every oncologist visit with specific, data-backed questions

Every data point is traceable to its source document. Every recommendation cites PubMed or ClinicalTrials.gov. No hallucinations — just your actual medical data, analyzed continuously.

This is what AI should be doing — empowering patients and caregivers with the same information quality that institutions have.

Built for a real patient. Running in production. Open architecture.

oncoteam.ai

#PatientAdvocacy #CancerCare #Oncology #AI #Caregiver #HealthEquity
