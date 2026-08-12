"""Actuator commands issued by a controller.

Commands are setpoints. The plant physics clip them to what is physically
possible given ramps, faults, storage and available power.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ControlAction:
    electrolyser_power_mw: float = 0.0
    co2_capture_power_mw: float = 0.0
    methanation_load: float = 0.0  # 0-1
    battery_power_mw: float = 0.0  # +discharge, -charge; 0 = idle
    curtailment_mw: float = 0.0
    electrolyser_run: bool = False
    isolate: set[str] = field(default_factory=set)
    recover: set[str] = field(default_factory=set)
    explanation: str = ""
    reason_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "electrolyser_power_mw": self.electrolyser_power_mw,
            "co2_capture_power_mw": self.co2_capture_power_mw,
            "methanation_load": self.methanation_load,
            "battery_power_mw": self.battery_power_mw,
            "curtailment_mw": self.curtailment_mw,
            "electrolyser_run": self.electrolyser_run,
            "isolate": sorted(self.isolate),
            "recover": sorted(self.recover),
            "explanation": self.explanation,
            "reason_code": self.reason_code,
            "metadata": self.metadata,
        }
