# oncoteam

Persistent AI agent for cancer treatment management. Searches PubMed and ClinicalTrials.gov, checks trial eligibility, tracks treatment data. All persistence goes through oncofiles MCP.

## Quick start

```bash
uv sync --extra dev
uv run pytest          # 592 tests
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

- `uv run pytest` — full suite (592 tests, ~2.3s)
- Tests mock `oncofiles_client` wrapper functions, not `call_oncofiles` directly
- Use `respx` for HTTP mocking (PubMed, ClinicalTrials.gov, GitHub)
- PostToolUse hook auto-runs tests after editing `src/oncoteam/`

## Deployment

- **Railway**: `oncoteam-production.up.railway.app` (health: /health, MCP: /mcp)
- Push to `main` auto-deploys via Railway
- `railway.toml` has `overlapSeconds=15` + `healthcheckPath=/health` — zero-downtime deploys
- Requires oncofiles MCP (`ONCOFILES_MCP_URL` env var)
- Requires `GITHUB_TOKEN` for create_improvement_issue tool
- **Security**: HTTP transport requires `MCP_BEARER_TOKEN`, `DASHBOARD_API_KEY`, `DASHBOARD_ALLOWED_ORIGINS`
- 592 tests, ruff clean
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
| `GITHUB_TOKEN` | Fine-grained PAT for issue creation | No |
| `NCBI_API_KEY` | NCBI E-utilities API key | No |
