"""GitHub REST API client for issue creation."""

from __future__ import annotations

import httpx

from .config import GITHUB_TOKEN

API_BASE = "https://api.github.com"


async def create_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> dict:
    """Create a GitHub issue. Returns {"number": N, "url": "..."}."""
    url = f"{API_BASE}/repos/{repo}/issues"
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"number": data["number"], "url": data["html_url"]}
