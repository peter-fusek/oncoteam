# LinkedIn Post Drafts — Oncoteam

> DO NOT publish without explicit user approval

## Post 1: The Story (Personal Profile — publish first)

**When my wife Erika was diagnosed with metastatic colorectal cancer, I found myself drowning in lab results, genetic reports, and treatment protocols I didn't understand.**

Every oncologist visit felt too short. Every new test raised questions I didn't know how to ask. And between appointments? Just me, a stack of papers, and Google.

I'm not a doctor or a software engineer — I'm an entrepreneur and a technology enthusiast. So I did what I could — I found a way to build something that helps.

Oncoteam is an AI tool that helps me — as a patient advocate — keep up with Erika's treatment:

→ Understand lab results in plain language, with trends over time
→ Prepare the right questions before every oncologist visit
→ Search for clinical trials across Europe and the US that match her molecular profile
→ Cross-reference treatment with medical textbooks as a second opinion
→ Get alerts on my phone when something needs attention

It's not a replacement for our oncologist. It's a way to make sure nothing gets overlooked — because even the best doctor has hundreds of patients and fifteen minutes per visit.

Built for a real patient. Open source. Running in production since February 2026. Free.

If you're in a similar situation, or know someone who is — I'd love to hear from you.

https://oncoteam.cloud

#PatientAdvocacy #CancerCare #Oncology #AI #Caregiver #OpenSource

---

## Post 2: The Problem (Personal Profile — publish 2-3 days after Post 1)

**Your oncologist is excellent. But they have hundreds of patients and fifteen minutes per visit.**

New clinical trials that could match your molecular profile open every week — not just locally, but across Europe and the US. No human can systematically search and evaluate them all, personalized to your case, on a daily basis.

Lab results pile up. Treatment evolves. Side effects shift. You need to know what to ask at the next appointment — and you need that answer now, not in three weeks.

This is the reality of modern oncology. It's not anyone's fault. It's just too much for one person to track.

That's why I built Oncoteam — an open-source AI tool for patient advocates. 18 AI agents work for you around the clock: monitoring 500+ clinical trials, analyzing lab trends, preparing questions for your next visit.

Chat on WhatsApp, open the dashboard, or connect via Claude.ai. Switch between plain language and medical terminology with one click. Slovak and English.

Not a replacement for your doctor. A way to make sure you walk in prepared and nothing gets missed.

Free during active treatment. No credit card. No catches.

https://oncoteam.cloud

#CancerTreatment #PatientAdvocacy #HealthTech #AI #Oncology #OpenSource

---

## Post 3: The Architecture (Company Page — instarea, publish 2-3 days after Post 2)

**How we built an AI patient advocacy tool for cancer treatment — and made it open source**

When my wife was diagnosed with cancer, I needed a tool to help me keep up with her treatment. Here's what we built and the technical decisions behind it.

**Two-layer architecture:**
- **Oncofiles** — data layer. Organizes medical documents from Google Drive: lab results, pathology reports, CT scans, genetic tests. OCR, structured extraction, metadata.
- **Oncoteam** — intelligence layer. Reads everything Oncofiles organizes. Searches PubMed and ClinicalTrials.gov. Cross-references with medical textbooks. Tracks trends. Prepares questions.

**In numbers:**
- 18 autonomous AI agents per patient
- 50+ tasks per patient per week
- 500+ clinical trials monitored across US and EU registries
- 6 specialist roles (lab analyst, trial researcher, protocol checker, briefing writer, family communicator, appointment prep)
- 620 tests, open source on GitHub

**Key decisions:**
1. Built on the Model Context Protocol (MCP) — works with Claude, ChatGPT, any compatible assistant
2. Google Drive as source of truth — the patient keeps control of their data
3. No local database — all persistence through MCP (data sovereignty by design)
4. WhatsApp integration — because treatment questions don't wait for a browser
5. Bilingual (Slovak/English) with medical ↔ plain language switching

**Access channels:** Dashboard for deep dives, WhatsApp for quick answers, Claude.ai for analysis.

Running in production for a real patient since February 2026. GDPR compliant. Free during active treatment.

An Instarea project.

https://oncoteam.cloud
GitHub: https://github.com/peter-fusek/oncoteam

#MCP #ModelContextProtocol #HealthTech #AI #Python #OpenSource #Oncology
