"""Turn a Pydantic model into a JSON schema that strict structured-output modes accept.

Both Claude structured outputs and OpenAI-style `json_schema` strict mode require every object
to list all of its properties as required and to set `additionalProperties: false`, and they
reject numeric/string constraints. Optional fields stay nullable, so "required" is harmless.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

_UNSUPPORTED_KEYS = {
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
}


def _tighten(node: Any) -> Any:
    if isinstance(node, dict):
        node = {k: _tighten(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYS}
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        return node
    if isinstance(node, list):
        return [_tighten(item) for item in node]
    return node


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    return _tighten(copy.deepcopy(model.model_json_schema()))
