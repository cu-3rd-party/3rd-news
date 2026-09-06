from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from ..base import Base

JsonObject = dict[str, Any]
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
JSON_OBJECT = MutableDict.as_mutable(JSON().with_variant(JSONB(), "postgresql"))
JSON_LIST = MutableList.as_mutable(JSON().with_variant(JSONB(), "postgresql"))

__all__ = [
    "Base",
    "BigInteger",
    "Boolean",
    "CheckConstraint",
    "DateTime",
    "Float",
    "ForeignKey",
    "Integer",
    "JSON_LIST",
    "JSON_OBJECT",
    "JSON_TYPE",
    "JsonObject",
    "LargeBinary",
    "Mapped",
    "String",
    "Text",
    "UniqueConstraint",
    "Uuid",
    "func",
    "mapped_column",
    "relationship",
]
