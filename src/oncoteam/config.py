from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Oncofiles MCP connection
ONCOFILES_MCP_URL: str = os.environ.get(
    "ONCOFILES_MCP_URL", "https://aware-kindness-production.up.railway.app/mcp"
)

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

# Oncofiles MCP auth
ONCOFILES_MCP_TOKEN: str = os.environ.get("ONCOFILES_MCP_TOKEN", "")

# GitHub API
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")

# Autonomous agent
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
AUTONOMOUS_ENABLED: bool = os.environ.get("AUTONOMOUS_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)
AUTONOMOUS_MODEL: str = os.environ.get("AUTONOMOUS_MODEL", "claude-sonnet-4-6")
AUTONOMOUS_COST_LIMIT: float = float(os.environ.get("AUTONOMOUS_COST_LIMIT", "1.0"))
