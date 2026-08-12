"""Operating modes and autonomous reconfiguration.

PlantOS does not shut the plant on every fault. It isolates the failed
asset when diagnosis supports an actuator/equipment hypothesis, derates
available capacity, and asks the controller to re-optimise.

Recovery is attempted after residuals remain quiet for a configurable
number of hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from plantos.config import PlantMode
from plantos.estimation.kalman import EstimatedState
from plantos.faults.diagnosis import Diagnosis
from plantos.weather.forecast import Forecast


@dataclass
class Reconfiguration:
    mode: PlantMode
    isolated: set[str] = field(default_factory=set)
    recover: set[str] = field(default_factory=set)
    capacity: dict[str, float] = field(default_factory=dict)
    soc_reserve: float = 0.22
    explanation: str = ""
    reason_code: str = "mode.normal"


class Reconfigurator:
    def __init__(self, quiet_hours_to_recover: float = 4.0):
        self.mode = PlantMode.NORMAL
        self.isolated: set[str] = set()
        self.capacity = {
            "solar": 1.0,
            "battery": 1.0,
            "electrolyser": 1.0,
            "co2_capture": 1.0,
            "methanation": 1.0,
        }
        self.soc_reserve = 0.22
        self._quiet_hours = 0.0
        self.quiet_hours_to_recover = quiet_hours_to_recover
        self._fault_hours = 0.0

    def update(
        self,
        diagnosis: Diagnosis,
        belief: EstimatedState,
        forecast: Forecast,
        dt_hours: float,
        thermal_emergency: bool = False,
    ) -> Reconfiguration:
        recover: set[str] = set()
        reason = "mode.normal"
        text = "Normal autonomous operation."

        uncertain = forecast.failed or belief.forecast_uncertainty > 0.7
        power_short = belief.battery_soc < self.soc_reserve + 0.04 or (
            belief.solar_power_mw < 0.4 and belief.battery_soc < 0.4
        )

        equipment_alarm = diagnosis.isolate or diagnosis.primary in {
            "electrolyser_degradation",
            "co2_capture_fault",
            "battery_degradation",
        }
        if not equipment_alarm or diagnosis.confidence < 0.35:
            self._quiet_hours += dt_hours
            self._fault_hours = max(0.0, self._fault_hours - dt_hours)
        else:
            if equipment_alarm:
                self._quiet_hours = 0.0
            self._fault_hours += dt_hours

        if diagnosis.isolate and diagnosis.component in {"electrolyser", "co2_capture", "methanation"}:
            self.isolated.add(diagnosis.component)
            self.capacity[diagnosis.component] = max(0.0, 1.0 - diagnosis.severity)
            reason = "fault.isolate"
            text = (
                f"Isolating {diagnosis.component}: {diagnosis.primary} "
                f"(confidence {diagnosis.confidence:.0%}). Remaining units stay in service."
            )
            self._quiet_hours = 0.0
        elif diagnosis.primary == "electrolyser_degradation" and diagnosis.confidence > 0.4:
            self.capacity["electrolyser"] = max(0.35, 1.0 - diagnosis.severity)
            reason = "fault.derate"
            text = (
                f"Electrolyser derated to {self.capacity['electrolyser']:.0%} "
                f"after efficiency residual (severity {diagnosis.severity:.2f})."
            )
        elif diagnosis.primary == "battery_degradation" and diagnosis.confidence > 0.4:
            self.capacity["battery"] = max(0.5, 1.0 - diagnosis.severity)
            self.soc_reserve = min(0.4, self.soc_reserve + 0.05)
            reason = "fault.battery"
            text = "Battery capacity hypothesis accepted; reserve target raised."
        elif diagnosis.primary == "weather_disturbance":
            self.soc_reserve = min(0.35, max(self.soc_reserve, 0.30))
            reason = "forecast.uncertain"
            text = "Solar residual vs forecast: raising battery reserve and shrinking commitment."
        elif diagnosis.primary in {"hydrogen_sensor_fault", "power_measurement_fault"}:
            reason = "sensor.fault"
            text = "Sensor hypothesis preferred over equipment trip; measurements down-weighted, plant not isolated."

        if self.isolated and self._quiet_hours >= self.quiet_hours_to_recover:
            recover = set(self.isolated)
            self.isolated = set()
            self.capacity = {k: 1.0 for k in self.capacity}
            reason = "recovery.start"
            text = "Residuals quiet; attempting restoration of isolated equipment."
            self.mode = PlantMode.RECOVERY
        elif thermal_emergency or (belief.battery_soc <= 0.12 and belief.solar_power_mw < 0.4):
            self.mode = PlantMode.EMERGENCY
            self.soc_reserve = 0.35
            reason = "emergency"
            text = "SOC or thermal limit: shedding battery-backed load. Solar-following production remains allowed."
        elif self.isolated:
            self.mode = PlantMode.FAULT
        elif min(self.capacity.values()) < 0.95:
            self.mode = PlantMode.DEGRADED
        elif power_short:
            self.mode = PlantMode.POWER_CONSTRAINED
            reason = "power.constrained"
            text = "Power constrained: defending battery reserve, reducing capture and stack load."
        elif uncertain:
            self.mode = PlantMode.FORECAST_UNCERTAIN
            self.soc_reserve = max(self.soc_reserve, 0.30)
            reason = "forecast.uncertain"
            text = "Forecast uncertainty elevated; reserve target increased."
        elif self.mode == PlantMode.RECOVERY and self._quiet_hours > 1:
            self.mode = PlantMode.NORMAL
        else:
            if self.mode not in {PlantMode.RECOVERY}:
                self.mode = PlantMode.NORMAL
                self.soc_reserve = max(0.22, self.soc_reserve - 0.01)

        return Reconfiguration(
            mode=self.mode,
            isolated=set(self.isolated),
            recover=recover,
            capacity=dict(self.capacity),
            soc_reserve=self.soc_reserve,
            explanation=text,
            reason_code=reason,
        )
