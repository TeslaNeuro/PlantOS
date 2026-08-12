"""Decoupled Kalman-style state estimator.

Each measured channel has a scalar constant-velocity / random-walk Kalman
filter. The process model for power and flow channels is 'persist last
commanded / last estimate'. SOC uses a simple coulomb-count prediction
from estimated battery power.

This is intentionally not a full EKF of the plant. The plant is nonlinear
and hybrid; a diagonal filter plus residual monitoring is the defensible
minimum that still treats measurement noise as a first-class object.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from plantos.config import BatteryConfig, PlantConfig
from plantos.estimation.sensors import Measurement
from plantos.plant.state import PlantState


@dataclass
class ScalarKF:
    x: float
    p: float
    q: float
    r: float

    def predict(self, x_pred: float | None = None) -> None:
        if x_pred is not None:
            self.x = x_pred
        self.p = self.p + self.q

    def update(self, z: float) -> float:
        k = self.p / (self.p + self.r + 1e-12)
        self.x = self.x + k * (z - self.x)
        self.p = (1.0 - k) * self.p
        return self.x


@dataclass
class EstimatedState:
    """Controller belief. Must not contain undetectable future information."""

    hour: float
    solar_power_mw: float
    battery_soc: float
    battery_soh: float
    battery_power_mw: float
    electrolyser_power_mw: float
    electrolyser_health: float
    electrolyser_temperature_c: float
    hydrogen_rate_kgph: float
    co2_capture_power_mw: float
    co2_capture_health: float
    co2_rate_kgph: float
    methanation_power_mw: float
    methanation_health: float
    methanation_temperature_c: float
    methane_rate_kgph: float
    h2_stored_kg: float
    co2_stored_kg: float
    plant_load_mw: float
    soc_uncertainty: float
    forecast_uncertainty: float
    isolated_components: set[str] = field(default_factory=set)
    available_capacity: dict[str, float] = field(default_factory=dict)
    electrolyser_status: str = "OFF"

    def to_plant_like(self, template: PlantState) -> PlantState:
        """Copy belief scalars onto a PlantState for digital-twin one-step preds."""
        s = template.copy()
        s.solar_power_mw = self.solar_power_mw
        s.battery_soc = self.battery_soc
        s.battery_soh = self.battery_soh
        s.battery_power_mw = self.battery_power_mw
        s.electrolyser_power_mw = self.electrolyser_power_mw
        s.electrolyser_health = self.electrolyser_health
        s.electrolyser_temperature_c = self.electrolyser_temperature_c
        s.hydrogen_rate_kgph = self.hydrogen_rate_kgph
        s.co2_capture_power_mw = self.co2_capture_power_mw
        s.co2_capture_health = self.co2_capture_health
        s.co2_rate_kgph = self.co2_rate_kgph
        s.methanation_power_mw = self.methanation_power_mw
        s.methanation_health = self.methanation_health
        s.methanation_temperature_c = self.methanation_temperature_c
        s.methane_rate_kgph = self.methane_rate_kgph
        s.h2_stored_kg = self.h2_stored_kg
        s.co2_stored_kg = self.co2_stored_kg
        s.plant_load_mw = self.plant_load_mw
        s.isolated_components = set(self.isolated_components)
        s.available_capacity = dict(self.available_capacity)
        return s


class StateEstimator:
    def __init__(self, config: PlantConfig, initial: PlantState):
        self.config = config
        self.filters = {
            "solar_power": ScalarKF(0.0, 1.0, 0.08, 0.05),
            "battery_soc": ScalarKF(initial.battery_soc, 0.01, 1e-4, 8e-3),
            "battery_power": ScalarKF(0.0, 0.5, 0.05, 0.04),
            "electrolyser_power": ScalarKF(0.0, 0.5, 0.05, 0.05),
            "hydrogen_flow": ScalarKF(0.0, 20.0, 4.0, 3.0),
            "co2_flow": ScalarKF(0.0, 40.0, 8.0, 8.0),
            "methane_flow": ScalarKF(0.0, 20.0, 4.0, 5.0),
            "electrolyser_temperature": ScalarKF(initial.electrolyser_temperature_c, 4.0, 0.3, 0.5),
            "methanation_temperature": ScalarKF(initial.methanation_temperature_c, 8.0, 0.5, 1.0),
            "co2_power": ScalarKF(0.0, 0.3, 0.02, 0.03),
        }
        self.soh = initial.battery_soh
        self.el_health = initial.electrolyser_health
        self.co2_health = initial.co2_capture_health
        self.meth_health = initial.methanation_health
        self.h2_stored = initial.h2_stored_kg
        self.co2_stored = initial.co2_stored_kg
        self.isolated: set[str] = set()
        self.available_capacity = dict(initial.available_capacity)
        self.status = initial.electrolyser_status.value
        self.forecast_uncertainty = 0.2

    def predict_soc(self, battery_power_mw: float, dt_hours: float) -> float:
        cfg: BatteryConfig = self.config.battery
        e = cfg.energy_capacity_mwh * max(self.soh, 0.05)
        soc = self.filters["battery_soc"].x
        if battery_power_mw >= 0:
            return float(np.clip(soc - battery_power_mw * dt_hours / (cfg.discharge_efficiency * e), 0, 1))
        return float(np.clip(soc + (-battery_power_mw) * cfg.charge_efficiency * dt_hours / e, 0, 1))

    def update(
        self,
        measurement: Measurement,
        dt_hours: float,
        forecast_uncertainty: float,
        isolated: set[str] | None = None,
        available_capacity: dict[str, float] | None = None,
        health_hints: dict[str, float] | None = None,
        soh_hint: float | None = None,
        storage_hints: dict[str, float] | None = None,
        status: str | None = None,
    ) -> EstimatedState:
        if isolated is not None:
            self.isolated = set(isolated)
        if available_capacity is not None:
            self.available_capacity = dict(available_capacity)
        if health_hints:
            self.el_health = health_hints.get("electrolyser", self.el_health)
            self.co2_health = health_hints.get("co2_capture", self.co2_health)
            self.meth_health = health_hints.get("methanation", self.meth_health)
        if soh_hint is not None:
            self.soh = soh_hint
        if storage_hints:
            self.h2_stored = storage_hints.get("h2", self.h2_stored)
            self.co2_stored = storage_hints.get("co2", self.co2_stored)
        if status is not None:
            self.status = status
        self.forecast_uncertainty = forecast_uncertainty

        batt_p = measurement.get("battery_power", self.filters["battery_power"].x)
        self.filters["battery_soc"].predict(self.predict_soc(batt_p, dt_hours))
        for name, kf in self.filters.items():
            if name == "battery_soc":
                continue
            kf.predict()

        for name, kf in self.filters.items():
            if name in measurement.failed_channels or name in measurement.frozen_channels:
                kf.p = min(kf.p * 1.5, 50.0)
                continue
            kf.update(measurement.get(name, kf.x))

        load = (
            self.filters["electrolyser_power"].x
            + self.filters["co2_power"].x
            + max(measurement.get("methane_flow", 0.0) * self.config.methanation.aux_kwh_per_kg / 1000.0, 0.0)
            + self.config.auxiliary_mw
        )
        return EstimatedState(
            hour=measurement.hour,
            solar_power_mw=max(self.filters["solar_power"].x, 0.0),
            battery_soc=float(np.clip(self.filters["battery_soc"].x, 0.0, 1.0)),
            battery_soh=self.soh,
            battery_power_mw=self.filters["battery_power"].x,
            electrolyser_power_mw=max(self.filters["electrolyser_power"].x, 0.0),
            electrolyser_health=self.el_health,
            electrolyser_temperature_c=self.filters["electrolyser_temperature"].x,
            hydrogen_rate_kgph=max(self.filters["hydrogen_flow"].x, 0.0),
            co2_capture_power_mw=max(self.filters["co2_power"].x, 0.0),
            co2_capture_health=self.co2_health,
            co2_rate_kgph=max(self.filters["co2_flow"].x, 0.0),
            methanation_power_mw=max(
                measurement.get("methane_flow", 0.0) * self.config.methanation.aux_kwh_per_kg / 1000.0, 0.0
            ),
            methanation_health=self.meth_health,
            methanation_temperature_c=self.filters["methanation_temperature"].x,
            methane_rate_kgph=max(self.filters["methane_flow"].x, 0.0),
            h2_stored_kg=self.h2_stored,
            co2_stored_kg=self.co2_stored,
            plant_load_mw=max(load, 0.0),
            soc_uncertainty=float(np.sqrt(max(self.filters["battery_soc"].p, 0.0))),
            forecast_uncertainty=forecast_uncertainty,
            isolated_components=set(self.isolated),
            available_capacity=dict(self.available_capacity),
            electrolyser_status=self.status,
        )
