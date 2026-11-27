"""Mask data classes in a tool result before it enters the conversation (rule 7).

A tool operation may tag result fields by data class:

    operations:
      - name: get_payment
        side_effects: read
        fields: {debtor.name: pii, debtor.account: pii, postings.*.iban: pii}

A path is dotted; ``*`` matches every element of a list or every key of a mapping.
When a redacting policy covers a class the operation tags nothing for, the whole
result is masked: an untagged result cannot be shown to be free of that class, so it
fails closed.
"""
from __future__ import annotations

import copy
from typing import Any

from ..agents import operations


def mask(data_class: str) -> str:
    return f"[REDACTED:{data_class}]"


def _apply(value: Any, parts: list[str], data_class: str) -> Any:
    if not parts:
        return mask(data_class)
    head, rest = parts[0], parts[1:]
    if isinstance(value, dict):
        keys = list(value) if head == "*" else [head] if head in value else []
        for k in keys:
            value[k] = _apply(value[k], rest, data_class)
    elif isinstance(value, list):
        idx = range(len(value)) if head == "*" else \
            [int(head)] if head.isdigit() and int(head) < len(value) else []
        for i in idx:
            value[i] = _apply(value[i], rest, data_class)
    return value


def redact(result: Any, tool: dict, operation: str, classes: tuple[str, ...] | list[str]) -> Any:
    """A copy of ``result`` with every field of the given classes masked."""
    if not classes:
        return result
    tags = (operations(tool).get(operation) or {}).get("fields") or {}
    out = copy.deepcopy(result)
    for data_class in classes:
        paths = [p for p, c in tags.items() if c == data_class]
        if not paths:
            return {"redacted": True, "classes": sorted(classes),
                    "reason": f"{tool.get('id')}.{operation} tags no fields as "
                              f"{data_class}, so the whole result is withheld"}
        for path in paths:
            out = _apply(out, path.split("."), data_class)
    return out
