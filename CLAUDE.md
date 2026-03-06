# oncoteam

Persistent AI agent for cancer treatment management. Searches PubMed and ClinicalTrials.gov, checks trial eligibility, tracks treatment data. All persistence goes through oncofiles MCP.

## Quick start

```bash
uv sync --extra dev
uv run pytest          # 160 tests
uv run ruff check
uv run oncoteam-mcp    # stdio mode
```

## Project structure

- `src/oncoteam/server.py` — MCP server, 18 tools, system instructions with biomarker rules + QA protocol
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

## Conventions

- Python 3.12+, async-first
- FastMCP 3.0+ for MCP server
- Pydantic for data models
- httpx for async HTTP (PubMed, ClinicalTrials.gov, GitHub)
- No local database — all persistence via oncofiles MCP
- ruff for linting/formatting
- All suppressed exceptions must call `record_suppressed_error()` for QA visibility

## Key commands

- `uv run oncoteam-mcp` — run MCP server (stdio)
- `MCP_TRANSPORT=streamable-http uv run oncoteam-mcp` — run HTTP server
- `uv run pytest` — run tests
- `uv run ruff check --fix` — lint and auto-fix

## Deployment

- **Railway**: `oncoteam-production.up.railway.app` (health: /health, MCP: /mcp)
- Push to `main` auto-deploys via Railway
- Requires oncofiles MCP (`ONCOFILES_MCP_URL` env var)
- Requires `GITHUB_TOKEN` for create_improvement_issue tool
- 160 tests, ruff clean

## Environment variables

| Variable | Description |
|----------|-------------|
| `ONCOFILES_MCP_URL` | Oncofiles MCP endpoint |
| `MCP_TRANSPORT` | `stdio` or `streamable-http` |
| `MCP_HOST` | Bind host (default `0.0.0.0`) |
| `MCP_PORT` / `PORT` | Bind port |
| `GITHUB_TOKEN` | Fine-grained PAT for issue creation |
| `MCP_BEARER_TOKEN` | Optional auth token |
| `NCBI_API_KEY` | NCBI E-utilities API key (optional) |
