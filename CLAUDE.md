# oncoteam

Persistent AI agent for cancer treatment management. Searches PubMed and ClinicalTrials.gov, checks trial eligibility, tracks treatment data. All persistence goes through oncofiles MCP.

## Quick start

```bash
uv sync --extra dev
uv run pytest          # 637 tests
uv run ruff check
uv run oncoteam-mcp    # stdio mode
```

## Project structure

- `src/oncoteam/server.py` — MCP server, 24 tools + 21 dashboard API routes (6 POST, 2 parameterized), system instructions with biomarker rules + QA protocol
- `src/oncoteam/dashboard_api.py` — Dashboard JSON API: /api/{status,activity,stats,timeline,patient,research,sessions,autonomous,protocol,briefings,toxicity,labs,diagnostics,documents,medications,weight,family-update,cumulative-dose,agent-runs,detail/{type}/{id},internal/document-webhook,internal/trigger-agent}
- `src/oncoteam/clinical_protocol.py` — Embedded clinical protocol: lab thresholds, reference ranges, dose mods, cumulative dose thresholds, cycle delay rules, nutrition escalation, milestones, safety flags, 2L options
- `src/oncoteam/autonomous.py` — Claude API autonomous agent loop with extended thinking
- `src/oncoteam/autonomous_tasks.py` — 18 autonomous task wrappers + document pipeline orchestrator with cooldown guards and WhatsApp notifications
- `src/oncoteam/agent_registry.py` — AgentConfig Pydantic model, all 18 agent definitions + document_pipeline, schedule/cooldown/model config
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

### Gotchas (from real incidents)

- Protocol cache (`_protocol_cache` dict in `dashboard_api.py`) must be cleared in tests: add `@pytest.fixture(autouse=True) def _clear_protocol_cache()` to any test module touching `/api/protocol`
- `lru_cache` on `_resolve_protocol_cached(lang)` — call `_resolve_protocol_cached.cache_clear()` in tests, not just the dict
- `dashboard_api.py` parallel MCP fetches use `asyncio.gather` with 2s per-task timeout — add mocks for ALL gathered calls in tests or they'll fail
- Nuxt `useFetch` query must use `computed()` (not plain object) for locale-reactive API calls
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
- `api_document_webhook` imports `_get_state`, `_extract_timestamp`, `run_document_pipeline` lazily from `autonomous_tasks` — test patches must target `oncoteam.autonomous_tasks`, not `oncoteam.dashboard_api`.
- `api_trigger_agent` clears cooldown state before triggering — imports `_get_task_functions` from `scheduler.py`. Same lazy-import pattern as webhook.
- Agent registry `model` field is display-only — the actual model override is in each `run_*()` function's `run_autonomous_task()` call. If you change model in registry, also update the corresponding `run_*()` function.
- `AUTONOMOUS_COST_LIMIT` default is $10 (temporary, target $5 after monitoring period ~2026-03-28)
- `_CONTAMINATED_EVENT_IDS` in `dashboard_api.py` filters known bad data (IDs 19-21: placeholder labs 100x too low, ID 32: duplicate of 27). Tests must not use these IDs.
- `_normalize_lab_values()` converts G/L → /µL for ANC (<30), PLT (<1000), ABS_LYMPH (<30), and maps HGB→hemoglobin
- `api_labs` outlier detection flags CEA/CA_19_9 entries with >90% single-reading change as `suspects[]`
- `oncofiles_client.py` has circuit breaker (5 fails → 30s cooldown), 20s per-call timeout, 0.5s retry backoff. `get_circuit_breaker_status()` exposes state for health endpoints.
- `oncofiles_client.py` concurrency: max 3 parallel calls (semaphore), heavy queries (`search_conversations`, `search_documents`) max 1 concurrent. `SEMAPHORE_WAIT_TIMEOUT=8s` rejects requests that can't acquire a slot (prevents zombie queue buildup from proxy-cancelled requests).
- `oncofiles_client.py` RSS backoff: checks oncofiles `/health` every 60s (throttled). RSS >= 400MB → 30s backoff, >= 450MB → 2min. Don't reduce `RSS_CHECK_INTERVAL` below 30s — per-call health checks cause dashboard proxy timeouts.
- `api_whatsapp_chat` checks circuit breaker before calling Claude API — returns clear Slovak/English message if oncofiles is down, saving API cost.
- Agent schedules are staggered to avoid morning pile-on: weekly_briefing 05:00, daily_cost 06:00, trial_monitor 07:45, daily_research 09:00, protocol_review Wed 11:30. Don't cluster agents within 30min of each other.
- WhatsApp chat tests must mock `oncofiles_client.get_circuit_breaker_status` (return `{"state": "closed"}`).
- Don't wrap `asyncio.gather(return_exceptions=True)` with `asyncio.wait_for` — timeout cancels ALL tasks, defeating partial results. Individual `call_oncofiles` already has 20s timeout.
- `api_health_deep` and `api_diagnostics` include `circuit_breaker` status. Tests mocking diagnostics must also mock `get_circuit_breaker_status`.
- RSS memory: `resource.getrusage` returns bytes on macOS, KB on Linux — use `sys.platform == "darwin"` check
- WhatsApp conversational (non-command) messages use async pattern: immediate "Premýšľam..." TwiML, then Claude response via Twilio REST API. Commands (labky, lieky, etc.) respond synchronously.
- `NUXT_TWILIO_WHATSAPP_FROM` env var may include `whatsapp:` prefix — code handles both formats to prevent double-wrapping.
- Multi-patient: `patient_context.py` has `PatientRegistry` (in-memory dict), `get_patient(patient_id)`, `register_patient()`, `build_system_prompt(patient_id)`. Erika is `patient_id="erika"`. Oncofiles bearer token scopes data per-patient — no need to pass patient_id to oncofiles calls.
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
- All `oncofiles_client` wrapper functions accept `*, token: str | None = None` — pass patient-specific token for non-erika patients via `_get_token_for_patient(patient_id)`.
- All 5 TTL caches use `_cache_key(prefix, patient_id, ...)` — NEVER use a cache key without patient_id.
- `_CURRENT_REQUEST` is a `contextvars.ContextVar`, NOT a global. Set/reset in `_auth_wrap()`.
- `_suppressed_errors` is `collections.deque(maxlen=100)` — bounded, never cleared on read.
- `_deduplicated_fetch()` coalesces concurrent identical requests via `asyncio.Future` — used on api_timeline, api_labs, api_briefings, api_documents.
- `_rate_timestamps` is `dict[str, deque]` keyed by patient_id. `_rate_global` is the 600/min safety valve.
- `_daily_cost` in `autonomous.py` is `dict[str, float]` keyed by patient_id (+ "global" key for total).
- `oncofiles_client` has two semaphore lanes: `_dashboard_semaphore` (2 slots) and `_agent_semaphore` (1 slot). `call_oncofiles(priority="express")` is the default for dashboard.
- Circuit breaker state is `_circuit_state: dict[str, dict]` keyed by token prefix. `_is_globally_open()` trips when 3+ per-token breakers are open.
- `_CORRELATION_ID` ContextVar generated per request in `_check_api_auth()`. Included in `X-Correlation-ID` response header.
- All 18 `run_*()` functions in `autonomous_tasks.py` accept `patient_id: str = "erika"`. State keys include patient_id: `f"last_{task_name}:{patient_id}"`.
- All `run_*()` functions resolve `token = get_patient_token(patient_id)` before `_should_skip`, then pass `token=token` to `_log_task`, `_set_state`, `_should_skip`. Never call `get_patient_token` twice.
- `scheduler.py` creates one job per `(agent, patient)` pair via `_make_runner` closures. Multi-patient jobs staggered by 2 minutes (cron minute offset). `keepalive_ping` is system-level (no patient iteration).
- `_get_current_patient_id()` in `server.py` resolves patient from MCP bearer token via `get_access_token().client_id`. `MCP_BEARER_TOKEN_<ID>` env vars map additional tokens to patient IDs.
- `useOncoteamApi.ts` has `postApi` helper that includes `patient_id` in query string for POST mutations. All dashboard POST calls must use `postApi`, not raw `$fetch`.
- `useDrilldown.ts` includes `patient_id` in detail fetch URL.
- `session-patch.ts` preserves `patientId`/`patientIds` when patching stale sessions.
- `approved-phones.ts` has `resolvePatientIdFromPhone()` — maps WhatsApp phone numbers to patient IDs via `NUXT_ROLE_MAP` phone+patient_id fields.
- `eligibility.py` `assess_research_relevance()` accepts optional `patient` param. `check_eligibility()` reason strings are built from `patient.biomarkers` dict, not hardcoded.
- `_DEFAULT_MEDICATIONS` in `dashboard_api.py` is empty — real medication data comes from oncofiles.
- Load tests in `tests/load/` — always run after concurrency changes.
- **Always run `uv run ruff format --check` after agent edits** — agents frequently miss formatting.

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

- `uv run pytest` — full suite (637 tests, ~4.5s)
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
- 637 tests, ruff clean
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
