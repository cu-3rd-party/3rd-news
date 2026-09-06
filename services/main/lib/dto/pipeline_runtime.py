from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PipelineRuntime:
    sessions: Any
    client: Any
    node_id: str
    public_base_url: str
    callback_audience: str
    callback_timeout: int
    request_timeout: float
    lease_seconds: int
    poll_seconds: float
    cooldown: int
    raw_retention_days: int
    protector: Any
