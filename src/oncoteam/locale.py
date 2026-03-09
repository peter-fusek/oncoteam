"""Bilingual locale utilities for SK/EN content."""

from __future__ import annotations

from typing import Any

# Type alias: bilingual string = {"en": "...", "sk": "..."}
type BiStr = dict[str, str]

DEFAULT_LANG = "sk"
SUPPORTED_LANGS = ("sk", "en")


def L(sk: str, en: str) -> BiStr:  # noqa: N802
    """Create a bilingual string dict."""
    return {"sk": sk, "en": en}


def resolve(value: Any, lang: str = DEFAULT_LANG) -> Any:
    """Resolve a bilingual value to the requested language.

    - BiStr dict {"sk": "...", "en": "..."} → returns the correct language
    - Plain str → returned as-is
    - list → recursively resolve each element
    - dict with "sk"/"en" keys → resolve as BiStr
    - dict without "sk"/"en" → recursively resolve values
    - Other types → returned as-is
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    if isinstance(value, dict):
        # BiStr detection: has both sk and en keys, and they're strings
        if "sk" in value and "en" in value and isinstance(value["sk"], str):
            return value.get(lang, value.get(DEFAULT_LANG, ""))
        # Regular dict: resolve values recursively
        return {k: resolve(v, lang) for k, v in value.items()}

    if isinstance(value, list):
        return [resolve(item, lang) for item in value]

    return value


def resolve_dict(data: dict, lang: str = DEFAULT_LANG) -> dict:
    """Resolve all bilingual values in a dict."""
    return {k: resolve(v, lang) for k, v in data.items()}


def get_lang(request: Any) -> str:
    """Extract language from request query params. Default: sk."""
    lang = DEFAULT_LANG
    if hasattr(request, "query_params"):
        lang = request.query_params.get("lang", DEFAULT_LANG)
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    return lang
