const translations = {
  en: {
    "nav.dashboard": "Dashboard",
    "hero.title": "AI-Powered Cancer Treatment Management",
    "hero.subtitle": "An autonomous AI agent that helps patients and caregivers navigate cancer treatment \u2014 from lab results to clinical trials.",
    "hero.cta": "Get in Touch",
    "hero.learn": "Learn More",
    "problem.title": "The Problem",
    "problem.text": "Cancer patients and their families face an overwhelming flood of medical data \u2014 lab results, imaging reports, genetic tests, treatment protocols, clinical trial options. Making sense of it all while fighting the disease is an impossible burden.",
    "solution.title": "Our Solution",
    "solution.text": "Oncoteam is a persistent AI agent that works alongside you. It reads your medical documents, tracks your labs, monitors clinical trials, checks drug interactions, and prepares you for every oncologist visit \u2014 so you can focus on what matters.",
    "features.title": "What Oncoteam Does",
    "features.dashboard.title": "Treatment Dashboard",
    "features.dashboard.text": "All your medical data in one place \u2014 labs, imaging, medications, treatment timeline. Bilingual interface (Slovak/English).",
    "features.labs.title": "Lab Analysis",
    "features.labs.text": "Automated lab result interpretation with reference ranges, trend analysis, inflammation indices (SII, Ne/Ly ratio), and pre-cycle safety checks.",
    "features.trials.title": "Clinical Trial Matching",
    "features.trials.text": "Searches ClinicalTrials.gov and PubMed for trials matching your molecular profile. Checks eligibility based on your biomarkers, prior treatments, and location.",
    "features.agent.title": "Autonomous Agent",
    "features.agent.text": "Runs autonomously to scan new documents, extract data, update your treatment timeline, and flag anything that needs attention \u2014 even when you\u2019re not looking.",
    "features.protocol.title": "Protocol Tracking",
    "features.protocol.text": "Embedded clinical protocol with dose modification rules, cumulative dose thresholds, toxicity grading, and cycle delay criteria.",
    "features.euTrials.title": "EU-Wide Trial Search",
    "features.euTrials.text": "Monitors clinical trials across 14 European countries \u2014 from Vienna to Barcelona. Prioritized by travel distance, checked every 6 hours.",
    "features.whatsapp.title": "Proactive WhatsApp Alerts",
    "features.whatsapp.text": "Safety alerts, weekly briefings, and trial updates delivered to your phone via WhatsApp \u2014 so nothing critical gets missed.",
    "features.dictionary.title": "Medical Dictionary",
    "features.dictionary.text": "Built-in bilingual dictionary with professional and plain-language explanations of every medical term. Searchable from any page.",
    "features.mcp.title": "MCP-Native Architecture",
    "features.mcp.text": "Built on the Model Context Protocol \u2014 open, interoperable, and designed to work with any AI assistant. Your data stays yours.",
    "how.title": "How It Works",
    "how.step1.title": "Connect Your Documents",
    "how.step1.text": "Upload lab results, pathology reports, imaging, and genetic tests to your secure Google Drive folder.",
    "how.step2.title": "AI Reads & Understands",
    "how.step2.text": "Oncoteam extracts structured data, identifies biomarkers, tracks trends, and builds your complete treatment profile.",
    "how.step3.title": "Stay Informed & Prepared",
    "how.step3.text": "Get daily briefings, pre-cycle checklists, trial recommendations, and safety alerts \u2014 via dashboard and WhatsApp, backed by your actual data.",
    "tech.title": "Built With",
    "contact.title": "Get in Touch",
    "contact.subtitle": "Oncoteam is currently in active development for a real patient. If you\u2019re interested in learning more or collaborating, reach out.",
    "privacy.title": "Privacy & Data Protection",
    "privacy.gdpr.title": "GDPR Compliant",
    "privacy.gdpr.text": "All patient data is processed in compliance with the EU General Data Protection Regulation. Data is encrypted at rest and in transit.",
    "privacy.ownership.title": "Your Data, Your Control",
    "privacy.ownership.text": "Patient documents are stored in your own Google Drive. Oncoteam reads and processes data but never stores originals outside your control.",
    "privacy.access.title": "Controlled Access",
    "privacy.access.text": "Multi-layer authentication: Google OAuth, API bearer tokens, and MCP server authentication. No unauthorized access to patient data.",
    "privacy.audit.title": "Full Audit Trail",
    "privacy.audit.text": "Every data access, AI decision, and document interaction is logged. Complete transparency for patients and caregivers.",
    "footer.rights": "Built with care for cancer patients and their families.",
    "footer.disclaimer": "Oncoteam is an AI-powered decision support tool. It does not replace professional medical advice. Always consult your oncologist for treatment decisions."
  },
  sk: {
    "nav.dashboard": "Dashboard",
    "hero.title": "AI spr\u00e1va onkologickej lie\u010dby",
    "hero.subtitle": "Auton\u00f3mny AI agent, ktor\u00fd pom\u00e1ha pacientom a ich bl\u00edzkym orientova\u0165 sa v onkologickej lie\u010dbe \u2014 od laborat\u00f3rnych v\u00fdsledkov po klinick\u00e9 \u0161t\u00fadie.",
    "hero.cta": "Kontaktujte n\u00e1s",
    "hero.learn": "Zisti\u0165 viac",
    "problem.title": "Probl\u00e9m",
    "problem.text": "Onkologick\u00ed pacienti a ich rodiny \u010delia z\u00e1plave medic\u00ednskych d\u00e1t \u2014 laborat\u00f3rne v\u00fdsledky, zobrazovacie spr\u00e1vy, genetick\u00e9 testy, lie\u010debn\u00e9 protokoly, mo\u017enosti klinick\u00fdch \u0161t\u00fadi\u00ed. Zorientova\u0165 sa v tom v\u0161etkom po\u010das boja s chorobou je ne\u00fanosn\u00e1 z\u00e1\u0165a\u017e.",
    "solution.title": "Na\u0161e rie\u0161enie",
    "solution.text": "Oncoteam je perzistentn\u00fd AI agent, ktor\u00fd pracuje po va\u0161om boku. \u010c\u00edta va\u0161e medic\u00ednske dokumenty, sleduje laborat\u00f3rne v\u00fdsledky, monitoruje klinick\u00e9 \u0161t\u00fadie, kontroluje liekov\u00e9 interakcie a priprav\u00ed v\u00e1s na ka\u017ed\u00fa n\u00e1v\u0161tevu onkol\u00f3ga.",
    "features.title": "\u010co Oncoteam rob\u00ed",
    "features.dashboard.title": "Dashboard lie\u010dby",
    "features.dashboard.text": "V\u0161etky va\u0161e medic\u00ednske d\u00e1ta na jednom mieste \u2014 laborat\u00f3rne v\u00fdsledky, zobrazovanie, lieky, \u010dasov\u00e1 os lie\u010dby. Dvojjazy\u010dn\u00e9 rozhranie (sloven\u010dina/angli\u010dtina).",
    "features.labs.title": "Anal\u00fdza laborat\u00f3rnych v\u00fdsledkov",
    "features.labs.text": "Automatick\u00e1 interpret\u00e1cia laborat\u00f3rnych v\u00fdsledkov s referen\u010dn\u00fdmi rozp\u00e4tiami, anal\u00fdzou trendov, z\u00e1palov\u00fdmi indexmi (SII, Ne/Ly) a predcyklovou bezpe\u010dnostnou kontrolou.",
    "features.trials.title": "H\u013eadanie klinick\u00fdch \u0161t\u00fadi\u00ed",
    "features.trials.text": "Vyh\u013ead\u00e1va na ClinicalTrials.gov a PubMed \u0161t\u00fadie zodpovedaj\u00face v\u00e1\u0161mu molekul\u00e1rnemu profilu. Overuje sp\u00f4sobilo\u0165 pod\u013ea biomarkerov, predch\u00e1dzaj\u00facej lie\u010dby a lokality.",
    "features.agent.title": "Auton\u00f3mny agent",
    "features.agent.text": "Pracuje auton\u00f3mne \u2014 skenuje nov\u00e9 dokumenty, extrahuje d\u00e1ta, aktualizuje \u010dasov\u00fa os lie\u010dby a upozor\u0148uje na v\u0161etko d\u00f4le\u017eit\u00e9, aj ke\u010f sa pr\u00e1ve nepozer\u00e1te.",
    "features.protocol.title": "Sledovanie protokolu",
    "features.protocol.text": "Vlo\u017een\u00fd klinick\u00fd protokol s pravidlami modifik\u00e1cie d\u00e1vok, kumulat\u00edvnymi prahmi, hodnoteniami toxicity a krit\u00e9riami odkladu cyklu.",
    "features.euTrials.title": "Vyh\u013ead\u00e1vanie \u0161t\u00fadi\u00ed v cel\u00e9 E\u00da",
    "features.euTrials.text": "Monitoruje klinick\u00e9 \u0161t\u00fadie v 14 eur\u00f3pskych krajin\u00e1ch \u2014 od Viedne po Barcelonu. Prioritizovan\u00e9 pod\u013ea vzdialenosti, kontrolovan\u00e9 ka\u017ed\u00fdch 6 hod\u00edn.",
    "features.whatsapp.title": "Proakt\u00edvne WhatsApp upozornenia",
    "features.whatsapp.text": "Bezpe\u010dnostn\u00e9 upozornenia, t\u00fd\u017edenn\u00e9 briefingy a aktualiz\u00e1cie \u0161t\u00fadi\u00ed priamo na v\u00e1\u0161 telef\u00f3n cez WhatsApp \u2014 aby ni\u010d d\u00f4le\u017eit\u00e9 neu\u0161lo.",
    "features.dictionary.title": "Medic\u00ednsky slovn\u00edk",
    "features.dictionary.text": "Vstavan\u00fd dvojjazy\u010dn\u00fd slovn\u00edk s odborn\u00fdm aj zrozumite\u013en\u00fdm vysvetlen\u00edm ka\u017ed\u00e9ho medic\u00ednskeho pojmu. Vyh\u013eadavate\u013en\u00fd z ka\u017edej str\u00e1nky.",
    "features.mcp.title": "MCP-nat\u00edvna architekt\u00fara",
    "features.mcp.text": "Postaven\u00fd na Model Context Protocol \u2014 otvoren\u00fd, interoperabiln\u00fd, navrhnut\u00fd pre spolupr\u00e1cu s ak\u00fdmko\u013evek AI asistentom. Va\u0161e d\u00e1ta zost\u00e1vaj\u00fa va\u0161e.",
    "how.title": "Ako to funguje",
    "how.step1.title": "Pripojte dokumenty",
    "how.step1.text": "Nahrajte laborat\u00f3rne v\u00fdsledky, patologick\u00e9 spr\u00e1vy, zobrazovanie a genetick\u00e9 testy do v\u00e1\u0161ho zabezpe\u010den\u00e9ho prie\u010dinka na Google Drive.",
    "how.step2.title": "AI \u010d\u00edta a rozumie",
    "how.step2.text": "Oncoteam extrahuje \u0161trukt\u00farovan\u00e9 d\u00e1ta, identifikuje biomarkery, sleduje trendy a buduje v\u00e1\u0161 kompletn\u00fd lie\u010debn\u00fd profil.",
    "how.step3.title": "Bu\u010fte informovan\u00ed a pripraven\u00ed",
    "how.step3.text": "Dostanete denn\u00e9 brie\u017eingy, predcyklov\u00e9 kontroln\u00e9 zoznamy, odpor\u00fa\u010dania \u0161t\u00fadi\u00ed a bezpe\u010dnostn\u00e9 upozornenia \u2014 cez dashboard aj WhatsApp, podlo\u017een\u00e9 va\u0161imi d\u00e1tami.",
    "tech.title": "Postaven\u00e9 na",
    "contact.title": "Kontakt",
    "contact.subtitle": "Oncoteam je akt\u00edvne vyv\u00edjan\u00fd pre re\u00e1lneho pacienta. Ak v\u00e1s zauj\u00edma viac alebo chcete spolupracova\u0165, nap\u00ed\u0161te n\u00e1m.",
    "privacy.title": "S\u00fakromie a ochrana \u00fadajov",
    "privacy.gdpr.title": "S\u00falad s GDPR",
    "privacy.gdpr.text": "V\u0161etky \u00fadaje pacientov s\u00fa sprac\u00favan\u00e9 v s\u00falade so v\u0161eobecn\u00fdm nariaden\u00edm E\u00da o ochrane \u00fadajov. D\u00e1ta s\u00fa \u0161ifrovan\u00e9 pri ulo\u017een\u00ed aj prenose.",
    "privacy.ownership.title": "Va\u0161e d\u00e1ta, va\u0161a kontrola",
    "privacy.ownership.text": "Dokumenty pacientov s\u00fa ulo\u017een\u00e9 na va\u0161om vlastnom Google Drive. Oncoteam \u010d\u00edta a spracov\u00e1va d\u00e1ta, ale nikdy neuklad\u00e1 origin\u00e1ly mimo va\u0161ej kontroly.",
    "privacy.access.title": "Kontrolovan\u00fd pr\u00edstup",
    "privacy.access.text": "Viacvrstvov\u00e1 autentifik\u00e1cia: Google OAuth, API bearer tokeny a autentifik\u00e1cia MCP servera. \u017diadny neopr\u00e1vnen\u00fd pr\u00edstup k \u00fadajom pacienta.",
    "privacy.audit.title": "Kompletn\u00fd audit trail",
    "privacy.audit.text": "Ka\u017ed\u00fd pr\u00edstup k d\u00e1tam, rozhodnutie AI a interakcia s dokumentom je zaznamenan\u00e1. \u00dapln\u00e1 transparentnos\u0165 pre pacientov a o\u0161etrovate\u013eov.",
    "footer.rights": "Vytvoren\u00e9 s l\u00e1skou pre onkologick\u00fdch pacientov a ich rodiny.",
    "footer.disclaimer": "Oncoteam je AI n\u00e1stroj na podporu rozhodovania. Nenahradzuje odborn\u00fa lek\u00e1rsku radu. V\u017edy sa pora\u010fte so svoj\u00edm onkol\u00f3gom o lie\u010debn\u00fdch rozhodnutiach."
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
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.lang === lang);
  });
  localStorage.setItem("oncoteam-lang", lang);
}

document.querySelectorAll(".lang-btn").forEach(btn => {
  btn.addEventListener("click", () => setLanguage(btn.dataset.lang));
});

// Restore saved language or detect from browser
const saved = localStorage.getItem("oncoteam-lang");
if (saved && translations[saved]) {
  setLanguage(saved);
} else if (navigator.language.startsWith("sk")) {
  setLanguage("sk");
}
