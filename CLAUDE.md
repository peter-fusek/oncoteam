# oncoteam

Persistent AI agent for cancer treatment management. Searches PubMed and ClinicalTrials.gov, checks trial eligibility, tracks treatment data. All persistence goes through oncofiles MCP.

## Quick start

```bash
uv sync --extra dev
uv run pytest          # 744 tests
uv run ruff check
uv run oncoteam-mcp    # stdio mode
```

## Project structure

- `src/oncoteam/server.py` — MCP server, 26 tools + dashboard API route registration, system instructions with biomarker rules + QA protocol
- `src/oncoteam/dashboard_api.py` — Dashboard JSON API: clinical handlers (timeline, labs, protocol, patient, research, sessions, briefings, toxicity, medications, etc.) + shared infrastructure (auth, caching, rate limiting, CORS)
- `src/oncoteam/api_whatsapp.py` — WhatsApp handlers: log, chat, resolve-patient, media, voice, history, status + thread memory + approved phones
- `src/oncoteam/api_agents.py` — Agent/autonomous handlers: autonomous status/cost, agent list/config/runs, diagnostics
- `src/oncoteam/api_webhooks.py` — Webhook handlers: bug-report, document-webhook, trigger-agent
- `src/oncoteam/api_admin.py` — Admin handlers: patients, onboard-patient, approve-user, access-rights
- `src/oncoteam/api_research.py` — Research handlers: research list, assess-funnel, funnel-stages GET/POST
- `src/oncoteam/request_context.py` — Request-scoped utilities: correlation ID, patient token resolution (extracted to break circular imports)
- `src/oncoteam/clinical_protocol.py` — Embedded clinical protocol: lab thresholds, reference ranges, dose mods, cumulative dose thresholds, cycle delay rules, nutrition escalation, milestones, safety flags, 2L options
- `src/oncoteam/autonomous.py` — Claude API autonomous agent loop with extended thinking
- `src/oncoteam/autonomous_tasks.py` — 24 autonomous task wrappers + document pipeline orchestrator with cooldown guards and WhatsApp notifications (count matches agent_registry.py; update both when adding agents)
- `src/oncoteam/agent_registry.py` — AgentConfig Pydantic model, all 24 agent definitions + document_pipeline, schedule/cooldown/model config
- `src/oncoteam/tags.py` — Canonical tag vocabulary with prefix:value format (sys:, clin:, bio:, tx:, res:, task:, safety:, src:)
- `src/oncoteam/activity_logger.py` — @log_activity decorator, suppressed error buffer, diary helpers
- `src/oncoteam/eligibility.py` — biomarker-aware trial eligibility checker
- `src/oncoteam/github_client.py` — GitHub REST API for issue creation
- `src/oncoteam/clinicaltrials_client.py` — ClinicalTrials.gov API v2
- `src/oncoteam/pubmed_client.py` — PubMed/NCBI E-utilities
- `src/oncoteam/oncofiles_client.py` — Oncofiles MCP client (StreamableHttpTransport)
- `src/oncoteam/patient_context.py` — Patient profile, research terms, biomarker data
- `src/oncoteam/models.py` — Pydantic models
- `src/oncoteam/config.py` — Environment variable configuration
- `tests/` — pytest tests with respx mocks
- `landing/` — Static landing page (nginx, Railway). robots.txt, sitemap.xml, llms.txt, og-image.png
- `dashboard/` — Nuxt 4 dashboard (SSR, Railway). `dashboard.oncoteam.cloud`

## Conventions

- Python 3.12+, async-first
- FastMCP 3.0+ for MCP server
- Pydantic for data models
- httpx for async HTTP (PubMed, ClinicalTrials.gov, GitHub)
- No local database — all persistence via oncofiles MCP
- ruff for linting/formatting
- All suppressed exceptions must call `record_suppressed_error()` for QA visibility

### Architectural invariant — oncoteam boots independently of oncofiles

**Critical invariant** (established after #431 / 2026-04-23 cascade incident): oncoteam MUST boot + serve `/health` 200 within 10 seconds of process start, regardless of oncofiles state. `server._run_http` MUST NOT `await` any oncofiles-touching coroutine before `mcp.run_async()`. Use `asyncio.create_task(_safe_bg(...))` for background loads (see commit b083479 for the pattern). CI chaos drill in `.github/workflows/ci.yml` `chaos-oncofiles-down` asserts this invariant — any PR that re-introduces a startup coupling fails there. Full postmortem: `docs/incidents/2026-04-23-oncofiles-cascade.md`.

### Gotchas (from real incidents)

- Protocol cache (`_protocol_cache` dict in `dashboard_api.py`) must be cleared in tests: add `@pytest.fixture(autouse=True) def _clear_protocol_cache()` to any test module touching `/api/protocol`
- `lru_cache` on `_resolve_protocol_cached(lang)` — call `_resolve_protocol_cached.cache_clear()` in tests, not just the dict
- `dashboard_api.py` parallel MCP fetches use `asyncio.gather` with 2s per-task timeout — add mocks for ALL gathered calls in tests or they'll fail
- Nuxt `useFetch` query must use `computed()` (not plain object) for locale-reactive API calls
- Nuxt `useFetch` keeps old `data` ref during refetch — `clearFetch()`, `watch:false+refresh()`, `dedupe:'cancel'` all fail to prevent stale data. For instant UI filtering (e.g., category chips), use **client-side computed filtering** on already-loaded data instead of triggering a server refetch.
- Dashboard uses **light theme** (colorMode: 'light') with CSS custom properties in `main.css` (--clinical-bg, --clinical-surface, etc.). DM Sans body + DM Serif Display headers. Gamification (XP, levels, streaks) was fully removed.
- Dashboard **navigation** uses 4 grouped sections: Overview (Home, Patient, Timeline), Treatment (Protocol, Labs, Toxicity, Medications, Prep), Intelligence (Briefings, Research, Family Update, Dictionary), Operations (Agents, Prompts, Sessions, Documents). Sidebar defined in `layouts/default.vue` as `navigationSections` computed. Agents page is at `/agents` (NOT the index).
- Dashboard **Home page** (`/`) fetches `/patient`, `/labs?limit=50`, `/briefings?limit=1`, `/timeline?limit=10` in parallel. Lab values merged across entries via `mergedLabSnapshot` computed (tumor markers and hematology often on different dated entries). Alerts collected from ALL entries via `flatMap`.
- `api_labs` enrichment from `get_lab_trends_data` triggers when ANY event has empty metadata (`has_empty`). This is needed because `lab_sync` agent often creates events with empty metadata (values in notes only). The merge logic at line 1930 only backfills events that lack metadata, so already-populated events are untouched. The 15s latency concern is mitigated by the 60s `_labs_cache` TTL — the expensive call runs at most once per minute per patient.
- `oncofiles_client.py` uses a persistent module-level MCP client singleton — `_get_client()` / `_invalidate_client()`. Tests mock wrapper functions (e.g. `oncofiles_client.list_treatment_events`), not `call_oncofiles` directly.
- `import collections` is at top of `dashboard_api.py`; rate limiter uses `collections.deque` — don't add a second import mid-file (E402)
- `landing/Dockerfile` must explicitly COPY every static file — new files (robots.txt, llms.txt, og-image.png) won't be served unless added to COPY line
- `autonomous.py` stores `prompt` (task_prompt) in result dict → persisted in run traces via `_log_task()`. The `api_agent_runs` endpoint returns full prompt + response without truncation.
- `autonomous_tasks._log_task()` stores agent_run entries with enriched tags: `cost:{cost},tools:{n},model:{model},dur:{ms}`. The `api_agent_runs` and `api_agent_runs_all` list views use `_parse_agent_run_entry()` helper to parse tags — never fetches full content (oncofiles `get_conversation` is too slow for list views).
- Dashboard proxy timeout (`dashboard/server/api/oncoteam/[...path].ts`) is 25s. Oncofiles MCP `search_conversations` takes ~15s per query — don't reduce below 20s.
- `document_pipeline` agent in registry has `schedule_params={"hours": 999}` — never fires on schedule. It's event-driven only, triggered by `POST /api/internal/document-webhook`.
- `api_document_webhook` accepts `patient_id` in JSON body (defaults to "q1b"). Must pass `patient_id` from oncofiles — without it, all documents are processed under q1b's context.
- `view_document` MCP tool accepts both `file_id` (string) and `document_id` (int). Numeric IDs are auto-resolved to `file_id` via `get_document()`. Haiku agents consistently use `document_id` param name despite prompts — the dual-param support is required.
- Single-doc pipeline agents (`file_scan_single`, `lab_sync_single`, `dose_extraction_single`, etc.) accept `file_id` kwarg. The pipeline resolves `file_id` once via `_resolve_file_id()` before dispatching downstream.
- `api_document_webhook` imports `_get_state`, `_extract_timestamp`, `run_document_pipeline` lazily from `autonomous_tasks` — test patches must target `oncoteam.autonomous_tasks`, not `oncoteam.dashboard_api`.
- `api_trigger_agent` clears cooldown state before triggering — imports `_get_task_functions` from `scheduler.py`. Same lazy-import pattern as webhook.
- Agent registry `model` field is display-only — the actual model override is in each `run_*()` function's `run_autonomous_task()` call. If you change model in registry, also update the corresponding `run_*()` function.
- `AUTONOMOUS_COST_LIMIT` default is $10 (temporary, target $5 after monitoring period ~2026-03-28)
- `_CONTAMINATED_EVENT_IDS` in `dashboard_api.py` filters known bad data (IDs 19-21: placeholder labs 100x too low, ID 32: duplicate of 27). Tests must not use these IDs.
- `_normalize_lab_values()` converts G/L → /µL for ANC (<30), PLT (<1000), ABS_LYMPH (<30), and maps HGB→hemoglobin
- `api_labs` outlier detection flags CEA/CA_19_9 entries with >90% single-reading change as `suspects[]`
- `oncofiles_client.py` has circuit breaker (5 fails → 30s cooldown), 20s per-call timeout, 0.5s retry backoff. `get_circuit_breaker_status()` exposes state for health endpoints. **Since #424**: local breaker only trips when the exception string matches an upstream-open signal (`"Circuit breaker open"` / `"Database briefly unavailable"`) via `_parse_upstream_breaker_signal()`. Generic timeouts / transient 5xx are retried within the attempt budget but do NOT increment the breaker — that was the double-breaker amplification that produced false "Database under load" banners. Upstream `retry in {N}s` hint drives local cooldown instead of fixed 30s.
- `oncofiles_client.py` concurrency: max 3 parallel calls (semaphore), heavy queries (`search_conversations`, `search_documents`) max 1 concurrent. `SEMAPHORE_WAIT_TIMEOUT=8s` rejects requests that can't acquire a slot (prevents zombie queue buildup from proxy-cancelled requests).
- `oncofiles_client.py` RSS backoff: checks oncofiles `/health` every 60s (throttled). RSS >= 400MB → 30s backoff, >= 450MB → 2min. Don't reduce `RSS_CHECK_INTERVAL` below 30s — per-call health checks cause dashboard proxy timeouts.
- Oncofiles `/health` includes `folder_404_suspended` when a patient's GDrive sync is paused (3 consecutive 404s). If WhatsApp reports "System Resource Constraint", check oncofiles RSS and `folder_404_suspended` first — a bad folder ID can cascade to full system degradation.
- `api_whatsapp_chat` checks circuit breaker before calling Claude API — returns clear Slovak/English message if oncofiles is down, saving API cost.
- Agent schedules are staggered to avoid morning pile-on: weekly_briefing 05:00, daily_cost 06:00, trial_monitor 07:45, daily_research 09:00, protocol_review Wed 11:30. Don't cluster agents within 30min of each other.
- WhatsApp chat tests must mock `oncofiles_client.get_circuit_breaker_status` (return `{"state": "closed"}`).
- Don't wrap `asyncio.gather(return_exceptions=True)` with `asyncio.wait_for` — timeout cancels ALL tasks, defeating partial results. Individual `call_oncofiles` already has 20s timeout.
- `api_health_deep` and `api_diagnostics` include `circuit_breaker` status. Tests mocking diagnostics must also mock `get_circuit_breaker_status`.
- RSS memory: `resource.getrusage` returns bytes on macOS, KB on Linux — use `sys.platform == "darwin"` check
- WhatsApp conversational (non-command) messages use async pattern: immediate "Premýšľam..." TwiML, then Claude response via Twilio REST API. Commands (labky, lieky, etc.) respond synchronously.
- `whatsapp-commands.ts` has 20 commands (17 SK + 20 EN aliases). Sub-command routing: `parseSubCommand()` extracts `{commandWord, subarg}`. Labs support filtering (cea/krv/pecen) and pagination (labky 2).
- `splitMessage()` splits long responses on `\n\n` boundaries (max 3 segments, 1500 chars each). Multi-segment: first via TwiML, rest via Twilio REST with 150ms delay.
- `CommandResult` union has 3 types: `reply` (single sync), `multi` (multi-segment sync), `async` (Claude conversational).
- WhatsApp conversation memory: `_load_wa_thread()` / `_save_wa_thread()` in `dashboard_api.py`. Keyed by `wa_thread:{patient_id}:{sha256(phone)[:12]}` in oncofiles agent_state — patient-scoped to prevent cross-patient context bleed. 2h TTL, max 5 exchanges, 3s non-blocking timeout. Tests must mock both `_load_wa_thread` and `_save_wa_thread`.
- `NUXT_TWILIO_WHATSAPP_FROM` env var may include `whatsapp:` prefix — code handles both formats to prevent double-wrapping.
- Multi-patient: `patient_context.py` has `PatientRegistry` (in-memory dict), `get_patient(patient_id)`, `register_patient()`, `build_system_prompt(patient_id)`. Erika is `patient_id="q1b"`. Oncofiles bearer token scopes data per-patient — no need to pass patient_id to oncofiles calls.
- `run_autonomous_task()` accepts `patient_id` param — uses `build_system_prompt(patient_id)` instead of hardcoded `AUTONOMOUS_SYSTEM_PROMPT`.
- Dashboard `useActivePatient` composable tracks active patient. `useOncoteamApi` includes `patient_id` in all API queries. Patient switcher in sidebar (advocate-only, activates when >1 patient).
- **NEVER apply Erika's biomarker rules (KRAS G12S, anti-EGFR excluded) to other patients** — each patient has different cancer type, biomarkers, drug contraindications. Use `build_biomarker_rules(patient)` to generate per-patient rules.


- `dashboard/server/api/oncoteam/[...path].ts` has session auth guard — `getUserSession()` check returns 401 for unauthenticated requests. All API calls go through this proxy.
- All dashboard pages use `{ lazy: true, server: false }` in `fetchApi` — SSR renders shell only, data loads client-side. This is enforced centrally in `useOncoteamApi.ts`. Without `server: false`, Railway's 17s edge timeout causes 503.
- TTL caches in `dashboard_api.py`: `_timeline_cache` (60s), `_briefings_cache` (120s), `_labs_cache` (60s), `_protocol_cache` (30s), `_documents_cache` (120s). Tests must clear ALL caches — `conftest.py` has autouse `_clear_api_caches` fixture.
- `api_timeline` returns `event_date`/`event_type` fields (not `date`/`type`) — matches frontend TypeScript interface in `index.vue`.
- `api_labs` POST path clears `_labs_cache` on new data.
- Dashboard `index.vue` must capture `status` and `error` from `fetchApi` — the v-if chain needs `labsStatus`/`labsError` to show "Data unavailable" instead of going blank.
- `dashboard/railway.toml` configures health check at `/api/health` (no-auth, no oncofiles dependency).
- Dashboard composables MUST use `useState()` (not module-level `ref()`) for SSR-safe state. Module-level refs cause hydration mismatches and blank pages on refresh. Fixed in: `useTestDataToggle`, `useDrilldown`, `useActivePatient`.
- **Dashboard HTTP contract (post #424)**: all oncoteam backend calls go through `useOncoteamApi.fetchApi` → `useApiFetch.apiFetch`. That helper honors `Retry-After` on 503 (both integer-seconds and HTTP-date per RFC 7231), retries 500/502/504/AbortError with base-500ms/cap-5s/±25% jitter up to 3 attempts, and NEVER retries inside a 503 cooldown. Nuxt proxy (`[...path].ts`) forwards `Retry-After` header verbatim.
- **Readiness source of truth**: `useCircuitBreakerStatus` polls `/api/oncofiles-readiness` (Nuxt proxy to `oncofiles.com/readiness`) every 30s, decrements `cooldown_remaining_s` locally at 1Hz between polls. Supports `closed`/`open`/`half_open`. Do NOT revive the old `/api/diagnostics`-inference path.
- **SWR cache (`useSwrCache`)**: sessionStorage-backed, per-patient keys, 10-min hard TTL. Opt-in paths: `/labs`, `/briefings`, `/timeline`. `fetchApi` writes on success, reads on failure, surfaces `stale` + `cacheAgeMs` so cards render "Showing cached data (N min old) — reconnecting" instead of empty state. Cleared on logout + patient switch from `layouts/default.vue`.
- **Breaker-aware throttling**: `useOncoteamApi.doFetch` short-circuits the upstream call when `state === 'open' && cooldown_remaining_s > 2`. Watch on state transitions auto-refreshes mounted fetches the instant the breaker closes.
- `dashboard/app/error.vue` catches runtime errors visibly (instead of blank white page). Uses `clearError({ redirect: '/' })`.
- `/demo` route bypasses auth (excluded in `auth.global.ts`), uses `layout: false`, static mock data only.
- `api_labs` strips non-numeric values from `entry["values"]` before sending to frontend — prevents raw JSON objects in table cells.
- `api_detail` has circuit breaker check at the top + 8s timeouts on research/fallback fetches — prevents proxy timeout 503s.
- `_classify_session_type()` uses tag-based classification (`sys:` → technical, `clin:` → clinical) with title 2x weight and 500-char body scan.
- `_translate_for_family()` merges lab values from up to 5 entries (limit=5) to include tumor markers + hematology in one report.
- `patient_context.get_genetic_profile()` uses `asyncio.Semaphore(3)` + two-pass optimization (summaries first, full docs only if markers missing, cap 10 docs). Without this, 100+ concurrent `view_document` calls overwhelm oncofiles queue.
- `pubmed_client._request_with_retry()` handles 429 responses with `Retry-After` header (up to 2 retries, max 10s wait).
- Research funnel `_FUNNEL_SYSTEM_PROMPT` includes surgical history + explicit later-line classification rules. Without these, Haiku defaults to "Watching" for 2L/3L trials.
- `eligibility.py` has programmatic later-line regex (`second-line|refractory|post-progression|salvage`) — runs before AI funnel assessment.
- `useFunnelStage.ts` stores movement audit log in localStorage (`funnel-log::` prefix), keeps 500 entries. `setStage()` auto-logs movements.
- `/health` endpoint includes `autonomous_enabled` + `scheduler` status (running, job count, job IDs) for remote diagnostics.
- `scheduler.get_scheduler_status()` exposes APScheduler state. `AUTONOMOUS_ENABLED` must be `true`/`1`/`yes` in Railway env.

### Multi-user hardening (Sprint 57)
- All `oncofiles_client` wrapper functions accept `*, token: str | None = None` — pass patient-specific token for non-q1b patients via `_get_token_for_patient(patient_id)`.
- All 5 TTL caches use `_cache_key(prefix, patient_id, ...)` — NEVER use a cache key without patient_id.
- `_CURRENT_REQUEST` is a `contextvars.ContextVar`, NOT a global. Set/reset in `_auth_wrap()`.
- `_suppressed_errors` is `collections.deque(maxlen=100)` — bounded, never cleared on read.
- `_deduplicated_fetch()` coalesces concurrent identical requests via `asyncio.Future` — used on api_timeline, api_labs, api_briefings, api_documents.
- `_rate_timestamps` is `dict[str, deque]` keyed by patient_id. `_rate_global` is the 600/min safety valve.
- `_daily_cost` in `autonomous.py` is `dict[str, float]` keyed by patient_id (+ "global" key for total).
- `oncofiles_client` has two semaphore lanes: `_dashboard_semaphore` (2 slots) and `_agent_semaphore` (1 slot). `call_oncofiles(priority="express")` is the default for dashboard.
- Circuit breaker state is `_circuit_state: dict[str, dict]` keyed by token prefix. `_is_globally_open()` trips when 3+ per-token breakers are open.
- `_CORRELATION_ID` ContextVar generated per request in `_check_api_auth()`. Included in `X-Correlation-ID` response header.
- All 18 `run_*()` functions in `autonomous_tasks.py` accept `patient_id: str = "q1b"`. State keys include patient_id: `f"last_{task_name}:{patient_id}"`.
- All `run_*()` functions resolve `token = get_patient_token(patient_id)` before `_should_skip`, then pass `token=token` to `_log_task`, `_set_state`, `_should_skip`. Never call `get_patient_token` twice.
- `scheduler.py` creates one job per `(agent, patient)` pair via `_make_runner` closures. Multi-patient jobs staggered by 2 minutes (cron minute offset). `keepalive_ping` is system-level (no patient iteration).
- `_get_current_patient_id()` in `server.py` resolves patient from MCP bearer token via `get_access_token().client_id`. `MCP_BEARER_TOKEN_<ID>` env vars map additional tokens to patient IDs.
- `useOncoteamApi.ts` has `postApi` helper that includes `patient_id` in query string for POST mutations. All dashboard POST calls must use `postApi`, not raw `$fetch`.
- `useDrilldown.ts` includes `patient_id` in detail fetch URL.
- `session-patch.ts` preserves `patientId`/`patientIds` when patching stale sessions. Skip guard compares session patientIds against roleMap patient_ids — re-patches when new patients are added to roleMap.
- `approved-phones.ts` has `resolvePatientIdFromPhone()` — maps WhatsApp phone numbers to patient IDs via `NUXT_ROLE_MAP` phone+patient_id fields.
- `eligibility.py` `assess_research_relevance()` accepts optional `patient` param. `check_eligibility()` reason strings are built from `patient.biomarkers` dict, not hardcoded.
- `PatientProfile.agent_whitelist` — empty list = all agents (backward compat). Scheduler at `scheduler.py:123` skips agents not in whitelist. Non-oncology patients (e.g., e5g) should whitelist only relevant agents.
- Patient e5g (Peter F.) is a general health patient (Z00.0), NOT oncology. Never apply oncology protocols/agents to non-oncology patients. Check `agent_whitelist` before adding new agents.

### General Health Patient Protocol (e5g / Peter F.)

**Critical**: `build_system_prompt()` in `autonomous.py` currently injects oncology clinical protocol (mFOLFOX6 thresholds, dose mods, treatment milestones, NCCN guidelines) for ALL patients including e5g. This MUST be made conditional on patient profile — e5g should get the general health protocol below instead.

**Required code change in `autonomous.py:build_system_prompt()`**:
- If `patient.diagnosis_code.startswith("Z")` or `patient.treatment_regimen == ""` → use general health protocol
- Otherwise → use existing oncology protocol (mFOLFOX6 thresholds, dose mods, etc.)

**General Health System Prompt** (for e5g and future non-oncology patients):
```
You are an autonomous health management agent for general preventive care.
ALL findings are for physician review only. You do NOT communicate with patients.

# Lab Analysis — General Health Protocol
Use EU/WHO/ESC reference ranges (NOT oncology thresholds):
- Metabolic: glucose fasting <5.6 mmol/L, HbA1c <42 mmol/mol
- Lipids: total cholesterol <5.0, HDL >1.0 (male), LDL <3.0, TG <1.7 (ESC/EAS 2019)
- Thyroid: TSH 0.4-4.0 mIU/L (ATA)
- Renal: creatinine 62-106 µmol/L (male), eGFR >90 (KDIGO)
- Hepatic: ALT <45, AST <35, bilirubin <17 µmol/L (standard adult male)
- CBC: WBC 4-10, HGB 130-175 g/L, PLT 150-400 (standard adult)
- Vitamins: vitamin D >75 nmol/L (Endocrine Society), ferritin 30-300 µg/L (male)
- Screening: PSA <4.0 ng/mL (EAU, male >50, shared decision)

DO NOT: calculate SII/NeLy ratio, reference mFOLFOX6/NCCN, suggest pre-cycle checklists.
DO: flag out-of-range values, compare to EU/WHO guidelines, track trends, end with
"Preventive care reminders" section.

# EU Preventive Care Screening
Track and remind based on age/sex:
- Colonoscopy: 50+, every 10y (EU Council 2022)
- FOBT/FIT: 50-74, every 2y
- Dental: every 6 months
- Ophthalmology: 40+, every 2y
- Dermatology: 35+, every 2y (Euromelanoma)
- CV risk (SCORE2): 40+, every 5y (ESC 2021)
- PSA: 50+ male, every 2y (EAU)
- Lipid panel: 40+, every 5y (ESC/EAS)
- Fasting glucose: 45+, every 3y (WHO)
- Flu vaccine: 50+, annual (ECDC)
- Tetanus booster: every 10y

# Document Processing
When reviewing uploaded documents:
1. Read via view_document() — extract date, institution, doctor, key findings, ICD codes
2. Store lab values via store_lab_values() with general health parameters
3. Create treatment_event (event_type: "checkup"/"screening"/"vaccination"/"procedure")
4. For handwritten notes: flag OCR uncertainties with [?]
5. Identify gaps in screening compliance

# Oncofiles Integration
- Patient uses `patient_type="general"` in oncofiles context
- 3 specific categories: vaccination, dental, preventive (alongside standard labs/imaging/etc.)
- Folder structure excludes chemo_sheet/pathology/genetics
- Use `get_preventive_care_status` tool for screening compliance report
- Use `get_lab_safety_check` — automatically uses general health thresholds for this patient
```

**Applicable agents for e5g** (set in `agent_whitelist`):
- `lab_sync` — parse and store lab values
- `document_pipeline` — process newly uploaded documents
- Potentially: a new `preventive_care_check` agent (future)

**NOT applicable**: pre_cycle_check, tumor_marker_review, trial_monitor, dose_review, neuropathy_check, vte_check — all oncology-specific.
- `_DEFAULT_MEDICATIONS` in `dashboard_api.py` is empty — real medication data comes from oncofiles.
- Load tests in `tests/load/` — always run after concurrency changes.
- **Always run `uv run ruff format --check` after agent edits** — agents frequently miss formatting.
- `/api/diagnostics` nests `oncofiles_rss_mb` inside `circuit_breaker` — dashboard must read `circuit_breaker.oncofiles_rss_mb`, NOT top-level `oncofiles_rss_mb`.
- `_rss_history` ring buffer (60 entries, ~1hr) in `oncofiles_client.py` — exposed via `get_circuit_breaker_status()["rss_history"]`. Resets on deploy.
- `api_cumulative_dose` reads actual dose from `patient.active_therapies` oxaliplatin entry (76.5 mg/m²), falls back to protocol standard (85). Don't use hardcoded `dose_per_cycle` for patient-specific calculations.
- Dictionary links pattern: `<NuxtLink :to="\`/dictionary?q=${term}\`" class="underline decoration-dotted decoration-gray-400 hover:decoration-green-600 hover:text-green-700 transition-colors">`. Used in LabThresholdTable, PreCycleChecklist, toxicity ECOG, labs headers, home page labs, EmergencyAlert, BiomarkerCard.
- `medical-dictionary.ts` has 39 entries across 7 categories (lab, tumor_marker, treatment, diagnosis, inflammation, general, toxicity). Add new entries there, not inline.
- `_classify_doc_type()` recognizes `chemo_sheet` via metadata category + text heuristics. Dispatcher routes to `run_dose_extraction_single()`.
- `dose_extraction` agent is event-driven only (`schedule_params={"hours": 999}`). Has `is_general_health_patient()` guard — never runs for e5g. Uses Sonnet (not Haiku) for better handwritten OCR accuracy.
- `_run_single_doc_task()` accepts optional `model` param — defaults to `AUTONOMOUS_MODEL_LIGHT` (Haiku). Dose extraction overrides to `AUTONOMOUS_MODEL` (Sonnet).
- `get_doc_detail()` in `oncofiles_client.py` is a REST call (not MCP) to `GET /api/doc-detail/{doc_id}`. Returns `preview_url`, `pages[]` with per-page OCR text. `api_detail` uses this first, falls back to MCP.
- `list_agent_states` wrapper does NOT send `limit` to oncofiles — truncates client-side. Oncofiles v5.2.5+ accepts `limit` but older versions reject it.
- `api_cumulative_dose` prefers real extracted data (`data_source="extracted"`) from `list_treatment_events(event_type="chemotherapy")`, falls back to `calculated` using patient profile dose. New fields: `data_source`, `cycles_detail`.
- Agent registry count: 21. Tests in `test_agent_registry.py` and `test_scheduler.py` assert counts — update when adding agents.
- `_patient_tokens` in `patient_context.py` auto-populates from `ONCOFILES_MCP_TOKEN_<ID>` env vars at module load. Set `ONCOFILES_MCP_TOKEN_E5G` in Railway. Without it, e5g calls fail or fall back to q1b's token (data isolation bug found in Sprint 69).

## Multi-Document Groups (Oncofiles v5.4+)

- Documents can have `group_id`, `part_number`, `total_parts` fields when they are parts of a split or consolidated group
- `split_source_doc_id` links split children back to the original PDF (which is soft-deleted)
- Use `get_document_group(group_id)` MCP tool to fetch all parts of a logical document ordered by part_number
- When viewing a document that's part of a group, always mention the group context (e.g., "Part 2 of 3")
- Lab analysis: if a lab report is split into multiple parts, combine values from all parts before analysis
- `detect_and_split_documents(dry_run=True)` and `detect_and_consolidate_documents(dry_run=True)` MCP tools available for scanning
- Cross-references now use AI-powered relationship types: `same_visit`, `follow_up`, `supersedes`, `related`, `contradicts` (replaces old heuristic same_visit/related)

## Key commands

- `uv run oncoteam-mcp` — run MCP server (stdio)
- `MCP_TRANSPORT=streamable-http uv run oncoteam-mcp` — run HTTP server
- `uv run pytest` — run tests
- `uv run pytest tests/test_file.py::test_name` — run single test
- `uv run ruff check --fix` — lint and auto-fix
- `uv run ruff format src/oncoteam/dashboard_api.py` — run after editing dashboard_api.py (long lines trigger format failures)
- `cd dashboard && pnpm dev` — run dashboard dev server
- `cd dashboard && pnpm build` — build dashboard (catches TS errors)

## Testing

- `uv run pytest` — full suite (744 tests, ~4.5s)
- Tests mock `oncofiles_client` wrapper functions, not `call_oncofiles` directly
- Use `respx` for HTTP mocking (PubMed, ClinicalTrials.gov, GitHub)
- PostToolUse hook auto-runs tests after editing `src/oncoteam/`

## Deployment

- **Railway**: `api.oncoteam.cloud` (health: /health, MCP: /mcp). Note: `oncoteam.cloud` is the landing page, NOT the backend.
- Push to `main` auto-deploys via Railway
- `railway.toml` has `overlapSeconds=15` + `healthcheckPath=/health` — zero-downtime deploys
- Requires oncofiles MCP (`ONCOFILES_MCP_URL` env var)
- Requires `GITHUB_TOKEN` for create_improvement_issue tool
- **Security**: HTTP transport requires `MCP_BEARER_TOKEN`, `DASHBOARD_API_KEY`, `DASHBOARD_ALLOWED_ORIGINS`
- 744 tests, ruff clean
- Claude.ai connectors: "Oncoteam" + "Oncofiles" custom connectors (Always allow)

## Environment variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ONCOFILES_MCP_URL` | Oncofiles MCP endpoint | Yes |
| `ONCOFILES_MCP_TOKEN` | Bearer token for oncofiles auth | Yes |
| `MCP_TRANSPORT` | `stdio` or `streamable-http` | No (default: stdio) |
| `MCP_HOST` | Bind host (default `0.0.0.0`) | No |
| `MCP_PORT` / `PORT` | Bind port | No |
| `MCP_BEARER_TOKEN` | Auth token for MCP connections | **Yes for HTTP** |
| `DASHBOARD_API_KEY` | Auth key for /api/* endpoints | **Yes for HTTP** |
| `DASHBOARD_ALLOWED_ORIGINS` | Comma-separated CORS origins | **Yes for HTTP** |
| `GITHUB_TOKEN` | Fine-grained PAT for issue creation (oncoteam-bug-reporter, expires Jun 23 2026) | No |
| `NCBI_API_KEY` | NCBI E-utilities API key | No |

## Security (from Sprint 54 hardening)

- `SecurityHeadersMiddleware` in `server.py` adds X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy to all HTTP responses
- `_parse_json_body()` in `dashboard_api.py` enforces 1MB request body limit for POST endpoints
- `_validate_id()` in `oncofiles_client.py` validates document/file IDs at the boundary (1-200 chars)
- `oncofiles_client.py` uses lazy import for `record_suppressed_error` to avoid circular import with `activity_logger.py`
- `landing/i18n.js` uses `data-i18n-html` attribute (via `innerHTML`) for demo mockup strings containing HTML entities/tags — safe because all values are hardcoded static strings, no user input
- Vue template Unicode: `\u2013` / `\u2193` in HTML template context renders as literal text. Use HTML entities (`&ndash;`, `&darr;`) or actual Unicode chars. Inside `{{ expression }}` (JS context), `\u` escapes work correctly.

## Clinical-user architecture (Sprint 92-94 in progress)

Target: MUDr. Mgr. Zuzana Mináriková, PhD. (klinický onkológ, NOÚ Bratislava) joining as physician user for q1b per #396. Triggered architectural changes across multiple surfaces:

- **#395 Two-lane funnel + immutable audit** (backend ✅ Sprint 93 S1): agents never mutate clinical funnel state directly. They post to a proposals lane (TTL 30d, physician triages). Clinical lane is physician-writable only. Every state change requires rationale + generates append-only audit event stored in oncofiles + backed up hourly to GCS per #397.
- **#397 DR/backup**: dedicated GCP project `oncoteam-prod-backups` (isolated from oncoteam-dashboard + oncofiles-490809), WORM hot bucket for audit (2y retention), versioned cold bucket for DB dumps (365d). CMEK encryption. Service account write-only. Script in `scripts/gcp_backup_setup.sh`.
- **#398 Structured oncopanel**: `Oncopanel` + `OncopanelVariant` + `CopyNumberVariant` Pydantic models on `PatientProfile.oncopanel_history`. Replaces flat `biomarkers: dict` for patients with NGS data. Variant-level source traceability per #382 + physician review state per variant per #395.
- **#399 /research as cockpit**: 8 sub-panels (Inbox / Clinical Funnel / Literature / News / Discussion / Audit / Watchlist / Re-Surfaced) as left-sidebar sub-nav. Server-persisted state (not localStorage). Physician lands on Inbox; advocate on Funnel. Spec in `docs/research_cockpit.md`.
- **#394 Geographic enrollment** (backend ✅ landed c20bc89): every PatientProfile carries `home_region` + `enrollment_preference`. `geographic_score(sites, patient)` filters non-enrollable trials upstream. Bratislava patients (q1b/e5g/sgu) seeded with `preferred_countries=[SK,CZ,AT,HU,PL,DE,CH]`.
- **#392 DDR pivot**: q1b oncopanel 2026-04-18 reveals ATM biallelic + TP53 splice → PARPi/ATRi/pan-RAS eligible. `is_ddr_deficient(patient)` structured helper (builds on #398). `ddr_monitor` agent posts to proposals lane with proximity scoring from #394.

**Key principle** (feedback memory `feedback_never-lose-a-clinical-decision.md`): **AI proposes, humans dispose**. Agents cannot silently mutate clinical state. Every decision is logged, attributed, reversible via audit trail (not via silent overwrite). Cross-device consistency is non-negotiable.

### Two-lane funnel API (#395 backend, Sprint 93)

- `src/oncoteam/models.py` — `FunnelCard`, `FunnelAuditEvent` (frozen), `FunnelLane`, `FunnelEventType`, `FunnelActorType`. `FUNNEL_STATE_CHANGING_EVENTS` and `FUNNEL_AGENT_ALLOWED_EVENTS` frozensets drive model-level invariants.
- `src/oncoteam/funnel_audit.py` — the only module that writes `funnel_audit:*` and `funnel_cards:*` agent_state keys. `record_event()` enforces invariants via Pydantic; `find_existing_card_for_nct()` powers re-surfacing protection.
- `src/oncoteam/api_funnel.py` — REST handlers:
  - **Agent-writable (proposal lane only)**: `POST /api/funnel/proposals` — re-surfacing check collapses duplicate NCTs into a `re_surfaced` event on the existing card.
  - **Physician-writable (clinical lane)**: `POST /api/funnel/cards` with action ∈ {promote, move, archive, comment}. Rejects `actor_type=agent` with HTTP 403.
  - **Read-only audit**: `GET /api/funnel/audit/{card_id}` and `GET /api/funnel/audit/patient` (filter by actor_type / event_type / limit).
- Actor identity: headers `X-Actor-Type` / `X-Actor-Id` / `X-Actor-Display-Name` set by Nuxt session proxy OR trusted agent body fields. Defaults to `human` to avoid accidental agent escalation.
- Stage vocabularies: `PROPOSAL_STAGES = ("new", "dismissed", "expired")`, `CLINICAL_STAGES = ("Watching", "Candidate", "Qualified", "Contacted", "Active", "Archived")`. Disjoint on purpose — `validate_stage(lane, stage)` enforces.
- Migration: `scripts/migrate_funnel_to_two_lane.py --patient q1b --commit` reads legacy `funnel_stages:{patient_id}`, writes a dated snapshot, and creates one clinical-lane card per legacy NCT with a `migrated_from_v1` audit event. Legacy state is NEVER deleted. `--dry-run` is the default.
- Invariants tested in `tests/test_funnel_audit.py` (immutability + rationale + agent restrictions + append-only persistence) and `tests/test_api_funnel.py` (HTTP contract + re-surfacing + lane isolation).

**Next sessions**: frontend two-lane UI (Nuxt `pages/research.vue` + `FunnelAuditLog` component), agent prompt updates to enforce "propose not mutate", snapshot-and-reset migration for q1b before MUDr. Mináriková's first login.
