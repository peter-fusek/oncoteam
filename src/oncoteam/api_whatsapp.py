"""WhatsApp API handlers — extracted from dashboard_api.py (#353)."""

from __future__ import annotations

import asyncio
import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import oncofiles_client
from .activity_logger import record_suppressed_error
from .autonomous import run_autonomous_task
from .config import (
    ANTHROPIC_API_KEY,
    AUTONOMOUS_MODEL_LIGHT,
    FUP_AI_QUERIES_PER_MONTH,
)
from .patient_context import DEFAULT_PATIENT_ID
from .request_context import get_token_for_patient as _get_token_for_patient

_logger = logging.getLogger("oncoteam.api_whatsapp")

# ---------------------------------------------------------------------------
# Lazy imports from dashboard_api to avoid circular dependency
# ---------------------------------------------------------------------------


def _cors_json(data: dict, status_code: int = 200, request: Request | None = None) -> JSONResponse:
    from .dashboard_api import _cors_json as _cj

    return _cj(data, status_code=status_code, request=request)


def _get_patient_id(request: Request) -> str:
    from .dashboard_api import _get_patient_id as _gpi

    return _gpi(request)


def _extract_list(result: dict | list | str, key: str) -> list[dict]:
    from .dashboard_api import _extract_list as _el

    return _el(result, key)


def _check_expensive_rate_limit() -> bool:
    from .dashboard_api import _check_expensive_rate_limit as _cerl

    return _cerl()


def _check_fup_ai_query(patient_id: str = "") -> bool:
    from .dashboard_api import _check_fup_ai_query as _cfaq

    return _cfaq(patient_id)


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_WA_THREAD_TTL = 2 * 3600  # 2 hours
_WA_THREAD_MAX_EXCHANGES = 5

# In-memory set of admin-approved WhatsApp phone numbers (#141)
_approved_phones: set[str] = set()
_approved_phones_loaded = False
_phone_patient_map: dict[str, str] = {}  # phone → patient_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_patient_name_map() -> dict[str, str]:
    """Return {patient_id: display_name} for all registered patients."""
    from .patient_context import get_patient, list_patient_ids

    result = {}
    for pid in list_patient_ids():
        try:
            result[pid] = get_patient(pid).name
        except KeyError:
            continue
    return result


def _wa_thread_key(phone: str, patient_id: str = "q1b") -> str:
    """Hash phone for privacy — no PII in state keys. Scoped per patient."""
    import hashlib

    h = hashlib.sha256(phone.encode()).hexdigest()[:12]
    return f"wa_thread:{patient_id}:{h}"


async def _load_wa_thread(
    phone: str, token: str | None = None, patient_id: str = "q1b"
) -> list[dict[str, str]]:
    """Load conversation thread from agent_state, respecting TTL."""
    try:
        state = await asyncio.wait_for(
            oncofiles_client.get_agent_state(_wa_thread_key(phone, patient_id), token=token),
            timeout=3.0,
        )
        if not state:
            return []
        data = state if isinstance(state, dict) else {}
        # Check TTL
        updated_at = data.get("updated_at", "")
        if updated_at:
            from datetime import UTC, datetime

            try:
                ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if (datetime.now(UTC) - ts).total_seconds() > _WA_THREAD_TTL:
                    return []  # Expired
            except (ValueError, TypeError):
                pass
        return data.get("exchanges", [])
    except Exception as e:
        record_suppressed_error("wa_thread", "load", e)
        return []


async def _save_wa_thread(
    phone: str,
    exchanges: list[dict[str, str]],
    token: str | None = None,
    patient_id: str = "q1b",
) -> None:
    """Persist conversation thread (non-blocking, fire-and-forget)."""
    from datetime import UTC, datetime

    try:
        await asyncio.wait_for(
            oncofiles_client.set_agent_state(
                _wa_thread_key(phone, patient_id),
                json.dumps(
                    {
                        "exchanges": exchanges[-_WA_THREAD_MAX_EXCHANGES:],
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                ),
                token=token,
            ),
            timeout=3.0,
        )
    except Exception as e:
        record_suppressed_error("wa_thread", "save", e)


def is_phone_approved(phone: str) -> bool:
    """Check if a phone number has been approved by an admin."""
    return phone in _approved_phones


async def load_approved_phones() -> None:
    """Load approved phones from oncofiles on startup. Safe to call multiple times."""
    global _approved_phones_loaded
    if _approved_phones_loaded:
        return
    try:
        result = await oncofiles_client.get_agent_state(key="phones", agent_id="approved_phones")
        phones = []
        if isinstance(result, dict):
            # The state value may be nested under "value" or "state"
            data = result.get("value") or result.get("state") or result
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                phones = data.get("phones", [])
            elif isinstance(data, list):
                phones = data
        for p in phones:
            if isinstance(p, str) and p.strip():
                _approved_phones.add(p.strip())
        _approved_phones_loaded = True
        if _approved_phones:
            _logger.info("Loaded %d approved phones from oncofiles", len(_approved_phones))
    except Exception as exc:
        record_suppressed_error("load_approved_phones", "get_agent_state", exc)
        _logger.warning("Failed to load approved phones from oncofiles: %s", exc)


async def load_patient_tokens() -> None:
    """Restore patient tokens from oncofiles agent_state on startup."""
    from .patient_context import _patient_tokens

    try:
        raw = await oncofiles_client.get_agent_state(
            key="tokens", agent_id="patient_token_registry"
        )
        if isinstance(raw, dict):
            data = raw.get("value") or raw.get("state") or raw
            if isinstance(data, dict):
                tokens = data.get("tokens", {})
                for pid, tok in tokens.items():
                    if tok and pid not in _patient_tokens:
                        _patient_tokens[pid] = tok
                        _logger.info("Restored token for patient %s from agent_state", pid)
    except Exception as exc:
        _logger.warning("Failed to load patient tokens from agent_state: %s", exc)


async def _persist_approved_phones() -> None:
    """Persist the current approved phones set to oncofiles."""
    try:
        await oncofiles_client.set_agent_state(
            key="phones",
            value={"phones": sorted(_approved_phones)},
            agent_id="approved_phones",
        )
    except Exception as exc:
        record_suppressed_error("_persist_approved_phones", "set_agent_state", exc)
        _logger.warning("Failed to persist approved phones to oncofiles: %s", exc)


async def _persist_patient_token(patient_id: str, token: str) -> None:
    """Persist a patient's oncofiles bearer token to agent_state for reload."""
    from datetime import UTC
    from datetime import datetime as _dt

    try:
        raw = await oncofiles_client.get_agent_state(
            key="tokens", agent_id="patient_token_registry"
        )
        registry: dict[str, str] = {}
        if isinstance(raw, dict):
            data = raw.get("value") or raw.get("state") or raw
            if isinstance(data, dict):
                registry = data.get("tokens", {})
        registry[patient_id] = token
        await oncofiles_client.set_agent_state(
            key="tokens",
            value={
                "tokens": registry,
                "updated_at": _dt.now(UTC).isoformat(),
            },
            agent_id="patient_token_registry",
        )
    except Exception as exc:
        _logger.warning("Failed to persist patient token for %s: %s", patient_id, exc)


# ---------------------------------------------------------------------------
# API Handlers
# ---------------------------------------------------------------------------


async def api_log_whatsapp(request: Request) -> JSONResponse:
    """POST /api/internal/log-whatsapp — log WhatsApp message exchange."""
    try:
        body = json.loads(await request.body())
        phone = body.get("phone", "unknown")
        user_msg = body.get("user_message", "")
        bot_response = body.get("bot_response", "")

        await oncofiles_client.log_conversation(
            title=f"WhatsApp: {user_msg[:50]}",
            content=(
                f"**From**: {phone}\n**Message**: {user_msg}\n\n**Response**:\n{bot_response}"
            ),
            entry_type="whatsapp",
            tags="sys:whatsapp,src:twilio",
        )
        return _cors_json({"logged": True})
    except Exception as e:
        record_suppressed_error("api_log_whatsapp", "log", e)
        return _cors_json({"error": str(e)}, status_code=502)


async def api_resolve_patient(request: Request) -> JSONResponse:
    """POST /api/internal/resolve-patient — AI-powered patient name resolution.

    Uses Claude Haiku to match free-form user input (names, nicknames,
    declined forms) to a patient slug.
    Body: {query: "eriku", allowed_ids: ["q1b", "e5g"]}
    Returns: {patient_id: "q1b", name: "Erika Fusekova"} or {patient_id: null}

    Note: auth is handled by _auth_wrap in server.py, not duplicated here.
    """
    try:
        body = json.loads(await request.body())
        query = (body.get("query") or "").strip()
        allowed_ids = body.get("allowed_ids") or []
    except Exception:
        return _cors_json({"error": "Invalid request body"}, status_code=400, request=request)

    if not query or not allowed_ids:
        return _cors_json({"patient_id": None})

    # Build patient context for Claude
    name_map = _get_patient_name_map()
    patients_desc = "\n".join(f"- {pid}: {name_map.get(pid, '?')}" for pid in allowed_ids)

    if not ANTHROPIC_API_KEY:
        return _cors_json({"patient_id": None, "error": "AI not configured"})

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Match the user input to a patient.\n\n"
                        f'User typed: "{query}"\n\n'
                        f"Available patients:\n{patients_desc}\n\n"
                        f"Reply with ONLY the patient ID (e.g. q1b) "
                        f"if you can match the input to a patient. "
                        f"Consider name variants, nicknames, declined "
                        f"forms (Slovak: Erika→Eriku/Eriky, Peter→Petra). "
                        f"Reply NONE if no match."
                    ),
                }
            ],
        )
        answer = resp.content[0].text.strip().lower()
        # Validate answer is one of the allowed IDs
        if answer in allowed_ids:
            return _cors_json({"patient_id": answer, "name": name_map.get(answer, "")})
        return _cors_json({"patient_id": None})
    except Exception as exc:
        record_suppressed_error("api_resolve_patient", "claude", exc)
        return _cors_json({"patient_id": None})


async def api_whatsapp_chat(request: Request) -> JSONResponse:
    """POST /api/internal/whatsapp-chat — conversational Claude response."""
    if not _check_expensive_rate_limit():
        return _cors_json(
            {"error": "Too many AI requests. Try again in a few minutes."},
            status_code=429,
            request=request,
        )
    try:
        body = json.loads(await request.body())
        message = body.get("message", "")
        phone = body.get("phone", "unknown")
        lang = body.get("lang", "sk")
        if lang not in ("sk", "en"):
            lang = "sk"
        patient_id = body.get("patient_id", "")
        user_name = body.get("user_name", "")
        user_roles = body.get("user_roles", [])
    except Exception:
        return _cors_json({"error": "Invalid request body"}, status_code=400, request=request)

    if not _check_fup_ai_query(patient_id or "global"):
        return _cors_json(
            {"error": f"Monthly AI query limit reached ({FUP_AI_QUERIES_PER_MONTH})."},
            status_code=429,
            request=request,
        )
    try:
        # Input validation: reject empty or excessively long messages
        if not message or not message.strip():
            return _cors_json({"error": "Empty message"}, status_code=400, request=request)
        if len(message) > 2000:
            message = message[:2000]  # Truncate to avoid inflated token costs

        if not ANTHROPIC_API_KEY:
            return _cors_json({"error": "AI not configured"}, status_code=500)

        # Fail fast if oncofiles is down — don't waste API call on doomed tool use
        cb = oncofiles_client.get_circuit_breaker_status()
        if cb["state"] == "open":
            msg = (
                "Databáza je dočasne nedostupná. Skúste znova o minútu."
                if lang == "sk"
                else "Database temporarily unavailable. Try again in a minute."
            )
            return _cors_json({"response": msg, "cost": 0})

        pid = patient_id or DEFAULT_PATIENT_ID
        token = _get_token_for_patient(pid)

        # Load conversation thread (non-blocking, 3s timeout)
        thread = await _load_wa_thread(phone, token=token, patient_id=pid)

        # Build prompt with conversation context
        history_block = ""
        if thread:
            history_block = "Previous conversation:\n"
            for ex in thread:
                history_block += f"User: {ex.get('user', '')}\n"
                history_block += f"Assistant: {ex.get('assistant', '')}\n"
            history_block += "\n"

        # Build patient name map for name resolution
        patient_names = _get_patient_name_map()
        name_map_str = ", ".join(f"{k}={v}" for k, v in patient_names.items())
        current_display = patient_names.get(pid, pid)

        # Build user identity block
        user_block = ""
        if user_name:
            user_block += f"User name: {user_name}. "
        if user_roles:
            roles_str = ", ".join(user_roles) if isinstance(user_roles, list) else str(user_roles)
            user_block += f"Role: {roles_str}. "

        prompt = (
            f"{history_block}"
            f"User message via WhatsApp "
            f"(lang: {lang}, patient: {pid} = {current_display}):"
            f"\n\n{message}\n\n"
            f"# Context\n"
            f"{user_block}"
            f"Patient name map: {name_map_str}. "
            f"Currently showing: {pid} ({current_display}).\n"
            f"If user mentions another patient by name, tell them to "
            f"send 'prepni <slug>' to switch.\n\n"
            f"# Instructions\n"
            f"Respond naturally in "
            f"{'Slovak' if lang == 'sk' else 'English'}. "
            f"Address the user by name when natural. "
            f"Do NOT list available commands unless the user asks "
            f"for help. "
            f"If you cannot answer with available data, suggest ONE "
            f"specific command (e.g. 'labáky'). "
            f"Max 1500 chars."
        )

        result = await run_autonomous_task(
            prompt,
            max_turns=5,
            task_name="whatsapp_chat",
            model=AUTONOMOUS_MODEL_LIGHT,
            patient_id=pid,
        )

        response_text = result.get("response", "")
        if not response_text:
            response_text = (
                "Prepáčte, nepodarilo sa spracovať správu. Skúste 'pomoc'."
                if lang == "sk"
                else "Sorry, I couldn't process that. Try 'help'."
            )

        # Leave ~50 chars for the traceability disclaimer (#382) appended below.
        response_text = response_text[:1450]

        # Every AI-generated medical reply ends with a physician-verifies line
        # (#382 traceability). Suppressed only if the response is a pure error
        # fallback (no medical content to disclaim) or already ends with one.
        disclaimer_sk = "\n\n— Informatívne, overí lekár."
        disclaimer_en = "\n\n— Informational, your physician verifies."
        disclaimer = disclaimer_sk if lang == "sk" else disclaimer_en
        already_disclaimed = any(
            marker in response_text
            for marker in ("overí lekár", "physician verifies", "Informatívne", "Informational")
        )
        if response_text and not already_disclaimed:
            response_text = f"{response_text.rstrip()}{disclaimer}"

        # Quality signal tags for continuous improvement
        quality_tags: list[str] = [
            "wa:chat",
            f"lang:{lang}",
            f"patient:{pid}",
        ]
        if user_name:
            quality_tags.append(f"user:{user_name}")
        # Detect quality issues for audit
        response_lower = response_text.lower()
        if any(
            cmd in response_lower
            for cmd in ["labáky,", "laboráky,", "labky,", "lieky,", "pomoc.", "dostupné príkazy"]
        ):
            quality_tags.append("wa:quality:command_dump")
        if response_text == result.get("response", ""):
            pass  # normal
        else:
            quality_tags.append("wa:quality:fallback")
        if len(response_text) > 1200:
            quality_tags.append("wa:quality:long")

        # Save updated thread (non-blocking)
        thread.append({"user": message[:500], "assistant": response_text[:500]})
        asyncio.create_task(_save_wa_thread(phone, thread, token=token, patient_id=pid))

        return _cors_json(
            {
                "response": response_text,
                "cost": result.get("cost", 0),
                "thread_length": min(len(thread), _WA_THREAD_MAX_EXCHANGES),
                "quality_tags": quality_tags,
            }
        )
    except Exception as e:
        record_suppressed_error("api_whatsapp_chat", "chat", e)
        return _cors_json(
            {
                "response": "Error processing message. Try 'help'.",
                "error": str(e),
            }
        )


async def api_whatsapp_media(request: Request) -> JSONResponse:
    """POST /api/internal/whatsapp-media — process WhatsApp media attachment.

    Expects JSON body: {media_base64, content_type, filename, phone, patient_id}
    Uploads to oncofiles, triggers AI analysis, returns document_id + summary.
    """
    try:
        body = await request.json()
    except Exception:
        return _cors_json({"error": "Invalid JSON body"}, status_code=400, request=request)

    media_base64 = (body.get("media_base64") or "").strip()
    content_type = (body.get("content_type") or "").strip()
    filename = (body.get("filename") or "").strip()
    phone = (body.get("phone") or "").strip()
    patient_id = (body.get("patient_id") or "").strip()

    if not media_base64 or not content_type or not filename:
        return _cors_json(
            {"error": "media_base64, content_type, and filename are required"},
            status_code=400,
            request=request,
        )

    # Content type allowlist — prevent content injection
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "application/pdf",
    }
    if content_type not in allowed_types:
        return _cors_json(
            {"error": f"Unsupported content type: {content_type}"},
            status_code=400,
            request=request,
        )

    # FUP limit check (per-patient)
    if not _check_fup_ai_query(patient_id or "global"):
        return _cors_json(
            {"error": "Monthly AI query limit exceeded"},
            status_code=429,
            request=request,
        )

    # Step 1: Upload document to oncofiles
    try:
        upload_result = await oncofiles_client.upload_document_via_mcp(
            content_base64=media_base64,
            filename=filename,
            content_type=content_type,
            patient_id=patient_id,
        )
    except Exception as exc:
        record_suppressed_error("api_whatsapp_media", "upload_document", exc)
        return _cors_json(
            {"error": f"Failed to upload document: {exc}"},
            status_code=502,
            request=request,
        )

    document_id = ""
    if isinstance(upload_result, dict):
        document_id = str(upload_result.get("document_id", upload_result.get("id", "")))

    if not document_id:
        _logger.error("upload_document returned no document_id: %s", upload_result)
        return _cors_json(
            {"error": "Upload succeeded but no document_id returned"},
            status_code=502,
            request=request,
        )

    # Step 2: Trigger OCR + AI analysis
    summary = ""
    if document_id:
        try:
            enhance_result = await oncofiles_client.enhance_document_via_mcp(document_id)
            if isinstance(enhance_result, dict):
                summary = enhance_result.get("summary", enhance_result.get("text", ""))
        except Exception as exc:
            record_suppressed_error("api_whatsapp_media", "enhance_document", exc)
            summary = "Document uploaded but analysis failed."

    # Step 3: Trigger document pipeline (lab_sync, dose_extraction, etc.)
    # Same logic as api_document_webhook but inline to avoid duplicate upload
    pipeline_status = "not_triggered"
    if document_id:
        try:
            from .autonomous_tasks import run_document_pipeline

            pid = patient_id or DEFAULT_PATIENT_ID
            doc_id_int = int(document_id)
            metadata = {
                "filename": filename,
                "category": "",
                "uploaded_at": "",
            }
            asyncio.create_task(run_document_pipeline(doc_id_int, metadata, patient_id=pid))
            pipeline_status = "started"
            _logger.info(
                "Document pipeline triggered from WhatsApp media: doc_id=%s, patient=%s",
                document_id,
                pid,
            )
        except Exception as exc:
            record_suppressed_error("api_whatsapp_media", "trigger_pipeline", exc)
            pipeline_status = "failed"

    _logger.info(
        "WhatsApp media processed: phone=%s, file=%s, doc_id=%s, pipeline=%s",
        phone[:6] + "..." if phone else "?",
        filename,
        document_id,
        pipeline_status,
    )

    return _cors_json(
        {
            "status": "ok",
            "document_id": document_id,
            "summary": summary,
            "pipeline": pipeline_status,
        },
        request=request,
    )


async def api_whatsapp_voice(request: Request) -> JSONResponse:
    """POST /api/internal/whatsapp-voice — transcribe voice note via Whisper.

    Accepts {audio_base64, content_type, phone, patient_id, lang_hint}.
    Returns {text, duration_s, cost, lang} or {error}.
    Audio is ephemeral — never stored.
    """
    # Parse body with 15MB limit (audio base64 can exceed default 1MB)
    import json as _json

    try:
        raw = await request.body()
        if len(raw) > 15_000_000:
            return _cors_json({"error": "Request too large"}, status_code=400, request=request)
        body = _json.loads(raw)
    except Exception:
        return _cors_json({"error": "Invalid JSON"}, status_code=400, request=request)

    audio_b64 = body.get("audio_base64", "")
    content_type = body.get("content_type", "audio/ogg")
    patient_id = body.get("patient_id", "q1b")
    lang_hint = body.get("lang_hint", "sk")

    if not audio_b64:
        return _cors_json({"error": "Missing audio_base64"}, status_code=400, request=request)

    import base64

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return _cors_json({"error": "Invalid base64 audio"}, status_code=400, request=request)

    # Size guards
    if len(audio_bytes) < 1024:
        return _cors_json({"error": "Audio too short"}, status_code=400, request=request)
    if len(audio_bytes) > 10 * 1024 * 1024:
        return _cors_json({"error": "Audio too large (max 10MB)"}, status_code=400, request=request)

    from .whisper_client import transcribe_audio

    result = await transcribe_audio(
        audio_bytes=audio_bytes,
        content_type=content_type,
        patient_id=patient_id,
        lang_hint=lang_hint,
    )

    if "error" in result:
        return _cors_json(result, status_code=503, request=request)

    return _cors_json(result, request=request)


async def api_whatsapp_history(request: Request) -> JSONResponse:
    """GET /api/whatsapp/history — WhatsApp message history for audit trail."""
    patient_id = _get_patient_id(request)
    token = _get_token_for_patient(patient_id)
    limit = min(100, max(1, int(request.query_params.get("limit", "50") or "50")))
    search = request.query_params.get("search", "").strip()

    try:
        result = await asyncio.wait_for(
            oncofiles_client.search_conversations(
                entry_type="whatsapp",
                limit=limit,
                token=token,
            ),
            timeout=15.0,
        )
        entries = _extract_list(result, "entries")

        messages: list[dict] = []
        for e in entries:
            content = e.get("content", "")
            # Parse structured content from log_conversation format
            phone = ""
            user_msg = ""
            bot_response = ""
            for line in content.split("\n"):
                if line.startswith("**From**:"):
                    phone = line.replace("**From**:", "").strip()
                elif line.startswith("**Message**:"):
                    user_msg = line.replace("**Message**:", "").strip()
                elif line.startswith("**Response**:"):
                    # Everything after this line is the response
                    idx = content.index("**Response**:")
                    bot_response = content[idx + len("**Response**:") :].strip()
                    break

            # Drop Twilio delivery-status callbacks that were (pre-#427) logged
            # as fake conversations — user_message = "[status:sent]" and
            # bot_response = MessageSID. Detect by the unambiguous "[status:"
            # prefix OR by the sys:status_callback tag. See
            # dashboard/server/api/webhook/whatsapp-status.post.ts.
            tags_raw = e.get("tags", [])
            tags_list = (
                tags_raw
                if isinstance(tags_raw, list)
                else [t.strip() for t in str(tags_raw).split(",") if t.strip()]
            )
            if user_msg.startswith("[status:") or "sys:status_callback" in tags_list:
                continue

            msg = {
                "id": e.get("id"),
                "date": e.get("created_at", ""),
                "phone_masked": phone[-4:].rjust(len(phone), "*") if phone else "",
                "user_message": user_msg,
                "bot_response": bot_response,
                "title": e.get("title", ""),
                "tags": tags_list,
            }
            # Fulltext search filter
            if (
                search
                and search.lower()
                not in (f"{msg['user_message']} {msg['bot_response']} {msg['title']}").lower()
            ):
                continue
            messages.append(msg)

        return _cors_json({"messages": messages, "total": len(messages)}, request=request)
    except Exception as exc:
        record_suppressed_error("api_whatsapp_history", "fetch", exc)
        return _cors_json({"messages": [], "total": 0, "error": str(exc)}, request=request)


async def api_whatsapp_status(request: Request) -> JSONResponse:
    """GET /api/whatsapp/status — WhatsApp integration status.

    Returns: approved phones count, active onboarding sessions,
    recent message stats, and circuit breaker state.
    """
    # Approved phones — union of:
    #  (1) explicit admin-approved phones (_approved_phones, loaded from
    #      oncofiles agent_state["phones"] under agent_id=approved_phones)
    #  (2) phones configured in the ROLE_MAP (advocates + physicians + family
    #      whose access is granted at env/DB layer, never went through the
    #      explicit admin-approval flow)
    # Before #379, only (1) was counted — so a live advocate phone showed 0.
    if not _approved_phones_loaded:
        await load_approved_phones()

    role_map_phones: set[str] = set()
    try:
        from .api_admin import _load_access_rights

        role_map = await _load_access_rights()
        if isinstance(role_map, dict):
            for entry in role_map.values():
                if isinstance(entry, dict):
                    phone = entry.get("phone")
                    if isinstance(phone, str) and phone.strip():
                        role_map_phones.add(phone.strip())
    except Exception as exc:
        record_suppressed_error("api_whatsapp_status", "role_map_phones", exc)

    all_phones = _approved_phones | role_map_phones

    # Recent WhatsApp conversations — filter by entry_type="whatsapp".
    # Bug before #419: passed query="sys:whatsapp", which is not a valid
    # search_conversations kwarg. The call raised TypeError, was silently
    # suppressed, and the counter sat at 0 while WhatsApp was actively in use.
    recent_count = 0
    try:
        result = await asyncio.wait_for(
            oncofiles_client.search_conversations(
                entry_type="whatsapp",
                limit=100,
            ),
            timeout=8,
        )
        entries = _extract_list(result, "entries")
        recent_count = len(entries)
    except Exception as exc:
        record_suppressed_error("api_whatsapp_status", "search_conversations", exc)

    cb_status = oncofiles_client.get_circuit_breaker_status()

    return _cors_json(
        {
            "status": "ok" if cb_status["state"] == "closed" else "degraded",
            "approved_phones": len(all_phones),
            "phone_patient_map": {p: pid for p, pid in _phone_patient_map.items()},
            "recent_conversations": recent_count,
            "circuit_breaker_state": cb_status["state"],
        },
        request=request,
    )
