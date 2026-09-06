from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

SCORE_DIMENSIONS = frozenset({"urgency", "impact", "editorial_priority"})


class EditorialRuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = False
    definition: dict[str, Any]

    @model_validator(mode="after")
    def validate_definition(self) -> EditorialRuleInput:
        unknown = self.definition.keys() - {"when", "set", "add", "stop", "priority"}
        if unknown:
            raise ValueError(f"unknown rule fields: {', '.join(sorted(unknown))}")
        conditions = self.definition.get("when", {})
        if not isinstance(conditions, dict) or not all(
            isinstance(axis, str)
            and (
                isinstance(expected, str)
                or isinstance(expected, list)
                and all(isinstance(value, str) for value in expected)
            )
            for axis, expected in conditions.items()
        ):
            raise ValueError("rule when must map axes to a string or list of strings")
        for operation in ("set", "add"):
            values = self.definition.get(operation, {})
            if not isinstance(values, dict) or values.keys() - SCORE_DIMENSIONS:
                raise ValueError(f"rule {operation} contains an invalid score dimension")
            if not all(
                isinstance(value, int) and not isinstance(value, bool) for value in values.values()
            ):
                raise ValueError(f"rule {operation} values must be integers")
        if "priority" in self.definition and not isinstance(self.definition["priority"], int):
            raise ValueError("rule priority must be an integer")
        if "stop" in self.definition and not isinstance(self.definition["stop"], bool):
            raise ValueError("rule stop must be a boolean")
        return self
