// Hero typewriter state (must be before setLanguage which calls startHeroTypewriter)
var heroTimers = [];
var heroConversations = {
  en: [
    { type: "user", text: "labky" },
    { type: "bot", text: "\ud83d\udcca Labs (Mar 19):\nANC 2,100 \u2705 PLT 269k HGB 112\nCEA 8.1 \u2193 35% CA19-9 4,820 \u2193 68%\n\n\u2705 Safe for next cycle" },
    { type: "user", text: "family update" },
    { type: "bot", text: "\ud83d\udc68\u200d\ud83d\udc69\u200d\ud83d\udc67 Treatment going well.\nMain tumor marker dropped 35% \u2014 very positive sign.\nNext appointment: Mar 28." },
  ],
  sk: [
    { type: "user", text: "labky" },
    { type: "bot", text: "\ud83d\udcca V\u00fdsledky (19. 3.):\nANC 2 100 \u2705 PLT 269k HGB 112\nCEA 8,1 \u2193 35% CA19-9 4 820 \u2193 68%\n\n\u2705 Bezpe\u010dn\u00e9 pre \u010fal\u0161\u00ed cyklus" },
    { type: "user", text: "s\u00fahrn pre rodinu" },
    { type: "bot", text: "\ud83d\udc68\u200d\ud83d\udc69\u200d\ud83d\udc67 Lie\u010dba prebieha dobre.\nHlavn\u00fd marker klesol o 35% \u2014 ve\u013emi pozit\u00edvny sign\u00e1l.\n\u010eal\u0161ia n\u00e1v\u0161teva: 28. 3." },
  ],
};

const translations = {
  en: {
    "nav.dashboard": "Dashboard",
    "nav.demo": "Try Demo",
    "nav.how": "How it works",
    "nav.features": "Features",
    "nav.getstarted": "Get Started",
    "nav.about": "About",
    "nav.faq": "FAQ",
    "hero.title": "When someone you love has cancer, you become their advocate.",
    "hero.subtitle": "Oncoteam helps you understand the treatment, ask the right questions, find clinical trials, and make sure nothing gets overlooked \u2014 all from your phone.",
    "hero.badge": "Open Source \u00b7 Used in Active Treatment",
    "hero.demo": "Try Live Demo",
    "hero.how": "See How It Works",
    "hero.github": "View on GitHub",
    "hero.whatsapp": "Try on WhatsApp",
    "hero.micro": "Free during active treatment. No credit card needed.",
    "hero.phone.status": "online",
    "demo.title": "See It in Action",
    "demo.subtitle": "Real dashboard, real data, real treatment.",
    "demo.tab.dashboard": "Dashboard",
    "demo.tab.labs": "Lab Trends",
    "demo.tab.funnel": "Trial Funnel",
    "demo.tab.protocol": "Protocol",
    "story.title": "Born from Real Life",
    "story.p1": "When Erika was diagnosed with metastatic colorectal cancer, her husband Peter \u2014 an entrepreneur and technology enthusiast, not a doctor \u2014 found himself buried in lab results, genetic reports, and treatment protocols he didn\u2019t understand. Every oncologist visit felt too short. Every new test raised questions he didn\u2019t know how to ask.",
    "story.p2": "So he built Oncoteam. Not as a replacement for their oncologist, but as a tool to help him keep up \u2014 to understand the numbers, prepare the right questions, track what\u2019s changing, and search for clinical trials that no single doctor has time to systematically monitor across Europe and the US.",
    "story.p3": "Alongside Oncoteam, he built Oncofiles \u2014 the data layer that organizes all medical documents from Google Drive: lab results, pathology reports, CT scans, genetic tests. Oncofiles structures and connects them. Oncoteam makes them useful \u2014 it\u2019s the intelligence layer that turns raw medical data into understanding, questions, and action.",
    "manifesto.text": "This is not a replacement for your oncologist. It\u2019s a tool that helps you \u2014 the patient, the spouse, the son, the daughter \u2014 keep up with a situation that moves faster than any one person can track. Not because you don\u2019t trust your doctor, but because even the best doctor has hundreds of patients and fifteen minutes per visit.",
    "reality.title": "The Reality You\u2019re Facing",
    "reality.subtitle": "None of this is anyone\u2019s fault. It\u2019s just the reality of modern oncology.",
    "reality.hundreds.title": "Hundreds of patients, one doctor",
    "reality.hundreds.text": "Your oncologist is excellent \u2014 but they care for hundreds of patients. It\u2019s humanly impossible to keep every detail of every case in their head during a fifteen-minute appointment.",
    "reality.trials.title": "New trials published every day",
    "reality.trials.text": "Clinical trials that could match your molecular profile open every week \u2014 not just locally, but across Europe and the US. No human can systematically search and evaluate them all, personalized to your case, on a daily basis.",
    "reality.data.title": "An avalanche of medical data",
    "reality.data.text": "Lab results, CT scans, pathology reports, genetic tests, treatment protocols \u2014 the paperwork piles up fast. Understanding what it means, how it connects, and what\u2019s changing over time is a full-time job.",
    "reality.time.title": "Treatment evolves, questions multiply",
    "reality.time.text": "As treatment progresses, the situation changes cycle by cycle. New side effects, dose adjustments, shifting biomarkers. You need to know what to ask at the next appointment \u2014 and you need that answer now, not in three weeks.",
    "hiw.title": "How It Works",
    "hiw.subtitle": "From a pile of medical paperwork to a clear picture \u2014 in three steps.",
    "hiw.step1.title": "Upload Documents",
    "hiw.step1.text": "Scan or photograph your lab results, CT scans, pathology reports \u2014 drop them into a Google Drive folder. That\u2019s it.",
    "hiw.step2.title": "AI Processes Everything",
    "hiw.step2.text": "Oncofiles structures the documents automatically. Oncoteam\u2019s 21 AI agents analyze them \u2014 tracking trends, checking safety, searching for trials.",
    "hiw.step3.title": "Understand & Act",
    "hiw.step3.text": "Open the dashboard or chat on WhatsApp \u2014 get lab interpretations, safety alerts, trial matches, and questions to ask your oncologist.",
    "stats.agents": "AI Agents Working 24/7",
    "stats.tests": "Automated Tests Passing",
    "stats.trials": "Clinical Trials Monitored",
    "stats.patients": "Patients in Active Use",
    "testimonial.quote": "Before Oncoteam, I\u2019d walk into the oncologist\u2019s office with a folder of papers I barely understood. Now I walk in with specific questions, trend charts, and trial options I\u2019ve already reviewed. The doctor noticed the difference by the second visit.",
    "testimonial.role": "Patient advocate & founder",
    "features.title": "What You Get",
    "features.subtitle": "Everything a patient advocate needs, explained in language you choose.",
    "features.labs.title": "Understand Your Lab Results",
    "features.labs.text": "See what every number means, whether it\u2019s improving or worsening, and how it compares to previous cycles. Inflammation indices, safety thresholds, and trend charts \u2014 in plain language or medical terminology, one click apart.",
    "features.questions.title": "Ask the Right Questions",
    "features.questions.text": "Before every oncologist visit, get a personalized list of questions based on the latest lab results, treatment stage, and any changes since the last appointment. Walk in prepared, not overwhelmed.",
    "features.trials.title": "Find Clinical Trials You Qualify For",
    "features.trials.text": "Automatically searches ClinicalTrials.gov and EU registries for trials matching your molecular profile, location, and treatment history. AI classifies each trial into a funnel \u2014 from excluded to action needed.",
    "features.opinion.title": "A Second Opinion, Always Available",
    "features.opinion.text": "Cross-references your treatment with medical textbooks (DeVita), NCCN protocols, and latest research. Not to question your doctor \u2014 but to make sure the standard of care is being met and no option is missed.",
    "features.mobile.title": "Everything in Your Pocket",
    "features.mobile.text": "Chat via WhatsApp anytime \u2014 ask about a lab value, check when the next cycle is, or get a quick summary. Open the dashboard for trends, timelines, and deep dives. It\u2019s there when you need it, wherever you are.",
    "features.language.title": "Medical \u2194 Plain Language",
    "features.language.text": "Every medical term, abbreviation, and lab value explained in words you understand. Switch between plain language and clinical terminology with one click. Learn at your own pace \u2014 or just get the answer fast.",
    "features.trends.title": "See How Treatment Is Working",
    "features.trends.text": "Visual trends of tumor markers, blood counts, and inflammation indices across every cycle. See the trajectory \u2014 is the treatment working? Are the numbers heading the right direction? No guessing.",
    "features.family.title": "Keep Your Family Informed",
    "features.family.text": "Generate clear, compassionate treatment summaries for family members who want to help but don\u2019t know how to ask. Share via WhatsApp or print \u2014 no medical degree required to understand.",
    "features.genetics.title": "Hereditary DNA Insights",
    "features.genetics.text": "Automatically surfaces hereditary cancer panel results \u2014 BRCA1/2, Lynch syndrome, ATM, PALB2 and more \u2014 with plain-language context. Every finding links back to the source report, so your oncologist (and your family) see exactly what was tested and why it matters.",
    "features.waudit.title": "WhatsApp Conversation History",
    "features.waudit.text": "Every WhatsApp message \u2014 questions, alerts, family updates \u2014 is saved and viewable on the dashboard. Nothing gets lost in scrollback. Ideal when the patient is in active treatment and caregivers are coordinating across time zones.",
    "gs.title": "Get Started in 5 Steps",
    "gs.subtitle": "From zero to a fully operational AI patient advocate \u2014 takes about 30 minutes.",
    "gs.shortcut.prefix": "Already have Oncofiles?",
    "gs.shortcut.link": "Skip to Step 4 \u2192",
    "gs.step1.title": "Create Your Account",
    "gs.step1.text": "Go to oncofiles.com, create a patient profile, and get your data organized in one place. This is the foundation everything else builds on.",
    "gs.step1.cta": "Go to Oncofiles.com",
    "gs.step2.title": "Connect Google Drive",
    "gs.step2.text": "Link your Google Drive to Oncofiles. It reads your medical documents, organizes them automatically, and applies OCR and AI structuring \u2014 no manual tagging needed.",
    "gs.step3.title": "Upload Your Documents",
    "gs.step3.text": "Drop lab results, pathology reports, CT scans, and genetic tests into the connected Google Drive folder. Oncofiles processes each file \u2014 OCR, classification, extraction \u2014 automatically.",
    "gs.step4.badge": "\u2190 Already have Oncofiles? Start here",
    "gs.step4.title": "Connect AI Connectors",
    "gs.step4.text": "In Claude.ai, go to Settings \u2192 Connectors and add both \"Oncoteam\" and \"Oncofiles\" as custom connectors. This gives the AI direct access to your treatment data.",
    "gs.step4.cta": "Open Claude.ai Connectors",
    "gs.step5.title": "Start Using",
    "gs.step5.text": "Send a message on WhatsApp or open the dashboard \u2014 your AI patient advocate is ready. Ask about labs, request a trial search, or get a briefing before the next oncologist visit.",
    "gs.step5.cta": "Open Dashboard",
    "gs.whatsapp.label": "Fastest way to start:",
    "gs.whatsapp.text": " Just message us on WhatsApp \u2014 we\u2019ll guide you through the rest.",
    "gs.whatsapp.btn": "WhatsApp",
    "gs.free.badge": "Free during active treatment",
    "gs.free.docs": "medical documents",
    "gs.free.queries": "AI queries / month",
    "gs.free.agents": "autonomous agent runs / month",
    "gs.free.note": "These limits are yours and we won\u2019t reduce them. We don\u2019t have a commercial model yet \u2014 our priority is the patient and getting the product right, not monetization. If that ever changes, you\u2019ll be the first to know.",
    "uc.title": "What Patients Actually Ask",
    "uc.subtitle": "Real scenarios from real caregivers. One WhatsApp message away.",
    "uc.1.title": "What did the last labs say?",
    "uc.1.story": "Mom used to bring a folder of papers to the doctor without understanding them. Now she types one word and gets a clear summary with trends.",
    "uc.2.title": "I don\u2019t know what to ask at the appointment",
    "uc.2.story": "Fifteen minutes with the oncologist. A list of questions from the latest results and changes since the last visit \u2014 ready in seconds.",
    "uc.2.cmd": "questions for doctor",
    "uc.3.title": "When is the next check-up?",
    "uc.3.story": "After treatment ends, surveillance doesn\u2019t stop. Appointments, biomarkers, next steps \u2014 all in one place.",
    "uc.4.title": "The family keeps asking how it\u2019s going",
    "uc.4.story": "A sibling abroad, grandparents at home. A clear treatment summary without medical jargon \u2014 in one message.",
    "uc.4.cmd": "update for family",
    "wa.title": "Your AI Ally on WhatsApp",
    "wa.subtitle": "Ask anything, anytime. Get informed answers with sources from your own medical records.",
    "wa.status": "online",
    "wa.conv1.q": "labs",
    "wa.conv1.a1": "&#x1F4CA; <strong>Labs (Mar 19):</strong><br>WBC 3.8, ANC 2,100, HGB 112<br>CEA 8.1 &#x2193;35%, CA19-9 4,820 &#x2193;68%<br><br>&#x2705; Safe for next cycle<br>&#x26A0;&#xFE0F; HGB slightly low \u2014 ask about iron",
    "wa.conv1.q2": "questions for doctor?",
    "wa.conv1.a2": "&#x1F4DD; <strong>For your oncologist:</strong><br>1. HGB trending down \u2014 iron supplementation?<br>2. Neuropathy grade after 3 cycles?<br>3. CEA response excellent \u2014 imaging timeline?",
    "wa.conv2.a1": "&#x1F50D; <strong>New trial match:</strong><br>NCT07284849 \u2014 FOLFOX + novel agent<br>Phase III, enrolling in Vienna (AT)<br><br>Compatible with your molecular profile.<br>Biomarker: KRAS mutant eligible &#x2705;",
    "wa.conv2.q": "more details?",
    "wa.conv2.a2": "&#x1F3E5; <strong>AKH Vienna</strong>, 90 min from Bratislava<br>Enrollment open until Aug 2026<br>Requires: &#x2265;2 prior lines, ECOG 0-1<br><br><em>I can prepare a summary for your oncologist.</em>",
    "wa.conv3.q": "update for family",
    "wa.conv3.a1": "&#x1F46A; <strong>Family update (Mar 20):</strong><br><br>Treatment is going well. Blood work looks good \u2014 safe to continue with the next cycle. The main tumor marker (CEA) dropped by 35% since last time, which is a very positive sign.<br><br>She may feel more tired than usual (hemoglobin is a little low). The doctor may suggest iron supplements.<br><br>Next appointment: March 28.",
    "wa.label1": "Before the appointment",
    "wa.label2": "AI finds trials for you",
    "wa.label3": "Family understands too",
    "tech.title": "Integrates With",
    "ecosystem.title": "Two Products, One Mission",
    "ecosystem.subtitle": "Your medical data, organized and understood.",
    "ecosystem.files.role": "Data Layer",
    "ecosystem.files.text": "Organizes medical documents from Google Drive. Lab results, pathology, CT scans, genetic tests \u2014 structured, connected, and searchable.",
    "ecosystem.team.role": "Intelligence Layer",
    "ecosystem.team.text": "Turns organized data into understanding. Lab trends, trial matching, appointment prep, family updates \u2014 powered by AI, controlled by you.",
    "contact.title": "Get in Touch",
    "contact.bug": "Report a Bug",
    "contact.role": " \u2014 Entrepreneur & Founder",
    "contact.subtitle": "Oncoteam was built for a real patient by a family member who needed it. If you\u2019re in a similar situation and want to learn more, reach out \u2014 we\u2019ve been there.",
    "privacy.title": "Your Data, Your Control",
    "privacy.gdpr.title": "GDPR Compliant",
    "privacy.gdpr.text": "All patient data is processed in compliance with the EU General Data Protection Regulation. Data is encrypted at rest and in transit.",
    "privacy.ownership.title": "Stored in Your Google Drive",
    "privacy.ownership.text": "Your medical documents stay in your own Google Drive. Oncoteam reads and processes data but never stores originals outside your control. You can revoke access anytime.",
    "privacy.access.title": "Multi-Layer Security",
    "privacy.access.text": "Google OAuth, API authentication, and encrypted connections. No unauthorized access to patient data \u2014 ever.",
    "privacy.audit.title": "Full Transparency",
    "privacy.audit.text": "Every data access and AI decision is logged. You can see exactly what Oncoteam read, analyzed, and recommended \u2014 and why.",
    "faq.title": "Frequently Asked Questions",
    "faq.subtitle": "Security, privacy & how your data is protected",
    "faq.tldr": "<strong>TL;DR \u2014 Data & Privacy Summary</strong><ul><li>Your documents live in <strong>your own Google Drive</strong> \u2014 we never store originals.</li><li>Oncofiles (the data layer) is <strong>open-source and self-hostable</strong> \u2014 you can run it on your own server if you prefer.</li><li>AI models <strong>never train on your data</strong> \u2014 guaranteed by <a href=\"https://www.anthropic.com/legal/commercial-terms\" target=\"_blank\" rel=\"noopener\">Anthropic\u2019s Commercial Terms</a>.</li><li>API data is <strong>auto-deleted within 30 days</strong> (safety review only, not training).</li><li>All communication is <strong>encrypted (HTTPS/TLS)</strong>. Patient IDs are <strong>anonymized</strong> in code.</li><li>Both Anthropic and Railway hold <strong>SOC 2 Type II</strong> certification.</li><li>Source code is 100% <strong>open-source</strong> \u2014 verify everything on <a href=\"https://github.com/peter-fusek/oncoteam\" target=\"_blank\" rel=\"noopener\">GitHub</a>.</li></ul>",
    "faq.group.data": "Data & Storage",
    "faq.group.ai": "AI Models & Privacy",
    "faq.group.infra": "Infrastructure & Compliance",
    "faq.group.general": "General",
    "faq.q1": "Where is my data stored?",
    "faq.a1": "All your medical documents stay in your own Google Drive. Oncoteam reads and analyzes them, but never copies or stores originals on any external server. You can revoke access anytime from your Google account settings.",
    "faq.q_selfhost": "Can I run Oncofiles on my own server?",
    "faq.a_selfhost": "Yes. <a href=\"https://github.com/peter-fusek/oncofiles\" target=\"_blank\" rel=\"noopener\">Oncofiles is open-source</a> \u2014 you can self-host it on your own infrastructure for maximum control. Alternatively, you can use the managed instance we operate on Railway (EU-available infrastructure, SOC 2 Type II certified). The choice is always yours: self-hosted for full sovereignty, or managed SaaS for convenience. Either way, your documents stay in your own Google Drive.",
    "faq.q5": "Is the data encrypted?",
    "faq.a5": "Yes. Google Drive encrypts all files at rest and in transit. Communication between Oncoteam and Google uses HTTPS. No data is transmitted unencrypted.",
    "faq.q4": "Who can see my data?",
    "faq.a4": "Only you. We have no access to your Google Drive or Gmail. Login uses official Google OAuth \u2014 we never see your password or your files. The source code is open-source, so you can verify everything.",
    "faq.q6": "Can I remove access?",
    "faq.a6": "Anytime. In your Google account settings (myaccount.google.com) you can remove Oncoteam access with one click. Your files remain untouched.",
    "faq.q2": "Does AI learn from my data?",
    "faq.a2_detailed": "No. Oncoteam uses the <strong>Anthropic API</strong> (not consumer Claude.ai). Anthropic\u2019s <a href=\"https://www.anthropic.com/legal/commercial-terms\" target=\"_blank\" rel=\"noopener\">Commercial Terms</a> explicitly state: <em>\u201cAnthropic may not train models on Customer Content from Services.\u201d</em> This is fundamentally different from consumer ChatGPT, which trains on your data by default. Your medical documents are processed in real-time, never stored for training, and auto-deleted within 30 days.",
    "faq.q_models": "Which AI models process my data?",
    "faq.a_models": "Oncoteam uses two models from Anthropic, both via the commercial API (zero training on your data):<br><br><strong>Claude Haiku 4.5</strong> \u2014 lightweight model for fast data tasks: document scanning, lab value extraction, medication parsing. Cost: ~$0.80/million tokens.<br><br><strong>Claude Sonnet 4.6</strong> \u2014 advanced reasoning model for: clinical trial analysis, treatment briefings, dose extraction from handwritten notes, family-friendly summaries. Cost: ~$3/million tokens.<br><br>Both models run via Anthropic\u2019s API (<a href=\"https://trust.anthropic.com/\" target=\"_blank\" rel=\"noopener\">SOC 2 Type II, ISO 27001</a>). No consumer-grade models (ChatGPT Free, Claude Free) are ever used.",
    "faq.q_retention": "How long does Anthropic keep my data?",
    "faq.a_retention": "API inputs and outputs are <strong>automatically deleted within 30 days</strong>. This retention is solely for safety monitoring (abuse prevention), not training. Anthropic also offers Zero Data Retention (ZDR) for enterprise customers. Details: <a href=\"https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data\" target=\"_blank\" rel=\"noopener\">Anthropic Privacy Center</a>. For comparison, consumer ChatGPT retains data indefinitely unless you manually delete it.",
    "faq.q_anon": "Are patient identities anonymized?",
    "faq.a_anon": "Yes. Patient IDs in the system are random 3-character codes (not names or birth dates). No personally identifiable information appears in environment variables, API keys, or code. Each patient gets a dedicated bearer token that isolates their data at the database level.",
    "faq.q_infra": "Where does Oncoteam run?",
    "faq.a_infra": "Oncoteam and Oncofiles run on <a href=\"https://railway.com\" target=\"_blank\" rel=\"noopener\">Railway</a> \u2014 a cloud platform with <strong>SOC 2 Type II</strong> certification (<a href=\"https://trust.railway.com/\" target=\"_blank\" rel=\"noopener\">Trust Center</a>). Railway offers data centers across Americas, EMEA, and APAC. HIPAA BAA is available on their Enterprise plan. If you self-host Oncofiles, you choose your own infrastructure entirely.",
    "faq.q_certs": "What security certifications apply?",
    "faq.a_certs": "<strong>Anthropic</strong> (AI provider): SOC 2 Type I & II, ISO 27001:2022, ISO 42001:2023 (AI Management), HIPAA BAA available. <a href=\"https://trust.anthropic.com/\" target=\"_blank\" rel=\"noopener\">Trust Center</a>.<br><strong>Railway</strong> (hosting): SOC 2 Type II, SOC 3, HIPAA BAA on Enterprise, GDPR DPA available. <a href=\"https://trust.railway.com/\" target=\"_blank\" rel=\"noopener\">Trust Center</a>.<br><strong>Google Drive</strong> (document storage): SOC 2, ISO 27001, HIPAA BAA on Workspace. Your files benefit from Google\u2019s enterprise-grade encryption.",
    "faq.q_vs_chatgpt": "How is this different from pasting results into ChatGPT?",
    "faq.a_vs_chatgpt": "<strong>Radically different.</strong> When you paste lab results into consumer ChatGPT, your data is used for model training by default, retained indefinitely, and has no patient isolation. Oncoteam uses the commercial Anthropic API where training on your data is contractually prohibited, retention is max 30 days, each patient has isolated access tokens, and the entire system is open-source for verification. It\u2019s the difference between shouting your diagnosis in a crowd vs. talking to your doctor in a private room.",
    "faq.q3": "Does Oncoteam replace my oncologist?",
    "faq.a3": "No. Oncoteam helps you prepare for appointments, understand lab results, and find relevant clinical trials. All treatment decisions should always be made with your oncology team.",
    "faq.q_opensource": "Why is the source code open?",
    "faq.a_opensource": "Because trust requires transparency. When it comes to your health data, \u201ctrust us\u201d isn\u2019t good enough. Every line of code is on <a href=\"https://github.com/peter-fusek/oncoteam\" target=\"_blank\" rel=\"noopener\">GitHub</a> \u2014 you (or any developer you trust) can verify exactly what happens with your data. Both <a href=\"https://github.com/peter-fusek/oncoteam\" target=\"_blank\" rel=\"noopener\">Oncoteam</a> and <a href=\"https://github.com/peter-fusek/oncofiles\" target=\"_blank\" rel=\"noopener\">Oncofiles</a> are fully open-source.",
    "faq.group.ehealth": "Slovak eHealth context",
    "faq.q_onkoasist": "How does Oncoteam relate to OnkoAsist / NCZI?",
    "faq.a_onkoasist": "<strong>OnkoAsist</strong> is a Slovak national eHealth project run by <a href=\"https://www.nczisk.sk\" target=\"_blank\" rel=\"noopener\">NCZI</a>. Its scope is the <em>pre-treatment</em> pathway \u2014 helping a patient get from first symptom to start of treatment within 60 days instead of 160. Oncoteam covers the opposite half of the journey: <em>from the moment treatment begins</em>, through every chemo cycle, lab result, and trial that might match. Different scope, different user, different cadence. We think it\u2019s a good project and we\u2019re happy to see the state investing in the first half.",
    "faq.q_national": "Does Oncoteam replace national eHealth systems?",
    "faq.a_national": "No. Oncoteam is not a national infrastructure or a registered medical device \u2014 it\u2019s a patient-and-family advocacy tool. It deliberately stays advisory-only. National systems like eZdravie, the National Oncology Register (N\u00e1rodn\u00fd onkologick\u00fd register), and OnkoAsist have legal mandates, eID integration, and inter-provider data flow that a bottom-up tool shouldn\u2019t try to replicate. If any of those systems eventually expose a standards-based API, we\u2019d welcome the chance to feed patient-reported outcomes (symptoms, toxicity, quality-of-life from WhatsApp) back into them.",
    "journey.title": "How Oncoteam Fits with Slovak eHealth",
    "journey.subtitle": "A patient\u2019s journey has many stages. We cover the time between visits.",
    "journey.national.label": "National eHealth (OnkoAsist \u2014 planned)",
    "journey.oncoteam.label": "Oncoteam (live today)",
    "journey.phase.symptoms": "Symptoms",
    "journey.phase.diagnosis": "Diagnosis",
    "journey.phase.start": "Start of treatment",
    "journey.phase.cycles": "Active cycles",
    "journey.phase.survivorship": "Survivorship",
    "journey.national.title": "National infrastructure",
    "journey.national.text": "OnkoAsist (NCZI) is a planned Slovak national system covering the pre-treatment pathway \u2014 from first symptom through diagnosis to the moment treatment starts. Its stated goal: cut time-to-treatment from 160 days to 60.",
    "journey.oncoteam.title": "Patient advocacy layer",
    "journey.oncoteam.text": "Oncoteam covers the opposite half of the journey \u2014 from the moment treatment begins. Pre-cycle safety checks, lab trend analysis, biomarker-aware trial matching, and a WhatsApp channel for the family. Live, open-source, three patients in active use.",
    "journey.footer": "We think both halves matter. When OnkoAsist is ready, we\u2019d be happy to feed patient-reported outcomes (WhatsApp symptom reports) back into it through standards-based APIs.",
    "stackup.title": "How We Stack Up \u2014 Honestly",
    "stackup.subtitle": "A factual comparison with existing and upcoming oncology platforms across the EU and CEE.",
    "stackup.intro": "We think the honest comparison matters more than any marketing claim. Numbers and dates are from public sources \u2014 tender portals, press releases, official registries \u2014 linked in our <a href=\"https://github.com/peter-fusek/oncoteam/blob/main/docs/competitive-landscape.md\" target=\"_blank\" rel=\"noopener\">competitive landscape document</a>.",
    "stackup.col.platform": "Platform",
    "stackup.col.status": "Status (Apr 2026)",
    "stackup.col.ai": "AI",
    "stackup.col.scope": "Scope",
    "stackup.col.funding": "Funding & model",
    "stackup.col.access": "Patient access",
    "stackup.row.us.status": "Live \u00b7 3 patients \u00b7 v0.80.0",
    "stackup.row.us.ai": "21 Claude agents",
    "stackup.row.us.scope": "During-treatment \u2192 survivorship",
    "stackup.row.us.funding": "Bootstrapped, open-source, free",
    "stackup.row.us.access": "Self-enroll via WhatsApp",
    "stackup.row.onkoasist.status": "In tender since Jan 2023 \u00b7 0 patients",
    "stackup.row.onkoasist.ai": "None \u2014 rule-based SOA",
    "stackup.row.onkoasist.scope": "Symptom \u2192 start of treatment",
    "stackup.row.onkoasist.funding": "\u20ac7.2M CAPEX, EU funds (planned)",
    "stackup.row.onkoasist.access": "National eID portal (planned)",
    "stackup.row.kso.status": "Live \u00b7 Apr 2025",
    "stackup.row.kso.ai": "None",
    "stackup.row.kso.scope": "Coordinator-driven pathways",
    "stackup.row.kso.funding": "Gov-funded (Fundusze Europejskie)",
    "stackup.row.kso.access": "Coordinator-mediated referrals",
    "stackup.row.belong.status": "Live",
    "stackup.row.belong.ai": "LLM mentor",
    "stackup.row.belong.scope": "Community + trial matching",
    "stackup.row.belong.funding": "VC \u00b7 freemium",
    "stackup.row.belong.access": "Self-enroll app",
    "stackup.row.o4m.status": "Live \u00b7 380k users combined",
    "stackup.row.o4m.ai": "AI-driven (breast + lung)",
    "stackup.row.o4m.scope": "Full journey, breast/lung only",
    "stackup.row.o4m.funding": "$21M Series 2025, closed-source",
    "stackup.row.o4m.access": "Self-enroll app (EN + DE)",
    "stackup.row.kaiku.status": "Live (enterprise)",
    "stackup.row.kaiku.ai": "ePRO analytics, no LLM",
    "stackup.row.kaiku.scope": "During-treatment ePRO",
    "stackup.row.kaiku.funding": "Elekta-owned enterprise",
    "stackup.row.kaiku.access": "Hospital contract only",
    "stackup.row.careology.status": "Live \u00b7 NHS pilots 2025",
    "stackup.row.careology.ai": "None",
    "stackup.row.careology.scope": "Symptom logging + wearables",
    "stackup.row.careology.funding": "VC + NHS pilots",
    "stackup.row.careology.access": "Self-enroll (English only)",
    "stackup.notes.heading": "What the numbers reveal",
    "stackup.notes.1": "<strong>\u20ac7.2M CAPEX \u00b7 zero live patients \u00b7 still in procurement since January 2023.</strong> That\u2019s OnkoAsist \u2014 Slovakia\u2019s national oncology eHealth tender. Oncoteam is a bootstrapped one-person hobby project that has shipped 89 sprints and has 3 patients in active use. When a weekend-coded open-source tool outpaces a \u20ac7M+ state initiative by three live patients to zero, that says something about top-down procurement versus patient-driven iteration.",
    "stackup.notes.2": "<strong>No surveyed national eHealth project uses AI agents.</strong> OnkoAsist (SK), KSO (PL), Czech Patient Portal (2026), EESZT (HU), Slovenian CRPD \u2014 all are classical SOA with rule-based decision logic. Many of these digital-health strategies span 2016 to 2026 and are still rolling out pre-AI architectures while LLM-agent platforms ship weekly.",
    "stackup.notes.3": "<strong>Enterprise ePRO vs. self-enroll.</strong> Kaiku Health (Elekta), Noona (Siemens), Moovcare and Resilience PRO all require a hospital or oncologist to enroll you. Oncoteam requires a WhatsApp number. Different go-to-market, different user.",
    "stackup.notes.4": "<strong>Oncoteam\u2019s unique intersection.</strong> No other surveyed platform covers all six of these at once: LLM-agent-native, WhatsApp/voice channel, open-source, multi-patient advocate mode, SK+EN multi-lingual, during-treatment clinical-protocol depth (pre-cycle safety, dose mods, cumulative dose, biomarker-aware exclusions).",
    "stackup.footer": "Full methodology, all 20+ surveyed platforms, and every source link lives in the <a href=\"https://github.com/peter-fusek/oncoteam/blob/main/docs/competitive-landscape.md\" target=\"_blank\" rel=\"noopener\">competitive landscape document on GitHub</a>. We update it when anything changes \u2014 pull requests welcome.",
    "about.title": "Who\u2019s behind this",
    "about.subtitle": "Oncoteam is an Instarea project \u2014 built by the same team that has been shipping software products for 18 years.",
    "about.stats.years": "years in business",
    "about.stats.products": "products shipped",
    "about.stats.alumni": "alumni",
    "about.stats.specialists": "dedicated specialists",
    "about.pf.role": "CEO & Founder",
    "about.pf.bio": "Serial entrepreneur and AI strategist. 4 years at Tatra banka. Co-founded marketlocator (exit to Deutsche Telekom, Deloitte Fast 50, FT 1000). Advisor to V\u00daB Bank CEO. 18+ years building technology products.",
    "about.pc.role": "CTO & Co-founder",
    "about.pc.bio": "Senior IT architect with 20+ years in enterprise banking (V\u00daB). Expert in .NET, Python, SQL and system architecture. Led the architecture across every Instarea product.",
    "about.portfolio.title": "Instarea portfolio \u2014 18 years, 23 products",
    "about.timeline.early": "telecom expense management, enterprise analytics, mobile-first products with PayPal integration",
    "about.timeline.marketlocator": "geo-data monetisation platform. Exit to Deutsche Telekom. Deloitte Fast 50, FT 1000.",
    "about.timeline.data": "enterprise data platforms, booking systems, IoT sensor networks",
    "about.timeline.dingodot": "PSD2 fintech (including Tatra banka PremiumAPI), swipe-sorting, QR payments",
    "about.timeline.aifirst": "AI-first products: team optimisation, AI-powered surveys, equity release",
    "about.timeline.now": "the AI-first era. Oncoteam is one of six products currently in active development.",
    "about.portfolio.footer": "Full story, team, and references at <a href=\"https://www.instarea.com\" target=\"_blank\" rel=\"noopener\">instarea.com</a>.",
    "about.cta": "Trust comes from track record. Every product above is live, shipping, or has a successful exit \u2014 that\u2019s the team building oncoteam.",
    "newsletter.heading": "Stay in the loop",
    "newsletter.sub": "Occasional updates on new features, clinical-protocol additions, and release notes. No spam, unsubscribe any time.",
    "footer.rights": "Built by a patient advocate, for patient advocates.",
    "footer.disclaimer": "Oncoteam is an AI-powered decision support tool. It does not replace professional medical advice. Always consult your oncologist for treatment decisions.",
    "footer.instarea": "An",
    "footer.instarea2": "project.",
    "demo.mock.alert": "ANC = 1,150 (threshold: 1,500) \u2014 hold chemo",
    "demo.mock.status": "TREATMENT STATUS",
    "demo.mock.cycle": "Cycle 3 \u00b7 Stage IV mCRC",
    "demo.mock.labs": "RECENT LABS",
    "demo.mock.briefing": "Latest AI Briefing: EU Clinical Trial Monitor \u2014 3 new trials matched...",
    "demo.mock.markers": "TUMOR MARKERS \u2014 3 CYCLES",
    "demo.mock.prec1": "Pre-C1 (Feb)",
    "demo.mock.prec2": "Pre-C2 (Feb)",
    "demo.mock.prec3": "Pre-C3 (Mar)",
    "demo.mock.labinsight": "Excellent treatment response \u2014 CEA declined 62% over 3 cycles",
    "demo.mock.funnel": "CLINICAL TRIAL FUNNEL \u2014 AI-CLASSIFIED",
    "demo.mock.excluded": "Excluded <span>20</span>",
    "demo.mock.later": "Later Line <span>2</span>",
    "demo.mock.watching": "Watching <span>14</span>",
    "demo.mock.bev": "Bevacizumab risk (VTE)",
    "demo.mock.checkpoint": "Checkpoint mono (MSS)",
    "demo.mock.registries": "3L+ registries",
    "demo.mock.pankras": "pan-KRAS trials",
    "demo.mock.ici": "ICI combinations",
    "demo.mock.funnelinsight": "36 trials classified by AI in 15 seconds \u2014 $0.025 total",
    "demo.mock.checklist": "PRE-CYCLE 3 CHECKLIST \u2014 mFOLFOX6",
    "demo.mock.anc": "ANC \u2265 1,500/\u00b5L \u2014 <strong>1,150 (HOLD)</strong>",
    "demo.mock.plt": "PLT \u2265 75,000/\u00b5L \u2014 269,000",
    "demo.mock.creat": "Creatinine \u2264 1.5x ULN \u2014 0.42",
    "demo.mock.bili": "Bilirubin \u2264 1.5x ULN \u2014 normal",
    "demo.mock.protocolinsight": "Pre-cycle safety check: 1 flag requires physician review before C3",
    "demo.tab.chat": "Chat",
    "demo.mock.whatsapp": "WHATSAPP",
    "demo.mock.chatreply1": "&#x1F4CA; <strong>Labs (Mar 19):</strong> ANC 1,150 &#x2193;, PLT 269k, HGB 118 &#x2191;<br>CEA 733 &#x2193;62%, CA19-9 22.3k &#x2193;68%<br><em>ANC below threshold \u2014 discuss with oncologist before C3</em>",
    "demo.mock.chatq2": "next cycle?",
    "demo.mock.chatreply2": "&#x1F4C5; Cycle 3 mFOLFOX6 \u2014 pending physician review (ANC hold).<br>Pre-cycle checklist: 1/4 flags. Ask oncologist about dose reduction.",
    "demo.mock.claudeai": "CLAUDE.AI (MCP CONNECTOR)",
    "demo.mock.claudeq": "Find clinical trials for KRAS G12S mCRC in Slovakia",
    "demo.mock.claudereply": "&#x1F50D; Searched ClinicalTrials.gov + EU registries (SK, CZ, AT, HU).<br><strong>3 matches:</strong> pan-KRAS inhibitor (Phase II, Bratislava), ICI+chemo combo (Phase III, Vienna), anti-TIGIT trial (Budapest).<br><em>All compatible with current KRAS G12S + active VTE profile.</em>"
  },
  sk: {
    "nav.dashboard": "Dashboard",
    "nav.demo": "Vysk\u00fa\u0161a\u0165 Demo",
    "nav.how": "Ako to funguje",
    "nav.features": "Funkcie",
    "nav.getstarted": "Za\u010da\u0165",
    "nav.about": "O n\u00e1s",
    "nav.faq": "FAQ",
    "hero.title": "Ke\u010f m\u00e1 v\u00e1\u0161 bl\u00edzky rakovinu, st\u00e1vate sa jeho hlavn\u00fdm spojencom.",
    "hero.subtitle": "Oncoteam v\u00e1m pom\u00f4\u017ee porozumie\u0165 lie\u010dbe, kl\u00e1s\u0165 spr\u00e1vne ot\u00e1zky, n\u00e1js\u0165 klinick\u00e9 \u0161t\u00fadie a ma\u0165 istotu, \u017ee sa ni\u010d neprehliadlo \u2014 v\u0161etko z v\u00e1\u0161ho telef\u00f3nu.",
    "hero.badge": "Open Source \u00b7 Pou\u017e\u00edvan\u00e9 v akt\u00edvnej lie\u010dbe",
    "hero.demo": "Vysk\u00fa\u0161a\u0165 Demo",
    "hero.how": "Ako to funguje",
    "hero.github": "Zobrazi\u0165 na GitHub",
    "hero.whatsapp": "Vysk\u00fa\u0161ajte cez WhatsApp",
    "hero.micro": "Zdarma po\u010das akt\u00edvnej lie\u010dby. Bez platobnej karty.",
    "hero.phone.status": "online",
    "demo.title": "Pozrite sa, ako to funguje",
    "demo.subtitle": "Re\u00e1lny dashboard, re\u00e1lne d\u00e1ta, re\u00e1lna lie\u010dba.",
    "demo.tab.dashboard": "Dashboard",
    "demo.tab.labs": "Laborat\u00f3rium",
    "demo.tab.funnel": "Lievik \u0161t\u00fadi\u00ed",
    "demo.tab.protocol": "Protokol",
    "story.title": "Vzniklo zo \u017eivota",
    "story.p1": "Ke\u010f Erike diagnostikovali metastatick\u00fd kolorekt\u00e1lny karcin\u00f3m, jej man\u017eel Peter \u2014 podnikate\u013e a technologick\u00fd nad\u0161enec, nie lek\u00e1r \u2014 sa ocitol zahraben\u00fd v laborat\u00f3rnych v\u00fdsledkoch, genetick\u00fdch spr\u00e1vach a lie\u010debn\u00fdch protokoloch, ktor\u00fdm nerozumel. Ka\u017ed\u00e1 n\u00e1v\u0161teva onkol\u00f3ga bola pr\u00edli\u0161 kr\u00e1tka. Ka\u017ed\u00e9 nov\u00e9 vy\u0161etrenie prinieslo ot\u00e1zky, ktor\u00e9 nevedel polo\u017ei\u0165.",
    "story.p2": "A tak postavil Oncoteam. Nie ako n\u00e1hradu onkol\u00f3ga, ale ako n\u00e1stroj, ktor\u00fd mu pom\u00e1ha dr\u017ea\u0165 krok \u2014 rozumie\u0165 \u010d\u00edslam, pripravi\u0165 spr\u00e1vne ot\u00e1zky, sledova\u0165 \u010do sa men\u00ed a vyh\u013ead\u00e1va\u0165 klinick\u00e9 \u0161t\u00fadie, ktor\u00e9 \u017eiaden lek\u00e1r nem\u00e1 \u010das systematicky monitorova\u0165 naprieč Eur\u00f3pou a USA.",
    "story.p3": "Spolu s Oncoteamom postavil Oncofiles \u2014 d\u00e1tov\u00fa vrstvu, ktor\u00e1 organizuje v\u0161etky medic\u00ednske dokumenty z Google Drive: laborat\u00f3rne v\u00fdsledky, patologick\u00e9 spr\u00e1vy, CT vy\u0161etrenia, genetick\u00e9 testy. Oncofiles ich \u0161trukt\u00faruje a prep\u00e1ja. Oncoteam z nich rob\u00ed u\u017eito\u010dn\u00e9 inform\u00e1cie \u2014 je to inteligentn\u00e1 vrstva, ktor\u00e1 premie\u0148a surov\u00e9 medic\u00ednske d\u00e1ta na porozumenie, ot\u00e1zky a akciu.",
    "manifesto.text": "Toto nie je n\u00e1hrada onkol\u00f3ga. Je to n\u00e1stroj, ktor\u00fd pom\u00e1ha v\u00e1m \u2014 pacientovi, partnerovi, synovi, dc\u00e9re \u2014 dr\u017ea\u0165 krok so situ\u00e1ciou, ktor\u00e1 sa vyv\u00edja r\u00fdchlej\u0161ie, ne\u017e dok\u00e1\u017ee sledova\u0165 jeden \u010dlovek. Nie preto, \u017ee by ste lek\u00e1rovi ned\u00f4verovali, ale preto, \u017ee aj ten najlep\u0161\u00ed lek\u00e1r m\u00e1 stovky pacientov a p\u00e4tn\u00e1s\u0165 min\u00fat na jednu n\u00e1v\u0161tevu.",
    "reality.title": "Realita, ktorej \u010del\u00edte",
    "reality.subtitle": "Nie je to ni\u010dia chyba. Je to jednoducho realita modernej onkol\u00f3gie.",
    "reality.hundreds.title": "Stovky pacientov, jeden lek\u00e1r",
    "reality.hundreds.text": "V\u00e1\u0161 onkol\u00f3g je vynikaj\u00faci \u2014 ale star\u00e1 sa o stovky pacientov. Nie je v \u013eudsk\u00fdch sil\u00e1ch dr\u017ea\u0165 ka\u017ed\u00fd detail ka\u017ed\u00e9ho pr\u00edpadu v hlave po\u010das p\u00e4tn\u00e1s\u0165min\u00fatovej n\u00e1v\u0161tevy v ambulancii.",
    "reality.trials.title": "Nov\u00e9 \u0161t\u00fadie ka\u017ed\u00fd de\u0148",
    "reality.trials.text": "Klinick\u00e9 \u0161t\u00fadie zodpovedaj\u00face v\u00e1\u0161mu molekul\u00e1rnemu profilu sa otv\u00e1raj\u00fa ka\u017ed\u00fd t\u00fd\u017ede\u0148 \u2014 nielen v okol\u00ed, ale v celej Eur\u00f3pe aj v USA. \u017diadny \u010dlovek ich nedok\u00e1\u017ee systematicky a personalizovane preh\u013ead\u00e1va\u0165 na dennej b\u00e1ze.",
    "reality.data.title": "Lavina medic\u00ednskych d\u00e1t",
    "reality.data.text": "Laborat\u00f3rne v\u00fdsledky, CT vy\u0161etrenia, patologick\u00e9 spr\u00e1vy, genetick\u00e9 testy, lie\u010debn\u00e9 protokoly \u2014 papiere sa r\u00fdchlo kopia. Porozumie\u0165 \u010do znamen\u00e1, ako s\u00favis\u00ed a \u010do sa meni v \u010dase, je pr\u00e1ca na pln\u00fd \u00fazv\u00e4zok.",
    "reality.time.title": "Lie\u010dba sa vyv\u00edja, ot\u00e1zky pribudaj\u00fa",
    "reality.time.text": "S ka\u017ed\u00fdm cyklom sa situ\u00e1cia men\u00ed. Nov\u00e9 ved\u013eaj\u0161ie \u00fa\u010dinky, \u00fapravy d\u00e1vok, meniace sa biomarkery. Potrebujete vedie\u0165, \u010do sa sp\u00fdta\u0165 na \u010fal\u0161ej n\u00e1v\u0161teve \u2014 a t\u00fa odpove\u010f potrebujete teraz, nie o tri t\u00fd\u017edne.",
    "hiw.title": "Ako to funguje",
    "hiw.subtitle": "Z k\u00f4pky medic\u00ednskych papierov k jasn\u00e9mu obrazu \u2014 v troch krokoch.",
    "hiw.step1.title": "Nahrajte dokumenty",
    "hiw.step1.text": "Naskenujte alebo odfotografujte laborat\u00f3rne v\u00fdsledky, CT vy\u0161etrenia, patologick\u00e9 spr\u00e1vy \u2014 vlo\u017ete ich do prie\u010dinka na Google Drive. To je v\u0161etko.",
    "hiw.step2.title": "AI spracuje v\u0161etko",
    "hiw.step2.text": "Oncofiles automaticky \u0161trukt\u00faruje dokumenty. 21 AI agentov Oncoteamu ich analyzuje \u2014 sleduj\u00fa trendy, kontroluj\u00fa bezpe\u010dnos\u0165, h\u013eadaj\u00fa \u0161t\u00fadie.",
    "hiw.step3.title": "Pochopte a konajte",
    "hiw.step3.text": "Otvorte dashboard alebo chatujte cez WhatsApp \u2014 dostanete interpret\u00e1cie labov, bezpe\u010dnostn\u00e9 upozornenia, zhody \u0161t\u00fadi\u00ed a ot\u00e1zky pre onkol\u00f3ga.",
    "stats.agents": "AI agentov pracuje 24/7",
    "stats.tests": "automatizovan\u00fdch testov prech\u00e1dza",
    "stats.trials": "sledovan\u00fdch klinick\u00fdch \u0161t\u00fadi\u00ed",
    "stats.patients": "pacienti v akt\u00edvnom pou\u017e\u00edvan\u00ed",
    "testimonial.quote": "Pred Oncoteamom som chodil k onkol\u00f3govi s prie\u010dinkom papierov, ktor\u00fdm som sotva rozumel. Teraz pr\u00eddem s konkr\u00e9tnymi ot\u00e1zkami, grafmi trendov a mo\u017enos\u0165ami \u0161t\u00fadi\u00ed, ktor\u00e9 som u\u017e presk\u00famal. Doktor si v\u0161imol rozdiel u\u017e pri druhej n\u00e1v\u0161teve.",
    "testimonial.role": "Patient advocate & zakladate\u013e",
    "features.title": "\u010co z\u00edskate",
    "features.subtitle": "V\u0161etko, \u010do patient advocate potrebuje, vysvetlen\u00e9 v jazyku, ktor\u00fd si vyberiete.",
    "features.labs.title": "Porozumejte v\u00fdsledkom",
    "features.labs.text": "Pozrite sa, \u010do ka\u017ed\u00e9 \u010d\u00edslo znamen\u00e1, \u010di sa zlep\u0161uje alebo zhor\u0161uje a ako sa porovn\u00e1va s predch\u00e1dzaj\u00facimi cyklami. Z\u00e1palov\u00e9 indexy, bezpe\u010dnostn\u00e9 prahy a grafy trendov \u2014 v zrozumite\u013enom jazyku alebo odbornej terminol\u00f3gii, na jedno kliknutie.",
    "features.questions.title": "Kla\u010fte spr\u00e1vne ot\u00e1zky",
    "features.questions.text": "Pred ka\u017edou n\u00e1v\u0161tevou onkol\u00f3ga dostanete personalizovan\u00fd zoznam ot\u00e1zok na z\u00e1klade aktu\u00e1lnych v\u00fdsledkov, f\u00e1zy lie\u010dby a zmien od poslednej n\u00e1v\u0161tevy. Pr\u00ed\u010fte pripraven\u00ed, nie zmäten\u00ed.",
    "features.trials.title": "N\u00e1jdite \u0161t\u00fadie, pre ktor\u00e9 sp\u013a\u0148ate krit\u00e9ri\u00e1",
    "features.trials.text": "Automaticky preh\u013ead\u00e1va ClinicalTrials.gov a eur\u00f3pske registre pre \u0161t\u00fadie zodpovedaj\u00face v\u00e1\u0161mu molekul\u00e1rnemu profilu, lokalite a hist\u00f3rii lie\u010dby. AI klasifikuje ka\u017ed\u00fa \u0161t\u00fadiu do lievika \u2014 od vyl\u00fa\u010denej po vy\u017eaduj\u00facu akciu.",
    "features.opinion.title": "Druh\u00fd n\u00e1zor, v\u017edy po ruke",
    "features.opinion.text": "Porovn\u00e1va va\u0161u lie\u010dbu s medic\u00ednskymi u\u010debnicami (DeVita), NCCN protokolmi a najnov\u0161\u00edm v\u00fdskumom. Nie aby spochyb\u0148oval lek\u00e1ra \u2014 ale aby ste mali istotu, \u017ee sa dodr\u017eiava \u0161tandard starostlivosti a ni\u010d sa nevynechalo.",
    "features.mobile.title": "V\u0161etko vo va\u0161om vreck\u00fa",
    "features.mobile.text": "Chatujte cez WhatsApp kedyko\u013evek \u2014 sp\u00fdtajte sa na v\u00fdsledok, skontrolujte termin \u010fal\u0161ieho cyklu alebo si nechajte urobi\u0165 r\u00fdchle zhrnutie. Otvorte dashboard pre trendy, \u010dasov\u00e9 osi a podrobnosti. Je to po ruke, ke\u010f to potrebujete.",
    "features.language.title": "Odborn\u00fd \u2194 Zrozumite\u013en\u00fd jazyk",
    "features.language.text": "Ka\u017ed\u00fd medic\u00ednsky pojem, skratka a laborat\u00f3rna hodnota vysvetlen\u00e1 slovami, ktor\u00fdm rozumiete. Prep\u00ednajte medzi zrozumite\u013en\u00fdm a klinick\u00fdm jazykom jedn\u00fdm klikom. U\u010dte sa vlastn\u00fdm tempom \u2014 alebo jednoducho dostanete odpove\u010f.",
    "features.trends.title": "Sledujte, ako lie\u010dba funguje",
    "features.trends.text": "Vizu\u00e1lne trendy n\u00e1dorov\u00fdch markerov, krvn\u00e9ho obrazu a z\u00e1palov\u00fdch indexov naprieč cyklami. Sledujte trajekt\u00f3riu \u2014 funguje lie\u010dba? Id\u00fa \u010d\u00edsla spr\u00e1vnym smerom? \u017diadne h\u00e1danie.",
    "features.family.title": "Informujte svoju rodinu",
    "features.family.text": "Vytvorte jasn\u00e9, \u013eudsk\u00e9 s\u00fahrny lie\u010dby pre \u010dlenov rodiny, ktor\u00ed chc\u00fa pom\u00f4c\u0165, ale nevedia ako sa sp\u00fdta\u0165. Zdie\u013eajte cez WhatsApp alebo tla\u010d \u2014 na pochopenie netreba medic\u00ednsky titul.",
    "features.genetics.title": "Dedi\u010dn\u00e1 DNA \u2014 panel v jednom poh\u013eade",
    "features.genetics.text": "Automaticky zobraz\u00ed v\u00fdsledky dedi\u010dn\u00e9ho onkologick\u00e9ho panelu \u2014 BRCA1/2, Lynchov syndr\u00f3m, ATM, PALB2 a \u010fal\u0161ie \u2014 s vysvetlen\u00edm v zrozumite\u013enom jazyku. Ka\u017ed\u00fd n\u00e1lez odkazuje na zdrojov\u00fa spr\u00e1vu, aby onkol\u00f3g aj rodina videli presne, \u010do sa testovalo.",
    "features.waudit.title": "Hist\u00f3ria WhatsApp konverz\u00e1ci\u00ed",
    "features.waudit.text": "Ka\u017ed\u00e1 spr\u00e1va z WhatsApp \u2014 ot\u00e1zky, upozornenia, s\u00fahrny pre rodinu \u2014 sa ukladá a d\u00e1 sa prezrie\u0165 na dashboarde. Ni\u010d sa nestrat\u00ed v scrollovan\u00ed. Ide\u00e1lne, ke\u010f pacient je v akt\u00edvnej lie\u010dbe a blízki sa koordinuj\u00fa medzi \u010dasov\u00fdmi p\u00e1smami.",
    "gs.title": "Za\u010dnite v 5 krokoch",
    "gs.subtitle": "Od nuly po pln\u00e9ho AI patient advocata \u2014 trv\u00e1 asi 30 min\u00fat.",
    "gs.shortcut.prefix": "U\u017e m\u00e1te Oncofiles?",
    "gs.shortcut.link": "Presko\u010dte na Krok 4 \u2192",
    "gs.step1.title": "Vytvorte si \u00fa\u010det",
    "gs.step1.text": "Chodte na oncofiles.com, vytvorte profil pacienta a za\u010dnite organizova\u0165 d\u00e1ta na jednom mieste. Toto je z\u00e1klad, na ktorom stavia v\u0161etko ostatn\u00e9.",
    "gs.step1.cta": "\u00cds\u0165 na Oncofiles.com",
    "gs.step2.title": "Prepojte Google Drive",
    "gs.step2.text": "Prepojte v\u00e1\u0161 Google Drive s Oncofiles. Automaticky \u010d\u00edta va\u0161e medic\u00ednske dokumenty, organizuje ich a aplikuje OCR a AI \u0161trukt\u00farovanie \u2014 \u017eiadne ru\u010dn\u00e9 tagovanie.",
    "gs.step3.title": "Nahrajte dokumenty",
    "gs.step3.text": "Vlo\u017ete laborat\u00f3rne v\u00fdsledky, patologick\u00e9 spr\u00e1vy, CT vy\u0161etrenia a genetick\u00e9 testy do pripojen\u00e9ho prie\u010dinka na Google Drive. Oncofiles ka\u017ed\u00fd s\u00fabor spracuje automaticky.",
    "gs.step4.badge": "\u2190 U\u017e m\u00e1te Oncofiles? Za\u010dnite tu",
    "gs.step4.title": "Pripojte AI konektory",
    "gs.step4.text": "V Claude.ai cho\u010fte do Nastavenia \u2192 Konektory a pridajte \"Oncoteam\" a \"Oncofiles\" ako vlastn\u00e9 konektory. AI tak z\u00edska priamy pr\u00edstup k va\u0161im d\u00e1tam.",
    "gs.step4.cta": "Otvori\u0165 Claude.ai Konektory",
    "gs.step5.title": "Za\u010dnite pou\u017e\u00edva\u0165",
    "gs.step5.text": "Po\u0161lite spr\u00e1vu cez WhatsApp alebo otvorte dashboard \u2014 v\u00e1\u0161 AI patient advocate je pripraven\u00fd. Sp\u00fdtajte sa na laby, po\u017eiadajte o h\u013eadanie \u0161t\u00fadi\u00ed alebo sa nechajte pripravi\u0165 na n\u00e1v\u0161tevu onkol\u00f3ga.",
    "gs.step5.cta": "Otvori\u0165 Dashboard",
    "gs.whatsapp.label": "Najr\u00fdchlej\u0161\u00ed sp\u00f4sob:",
    "gs.whatsapp.text": " Sta\u010d\u00ed nap\u00edsa\u0165 na WhatsApp \u2014 prevedieme v\u00e1s zvy\u0161kom.",
    "gs.whatsapp.btn": "WhatsApp",
    "gs.free.badge": "Zadarmo po\u010das akt\u00edvnej lie\u010dby",
    "gs.free.docs": "medic\u00ednskych dokumentov",
    "gs.free.queries": "AI dotazov / mesiac",
    "gs.free.agents": "auton\u00f3mnych agentov / mesiac",
    "gs.free.note": "Tieto limity s\u00fa va\u0161e a nebudeme v\u00e1m ich zni\u017eova\u0165. Komer\u010dn\u00fd model zatia\u013e nem\u00e1me \u2014 prioritou je pacient a vyladenie produktu, nie monetiz\u00e1cia. Ke\u010f sa to zmen\u00ed, dozviete sa to ako prv\u00ed.",
    "uc.title": "\u010co sa pacienti naozaj p\u00fdtaj\u00fa",
    "uc.subtitle": "Skuto\u010dn\u00e9 situ\u00e1cie od skuto\u010dn\u00fdch opatrovate\u013eov. Jedna spr\u00e1va na WhatsApp.",
    "uc.1.title": "\u010co hovorili posledn\u00e9 labky?",
    "uc.1.story": "Mama nosila v\u00fdsledky na kontrolu bez toho, aby im rozumela. Teraz nap\u00ed\u0161e jedno slovo a dostane jasn\u00fd preh\u013ead s trendmi.",
    "uc.2.title": "Neviem, \u010do sa op\u00fdta\u0165 na kontrole",
    "uc.2.story": "P\u00e4tn\u00e1s\u0165 min\u00fat na onkol\u00f3gii. Zoznam ot\u00e1zok z najnov\u0161\u00edch v\u00fdsledkov a zmien od poslednej n\u00e1v\u0161tevy \u2014 pripraven\u00fd za sekundu.",
    "uc.2.cmd": "ot\u00e1zky pre lek\u00e1ra",
    "uc.3.title": "Kedy je \u010fal\u0161ia kontrola?",
    "uc.3.story": "Po ukon\u010den\u00ed lie\u010dby sledovanie neprest\u00e1va. Term\u00edny, biomarkery, \u010fal\u0161ie kroky \u2014 v\u0161etko na jednom mieste.",
    "uc.4.title": "Rodina sa p\u00fdta, ako sa dar\u00ed",
    "uc.4.story": "S\u00farodenec v zahrani\u010d\u00ed, star\u00ed rodi\u010dia doma. Zrozumite\u013en\u00e9 zhrnutie lie\u010dby bez medic\u00ednskych term\u00ednov \u2014 jednou spr\u00e1vou.",
    "uc.4.cmd": "inform\u00e1cia pre rodinu",
    "wa.title": "V\u00e1\u0161 AI pomocn\u00edk na WhatsApp",
    "wa.subtitle": "Sp\u00fdtajte sa \u010doho\u013evek, kedyko\u013evek. Dostanete informovan\u00e9 odpovede zo zdrojov va\u0161ich vlastn\u00fdch zdravotn\u00fdch z\u00e1znamov.",
    "wa.status": "online",
    "wa.conv1.q": "labky",
    "wa.conv1.a1": "&#x1F4CA; <strong>Odbery (19. mar):</strong><br>WBC 3,8, ANC 2 100, HGB 112<br>CEA 8,1 &#x2193;35 %, CA19-9 4 820 &#x2193;68 %<br><br>&#x2705; Bezpe\u010dn\u00e9 pre \u010fal\u0161\u00ed cyklus<br>&#x26A0;&#xFE0F; HGB mierne n\u00edzky \u2014 sp\u00fdtajte sa na \u017eelezo",
    "wa.conv1.q2": "ot\u00e1zky pre lek\u00e1ra?",
    "wa.conv1.a2": "&#x1F4DD; <strong>Pre v\u00e1\u0161ho onkol\u00f3ga:</strong><br>1. HGB kles\u00e1 \u2014 suplementa\u010dne \u017eelezo?<br>2. Stupe\u0148 neuropatie po 3 cykloch?<br>3. CEA odpove\u010f v\u00fdborn\u00e1 \u2014 \u010dasov\u00fd pl\u00e1n zobrazenia?",
    "wa.conv2.a1": "&#x1F50D; <strong>Nov\u00e1 zhoda \u0161t\u00fadie:</strong><br>NCT07284849 \u2014 FOLFOX + nov\u00fd liek<br>F\u00e1za III, n\u00e1bor vo Viedni (AT)<br><br>Kompatibiln\u00e9 s va\u0161\u00edm molekul\u00e1rnym profilom.<br>Biomarker: KRAS mutant elig. &#x2705;",
    "wa.conv2.q": "viac detailov?",
    "wa.conv2.a2": "&#x1F3E5; <strong>AKH Viede\u0148</strong>, 90 min z Bratislavy<br>N\u00e1bor otvoren\u00fd do aug 2026<br>Vy\u017eaduje: &#x2265;2 predch\u00e1dzaj\u00face l\u00ednie, ECOG 0-1<br><br><em>M\u00f4\u017em pripravi\u0165 zhrnutie pre v\u00e1\u0161ho onkol\u00f3ga.</em>",
    "wa.conv3.q": "inform\u00e1cia pre rodinu",
    "wa.conv3.a1": "&#x1F46A; <strong>Inform\u00e1cia pre rodinu (20. mar):</strong><br><br>Lie\u010dba ide dobre. Krvn\u00fd obraz vyzer\u00e1 dobre \u2014 bezpe\u010dn\u00e9 pokra\u010dova\u0165 \u010fal\u0161\u00edm cyklom. Hlavn\u00fd n\u00e1dorov\u00fd marker (CEA) klesol o 35 % oproti minulemu, \u010do je ve\u013emi pozit\u00edvny znak.<br><br>M\u00f4\u017ee sa c\u00edti\u0165 unavenej\u0161ia ako zvykne (hemoglob\u00edn je trochu n\u00edzky). Lek\u00e1r m\u00f4\u017ee navrhn\u00fa\u0165 \u017eelezo.<br><br>\u010eal\u0161ie vy\u0161etrenie: 28. marca.",
    "wa.label1": "Pred vy\u0161etren\u00edm",
    "wa.label2": "AI h\u013ead\u00e1 \u0161t\u00fadie za v\u00e1s",
    "wa.label3": "Aj rodina rozumie",
    "tech.title": "Integruje sa s",
    "ecosystem.title": "Dva produkty, jedna misia",
    "ecosystem.subtitle": "Va\u0161e medic\u00ednske d\u00e1ta, organizovan\u00e9 a pochopen\u00e9.",
    "ecosystem.files.role": "D\u00e1tov\u00e1 vrstva",
    "ecosystem.files.text": "Organizuje medic\u00ednske dokumenty z Google Drive. Laborat\u00f3rne v\u00fdsledky, patol\u00f3gia, CT, genetick\u00e9 testy \u2014 \u0161trukt\u00farovan\u00e9, prepojen\u00e9, vyh\u013eadaten\u00e9.",
    "ecosystem.team.role": "Inteligentn\u00e1 vrstva",
    "ecosystem.team.text": "Premie\u0148a organizovan\u00e9 d\u00e1ta na porozumenie. Trendy labov, matching \u0161t\u00fadi\u00ed, pr\u00edprava na n\u00e1v\u0161tevu, spr\u00e1vy pre rodinu \u2014 poháňané AI, pod va\u0161ou kontrolou.",
    "contact.title": "Kontakt",
    "contact.bug": "Nahl\u00e1si\u0165 chybu",
    "contact.role": " \u2014 Podnikate\u013e & Zakladate\u013e",
    "contact.subtitle": "Oncoteam vznikol pre re\u00e1lneho pacienta. Postavil ho rodinn\u00fd pr\u00edslu\u0161n\u00edk, ktor\u00fd to potreboval. Ak ste v podobnej situ\u00e1cii a chcete sa dozvedie\u0165 viac, ozvite sa \u2014 boli sme tam tie\u017e.",
    "privacy.title": "Va\u0161e d\u00e1ta, va\u0161a kontrola",
    "privacy.gdpr.title": "S\u00falad s GDPR",
    "privacy.gdpr.text": "V\u0161etky \u00fadaje pacientov s\u00fa sprac\u00favan\u00e9 v s\u00falade so v\u0161eobecn\u00fdm nariaden\u00edm E\u00da o ochrane \u00fadajov. D\u00e1ta s\u00fa \u0161ifrovan\u00e9 pri ulo\u017een\u00ed aj prenose.",
    "privacy.ownership.title": "Ulo\u017een\u00e9 na va\u0161om Google Drive",
    "privacy.ownership.text": "Va\u0161e medic\u00ednske dokumenty zost\u00e1vaj\u00fa na va\u0161om vlastnom Google Drive. Oncoteam \u010d\u00edta a spracov\u00e1va d\u00e1ta, ale nikdy neuklad\u00e1 origin\u00e1ly mimo va\u0161ej kontroly. Pr\u00edstup m\u00f4\u017eete kedyko\u013evek zru\u0161i\u0165.",
    "privacy.access.title": "Viacvrstvov\u00e9 zabezpe\u010denie",
    "privacy.access.text": "Google OAuth, API autentifik\u00e1cia a \u0161ifrovan\u00e9 pripojenia. \u017diadny neopr\u00e1vnen\u00fd pr\u00edstup k \u00fadajom pacienta \u2014 nikdy.",
    "privacy.audit.title": "\u00dapln\u00e1 transparentnos\u0165",
    "privacy.audit.text": "Ka\u017ed\u00fd pr\u00edstup k d\u00e1tam a rozhodnutie AI je zaznamenan\u00e9. Pozrite sa presne, \u010do Oncoteam pre\u010d\u00edtal, analyzoval a odporu\u010dil \u2014 a pre\u010do.",
    "faq.title": "\u010casto kladen\u00e9 ot\u00e1zky",
    "faq.subtitle": "Bezpe\u010dnos\u0165, s\u00fakromie a ochrana va\u0161ich d\u00e1t",
    "faq.tldr": "<strong>TL;DR \u2014 S\u00fahrn d\u00e1t a s\u00fakromia</strong><ul><li>Va\u0161e dokumenty \u017eij\u00fa na <strong>va\u0161om vlastnom Google Drive</strong> \u2014 origin\u00e1ly nikdy neuklad\u00e1me.</li><li>Oncofiles (d\u00e1tov\u00e1 vrstva) je <strong>open-source a self-hostovate\u013en\u00fd</strong> \u2014 m\u00f4\u017eete si ho spusti\u0165 na vlastnom serveri.</li><li>AI modely sa <strong>nikdy neu\u010dia na va\u0161ich d\u00e1tach</strong> \u2014 garantuj\u00fa to <a href=\"https://www.anthropic.com/legal/commercial-terms\" target=\"_blank\" rel=\"noopener\">Obchodn\u00e9 podmienky Anthropic</a>.</li><li>D\u00e1ta z API s\u00fa <strong>automaticky zmazan\u00e9 do 30 dn\u00ed</strong> (len bezpe\u010dnostn\u00fd monitoring, nie tr\u00e9ning).</li><li>V\u0161etka komunik\u00e1cia je <strong>\u0161ifrovan\u00e1 (HTTPS/TLS)</strong>. ID pacientov s\u00fa <strong>anonymizovan\u00e9</strong> v k\u00f3de.</li><li>Anthropic aj Railway maj\u00fa certifik\u00e1ciu <strong>SOC 2 Type II</strong>.</li><li>Zdrojov\u00fd k\u00f3d je 100% <strong>open-source</strong> \u2014 overte si v\u0161etko na <a href=\"https://github.com/peter-fusek/oncoteam\" target=\"_blank\" rel=\"noopener\">GitHub</a>.</li></ul>",
    "faq.group.data": "D\u00e1ta a \u00falo\u017eisko",
    "faq.group.ai": "AI modely a s\u00fakromie",
    "faq.group.infra": "Infra\u0161trukt\u00fara a certifik\u00e1cie",
    "faq.group.general": "V\u0161eobecn\u00e9",
    "faq.q1": "Kde s\u00fa ulo\u017een\u00e9 moje d\u00e1ta?",
    "faq.a1": "V\u0161etky va\u0161e medic\u00ednske dokumenty zost\u00e1vaj\u00fa na va\u0161om vlastnom Google Drive. Oncoteam ich \u010d\u00edta a analyzuje, ale nikdy nekop\u00edruje ani neuklad\u00e1 origin\u00e1ly na \u017eiadny extern\u00fd server. Pr\u00edstup m\u00f4\u017eete kedyko\u013evek zru\u0161i\u0165 v nastaven\u00edch Google \u00fa\u010dtu.",
    "faq.q_selfhost": "M\u00f4\u017eem si Oncofiles spusti\u0165 na vlastnom serveri?",
    "faq.a_selfhost": "\u00c1no. <a href=\"https://github.com/peter-fusek/oncofiles\" target=\"_blank\" rel=\"noopener\">Oncofiles je open-source</a> \u2014 m\u00f4\u017eete si ho nasadi\u0165 na vlastn\u00fa infra\u0161trukt\u00faru pre maxim\u00e1lnu kontrolu. Alternat\u00edvne m\u00f4\u017eete pou\u017ei\u0165 spravovan\u00fa in\u0161tanciu, ktor\u00fa prev\u00e1dzkujeme na Railway (infra\u0161trukt\u00fara dostupn\u00e1 v E\u00da, certifik\u00e1cia SOC 2 Type II). Vo\u013eba je v\u017edy va\u0161a: self-hosted pre \u00fapln\u00fa suverenitu, alebo spravovan\u00fd SaaS pre pohodlie. V oboch pr\u00edpadoch va\u0161e dokumenty zost\u00e1vaj\u00fa na va\u0161om Google Drive.",
    "faq.q5": "S\u00fa d\u00e1ta \u0161ifrovan\u00e9?",
    "faq.a5": "\u00c1no. Google Drive \u0161ifruje v\u0161etky s\u00fabory v pokoji aj pri prenose. Komunik\u00e1cia medzi Oncoteam a Google prebieha cez HTTPS. \u017diadne d\u00e1ta sa nepren\u00e1\u0161aj\u00fa ne\u0161ifrovane.",
    "faq.q4": "Kto vid\u00ed moje d\u00e1ta?",
    "faq.a4": "Len vy. Nem\u00e1me pr\u00edstup k v\u00e1\u0161mu Google Drive ani Gmailu. Prihl\u00e1senie prebieha cez ofici\u00e1lny Google OAuth \u2014 nevid\u00edme va\u0161e heslo ani va\u0161e s\u00fabory. Zdrojov\u00fd k\u00f3d je open-source, m\u00f4\u017eete si overi\u0165 v\u0161etko.",
    "faq.q6": "M\u00f4\u017eem odstr\u00e1ni\u0165 pr\u00edstup?",
    "faq.a6": "Kedyko\u013evek. V nastaven\u00edch Google \u00fa\u010dtu (myaccount.google.com) m\u00f4\u017eete jedn\u00fdm klikom odstr\u00e1ni\u0165 pr\u00edstup Oncoteam. Va\u0161e s\u00fabory zost\u00e1vaj\u00fa nedotknut\u00e9.",
    "faq.q2": "U\u010d\u00ed sa AI na mojich d\u00e1tach?",
    "faq.a2_detailed": "Nie. Oncoteam pou\u017e\u00edva <strong>Anthropic API</strong> (nie spotrebite\u013esk\u00fd Claude.ai). <a href=\"https://www.anthropic.com/legal/commercial-terms\" target=\"_blank\" rel=\"noopener\">Obchodn\u00e9 podmienky Anthropic</a> expl\u00edcitne uv\u00e1dzaj\u00fa: <em>\u201eAnthropic may not train models on Customer Content from Services.\u201c</em> To je z\u00e1sadn\u00fd rozdiel oproti spotrebite\u013esk\u00e9mu ChatGPT, ktor\u00fd tr\u00e9nuje na va\u0161ich d\u00e1tach \u0161tandardne. Va\u0161e medic\u00ednske dokumenty sa spracuj\u00fa v re\u00e1lnom \u010dase, nikdy sa neukladaj\u00fa na tr\u00e9ning a automaticky sa zma\u017e\u00fa do 30 dn\u00ed.",
    "faq.q_models": "Ak\u00e9 AI modely spracov\u00e1vaj\u00fa moje d\u00e1ta?",
    "faq.a_models": "Oncoteam pou\u017e\u00edva dva modely od Anthropic, oba cez komer\u010dn\u00e9 API (nulov\u00fd tr\u00e9ning na va\u0161ich d\u00e1tach):<br><br><strong>Claude Haiku 4.5</strong> \u2014 \u013eahk\u00fd model pre r\u00fdchle d\u00e1tov\u00e9 \u00falohy: skenovanie dokumentov, extrakcia laborat\u00f3rnych hodn\u00f4t, parsovanie liekov. Cena: ~$0,80/mili\u00f3n tokenov.<br><br><strong>Claude Sonnet 4.6</strong> \u2014 pokro\u010dil\u00fd model pre: anal\u00fdzu klinick\u00fdch \u0161t\u00fadi\u00ed, lie\u010debn\u00e9 briefy, extrakciu d\u00e1vok z ru\u010dne p\u00edsan\u00fdch pozn\u00e1mok, zhrnutia pre rodinu. Cena: ~$3/mili\u00f3n tokenov.<br><br>Oba modely be\u017eia cez Anthropic API (<a href=\"https://trust.anthropic.com/\" target=\"_blank\" rel=\"noopener\">SOC 2 Type II, ISO 27001</a>). \u017diadne spotrebite\u013esk\u00e9 modely (ChatGPT Free, Claude Free) sa nikdy nepou\u017e\u00edvaj\u00fa.",
    "faq.q_retention": "Ako dlho si Anthropic uchov\u00e1va moje d\u00e1ta?",
    "faq.a_retention": "Vstupy a v\u00fdstupy z API sa <strong>automaticky zma\u017e\u00fa do 30 dn\u00ed</strong>. Toto uchov\u00e1vanie sl\u00fa\u017ei v\u00fdhradne na bezpe\u010dnostn\u00fd monitoring (prevencia zneu\u017eitia), nie na tr\u00e9ning. Anthropic tie\u017e pon\u00faka Zero Data Retention (ZDR) pre enterprise z\u00e1kazn\u00edkov. Detaily: <a href=\"https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data\" target=\"_blank\" rel=\"noopener\">Anthropic Privacy Center</a>. Pre porovnanie, spotrebite\u013esk\u00fd ChatGPT uchov\u00e1va d\u00e1ta neobmedzene, pokia\u013e ich manu\u00e1lne nezma\u017eete.",
    "faq.q_anon": "S\u00fa identity pacientov anonymizovan\u00e9?",
    "faq.a_anon": "\u00c1no. ID pacientov v syst\u00e9me s\u00fa n\u00e1hodn\u00e9 3-znakov\u00e9 k\u00f3dy (nie men\u00e1 \u010di d\u00e1tumy narodenia). \u017diadne osobn\u00e9 \u00fadaje sa nenach\u00e1dzaj\u00fa v premenn\u00fdch prostredia, API k\u013e\u00fa\u010doch ani k\u00f3de. Ka\u017ed\u00fd pacient m\u00e1 dedikovan\u00fd bearer token, ktor\u00fd izoluje jeho d\u00e1ta na \u00farovni datab\u00e1zy.",
    "faq.q_infra": "Kde be\u017e\u00ed Oncoteam?",
    "faq.a_infra": "Oncoteam a Oncofiles be\u017eia na <a href=\"https://railway.com\" target=\"_blank\" rel=\"noopener\">Railway</a> \u2014 cloudovej platforme s certifik\u00e1ciou <strong>SOC 2 Type II</strong> (<a href=\"https://trust.railway.com/\" target=\"_blank\" rel=\"noopener\">Trust Center</a>). Railway pon\u00faka d\u00e1tov\u00e9 centr\u00e1 v Amerike, EMEA a APAC. HIPAA BAA je dostupn\u00e9 na Enterprise pl\u00e1ne. Ak si Oncofiles hostujete sami, infra\u0161trukt\u00faru si vol\u00edte \u00faplne sami.",
    "faq.q_certs": "Ak\u00e9 bezpe\u010dnostn\u00e9 certifik\u00e1cie platia?",
    "faq.a_certs": "<strong>Anthropic</strong> (AI poskytovate\u013e): SOC 2 Type I & II, ISO 27001:2022, ISO 42001:2023 (AI Management), HIPAA BAA dostupn\u00e9. <a href=\"https://trust.anthropic.com/\" target=\"_blank\" rel=\"noopener\">Trust Center</a>.<br><strong>Railway</strong> (hosting): SOC 2 Type II, SOC 3, HIPAA BAA na Enterprise, GDPR DPA dostupn\u00e9. <a href=\"https://trust.railway.com/\" target=\"_blank\" rel=\"noopener\">Trust Center</a>.<br><strong>Google Drive</strong> (\u00falo\u017eisko dokumentov): SOC 2, ISO 27001, HIPAA BAA na Workspace. Va\u0161e s\u00fabory profituj\u00fa z enterprise \u0161ifrovania Google.",
    "faq.q_vs_chatgpt": "Ako sa to l\u00ed\u0161i od vlo\u017eenia v\u00fdsledkov do ChatGPT?",
    "faq.a_vs_chatgpt": "<strong>Z\u00e1sadne.</strong> Ke\u010f vlo\u017e\u00edte laborat\u00f3rne v\u00fdsledky do spotrebite\u013esk\u00e9ho ChatGPT, va\u0161e d\u00e1ta sa \u0161tandardne pou\u017e\u00edvaj\u00fa na tr\u00e9ning modelov, uchov\u00e1vaj\u00fa sa neobmedzene a nemaj\u00fa izol\u00e1ciu pacientov. Oncoteam pou\u017e\u00edva komer\u010dn\u00e9 Anthropic API, kde je tr\u00e9ning na va\u0161ich d\u00e1tach zmluvne zak\u00e1zan\u00fd, uchov\u00e1vanie max 30 dn\u00ed, ka\u017ed\u00fd pacient m\u00e1 izolovan\u00e9 pr\u00edstupov\u00e9 tokeny a cel\u00fd syst\u00e9m je open-source na overenie. Je to rozdiel medzi t\u00fdm, \u010di svoju diagn\u00f3zu kri\u010d\u00edte v dave, alebo sa rozpr\u00e1vate s lek\u00e1rom v s\u00fakromnej ordina\u010dii.",
    "faq.q3": "Nahradzuje Oncoteam m\u00f4jho onkol\u00f3ga?",
    "faq.a3": "Nie. Oncoteam v\u00e1m pom\u00e1ha pripravi\u0165 sa na vy\u0161etrenia, porozumie\u0165 v\u00fdsledkom odberov a n\u00e1js\u0165 relevantn\u00e9 klinick\u00e9 \u0161t\u00fadie. V\u0161etky rozhodnutia o lie\u010dbe by ste mali v\u017edy robi\u0165 so svoj\u00edm onkologick\u00fdm t\u00edmom.",
    "faq.q_opensource": "Pre\u010do je zdrojov\u00fd k\u00f3d otvoren\u00fd?",
    "faq.a_opensource": "Preto\u017ee d\u00f4vera vy\u017eaduje transparentnos\u0165. Ke\u010f ide o va\u0161e zdravotn\u00e9 d\u00e1ta, \u201ever\u0165te n\u00e1m\u201c nesta\u010d\u00ed. Ka\u017ed\u00fd riadok k\u00f3du je na <a href=\"https://github.com/peter-fusek/oncoteam\" target=\"_blank\" rel=\"noopener\">GitHub</a> \u2014 vy (alebo ak\u00fdko\u013evek v\u00fdvoj\u00e1r, ktor\u00e9mu d\u00f4verujete) si m\u00f4\u017eete overi\u0165 presne, \u010do sa s va\u0161imi d\u00e1tami deje. <a href=\"https://github.com/peter-fusek/oncoteam\" target=\"_blank\" rel=\"noopener\">Oncoteam</a> aj <a href=\"https://github.com/peter-fusek/oncofiles\" target=\"_blank\" rel=\"noopener\">Oncofiles</a> s\u00fa plne open-source.",
    "faq.group.ehealth": "Slovensk\u00fd eHealth kontext",
    "faq.q_onkoasist": "Ako s\u00favis\u00ed Oncoteam s OnkoAsistom / NCZI?",
    "faq.a_onkoasist": "<strong>OnkoAsist</strong> je slovensk\u00fd n\u00e1rodn\u00fd eHealth projekt pod vedením <a href=\"https://www.nczisk.sk\" target=\"_blank\" rel=\"noopener\">NCZI</a>. Jeho rozsah je <em>pred-lie\u010debn\u00e1</em> cesta pacienta \u2014 pomoc\u0165 dosta\u0165 pacienta od prv\u00fdch pr\u00edznakov k za\u010diatku lie\u010dby za 60 dn\u00ed miesto 160. Oncoteam pokr\u00fdva druh\u00fa polovicu cesty: <em>od okamihu, ke\u010f lie\u010dba za\u010d\u00edna</em> \u2014 ka\u017ed\u00fd chemo cyklus, laborat\u00f3rny v\u00fdsledok a klinick\u00fa \u0161t\u00fadiu, ktor\u00e1 by mohla pasova\u0165. Odli\u0161n\u00fd rozsah, odli\u0161n\u00fd pou\u017e\u00edvate\u013e, odli\u0161n\u00e9 tempo. Mysl\u00edme si, \u017ee je to dobr\u00fd projekt a ve\u013emi n\u00e1s te\u0161\u00ed, \u017ee \u0161t\u00e1t investuje do prvej polovice cesty.",
    "faq.q_national": "Nahradzuje Oncoteam n\u00e1rodn\u00e9 eHealth syst\u00e9my?",
    "faq.a_national": "Nie. Oncoteam nie je n\u00e1rodnou infra\u0161trukt\u00farou ani registrovanou zdravotn\u00edckou pom\u00f4ckou \u2014 je to n\u00e1stroj pre pacienta a rodinu. Zost\u00e1vame v\u00e9dome pri odpor\u00fa\u010daco-poradnej polohe. N\u00e1rodn\u00e9 syst\u00e9my ako eZdravie, N\u00e1rodn\u00fd onkologick\u00fd register a OnkoAsist maj\u00fa z\u00e1konn\u00e9 mand\u00e1ty, integr\u00e1ciu s eID a v\u00fdmenu d\u00e1t medzi poskytovate\u013emi, \u010do bottom-up n\u00e1stroj nem\u00e1 pre\u010do nahr\u00e1dza\u0165. Ak tieto syst\u00e9my niekedy ponúknu \u0161tandardizovan\u00e9 API, radi by sme do nich posielali pacientmi nahl\u00e1sen\u00e9 v\u00fdstupy (pr\u00edznaky, toxicita, kvalita \u017eivota cez WhatsApp).",
    "journey.title": "Ako Oncoteam zapad\u00e1 do slovensk\u00e9ho eHealthu",
    "journey.subtitle": "Cesta pacienta m\u00e1 ve\u013ea f\u00e1z. My pokr\u00fdvame \u010das medzi n\u00e1v\u0161tevami lek\u00e1ra.",
    "journey.national.label": "N\u00e1rodn\u00fd eHealth (OnkoAsist \u2014 pl\u00e1novan\u00fd)",
    "journey.oncoteam.label": "Oncoteam (dnes \u00fa\u010dinn\u00fd)",
    "journey.phase.symptoms": "Pr\u00edznaky",
    "journey.phase.diagnosis": "Diagn\u00f3za",
    "journey.phase.start": "Za\u010diatok lie\u010dby",
    "journey.phase.cycles": "Akt\u00edvna lie\u010dba",
    "journey.phase.survivorship": "Surveillance",
    "journey.national.title": "N\u00e1rodn\u00e1 infra\u0161trukt\u00fara",
    "journey.national.text": "OnkoAsist (NCZI) je pl\u00e1novan\u00fd slovensk\u00fd n\u00e1rodn\u00fd syst\u00e9m pokr\u00fdvaj\u00faci pred-lie\u010debn\u00fa cestu \u2014 od prv\u00fdch pr\u00edznakov cez diagn\u00f3zu a\u017e po okamih, ke\u010f lie\u010dba za\u010d\u00edna. Cie\u013e: skr\u00e1ti\u0165 \u010das od pr\u00edznaku po lie\u010dbu zo 160 dn\u00ed na 60.",
    "journey.oncoteam.title": "Vrstva pre pacientsk\u00e9ho advocata",
    "journey.oncoteam.text": "Oncoteam pokr\u00fdva opa\u010dn\u00fa polovicu cesty \u2014 od okamihu, ke\u010f lie\u010dba za\u010d\u00edna. Bezpe\u010dnostn\u00e9 checky pred cyklom, anal\u00fdza trendov labov, matching \u0161t\u00fadi\u00ed pod\u013ea biomarkerov a WhatsApp kan\u00e1l pre rodinu. \u00da\u010dinn\u00fd, open-source, traja pacienti v akt\u00edvnom pou\u017e\u00edvan\u00ed.",
    "journey.footer": "Mysl\u00edme si, \u017ee obe polovice s\u00fa d\u00f4le\u017eit\u00e9. Ke\u010f bude OnkoAsist pripraven\u00fd, radi do neho cez \u0161tandardizovan\u00e9 API posielali pacientmi nahl\u00e1sen\u00e9 v\u00fdstupy (pr\u00edznaky z WhatsApp).",
    "stackup.title": "Ako si stoj\u00edme \u2014 \u00faprimne",
    "stackup.subtitle": "Faktick\u00e9 porovnanie so s\u00fa\u010dasn\u00fdmi aj pripravovan\u00fdmi onkologick\u00fdmi platformami v EU a CEE.",
    "stackup.intro": "Mysl\u00edme si, \u017ee \u00faprimn\u00e9 porovnanie zna\u010d\u00ed viac ako marketingov\u00e9 tvrdenia. \u010c\u00edsla a d\u00e1tumy s\u00fa z verejn\u00fdch zdrojov \u2014 tendre, tla\u010dov\u00e9 spr\u00e1vy, ofici\u00e1lne registre \u2014 linkovan\u00e9 v na\u0161om <a href=\"https://github.com/peter-fusek/oncoteam/blob/main/docs/competitive-landscape.md\" target=\"_blank\" rel=\"noopener\">dokumente konkuren\u010dn\u00e9ho prostredia</a>.",
    "stackup.col.platform": "Platforma",
    "stackup.col.status": "Stav (apr\u00edl 2026)",
    "stackup.col.ai": "AI",
    "stackup.col.scope": "Rozsah",
    "stackup.col.funding": "Financovanie a model",
    "stackup.col.access": "Pr\u00edstup pre pacienta",
    "stackup.row.us.status": "\u00da\u010dinn\u00fd \u00b7 3 pacienti \u00b7 v0.80.0",
    "stackup.row.us.ai": "21 Claude agentov",
    "stackup.row.us.scope": "Po\u010das lie\u010dby \u2192 sledovanie",
    "stackup.row.us.funding": "Bootstrap, open-source, zadarmo",
    "stackup.row.us.access": "Samostatn\u00e9 prihl\u00e1senie cez WhatsApp",
    "stackup.row.onkoasist.status": "V tendri od janu\u00e1ra 2023 \u00b7 0 pacientov",
    "stackup.row.onkoasist.ai": "\u017diadna \u2014 klasick\u00e1 SOA",
    "stackup.row.onkoasist.scope": "Pr\u00edznaky \u2192 za\u010diatok lie\u010dby",
    "stackup.row.onkoasist.funding": "7,2 mil. EUR CAPEX, EU fondy (pl\u00e1n)",
    "stackup.row.onkoasist.access": "N\u00e1rodn\u00fd eID port\u00e1l (pl\u00e1n)",
    "stackup.row.kso.status": "\u00da\u010dinn\u00fd \u00b7 apr\u00edl 2025",
    "stackup.row.kso.ai": "\u017diadna",
    "stackup.row.kso.scope": "Koordin\u00e1torom riaden\u00e9 cesty",
    "stackup.row.kso.funding": "Vl\u00e1dne (Fundusze Europejskie)",
    "stackup.row.kso.access": "Odpor\u00fa\u010danie cez koordin\u00e1tora",
    "stackup.row.belong.status": "\u00da\u010dinn\u00fd",
    "stackup.row.belong.ai": "LLM mentor",
    "stackup.row.belong.scope": "Komunita + matching \u0161t\u00fadi\u00ed",
    "stackup.row.belong.funding": "VC \u00b7 freemium",
    "stackup.row.belong.access": "Samostatn\u00e1 aplik\u00e1cia",
    "stackup.row.o4m.status": "\u00da\u010dinn\u00fd \u00b7 380k pou\u017e\u00edvate\u013eov",
    "stackup.row.o4m.ai": "AI (prsn\u00edk + p\u013e\u00faca)",
    "stackup.row.o4m.scope": "Cel\u00e1 cesta, len prsn\u00edk/p\u013e\u00faca",
    "stackup.row.o4m.funding": "$21 mil. Series 2025, closed-source",
    "stackup.row.o4m.access": "Samostatn\u00e1 aplik\u00e1cia (EN + DE)",
    "stackup.row.kaiku.status": "\u00da\u010dinn\u00fd (enterprise)",
    "stackup.row.kaiku.ai": "ePRO anal\u00fdza, bez LLM",
    "stackup.row.kaiku.scope": "ePRO po\u010das lie\u010dby",
    "stackup.row.kaiku.funding": "Elekta enterprise",
    "stackup.row.kaiku.access": "Len cez kontrakt nemocnice",
    "stackup.row.careology.status": "\u00da\u010dinn\u00fd \u00b7 NHS pilot 2025",
    "stackup.row.careology.ai": "\u017diadna",
    "stackup.row.careology.scope": "Sledovanie pr\u00edznakov + wearables",
    "stackup.row.careology.funding": "VC + NHS pilot",
    "stackup.row.careology.access": "Samostatn\u00e1 aplik\u00e1cia (iba anglicky)",
    "stackup.notes.heading": "\u010co hovoria \u010d\u00edsla",
    "stackup.notes.1": "<strong>7,2 mil. EUR CAPEX \u00b7 nula \u017eiv\u00fdch pacientov \u00b7 st\u00e1le v obstar\u00e1van\u00ed od janu\u00e1ra 2023.</strong> To je OnkoAsist \u2014 slovensk\u00fd n\u00e1rodn\u00fd tender pre onkologick\u00fd eHealth. Oncoteam je bootstrapp\u00fd jedno-osobov\u00fd hobby projekt, ktor\u00fd m\u00e1 za sebou 89 sprintov a 3 pacientov v akt\u00edvnom pou\u017e\u00edvan\u00ed. Ke\u010f cez v\u00edkendy kodovan\u00fd open-source n\u00e1stroj predbehne viac ako 7-mili\u00f3nov\u00fa \u0161t\u00e1tnu iniciat\u00edvu pomerom tri \u017eiv\u00ed pacienti ku nula, nie\u010do to o prot\u00edklade top-down obstar\u00e1vania a pacientom riadenej iter\u00e1cie hovor\u00ed.",
    "stackup.notes.2": "<strong>Ani jeden zo skúmanych n\u00e1rodn\u00fdch eHealth projektov nepou\u017e\u00edva AI agentov.</strong> OnkoAsist (SK), KSO (PL), Czech Patient Portal (2026), EESZT (HU), slovinsk\u00fd CRPD \u2014 v\u0161etko klasick\u00e1 SOA s rule-based logikou. Mnoh\u00e9 n\u00e1rodn\u00e9 digit\u00e1lne strat\u00e9gie sa \u0165ahaj\u00fa od 2016 po 2026 a st\u00e1le sp\u00fa\u0161\u0165aj\u00fa pre-AI architekt\u00faru, zatia\u013e \u010do LLM-agent platformy vych\u00e1dzaj\u00fa t\u00fd\u017edenne.",
    "stackup.notes.3": "<strong>Enterprise ePRO vs. samostatn\u00e9 prihl\u00e1senie.</strong> Kaiku Health (Elekta), Noona (Siemens), Moovcare a Resilience PRO vy\u017eaduj\u00fa, aby v\u00e1s zaregistrovala nemocnica alebo onkol\u00f3g. Oncoteam vy\u017eaduje WhatsApp \u010d\u00edslo. In\u00fd go-to-market, in\u00fd pou\u017e\u00edvate\u013e.",
    "stackup.notes.4": "<strong>Unik\u00e1tny priesek Oncoteamu.</strong> \u017diadna in\u00e1 skúmana platforma nepokr\u00fdva v\u0161etk\u00fdch \u0161es\u0165 z t\u00fdchto rozmerov s\u00fa\u010dasne: LLM-agent-native, WhatsApp/hlasov\u00fd kan\u00e1l, open-source, mnohopacientsk\u00fd advocate m\u00f3d, SK+EN viacjazy\u010dnos\u0165, klinick\u00e1 hlbka po\u010das lie\u010dby (pred-cyklick\u00e1 bezpe\u010dnos\u0165, dose modifications, kumulat\u00edvna d\u00e1vka, biomarkerom riaden\u00e9 vyl\u00fa\u010denia).",
    "stackup.footer": "Cel\u00e1 metodol\u00f3gia, v\u0161etk\u00fdch 20+ skúmanych platforiem a ka\u017ed\u00fd zdroj \u017eije v <a href=\"https://github.com/peter-fusek/oncoteam/blob/main/docs/competitive-landscape.md\" target=\"_blank\" rel=\"noopener\">dokumente konkuren\u010dn\u00e9ho prostredia na GitHube</a>. Aktualizujeme ho, ke\u010f sa nie\u010do zmen\u00ed \u2014 pull requesty v\u00edtan\u00e9.",
    "about.title": "Kto je za t\u00fdmto",
    "about.subtitle": "Oncoteam je projektom Instarea \u2014 stav\u00e1 ho ten ist\u00fd t\u00edm, ktor\u00fd 18 rokov dod\u00e1va softv\u00e9rov\u00e9 produkty.",
    "about.stats.years": "rokov na trhu",
    "about.stats.products": "dodan\u00fdch produktov",
    "about.stats.alumni": "alumni",
    "about.stats.specialists": "dedikovan\u00fdch \u0161pecialistov",
    "about.pf.role": "CEO & Zakladate\u013e",
    "about.pf.bio": "S\u00e9riov\u00fd podnikate\u013e a AI stratég. 4 roky v Tatra banke. Co-founder marketlocator (exit do Deutsche Telekom, Deloitte Fast 50, FT 1000). Poradca CEO V\u00daB banky. 18+ rokov buduje technologick\u00e9 produkty.",
    "about.pc.role": "CTO & Co-founder",
    "about.pc.bio": "Senior IT architekt s 20+ rokmi v enterprise bankov\u00edctve (V\u00daB). Expert na .NET, Python, SQL a syst\u00e9mov\u00fa architekt\u00faru. Navrhol architekt\u00faru v\u0161etk\u00fdch produktov Instarea.",
    "about.portfolio.title": "Portf\u00f3lio Instarea \u2014 18 rokov, 23 produktov",
    "about.timeline.early": "telecom expense management, enterprise analytika, mobile-first produkty s integr\u00e1ciou PayPal",
    "about.timeline.marketlocator": "platforma pre monetiz\u00e1ciu geo-dát. Exit do Deutsche Telekom. Deloitte Fast 50, FT 1000.",
    "about.timeline.data": "enterprise d\u00e1tov\u00e9 platformy, booking syst\u00e9my, IoT senzorov\u00e9 siete",
    "about.timeline.dingodot": "PSD2 fintech (vr\u00e1tane Tatra banka PremiumAPI), swipe-sorting, QR platby",
    "about.timeline.aifirst": "AI-first produkty: t\u00edmov\u00e1 optimaliz\u00e1cia, AI prieskumy, equity release",
    "about.timeline.now": "éra AI-first. Oncoteam je jedn\u00fdm zo \u0161iestich produktov v akt\u00edvnom v\u00fdvoji.",
    "about.portfolio.footer": "Cel\u00fd pr\u00edbeh, t\u00edm a referencie na <a href=\"https://www.instarea.com\" target=\"_blank\" rel=\"noopener\">instarea.com</a>.",
    "about.cta": "D\u00f4vera sa rod\u00ed z track-recordu. Ka\u017ed\u00fd produkt vy\u0161\u0161ie je \u017eiv\u00fd, be\u017e\u00ed alebo m\u00e1 \u00faspe\u0161n\u00fd exit \u2014 to je t\u00edm, ktor\u00fd stav\u00e1 oncoteam.",
    "newsletter.heading": "Ostante v obraze",
    "newsletter.sub": "Ob\u010dasn\u00e9 novinky o nov\u00fdch funkci\u00e1ch, klinick\u00fdch protokoloch a vydaniach. \u017diadny spam, odhl\u00e1senie kedyko\u013evek.",
    "footer.rights": "Vytvoren\u00e9 patient advocatom, pre patient advocatov.",
    "footer.disclaimer": "Oncoteam je AI n\u00e1stroj na podporu rozhodovania. Nenahradzuje odborn\u00fa lek\u00e1rsku radu. V\u017edy sa pora\u010fte so svoj\u00edm onkol\u00f3gom o lie\u010debn\u00fdch rozhodnutiach.",
    "footer.instarea": "Projekt spolo\u010dnosti",
    "footer.instarea2": ".",
    "demo.mock.alert": "ANC = 1 150 (prah: 1 500) \u2014 pozastavte chemoterapiu",
    "demo.mock.status": "STAV LIE\u010cBY",
    "demo.mock.cycle": "Cyklus 3 \u00b7 \u0160t\u00e1dium IV mCRC",
    "demo.mock.labs": "POSLEDN\u00c9 V\u00ddSLEDKY",
    "demo.mock.briefing": "Posledn\u00fd AI briefing: EU monitor klinick\u00fdch \u0161t\u00fadi\u00ed \u2014 3 nov\u00e9 zhody...",
    "demo.mock.markers": "N\u00c1DOROV\u00c9 MARKERY \u2014 3 CYKLY",
    "demo.mock.prec1": "Pred C1 (feb)",
    "demo.mock.prec2": "Pred C2 (feb)",
    "demo.mock.prec3": "Pred C3 (mar)",
    "demo.mock.labinsight": "V\u00fdborn\u00e1 odpove\u010f na lie\u010dbu \u2014 CEA klesol o 62 % za 3 cykly",
    "demo.mock.funnel": "LIEVIK KLINICK\u00ddCH \u0160T\u00daDI\u00cd \u2014 AI KLASIFIK\u00c1CIA",
    "demo.mock.excluded": "Vyl\u00fa\u010den\u00e9 <span>20</span>",
    "demo.mock.later": "Neskor\u0161ia l\u00ednia <span>2</span>",
    "demo.mock.watching": "Sledovan\u00e9 <span>14</span>",
    "demo.mock.bev": "Bevacizumab riziko (VTE)",
    "demo.mock.checkpoint": "Checkpoint mono (MSS)",
    "demo.mock.registries": "3L+ registre",
    "demo.mock.pankras": "pan-KRAS \u0161t\u00fadie",
    "demo.mock.ici": "ICI kombin\u00e1cie",
    "demo.mock.funnelinsight": "36 \u0161t\u00fadi\u00ed klasifikovan\u00fdch AI za 15 sek\u00fand \u2014 $0,025 celkom",
    "demo.mock.checklist": "KONTROLN\u00dd ZOZNAM PRED CYKLOM 3 \u2014 mFOLFOX6",
    "demo.mock.anc": "ANC \u2265 1 500/\u00b5L \u2014 <strong>1 150 (POZASTAVENIE)</strong>",
    "demo.mock.plt": "PLT \u2265 75 000/\u00b5L \u2014 269 000",
    "demo.mock.creat": "Kreatinin \u2264 1,5x ULN \u2014 0,42",
    "demo.mock.bili": "Bilirub\u00edn \u2264 1,5x ULN \u2014 norm\u00e1l",
    "demo.mock.protocolinsight": "Predcyklov\u00e1 kontrola: 1 pr\u00edznak vy\u017eaduje pos\u00fadenie lek\u00e1rom pred C3",
    "demo.tab.chat": "Chat",
    "demo.mock.whatsapp": "WHATSAPP",
    "demo.mock.chatreply1": "&#x1F4CA; <strong>Laby (19. mar):</strong> ANC 1 150 &#x2193;, PLT 269k, HGB 118 &#x2191;<br>CEA 733 &#x2193;62 %, CA19-9 22,3k &#x2193;68 %<br><em>ANC pod prahom \u2014 konzultujte s onkol\u00f3gom pred C3</em>",
    "demo.mock.chatq2": "\u010fal\u0161\u00ed cyklus?",
    "demo.mock.chatreply2": "&#x1F4C5; Cyklus 3 mFOLFOX6 \u2014 \u010dak\u00e1 na pos\u00fadenie lek\u00e1rom (ANC pozastavenie).<br>Predcyklov\u00fd kontroln\u00fd zoznam: 1/4 pr\u00edznakov. Op\u00fdtajte sa onkol\u00f3ga na zn\u00ed\u017eenie d\u00e1vky.",
    "demo.mock.claudeai": "CLAUDE.AI (MCP KONEKTOR)",
    "demo.mock.claudeq": "N\u00e1jdi klinick\u00e9 \u0161t\u00fadie pre KRAS G12S mCRC na Slovensku",
    "demo.mock.claudereply": "&#x1F50D; Preh\u013eadan\u00e9 ClinicalTrials.gov + EU registre (SK, CZ, AT, HU).<br><strong>3 zhody:</strong> pan-KRAS inhib\u00edtor (F\u00e1za II, Bratislava), ICI+chemo kombo (F\u00e1za III, Viede\u0148), anti-TIGIT \u0161t\u00fadia (Budape\u0161\u0165).<br><em>V\u0161etky kompatibiln\u00e9 s aktu\u00e1lnym profilom KRAS G12S + akt\u00edvna VTE.</em>"
  }
};

function setLanguage(lang) {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (translations[lang] && translations[lang][key]) {
      el.textContent = translations[lang][key];
    }
  });
  // Static HTML translations for demo mockups (contains entities like &ge; and tags like <strong>).
  // Safe: all values are hardcoded in the translations object above, no user input.
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
    const key = el.getAttribute("data-i18n-html");
    if (translations[lang] && translations[lang][key]) {
      el.innerHTML = translations[lang][key];
    }
  });
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.lang === lang);
  });
  // Pass language to cross-site links (#156)
  document.querySelectorAll('a[href*="oncofiles.com"]').forEach(function(a) {
    var url = new URL(a.href);
    url.searchParams.set("lang", lang);
    a.href = url.toString();
  });
  localStorage.setItem("oncoteam-lang", lang);
  startHeroTypewriter(lang);
}

document.querySelectorAll(".lang-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    setLanguage(btn.dataset.lang);
    // GA4: track language switch
    if (typeof gtag === "function") {
      gtag("event", "language_switch", { language: btn.dataset.lang });
    }
  });
});

// Restore saved language or detect from browser
const saved = localStorage.getItem("oncoteam-lang");
if (saved && translations[saved]) {
  setLanguage(saved);
} else if (navigator.language.startsWith("en")) {
  setLanguage("en");
} else {
  // Default SK — primary audience is Slovak caregivers/patients
  setLanguage("sk");
}

// ── GA4 Custom Events ──────────────────────────────────────────────

// Track CTA and link clicks
document.querySelectorAll("a[href], button").forEach(el => {
  el.addEventListener("click", () => {
    if (typeof gtag !== "function") return;
    const href = el.getAttribute("href") || "";
    const text = el.textContent.trim().slice(0, 50);

    // Hero CTA buttons
    if (el.classList.contains("btn-primary") || el.classList.contains("btn-secondary")) {
      gtag("event", "cta_click", { link_text: text, link_url: href });
    }
    // Contact section links
    if (el.classList.contains("contact-link") || el.classList.contains("story-link")) {
      gtag("event", "contact_click", { link_text: text, link_url: href });
    }
    // Dashboard link
    if (href.includes("dashboard.oncoteam.cloud")) {
      gtag("event", "dashboard_click", { link_text: text });
    }
    // GitHub link
    if (href.includes("github.com")) {
      gtag("event", "github_click", { link_text: text, link_url: href });
    }
  });
});

// Track section visibility (scroll depth)
if ("IntersectionObserver" in window) {
  const sections = document.querySelectorAll("section[id], section[class]");
  const seen = new Set();
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const name = entry.target.id || entry.target.className.split(" ")[0];
      if (seen.has(name)) return;
      seen.add(name);
      if (typeof gtag === "function") {
        gtag("event", "section_view", { section_name: name });
      }
    });
  }, { threshold: 0.3 });
  sections.forEach(s => observer.observe(s));
}

// ── Hero Typewriter Engine ────────────────────────────────────────────

function clearHeroTimers() {
  heroTimers.forEach(t => clearTimeout(t));
  heroTimers = [];
}

function startHeroTypewriter(lang) {
  clearHeroTimers();
  var container = document.getElementById("hero-chat-messages");
  var inputEl = document.getElementById("hero-chat-input-text");
  if (!container || !inputEl) return;

  var conv = heroConversations[lang] || heroConversations.en;

  // prefers-reduced-motion: show static final state
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    while (container.firstChild) container.removeChild(container.firstChild);
    conv.forEach(function(step) {
      var div = document.createElement("div");
      div.className = "wa-msg " + (step.type === "user" ? "wa-msg-user" : "wa-msg-bot");
      div.style.whiteSpace = "pre-line";
      div.textContent = step.text;
      container.appendChild(div);
    });
    return;
  }

  function runLoop() {
    while (container.firstChild) container.removeChild(container.firstChild);
    inputEl.textContent = "";
    var delay = 800;

    conv.forEach(function(step) {
      if (step.type === "user") {
        // Type characters one by one
        var chars = step.text.split("");
        chars.forEach(function(ch, ci) {
          heroTimers.push(setTimeout(function() {
            inputEl.textContent += ch;
          }, delay + ci * 60));
        });
        delay += chars.length * 60 + 300;

        // Move typed text to chat bubble
        heroTimers.push(setTimeout(function() {
          var div = document.createElement("div");
          div.className = "wa-msg wa-msg-user wa-msg-fade";
          div.textContent = step.text;
          container.appendChild(div);
          inputEl.textContent = "";
          container.scrollTop = container.scrollHeight;
        }, delay));
        delay += 400;
      } else {
        // Bot: thinking pause, then fade in
        delay += 600;
        heroTimers.push(setTimeout(function() {
          var div = document.createElement("div");
          div.className = "wa-msg wa-msg-bot wa-msg-fade";
          div.style.whiteSpace = "pre-line";
          div.textContent = step.text;
          container.appendChild(div);
          container.scrollTop = container.scrollHeight;
        }, delay));
        delay += 800;
      }
    });

    // Loop after pause
    heroTimers.push(setTimeout(runLoop, delay + 4000));
  }

  runLoop();
}
