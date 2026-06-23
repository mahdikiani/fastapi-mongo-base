"""Bilingual (en/fa) helpers for HTTP error messages."""

from __future__ import annotations

from fastapi import Request

SUPPORTED_LOCALES = ("en", "fa")
DEFAULT_LOCALE = "en"
FALLBACK_LOCALE = "en"


def build_messages(en: str, fa: str | None = None) -> dict[str, str]:
    """
    Build a bilingual language map with English and Persian text.

    Always includes both ``en`` and ``fa``. When Persian text is omitted,
    ``fa`` falls back to the English string.
    """
    return {"en": en, "fa": fa if fa is not None else en}


def normalize_messages(
    value: str | dict[str, str] | None,
    *,
    fallback: str,
) -> dict[str, str]:
    """Normalize catalog entries that may be a plain string or a locale map."""
    if value is None:
        return build_messages(fallback)
    if isinstance(value, str):
        return build_messages(value)
    messages = dict(value)
    if "en" not in messages and fallback:
        messages["en"] = fallback
    if "fa" not in messages and "en" in messages:
        messages["fa"] = messages["en"]
    return messages


def resolve_locale(request: Request | None) -> str:
    """Resolve ``en`` or ``fa`` from the ``Accept-Language`` header."""
    if request is None:
        return DEFAULT_LOCALE

    header = request.headers.get("accept-language", "")
    if not header:
        return DEFAULT_LOCALE

    for part in header.split(","):
        token = part.split(";")[0].strip().lower()
        if not token:
            continue
        if token.startswith("fa"):
            return "fa"
        if token.startswith("en"):
            return "en"
    return DEFAULT_LOCALE


def localized_text(
    message: dict[str, str],
    locale: str | None = None,
) -> str:
    """Return the best available translation for *locale*."""
    if not message:
        return ""
    locale = locale or DEFAULT_LOCALE
    if locale in message:
        return message[locale]
    if FALLBACK_LOCALE in message:
        return message[FALLBACK_LOCALE]
    return next(iter(message.values()))


def resolve_detail(
    *,
    message: dict[str, str],
    detail: str | None,
    locale: str | None = None,
) -> str:
    """
    Pick ``detail`` for the JSON body.

    Explicit ``detail`` wins unless it matches the default English ``message``
    (auto-generated), in which case the requested locale is used.
    """
    locale = locale or DEFAULT_LOCALE
    localized = localized_text(message, locale)
    if detail is None:
        return localized
    if "en" in message and detail == message["en"]:
        return localized
    return detail


def http_error_content(
    request: Request | None,
    *,
    message: dict[str, str],
    error: str,
    detail: str | None,
    data: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    Build the standard error JSON payload.

    Response always includes the full ``message`` map (``en`` and ``fa`` when
    available). ``detail`` follows ``Accept-Language`` when not set explicitly.
    """
    locale = resolve_locale(request)
    return {
        "message": message,
        "error": error,
        "detail": resolve_detail(
            message=message, detail=detail, locale=locale
        ),
        **(data or {}),
    }
