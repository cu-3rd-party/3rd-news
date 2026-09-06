from typing import Any
from unicodedata import category


def reject_unsafe_controls(value: Any, path: str = "payload") -> None:
    if isinstance(value, str):
        if any(category(character) == "Cc" and character not in "\t\n\r" for character in value):
            raise ValueError(f"{path} contains a forbidden control character")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            reject_unsafe_controls(key, f"{path}.key")
            reject_unsafe_controls(nested, f"{path}.value")
        return
    if isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            reject_unsafe_controls(nested, f"{path}[{index}]")
