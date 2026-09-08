# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Model-based fault detection.

Compare a one-step digital-twin prediction (from controller belief and the
last action) against measurements. Persist residuals before raising an alarm
to limit false positives from sensor noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from plantos.config import PlantConfig
from plantos.estimation.kalman import EstimatedState
from plantos.estimation.sensors import Measurement
from plantos.plant.electrolyser import hydrogen_from_power
from plantos.plant.solar import available_solar_mw


@dataclass
class ResidualSet:
    solar_power: float = 0.0
    hydrogen: float = 0.0
    co2: float = 0.0
    methane: float = 0.0
    electrolyser_power: float = 0.0
    soc: float = 0.0
    el_temp: float = 0.0
    efficiency_pp: float = 0.0  # percentage points vs expected


@dataclass
class DetectionResult:
    residuals: ResidualSet
    fault_probability: float
    fault_type: str
    fault_severity: float
    confidence: float
    alarmed: bool
    notes: str = ""


class FaultDetector:
    def __init__(self, config: PlantConfig, persist_hours: float = 2.0):
        self.config = config
        self.persist_hours = persist_hours
        self._streak: dict[str, float] = {}
        self._last: ResidualSet = ResidualSet()

    def expected_hydrogen(self, power_mw: float, health: float) -> float:
        return hydrogen_from_power(power_mw, self.config.electrolyser, health)

    def compute_residuals(
        self,
        belief: EstimatedState,
        measurement: Measurement,
        predicted_solar_mw: float,
    ) -> ResidualSet:
        h2_exp = self.expected_hydrogen(belief.electrolyser_power_mw, belief.electrolyser_health)
        h2_meas = measurement.get("hydrogen_flow")
        p_el = max(measurement.get("electrolyser_power"), 1e-6)
        meas_kwh_kg = (p_el * 1000.0) / max(h2_meas, 1e-3) if h2_meas > 1.0 else self.config.electrolyser.nominal_kwh_per_kg
        exp_kwh_kg = (belief.electrolyser_power_mw * 1000.0) / max(h2_exp, 1e-3) if h2_exp > 1.0 else self.config.electrolyser.nominal_kwh_per_kg
        # Efficiency residual in percentage points (LHV).
        eta_meas = 33.33 / meas_kwh_kg * 100.0
        eta_exp = 33.33 / exp_kwh_kg * 100.0
        r = ResidualSet(
            solar_power=measurement.get("solar_power") - predicted_solar_mw,
            hydrogen=h2_meas - h2_exp,
            co2=measurement.get("co2_flow") - belief.co2_rate_kgph,
            methane=measurement.get("methane_flow") - belief.methane_rate_kgph,
            electrolyser_power=measurement.get("electrolyser_power") - belief.electrolyser_power_mw,
            soc=measurement.get("battery_soc") - belief.battery_soc,
            el_temp=measurement.get("electrolyser_temperature") - belief.electrolyser_temperature_c,
            efficiency_pp=eta_meas - eta_exp,
        )
        self._last = r
        return r

    def update(
        self,
        belief: EstimatedState,
        measurement: Measurement,
        irradiance_forecast_now: float,
        ambient_forecast_now: float,
        dt_hours: float,
    ) -> DetectionResult:
        pred_solar = available_solar_mw(
            irradiance_forecast_now, ambient_forecast_now, self.config.solar
        )
        r = self.compute_residuals(belief, measurement, pred_solar)

        if belief.electrolyser_status in {"STARTING", "SHUTDOWN", "OFF"}:
            r.efficiency_pp = 0.0

        candidates: list[tuple[str, float, float]] = []  # type, score, severity
        running = belief.electrolyser_status in {"RUNNING", "DEGRADED"}
        if running and belief.electrolyser_power_mw > 1.0 and r.efficiency_pp < -8.0:
            sev = float(np.clip(-r.efficiency_pp / 40.0, 0.05, 0.9))
            candidates.append(("electrolyser_efficiency", min(0.95, -r.efficiency_pp / 12.0), sev))
        if running and r.hydrogen < -15.0 and belief.electrolyser_power_mw > 1.0:
            candidates.append(("electrolyser_partial", min(0.9, -r.hydrogen / 40.0), 0.4))
        if running and belief.electrolyser_power_mw > 2.0 and measurement.get("hydrogen_flow") < 2.0:
            candidates.append(("electrolyser_complete", 0.8, 1.0))
        if r.solar_power < -0.8 and pred_solar > 1.0:
            candidates.append(("solar_loss", min(0.85, -r.solar_power / max(pred_solar, 1e-3)), 0.3))
        if abs(r.soc) > 0.06:
            candidates.append(("battery_capacity", min(0.7, abs(r.soc) / 0.12), 0.25))
        if r.co2 < -30 and belief.co2_capture_power_mw > 0.4:
            candidates.append(("co2_reduced", min(0.8, -r.co2 / 80.0), 0.35))
        if r.el_temp > 12:
            candidates.append(("electrolyser_thermal", min(0.75, r.el_temp / 25.0), 0.3))

        # Persistence
        for key in list(self._streak.keys()):
            if not any(c[0] == key for c in candidates):
                self._streak[key] = max(0.0, self._streak[key] - dt_hours)
        best = ("none", 0.0, 0.0)
        for typ, score, sev in candidates:
            self._streak[typ] = self._streak.get(typ, 0.0) + dt_hours
            persist = self._streak[typ] / self.persist_hours
            adj = score * float(np.clip(persist, 0.15, 1.0))
            if adj > best[1]:
                best = (typ, adj, sev)

        alarmed = best[1] >= 0.55 and self._streak.get(best[0], 0.0) >= self.persist_hours * 0.6
        conf = float(np.clip(best[1], 0.0, 0.99))
        return DetectionResult(
            residuals=r,
            fault_probability=conf,
            fault_type=best[0],
            fault_severity=best[2],
            confidence=conf,
            alarmed=alarmed,
            notes=f"efficiency_pp={r.efficiency_pp:.1f}, h2_resid={r.hydrogen:.1f}",
        )
