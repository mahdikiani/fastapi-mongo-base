"""Request-scoped audit actor context and enable flag."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditActor:
    """Who performed a mutating action."""

    tenant_id: str | None = None
    user_id: str | None = None
    workspace_id: str | None = None
    sub_type: str | None = None
    principal_id: str | None = None


_audit_actor: ContextVar[AuditActor | None] = ContextVar(
    "audit_actor",
    default=None,
)
_audit_enabled: ContextVar[bool | None] = ContextVar(
    "audit_enabled",
    default=None,
)

# Process-level default, synced from settings at DB init.
_process_audit_enabled: bool = False


def set_audit_enabled(enabled: bool) -> None:
    """Set the process-level audit enable flag (from settings)."""
    global _process_audit_enabled
    _process_audit_enabled = enabled


def is_audit_enabled() -> bool:
    """Return whether audit logging is active for this process/request."""
    override = _audit_enabled.get()
    if override is not None:
        return override
    return _process_audit_enabled


def get_audit_actor() -> AuditActor | None:
    """Return the bound audit actor, if any."""
    return _audit_actor.get()


def bind_audit_actor(actor: AuditActor | None) -> Token:
    """Bind an audit actor to the current context."""
    return _audit_actor.set(actor)


def reset_audit_actor(token: Token) -> None:
    """Reset the audit actor context to a previous token."""
    _audit_actor.reset(token)


def actor_from_user(user: object) -> AuditActor:
    """Build an ``AuditActor`` from a USSO-like user object."""
    claims = getattr(user, "claims", None) or {}
    sub_type = claims.get("sub_type") if isinstance(claims, dict) else None
    sub_type = str(sub_type) if sub_type is not None else "user"

    uid = getattr(user, "uid", None) or getattr(user, "sub", None)
    user_id = getattr(user, "user_id", None)
    principal_id = str(uid) if uid is not None else None
    actor_user_id = str(uid or user_id) if (uid or user_id) else None

    workspace_id = getattr(user, "workspace_id", None)
    tenant_id = getattr(user, "tenant_id", None)

    return AuditActor(
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        user_id=actor_user_id,
        workspace_id=str(workspace_id) if workspace_id else None,
        sub_type=sub_type,
        principal_id=principal_id,
    )


@contextmanager
def audit_actor_scope(
    user: object | None = None,
    *,
    user_id: str | None = None,
) -> Iterator[None]:
    """
    Bind audit actor for the duration of a mutating router call.

    Prefer passing the full ``user`` when available (USSO). ``user_id`` alone
    is used by simpler routers.
    """
    if user is not None:
        actor = actor_from_user(user)
    elif user_id is not None:
        actor = AuditActor(
            user_id=user_id,
            sub_type="user",
            principal_id=user_id,
        )
    else:
        actor = None
    token = bind_audit_actor(actor)
    try:
        yield
    finally:
        reset_audit_actor(token)
