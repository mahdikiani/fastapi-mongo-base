"""Tests for BSON conversion helpers."""

from __future__ import annotations

import uuid
from decimal import Decimal

from bson import Binary
from bson.decimal128 import Decimal128

from src.fastapi_mongo_base.utils import bsontools


def test_decimal_amount_from_decimal128() -> None:
    """decimal_amount converts BSON Decimal128."""
    value = Decimal128(Decimal("12.34"))
    assert bsontools.decimal_amount(value) == Decimal("12.34")


def test_decimal_amount_from_scalar_and_none() -> None:
    """decimal_amount handles scalars and None."""
    assert bsontools.decimal_amount(None) is None
    assert bsontools.decimal_amount("9.99") == Decimal("9.99")
    assert bsontools.decimal_amount(5) == Decimal("5")


def test_get_bson_value_converts_nested_structures() -> None:
    """get_bson_value recursively converts supported types."""
    uid = uuid.uuid4()
    payload = {
        "amount": Decimal("1.5"),
        "raw": b"bytes",
        "id": uid,
        "items": [Decimal("2")],
    }
    converted = bsontools.get_bson_value(payload)
    assert isinstance(converted["amount"], Decimal128)
    assert isinstance(converted["raw"], Binary)
    assert isinstance(converted["id"], Binary)
    assert isinstance(converted["items"][0], Decimal128)
