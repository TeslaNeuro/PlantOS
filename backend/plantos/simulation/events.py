"""Machine-readable decision log with a human-readable explanation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionEvent:
    hour: float
    reason_code: str
    explanation: str
    mode: str
    action: dict[str, Any] = field(default_factory=dict)
    diagnosis: dict[str, Any] | None = None
    detection: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "mode": self.mode,
            "action": self.action,
            "diagnosis": self.diagnosis,
            "detection": self.detection,
        }
