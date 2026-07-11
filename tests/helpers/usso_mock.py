"""Install a minimal ``usso`` stub for router tests without the extra."""

from __future__ import annotations

import sys
from types import ModuleType


class MockUserData:
    """Minimal stand-in for ``usso.user.UserData``."""

    def __init__(self, **kwargs: object) -> None:
        """Build a user from JWT-like claim kwargs."""
        self.iss = kwargs.get("iss")
        self.sub = kwargs.get("sub")
        self.aud = kwargs.get("aud")
        self.tenant_id = kwargs.get("tenant_id")
        self.workspace_id = kwargs.get("workspace_id")
        self.scopes = kwargs.get("scopes")
        self.roles = kwargs.get("roles")
        self.claims = dict(kwargs)

    @property
    def user_id(self) -> str:
        """Explicit user_id claim, or sub when absent."""
        if self.claims and "user_id" in self.claims:
            return str(self.claims["user_id"])
        return self.sub or ""

    @property
    def uid(self) -> str:
        """Alias for user_id used by ownership helpers."""
        return self.user_id

    def model_dump(self, **_kwargs: object) -> dict[str, object]:
        """Return claim payload for authorization filters."""
        return dict(self.claims)


def install_usso_mock() -> None:
    """Register stub ``usso`` modules in ``sys.modules``."""
    if "usso" in sys.modules:
        return

    authorization = ModuleType("usso.authorization")
    authorization.owner_authorization = lambda **_kwargs: False

    def _check_access(**kwargs: object) -> bool:
        scopes = kwargs.get("user_scopes") or []
        return "*:*" in scopes or any(
            not str(scope).endswith("?")
            and "?" not in str(scope).split(":", 2)[-1]
            for scope in scopes
            if ":" in str(scope)
        )

    authorization.check_access = _check_access
    authorization.get_scope_filters = lambda **_kwargs: []
    authorization.broadest_scope_filter = lambda scopes: (
        scopes[0] if scopes else {}
    )

    config_mod = ModuleType("usso.config")

    class _APIHeaderConfig:
        def __init__(self, **kwargs: object) -> None:
            self.header_name = kwargs.get("header_name", "x-api-key")
            self.verify_endpoint = kwargs.get("verify_endpoint", "")

    class _AuthConfig:
        def __init__(self, **kwargs: object) -> None:
            self.jwks_url = kwargs.get("jwks_url", "")
            self.api_key_header = kwargs.get("api_key_header")

    config_mod.APIHeaderConfig = _APIHeaderConfig
    config_mod.AuthConfig = _AuthConfig

    exceptions_mod = ModuleType("usso.exceptions")

    class _USSOError(Exception):
        """Base USSO error stub."""

    class _PermissionDeniedError(_USSOError):
        """Permission denied stub."""

    exceptions_mod.USSOException = _USSOError
    exceptions_mod.PermissionDenied = _PermissionDeniedError

    integrations_fastapi = ModuleType("usso.integrations.fastapi")

    class _USSOAuthentication:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __call__(self, _request: object) -> MockUserData:
            return MockUserData(sub="mock-user")

    integrations_fastapi.USSOAuthentication = _USSOAuthentication
    integrations_fastapi.EXCEPTION_HANDLERS = {}

    integrations = ModuleType("usso.integrations")
    integrations.fastapi = integrations_fastapi

    user_mod = ModuleType("usso.user")
    user_mod.UserData = MockUserData

    usso_pkg = ModuleType("usso")
    usso_pkg.UserData = MockUserData
    usso_pkg.authorization = authorization

    sys.modules["usso"] = usso_pkg
    sys.modules["usso.user"] = user_mod
    sys.modules["usso.authorization"] = authorization
    sys.modules["usso.config"] = config_mod
    sys.modules["usso.exceptions"] = exceptions_mod
    sys.modules["usso.integrations"] = integrations
    sys.modules["usso.integrations.fastapi"] = integrations_fastapi
