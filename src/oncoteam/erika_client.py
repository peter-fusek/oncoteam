from __future__ import annotations

import json

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from .config import ERIKA_MCP_URL


def _get_transport() -> StreamableHttpTransport:
    return StreamableHttpTransport(ERIKA_MCP_URL)


async def call_erika(tool_name: str, arguments: dict) -> dict | list | str:
    """Call an erika-files-mcp tool and return parsed result."""
    transport = _get_transport()
    async with Client(transport) as client:
        result = await client.call_tool(tool_name, arguments)
        # FastMCP 3.x returns CallToolResult with .content list
        if result.content and hasattr(result.content[0], "text"):
            try:
                return json.loads(result.content[0].text)
            except (json.JSONDecodeError, TypeError):
                return result.content[0].text
        return str(result)


async def search_documents(text: str, category: str | None = None) -> dict:
    args: dict = {"text": text}
    if category:
        args["category"] = category
    return await call_erika("search_documents", args)


async def get_document(document_id: int) -> dict:
    return await call_erika("get_document", {"document_id": document_id})


async def set_agent_state(key: str, value: dict, agent_id: str = "oncoteam") -> dict:
    return await call_erika(
        "set_agent_state",
        {"key": key, "value": json.dumps(value), "agent_id": agent_id},
    )


async def get_agent_state(key: str, agent_id: str = "oncoteam") -> dict:
    return await call_erika("get_agent_state", {"key": key, "agent_id": agent_id})


async def add_research_entry(
    source: str,
    external_id: str,
    title: str,
    summary: str = "",
    tags: list[str] | None = None,
    raw_data: str = "",
) -> dict:
    return await call_erika(
        "add_research_entry",
        {
            "source": source,
            "external_id": external_id,
            "title": title,
            "summary": summary,
            "tags": json.dumps(tags or []),
            "raw_data": raw_data,
        },
    )


async def search_research(text: str, source: str | None = None, limit: int = 20) -> dict:
    args: dict = {"text": text, "limit": limit}
    if source:
        args["source"] = source
    return await call_erika("search_research", args)


async def add_treatment_event(
    event_date: str,
    event_type: str,
    title: str,
    notes: str = "",
    metadata: dict | None = None,
) -> dict:
    return await call_erika(
        "add_treatment_event",
        {
            "event_date": event_date,
            "event_type": event_type,
            "title": title,
            "notes": notes,
            "metadata": json.dumps(metadata or {}),
        },
    )


async def list_treatment_events(event_type: str | None = None, limit: int = 50) -> dict:
    args: dict = {"limit": limit}
    if event_type:
        args["event_type"] = event_type
    return await call_erika("list_treatment_events", args)
