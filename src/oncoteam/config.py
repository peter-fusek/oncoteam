from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Oncofiles MCP connection (no default — must be set explicitly)
ONCOFILES_MCP_URL: str = os.environ.get("ONCOFILES_MCP_URL", "")

# NCBI E-utilities
NCBI_BASE_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_API_KEY: str = os.environ.get("NCBI_API_KEY", "")

# ClinicalTrials.gov API v2
CTGOV_BASE_URL: str = "https://clinicaltrials.gov/api/v2"

# MCP server transport
MCP_TRANSPORT: str = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HOST: str = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.environ.get("MCP_PORT", os.environ.get("PORT", "8000")))
MCP_BEARER_TOKEN: str = os.environ.get("MCP_BEARER_TOKEN", "")
MCP_BASE_URL: str = os.environ.get("MCP_BASE_URL", "")

# Dashboard API auth — required for /api/* endpoints
DASHBOARD_API_KEY: str = os.environ.get("DASHBOARD_API_KEY", "")
DASHBOARD_ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("DASHBOARD_ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# Oncofiles MCP auth
ONCOFILES_MCP_TOKEN: str = os.environ.get("ONCOFILES_MCP_TOKEN", "")

# GitHub API
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

# Git commit hash (injected at build time or set in Railway env)
GIT_COMMIT: str = os.environ.get("RAILWAY_GIT_COMMIT_SHA", os.environ.get("GIT_COMMIT", "dev"))[:8]

# Autonomous agent
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
AUTONOMOUS_ENABLED: bool = os.environ.get("AUTONOMOUS_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)
AUTONOMOUS_MODEL: str = os.environ.get("AUTONOMOUS_MODEL", "claude-sonnet-4-6")
AUTONOMOUS_MODEL_LIGHT: str = os.environ.get("AUTONOMOUS_MODEL_LIGHT", "claude-haiku-4-5-20251001")
AUTONOMOUS_COST_LIMIT: float = float(os.environ.get("AUTONOMOUS_COST_LIMIT", "10.0"))

# Anthropic API credit balance (set in Railway env, updated manually or via billing API)
ANTHROPIC_CREDIT_BALANCE: float = float(os.environ.get("ANTHROPIC_CREDIT_BALANCE", "0"))
ANTHROPIC_BUDGET_ALERT_THRESHOLD: float = float(
    os.environ.get("ANTHROPIC_BUDGET_ALERT_THRESHOLD", "15.0")
)

# HTTP timeouts (seconds)
TIMEOUT_EXTERNAL_API: int = 30  # PubMed, ClinicalTrials.gov
TIMEOUT_GITHUB_API: int = 15
TIMEOUT_INTERNAL_MCP: int = 10  # oncofiles keepalive
TIMEOUT_DASHBOARD_API: int = 5  # internal API calls
