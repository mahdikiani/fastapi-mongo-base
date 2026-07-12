"""Localized message helpers and shared catalog strings."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

LocalizedMessage = dict[str, str]

DEFAULT_LOCALES: tuple[str, ...] = ("en", "fa")

VALIDATION_ERROR_MESSAGE: LocalizedMessage = {
    "en": "Validation error",
    "fa": "اطلاعات وارد شده صحیح نیست",
}


def localized(
    en: str,
    fa: str | None = None,
    **others: str,
) -> LocalizedMessage:
    """Build a locale-keyed message dictionary."""
    messages: LocalizedMessage = {"en": en}
    if fa is not None:
        messages["fa"] = fa
    messages.update(others)
    return messages


def parse_accept_language(header: str | None) -> list[str]:
    """
    Parse an Accept-Language header into ordered locale codes.

    Quality values are ignored; primary language subtags are returned
    in header order (for example ``fa-IR, en;q=0.8`` -> ``["fa", "en"]``).
    """
    if not header:
        return []

    locales: list[str] = []
    for part in header.split(","):
        tag = part.strip().split(";", maxsplit=1)[0].strip()
        if not tag:
            continue
        code = tag.split("-", maxsplit=1)[0].lower()
        if code not in locales:
            locales.append(code)
    return locales


def select_localized_messages(
    messages: LocalizedMessage,
    requested_locales: list[str],
) -> LocalizedMessage:
    """
    Return message entries matching requested locales.

    When no locale matches, the full message dictionary is returned.
    """
    if not requested_locales:
        return messages

    selected = {
        locale: messages[locale]
        for locale in requested_locales
        if locale in messages
    }
    return selected or messages


def resolve_request_locales(request: "Request") -> list[str]:
    """Extract ordered locale codes from a FastAPI request."""
    return parse_accept_language(request.headers.get("accept-language"))


def select_request_messages(
    request: "Request", messages: LocalizedMessage
) -> LocalizedMessage:
    """Select localized messages based on request Accept-Language."""
    return select_localized_messages(
        messages,
        resolve_request_locales(request),
    )
