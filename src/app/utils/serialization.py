from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


class AppJsonEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def to_json(data: Any) -> str:
    return json.dumps(data, cls=AppJsonEncoder, ensure_ascii=False, indent=2)


def from_json(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        msg = "Expected a JSON object."
        raise ValueError(msg)
    return value
