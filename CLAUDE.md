# oncoteam

Persistent AI agent for cancer treatment management. Searches PubMed and ClinicalTrials.gov, tracks treatment data. All persistence goes through oncofiles MCP.

## Quick start

```bash
uv sync --extra dev
uv run pytest
uv run ruff check
uv run oncoteam-mcp          # stdio mode
```

## Project structure

- `src/oncoteam/` — main package
- `tests/` — pytest tests with respx mocks

## Conventions

- Python 3.12+, async-first
- FastMCP 3.0+ for MCP server
- Pydantic for data models
- httpx for async HTTP (PubMed, ClinicalTrials.gov)
- No local database — all persistence via oncofiles MCP
- ruff for linting/formatting

## Key commands

- `uv run oncoteam-mcp` — run MCP server (stdio)
- `MCP_TRANSPORT=streamable-http uv run oncoteam-mcp` — run HTTP server
- `uv run pytest` — run tests
- `uv run ruff check --fix` — lint and auto-fix
- `uv run ruff format` — format code

## Deployment

- **Railway**: `oncoteam-production.up.railway.app` (health: /health, MCP: /mcp)
- Push to `main` auto-deploys via Railway
- Requires oncofiles MCP running (`ONCOFILES_MCP_URL` env var)
- 65 tests, ruff clean
