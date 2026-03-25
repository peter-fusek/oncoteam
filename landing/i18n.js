const translations = {
  en: {
    "nav.dashboard": "Dashboard",
    "hero.title": "When someone you love has cancer, you become their advocate.",
    "hero.subtitle": "Oncoteam helps you understand the treatment, ask the right questions, find clinical trials, and make sure nothing gets overlooked \u2014 all from your phone.",
    "hero.badge": "Open Source \u00b7 Used in Active Treatment",
    "hero.cta": "Open Dashboard",
    "hero.github": "View on GitHub",
    "hero.learn": "Why You Need This",
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
    "stats.agents": "AI Agents Working for You",
    "stats.tasks": "Tasks per Patient per Week",
    "stats.trials": "Clinical Trials Monitored",
    "stats.roles": "Specialist Roles",
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
    "gs.whatsapp.text": " Message us on WhatsApp and we\u2019ll walk you through setup.",
    "gs.whatsapp.btn": "WhatsApp",
    "gs.free.badge": "Free during active treatment",
    "gs.free.docs": "medical documents",
    "gs.free.queries": "AI queries / month",
    "gs.free.agents": "autonomous agent runs / month",
    "gs.free.note": "These limits are yours and we won\u2019t reduce them. We don\u2019t have a commercial model yet \u2014 our priority is the patient and getting the product right, not monetization. If that ever changes, you\u2019ll be the first to know.",
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
    "hero.title": "Ke\u010f m\u00e1 v\u00e1\u0161 bl\u00edzky rakovinu, st\u00e1vate sa jeho hlavn\u00fdm spojencom.",
    "hero.subtitle": "Oncoteam v\u00e1m pom\u00f4\u017ee porozumie\u0165 lie\u010dbe, kl\u00e1s\u0165 spr\u00e1vne ot\u00e1zky, n\u00e1js\u0165 klinick\u00e9 \u0161t\u00fadie a ma\u0165 istotu, \u017ee sa ni\u010d neprehliadlo \u2014 v\u0161etko z v\u00e1\u0161ho telef\u00f3nu.",
    "hero.badge": "Open Source \u00b7 Pou\u017e\u00edvan\u00e9 v akt\u00edvnej lie\u010dbe",
    "hero.cta": "Otvori\u0165 Dashboard",
    "hero.github": "Zobrazi\u0165 na GitHub",
    "hero.learn": "Pre\u010do to potrebujete",
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
    "stats.agents": "AI agentov pracuje pre v\u00e1s",
    "stats.tasks": "\u00faloh na pacienta t\u00fd\u017edenne",
    "stats.trials": "sledovan\u00fdch klinick\u00fdch \u0161t\u00fadi\u00ed",
    "stats.roles": "odborn\u00fdch rol\u00ed",
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
    "gs.whatsapp.text": " Nap\u00ed\u0161te n\u00e1m na WhatsApp a prevedieme v\u00e1s nastaven\u00edm.",
    "gs.whatsapp.btn": "WhatsApp",
    "gs.free.badge": "Zadarmo po\u010das akt\u00edvnej lie\u010dby",
    "gs.free.docs": "medic\u00ednskych dokumentov",
    "gs.free.queries": "AI dotazov / mesiac",
    "gs.free.agents": "auton\u00f3mnych agentov / mesiac",
    "gs.free.note": "Tieto limity s\u00fa va\u0161e a nebudeme v\u00e1m ich zni\u017eova\u0165. Komer\u010dn\u00fd model zatia\u013e nem\u00e1me \u2014 prioritou je pacient a vyladenie produktu, nie monetiz\u00e1cia. Ke\u010f sa to zmen\u00ed, dozviete sa to ako prv\u00ed.",
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
} else if (navigator.language.startsWith("sk")) {
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
