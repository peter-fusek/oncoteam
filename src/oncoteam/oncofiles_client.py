from __future__ import annotations

import json

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from .config import ONCOFILES_MCP_URL


def _get_transport() -> StreamableHttpTransport:
    return StreamableHttpTransport(ONCOFILES_MCP_URL)


async def call_oncofiles(tool_name: str, arguments: dict) -> dict | list | str:
    """Call an oncofiles MCP tool and return parsed result."""
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
    return await call_oncofiles("search_documents", args)


async def get_document(document_id: int) -> dict:
    return await call_oncofiles("get_document", {"document_id": document_id})


async def set_agent_state(key: str, value: dict, agent_id: str = "oncoteam") -> dict:
    return await call_oncofiles(
        "set_agent_state",
        {"key": key, "value": json.dumps(value), "agent_id": agent_id},
    )


async def get_agent_state(key: str, agent_id: str = "oncoteam") -> dict:
    return await call_oncofiles("get_agent_state", {"key": key, "agent_id": agent_id})


async def add_research_entry(
    source: str,
    external_id: str,
    title: str,
    summary: str = "",
    tags: list[str] | None = None,
    raw_data: str = "",
) -> dict:
    return await call_oncofiles(
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
    return await call_oncofiles("search_research", args)


async def add_treatment_event(
    event_date: str,
    event_type: str,
    title: str,
    notes: str = "",
    metadata: dict | None = None,
) -> dict:
    return await call_oncofiles(
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
    return await call_oncofiles("list_treatment_events", args)


# ── Activity log wrappers ──────────────────────


async def add_activity_log(
    session_id: str,
    agent_id: str,
    tool_name: str,
    input_summary: str | None = None,
    output_summary: str | None = None,
    duration_ms: int | None = None,
    status: str = "ok",
    error_message: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    args: dict = {
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "status": status,
    }
    if input_summary:
        args["input_summary"] = input_summary
    if output_summary:
        args["output_summary"] = output_summary
    if duration_ms is not None:
        args["duration_ms"] = duration_ms
    if error_message:
        args["error_message"] = error_message
    if tags:
        args["tags"] = json.dumps(tags)
    return await call_oncofiles("add_activity_log", args)


async def search_activity_log(
    session_id: str | None = None,
    agent_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict:
    args: dict = {"limit": limit}
    if session_id:
        args["session_id"] = session_id
    if agent_id:
        args["agent_id"] = agent_id
    if tool_name:
        args["tool_name"] = tool_name
    if status:
        args["status"] = status
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("search_activity_log", args)


# ── Conversation wrappers ──────────────────────


async def log_conversation(
    title: str,
    content: str,
    entry_type: str = "note",
    participant: str = "oncoteam",
    session_id: str | None = None,
    tags: str | None = None,
    document_ids: str | None = None,
) -> dict:
    args: dict = {
        "title": title,
        "content": content,
        "entry_type": entry_type,
        "participant": participant,
    }
    if session_id:
        args["session_id"] = session_id
    if tags:
        args["tags"] = tags
    if document_ids:
        args["document_ids"] = document_ids
    return await call_oncofiles("log_conversation", args)


async def search_conversations(
    text: str | None = None,
    entry_type: str | None = None,
    participant: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    tags: str | None = None,
    limit: int = 20,
) -> dict:
    args: dict = {"limit": limit}
    if text:
        args["text"] = text
    if entry_type:
        args["entry_type"] = entry_type
    if participant:
        args["participant"] = participant
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    if tags:
        args["tags"] = tags
    return await call_oncofiles("search_conversations", args)


async def get_journey_timeline(
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict:
    args: dict = {"limit": limit}
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await call_oncofiles("get_journey_timeline", args)
