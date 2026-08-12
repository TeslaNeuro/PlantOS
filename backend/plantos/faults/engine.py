"""Configurable fault injection.

Faults modify plant physics (AppliedFaults) or the sensor bank. They are
scenario data, not controller inputs. The controller must infer them from
residuals.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from plantos.config import FaultConfig, FaultSpec
from plantos.estimation.sensors import SensorBank
from plantos.plant.plant import AppliedFaults
from plantos.plant.state import FaultRecord, PlantState


@dataclass
class ActiveFault:
    spec: FaultSpec
    fault_id: str
    started: bool = False
    ended: bool = False


class FaultEngine:
    def __init__(self, config: FaultConfig):
        self.active: list[ActiveFault] = [
            ActiveFault(spec=f, fault_id=f"{f.type}_{i}_{f.start_hour}")
            for i, f in enumerate(config.faults)
        ]

    def apply(
        self,
        hour: float,
        state: PlantState,
        sensors: SensorBank,
    ) -> tuple[AppliedFaults, PlantState, list[FaultRecord]]:
        af = AppliedFaults()
        records: list[FaultRecord] = []
        for item in self.active:
            f = item.spec
            on = hour >= f.start_hour and (f.end_hour is None or hour < f.end_hour)
            if not on:
                if item.started and f.type.startswith("sensor_"):
                    channel = f.component or "hydrogen_flow"
                    sensors.clear(channel)
                continue
            item.started = True
            rec = FaultRecord(
                fault_id=item.fault_id,
                fault_type=f.type,
                component=f.component or _default_component(f.type),
                severity=f.severity,
                start_hour=f.start_hour,
                active=True,
            )
            records.append(rec)
            _apply_one(f, af, sensors)
        state.active_faults = records
        return af, state, records


def _default_component(fault_type: str) -> str:
    if fault_type.startswith("solar"):
        return "solar"
    if fault_type.startswith("battery"):
        return "battery"
    if fault_type.startswith("electrolyser"):
        return "electrolyser"
    if fault_type.startswith("co2"):
        return "co2_capture"
    if fault_type.startswith("methanation"):
        return "methanation"
    if fault_type.startswith("sensor"):
        return "sensor"
    return "unknown"


def _apply_one(f: FaultSpec, af: AppliedFaults, sensors: SensorBank) -> None:
    s = float(f.severity)
    t = f.type
    if t in {"solar_shading", "solar_partial", "solar_loss"}:
        af.solar_shading = min(af.solar_shading, 1.0 - s)
    elif t == "battery_capacity":
        af.battery_capacity = min(af.battery_capacity, 1.0 - s)
    elif t in {"battery_losses", "battery_internal_loss"}:
        af.battery_loss = max(af.battery_loss, 1.0 + s)
    elif t in {"battery_overheat", "battery_thermal"}:
        af.battery_thermal = max(af.battery_thermal, s)
    elif t == "electrolyser_efficiency":
        af.el_efficiency = max(af.el_efficiency, s)
    elif t == "electrolyser_partial":
        af.el_partial = max(af.el_partial, s)
    elif t == "electrolyser_complete":
        af.el_complete = True
    elif t in {"co2_reduced", "co2_capacity"}:
        af.co2_capacity = max(af.co2_capacity, s)
    elif t == "co2_complete":
        af.co2_complete = True
    elif t in {"methanation_throughput", "methanation_reduced"}:
        af.meth_throughput = max(af.meth_throughput, s)
    elif t in {"methanation_thermal", "methanation_temperature"}:
        af.meth_thermal = max(af.meth_thermal, s)
    elif t.startswith("sensor_"):
        channel = f.component or "hydrogen_flow"
        mode = {
            "sensor_bias": "bias",
            "sensor_drift": "drift",
            "sensor_frozen": "freeze",
            "sensor_fail": "fail",
            "sensor_random": "fail",
        }.get(t, "bias")
        sensors.inject(channel, mode, s)
