"""Tests for TenantSubjectEntitySchema XOR validation."""

import pytest
from pydantic import ValidationError

from src.fastapi_mongo_base.schemas import TenantSubjectEntitySchema


class _SubjectSchema(TenantSubjectEntitySchema):
    """Concrete schema for validation tests."""

    label: str = "test"


def test_subject_requires_exactly_one_id() -> None:
    """Neither or both subject ids must fail validation."""
    with pytest.raises(ValidationError):
        _SubjectSchema(tenant_id="t1", user_id=None, workspace_id=None)
    with pytest.raises(ValidationError):
        _SubjectSchema(
            tenant_id="t1",
            user_id="u1",
            workspace_id="w1",
        )


def test_subject_accepts_user_only() -> None:
    """User-only subject is valid."""
    item = _SubjectSchema(tenant_id="t1", user_id="u1", workspace_id=None)
    assert item.user_id == "u1"
    assert item.workspace_id is None


def test_subject_accepts_workspace_only() -> None:
    """Workspace-only subject is valid."""
    item = _SubjectSchema(tenant_id="t1", user_id=None, workspace_id="w1")
    assert item.workspace_id == "w1"
    assert item.user_id is None
