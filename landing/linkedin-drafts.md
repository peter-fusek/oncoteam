# LinkedIn Post Drafts — Oncoteam

> DO NOT publish without explicit user approval
> Updated: 2026-04-16 (Sprint 89)

## Post 4: Sprint 87-89 Showcase (Personal Profile — when ready for an update)

**Six weeks of patient feedback, turned into product.**

When you build a tool for someone in active cancer treatment, every small friction compounds. Over the last three sprints, I focused on the parts of Oncoteam that caregivers actually touch every day.

What shipped:

→ **WhatsApp conversation history** — every message saved, searchable on the dashboard. When a sibling abroad asks "what did the doctor say last week?" the thread is right there.

→ **Hereditary DNA panel** — BRCA1/2, Lynch syndrome, ATM, PALB2 now shown directly on the patient page with plain-language context. Linked back to the source report so the oncologist sees exactly what was tested.

→ **Research hub with persistent kanban** — clinical trial funnel that remembers where you parked each trial (excluded / later line / watching / action needed). Full movement audit log in localStorage.

→ **Restructured dashboard navigation** — 5 logical sections (Overview, Clinical, Intelligence, Records, Operations) — based on where caregivers were actually losing time.

→ **Reliability** — retry budget, protocol caching, request deduplication. The boring work behind "it just works when you need it at 11pm."

→ **Modularized 5,300-line backend file into 7 focused modules.** Tests up to 744 from 688. Three patients now in active use.

None of this is glamorous. It's the kind of work that only matters if someone is using the product for real. But that's the whole point.

Free during active treatment. Open source.

→ See it: https://oncoteam.cloud
→ Try the demo: https://dashboard.oncoteam.cloud/demo

#PatientAdvocacy #CancerCare #HealthTech #AI #OpenSource

---

## Post 1: The Story (Personal Profile — publish first)

**When my wife Erika was diagnosed with metastatic colorectal cancer, I found myself drowning in lab results, genetic reports, and treatment protocols I didn't understand.**

Every oncologist visit felt too short. Every new test raised questions I didn't know how to ask. And between appointments? Just me, a stack of papers, and Google.

I'm not a doctor — I'm an entrepreneur and technology enthusiast. So I did what I could — I found a way to build something that helps.

Oncoteam is an AI tool that helps me — as a patient advocate — keep up with Erika's treatment:

→ Understand lab results in plain language, with trends over time
→ Prepare the right questions before every oncologist visit
→ Search for clinical trials across Europe and the US that match her molecular profile
→ Cross-reference treatment with medical textbooks and NCCN guidelines
→ Get alerts on my phone when something needs attention

Before Oncoteam, I'd walk into the oncologist's office with a folder of papers I barely understood. Now I walk in with specific questions, trend charts, and trial options I've already reviewed. The doctor noticed the difference by the second visit.

It's not a replacement for our oncologist. It's a way to make sure nothing gets overlooked — because even the best doctor has hundreds of patients and fifteen minutes per visit.

Built for a real patient. Open source. Running in production since February 2026. Free during active treatment.

If you're in a similar situation, or know someone who is — reach out. I've been there.

→ Try the live demo: https://oncoteam.cloud
→ Open source: https://github.com/peter-fusek/oncoteam

#PatientAdvocacy #CancerCare #Oncology #AI #Caregiver #OpenSource #HealthTech

---

## Post 2: The Problem (Personal Profile — publish 3-4 days after Post 1)

**Your oncologist is excellent. But they have hundreds of patients and fifteen minutes per visit.**

New clinical trials that could match your molecular profile open every week — not just locally, but across Europe and the US. No human can systematically search and evaluate them all, personalized to your case, on a daily basis.

Lab results pile up. Treatment evolves. Side effects shift. You need to know what to ask at the next appointment — and you need that answer now, not in three weeks.

This is the reality of modern oncology. It's not anyone's fault. It's just too much for one person to track.

That's why I built Oncoteam — an open-source AI tool for patient advocates:

→ 21 AI agents work for you around the clock
→ 500+ clinical trials monitored across US and EU registries
→ Lab trend analysis with safety checks before every cycle
→ WhatsApp chat for quick answers, dashboard for deep dives
→ Works with Claude.ai via MCP connectors
→ Slovak and English, medical ↔ plain language with one click

How it works: Upload your medical documents to Google Drive → AI processes everything automatically → Open the dashboard or chat on WhatsApp for insights, alerts, and questions for your oncologist.

Not a replacement for your doctor. A tool to make sure you walk in prepared and nothing gets missed.

Free during active treatment. No credit card. No catches.

→ See it in action: https://oncoteam.cloud
→ Dashboard demo: https://dashboard.oncoteam.cloud/demo

#CancerTreatment #PatientAdvocacy #HealthTech #AI #Oncology #OpenSource

---

## Post 3: The Architecture (Company Page — instarea, publish 3-4 days after Post 2)

**How we built an AI patient advocacy tool for cancer treatment — and made it open source.**

When my wife was diagnosed with cancer, I needed a tool to help me keep up with her treatment. Here's what we built and the technical decisions behind it.

**Two-layer architecture:**
- **Oncofiles** (oncofiles.com) — data layer. Organizes medical documents from Google Drive: lab results, pathology reports, CT scans, genetic tests. OCR, structured extraction, metadata linking.
- **Oncoteam** (oncoteam.cloud) — intelligence layer. 21 autonomous AI agents analyze everything Oncofiles organizes. Searches PubMed and ClinicalTrials.gov. Cross-references with NCCN guidelines. Tracks trends. Prepares questions.

**By the numbers:**
- 21 autonomous AI agents per patient
- 744 automated tests passing
- 500+ clinical trials monitored across US and EU registries
- 3 patients in active use (oncology + general health)
- Multi-patient architecture with per-patient data isolation

**Key technical decisions:**
1. Built on the Model Context Protocol (MCP) — works with Claude.ai, extensible to any MCP-compatible assistant
2. Google Drive as source of truth — the patient keeps full control of their data
3. No local database — all persistence through MCP (data sovereignty by design)
4. WhatsApp integration — treatment questions don't wait for a browser
5. Bilingual (Slovak/English) with medical ↔ plain language switching
6. Nuxt 4 dashboard with SSR, deployed on Railway with zero-downtime deploys

**Access channels:** Dashboard for deep dives and trends, WhatsApp for quick lab checks and alerts, Claude.ai MCP connectors for ad-hoc analysis.

Running in production for real patients since February 2026. GDPR compliant. Free during active treatment.

An Instarea project.

→ Landing: https://oncoteam.cloud
→ Dashboard demo: https://dashboard.oncoteam.cloud/demo
→ GitHub: https://github.com/peter-fusek/oncoteam

#MCP #ModelContextProtocol #HealthTech #AI #Python #NuxtJS #OpenSource #Oncology

---

## LinkedIn Company Page Description — Suggested Addition

> Add to instarea's Overview section (append after existing text, or add as a "Featured product" section):

**Latest project: Oncoteam** — AI-powered patient advocacy tool for cancer treatment management. Built on the Model Context Protocol (MCP), Oncoteam helps patients and their families understand lab results, find clinical trials, and prepare for oncologist visits. Open source, GDPR compliant, running in production since February 2026. → oncoteam.cloud

---

## OG Images — Status

LinkedIn auto-pulls OG images from shared links. oncoteam.cloud already has:
- `og-image.png` (1200x630) — used for all social sharing
- Twitter card: `summary_large_image`
- All required OG meta tags present

No separate images needed per post — the link preview will show the OG image automatically.

---

## Community Cross-Post Targets

> Research these communities. Approach authentically — share the personal story, not a product pitch. Peter should post from his personal account.

### Reddit
- **r/cancer** — 130k+ members. Personal stories welcome. Share Post 1 style (the story, not the tech).
- **r/colorectalcancer** — smaller, more specific. Very relevant.
- **r/caregiversupport** — for caregivers/advocates. Erika's story fits perfectly.
- **r/HealthIT** — for the technical architecture post.
- **r/machinelearning** — monthly "What are you working on?" thread. Post 3 style.

### Facebook Groups
- Cancer patient/caregiver groups (search: "colorectal cancer support", "cancer caregiver")
- Slovak cancer patient groups (search: "rakovina podpora", "onkologia")

### Health-Tech / AI Communities
- **Hacker News** (Show HN) — "Show HN: Open-source AI tool for cancer patient advocacy" — technical + personal angle
- **Product Hunt** — launch when ready for broader audience
- **MCP Community** (Discord/GitHub) — Oncoteam is a real-world MCP use case
- **Claude.ai community** — share as MCP connector example

### Professional / Medical
- **cancer.net forums** — patient education community
- **LinkedIn health-tech groups** — share Post 2 or 3
- **ESMO (European Society for Medical Oncology)** patient advocacy programs

### Strategy
1. **Week 1**: Post 1 on Peter's LinkedIn (personal story)
2. **Week 1**: Share on r/cancer, r/colorectalcancer (personal angle)
3. **Week 2**: Post 2 on Peter's LinkedIn (the problem)
4. **Week 2**: Post 3 on instarea company page (architecture)
5. **Week 2**: Show HN submission
6. **Week 3**: Cross-post to Facebook groups, MCP community
7. **Ongoing**: Engage with comments, answer questions
