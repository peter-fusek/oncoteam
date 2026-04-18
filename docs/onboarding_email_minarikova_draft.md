# Onboarding email draft — MUDr. Mgr. Zuzana Mináriková, PhD.

**File purpose**: copy-paste-ready draft for the onboarding email. Peter reviews + fills tokens + copies into Gmail composer. Not a Gmail API draft (those carry credential-distribution risk until tokens are real).

---

## ⚠️ TODO before sending

- [ ] Provision tokens: oncoteam #400 + oncofiles #430 must complete first
- [ ] Replace `<ONCOTEAM_TOKEN>` below with the real token from oncoteam #400
- [ ] Replace `<ONCOFILES_TOKEN>` below with the real token from oncofiles #430 (delivered by the oncofiles Claude agent)
- [ ] Confirm her email address — likely @noou.sk institutional OR personal Gmail she uses for professional work — put in the "To:" field in Gmail
- [ ] Fill in `<YOUR_WHATSAPP_NUMBER>` in the Support section (both SK + EN)
- [ ] Spell-check "MUDr. Mgr. Zuzana Mináriková, PhD." in the greeting
- [ ] Decide whether to send bilingual (SK + EN) or SK-only (she's a Slovak clinician; SK-only may feel warmer, EN is a safety net for technical terms)
- [ ] Optional: attach `docs/research_cockpit.md` PDF export (if #399 lives and she wants to preview the UI)
- [ ] Optional: attach `docs/clinical_decision_audit.md` PDF export (once #395 docs land)

## Subject

```
Prístup do oncoteam platformy pre pacientku Erika F. / Oncoteam platform access for patient Erika F.
```

## Body (plain text, paste into Gmail compose)

```
Vážená pani doktorka Mináriková,

ďakujem, že ste súhlasili s odbornou spoluprácou pri klinickom
manažmente pacientky Erika F. V tomto e-maile Vám posielam všetky
prístupové údaje k platforme oncoteam, ktorú som vyvinul na podporu
vyhľadávania klinických štúdií, sledovania laboratórnych trendov
a správy dokumentácie pre Erikinu liečbu.


━━━ Čo je oncoteam ━━━

Oncoteam je asistenčná AI platforma pre onkológov a opatrovateľov.
Mojim cieľom NIE JE nahradiť Vaše klinické rozhodnutia — platforma
slúži ako Váš pomocník pre:

  • automatické vyhľadávanie relevantných klinických štúdií v EU
    (aktuálne zamerané na PARPi / ATRi / pan-RAS inhibítory
    zodpovedajúce Erikinmu onkopanelu)
  • sledovanie trendov onkomarkerov (CEA, CA 19-9) a CBC parametrov
    (Ne/Ly ratio, SII)
  • organizáciu klinickej dokumentácie (GDrive + oncofiles)
  • striktný "human-in-the-loop" audit log — každá zmena v klinickom
    funneli má dôvod, čas a autora


━━━ Vaša rola: klinický konzultant pre pacientku q1b (Erika F.) ━━━

Máte plný prístup k Erikiným dátam. Vaše klinické rozhodnutia
majú prednosť pred AI odporúčaniami. Každá akcia je audit-logovaná
a zálohovaná hodinovo. Nemôžete vidieť dáta iných pacientov —
prísne patient-scoping je vynútené na úrovni tokenov.


━━━ Prístupové údaje ━━━

Dashboard (web):
  URL:             https://dashboard.oncoteam.cloud
  Prihlasovanie:   Google SSO Vašim e-mailom (tým, na ktorý
                   prichádza tento mail)
  Štart. stránka:  /research/inbox (fronta na klinické posúdenie)

MCP token pre oncoteam (pre Vaše ChatGPT alebo Claude.ai):
  Server URL:      https://api.oncoteam.cloud/mcp
  Token:           <ONCOTEAM_TOKEN>
  Rozsah:          len pacientka q1b, read + komentáre

MCP token pre oncofiles (klinické dokumenty Eriky — laby,
zobrazovania, patológie, onkopanely):
  Server URL:      https://oncofiles.com/mcp
  Token:           <ONCOFILES_TOKEN>
  Rozsah:          len dokumenty q1b, read + pridávanie komentárov


━━━ Nastavenie vo Vašom AI nástroji ━━━

V Claude.ai (najspoľahlivejšia MCP podpora) alebo ChatGPT (ak
Váš plán podporuje MCP Connectors):

  1. Otvorte Settings → Connectors / Integrations
  2. Add custom connector → MCP
  3. Vložte Server URL a Token (vyššie)
  4. Uložte. Connector sa automaticky objaví pri ďalšom chat session.
  5. Postup zopakujte aj pre druhý token (oncofiles).

Ak ChatGPT na Vašom pláne aktuálne nepodporuje MCP Connectors,
odporúčam Claude.ai (claude.ai) — podporuje MCP natívne a je
funkčne ekvivalentný.


━━━ Prvé kroky po prihlásení ━━━

  1. Otvorte https://dashboard.oncoteam.cloud/research — nájdete
     pre-pripravené klinické štúdie (PARPi/ATRi/pan-RAS), ktoré
     zodpovedajú Erikinmu onkopanelu (KRAS G12S TIER IA +
     ATM biallelic strata TIER IIC + TP53 splice + MSS +
     TMB-low 6,67 Mut/Mb)
  2. Sekcia Overview ukazuje aktuálne lab trendy a liečebné míľniky
  3. Nastavte Vašu preferovanú klinickú smernicu (ESMO mCRC 2023
     alebo NOÚ lokálna) — AI návrhy budú potom citovať správny zdroj
  4. Prípadne doplňte Vašu osobnú watchlist (štúdie, ktoré chcete
     sledovať nad rámec systémovej watchlist)


━━━ Bezpečnostné odporúčania ━━━

  • Tokeny si uložte do password manageru (1Password / KeePass /
    Bitwarden)
  • Tokeny NEZDIELAJTE — sú osobné a scoped len na Vašu rolu
  • Rotácia tokenov: každých 90 dní (pripomeniem sa)
  • Ak podozrievate kompromitáciu, kontaktujte ma OKAMŽITE —
    revokácia je < 5 minút
  • Dashboard používa HTTPS a prihlásenie len cez Google SSO


━━━ Podpora ━━━

Akékoľvek otázky, chyby, návrhy — napíšte mi kedykoľvek:

  E-mail:       peter.fusek@instarea.sk
  WhatsApp:     <YOUR_WHATSAPP_NUMBER>
  V platforme:  dashboard je live, ale aktívne vyvíjaný — feedback
                je vítaný a realizovaný rýchlo

Teším sa na našu spoluprácu. Ak niečo nefunguje alebo potrebujete
zmenu UX, som v režime "okamžitá reakcia" — oncoteam je tu, aby
Vás podporil, nie naopak.

S úctou,
Peter Fusek


══════════════════════════════════════════════════════════════════
═════════ ENGLISH VERSION BELOW / Anglická verzia nižšie ═════════
══════════════════════════════════════════════════════════════════


Dear Dr. Mináriková,

Thank you for agreeing to clinical collaboration on Erika F.'s
case management. This email provides your full access to the
oncoteam platform, which I've developed to support clinical-trial
discovery, lab-trend monitoring, and document management for her
treatment.


━━━ About oncoteam ━━━

Oncoteam is an AI-assisted clinical support platform for oncologists
and caregivers. My goal is NOT to replace your clinical judgment —
the platform serves as your assistant for:

  • Automated discovery of relevant EU clinical trials (currently
    focused on PARPi / ATRi / pan-RAS inhibitors matching Erika's
    oncopanel)
  • Tumor marker trends (CEA, CA 19-9) and CBC parameter tracking
    (Ne/Ly, SII)
  • Documentation organization (GDrive + oncofiles)
  • Strict human-in-the-loop audit log — every clinical-funnel move
    has a reason, timestamp, and author


━━━ Your role: clinical consultant for patient q1b (Erika F.) ━━━

You have full access to Erika's data. Your clinical decisions
override AI recommendations. Every action is audit-logged and
backed up hourly to GCP. You cannot access other patients' data —
strict patient-scoping is enforced at token level.


━━━ Access credentials ━━━

Dashboard (web):
  URL:           https://dashboard.oncoteam.cloud
  Login:         Google SSO with your email (the one receiving
                 this email)
  Landing page:  /research/inbox (clinical review queue)

MCP token for oncoteam (for your ChatGPT or Claude.ai):
  Server URL:    https://api.oncoteam.cloud/mcp
  Token:         <ONCOTEAM_TOKEN>
  Scope:         q1b only, read + commentary

MCP token for oncofiles (Erika's clinical documents — labs,
imaging, pathology, oncopanels):
  Server URL:    https://oncofiles.com/mcp
  Token:         <ONCOFILES_TOKEN>
  Scope:         q1b documents only, read + add comments


━━━ AI tool setup ━━━

In Claude.ai (most reliable MCP support) or ChatGPT (if your plan
supports MCP Connectors):

  1. Open Settings → Connectors / Integrations
  2. Add custom connector → MCP
  3. Paste Server URL + Token (above)
  4. Save. Connector appears in your next chat session.
  5. Repeat for the second token (oncofiles).

If ChatGPT on your current plan doesn't support MCP Connectors,
I recommend Claude.ai (claude.ai) — native MCP support and
functionally equivalent.


━━━ First steps after login ━━━

  1. Visit https://dashboard.oncoteam.cloud/research — you'll find
     pre-populated clinical trials (PARPi/ATRi/pan-RAS) matching
     Erika's oncopanel (KRAS G12S TIER IA + ATM biallelic loss
     TIER IIC + TP53 splice + MSS + TMB-low 6.67 Mut/Mb)
  2. Overview section shows current lab trends and treatment
     milestones
  3. Set your preferred clinical guideline (ESMO mCRC 2023 or NOÚ
     local) — AI suggestions will then cite the correct source
  4. Optionally add your personal watchlist (trials to monitor
     beyond the system watchlist)


━━━ Security recommendations ━━━

  • Store tokens in a password manager (1Password / KeePass /
    Bitwarden)
  • DO NOT share tokens — they're personal and scoped to your
    role only
  • Token rotation: every 90 days (I'll remind you)
  • If compromise suspected, contact me IMMEDIATELY — revocation
    takes < 5 min
  • Dashboard uses HTTPS and Google SSO authentication only


━━━ Support ━━━

Any questions, bugs, feature requests — contact me anytime:

  Email:         peter.fusek@instarea.sk
  WhatsApp:      <YOUR_WHATSAPP_NUMBER>
  In-platform:   the dashboard is live but under active development
                 — feedback is welcome and implemented quickly

Looking forward to our collaboration. If something doesn't work
or you need a UX change, I'm in "immediate response" mode —
oncoteam is here to support you, not the other way around.

With respect,
Peter Fusek
```

---

## Why a file and not a Gmail draft

Creating this as a file instead of a Gmail API draft:

1. **Tokens don't exist yet** — both oncoteam #400 and oncofiles #430 need to provision tokens first; until then the draft is a shell with placeholders
2. **No accidental send risk** — a Gmail draft can be accidentally sent; a markdown file cannot
3. **Reviewable asynchronously** — you can open it in your editor, refine Slovak phrasing, then copy into Gmail when tokens are ready
4. **Version-controlled** — revisions visible in git history if you tune the language later for other physicians
5. **Audit-friendly** — the onboarding template evolves over time; having it in-repo lets future physician onboardings reuse + adapt

When ready: open Gmail compose, paste subject + body, edit tokens + WhatsApp number + recipient, send.
