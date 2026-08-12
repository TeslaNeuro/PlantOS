"""Unified plant state.

Reality and controller belief share this schema. The simulator keeps two
instances and never copies future reality into the controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from plantos.config import ElectrolyserStatus, PlantMode


@dataclass
class FaultRecord:
    fault_id: str
    fault_type: str
    component: str
    severity: float
    start_hour: float
    active: bool = True


@dataclass
class PlantState:
    hour: float = 0.0
    timestamp_hour: float = 0.0

    irradiance_wm2: float = 0.0
    ambient_temp_c: float = 15.0
    cloud_cover: float = 0.0

    solar_power_mw: float = 0.0
    solar_available_mw: float = 0.0
    curtailed_power_mw: float = 0.0

    battery_soc: float = 0.55
    battery_soh: float = 1.0
    battery_power_mw: float = 0.0  # +discharge / -charge
    battery_throughput_mwh: float = 0.0
    battery_temp_c: float = 25.0

    electrolyser_power_mw: float = 0.0
    electrolyser_health: float = 1.0
    electrolyser_temperature_c: float = 25.0
    electrolyser_status: ElectrolyserStatus = ElectrolyserStatus.OFF
    electrolyser_startup_progress: float = 0.0
    hydrogen_rate_kgph: float = 0.0

    co2_capture_power_mw: float = 0.0
    co2_capture_health: float = 1.0
    co2_rate_kgph: float = 0.0

    methanation_load: float = 0.0  # 0-1 commanded conversion level
    methanation_power_mw: float = 0.0
    methanation_health: float = 1.0
    methanation_temperature_c: float = 25.0
    methane_rate_kgph: float = 0.0
    methanation_warmup: float = 0.0

    h2_stored_kg: float = 120.0
    co2_stored_kg: float = 400.0
    methane_total_kg: float = 0.0
    hydrogen_total_kg: float = 0.0
    co2_total_kg: float = 0.0

    plant_load_mw: float = 0.0
    plant_mode: PlantMode = PlantMode.NORMAL
    active_faults: list[FaultRecord] = field(default_factory=list)

    isolated_components: set[str] = field(default_factory=set)
    available_capacity: dict[str, float] = field(default_factory=dict)

    def copy(self) -> PlantState:
        return replace(
            self,
            active_faults=[replace(f) for f in self.active_faults],
            isolated_components=set(self.isolated_components),
            available_capacity=dict(self.available_capacity),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "timestamp_hour": self.timestamp_hour,
            "irradiance_wm2": self.irradiance_wm2,
            "ambient_temp_c": self.ambient_temp_c,
            "cloud_cover": self.cloud_cover,
            "solar_power_mw": self.solar_power_mw,
            "solar_available_mw": self.solar_available_mw,
            "curtailed_power_mw": self.curtailed_power_mw,
            "battery_soc": self.battery_soc,
            "battery_soh": self.battery_soh,
            "battery_power_mw": self.battery_power_mw,
            "battery_throughput_mwh": self.battery_throughput_mwh,
            "battery_temp_c": self.battery_temp_c,
            "electrolyser_power_mw": self.electrolyser_power_mw,
            "electrolyser_health": self.electrolyser_health,
            "electrolyser_temperature_c": self.electrolyser_temperature_c,
            "electrolyser_status": self.electrolyser_status.value,
            "hydrogen_rate_kgph": self.hydrogen_rate_kgph,
            "co2_capture_power_mw": self.co2_capture_power_mw,
            "co2_capture_health": self.co2_capture_health,
            "co2_rate_kgph": self.co2_rate_kgph,
            "methanation_load": self.methanation_load,
            "methanation_power_mw": self.methanation_power_mw,
            "methanation_health": self.methanation_health,
            "methanation_temperature_c": self.methanation_temperature_c,
            "methane_rate_kgph": self.methane_rate_kgph,
            "h2_stored_kg": self.h2_stored_kg,
            "co2_stored_kg": self.co2_stored_kg,
            "methane_total_kg": self.methane_total_kg,
            "plant_load_mw": self.plant_load_mw,
            "plant_mode": self.plant_mode.value,
            "active_faults": [
                {
                    "fault_id": f.fault_id,
                    "fault_type": f.fault_type,
                    "component": f.component,
                    "severity": f.severity,
                    "start_hour": f.start_hour,
                    "active": f.active,
                }
                for f in self.active_faults
            ],
            "isolated_components": sorted(self.isolated_components),
        }
