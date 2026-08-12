"""Closed-loop simulator: reality, sensors, estimator, FDD, reconfiguration, control.

The controller is never passed PlantState reality or future actual weather.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from plantos.config import ControllerType, ExperimentConfig, PlantMode
from plantos.constants import CO2_PER_CH4_KG, H2_PER_CH4_KG
from plantos.controllers import make_controller
from plantos.estimation.kalman import EstimatedState, StateEstimator
from plantos.estimation.sensors import SensorBank
from plantos.faults.detection import FaultDetector
from plantos.faults.diagnosis import diagnose
from plantos.faults.engine import FaultEngine
from plantos.faults.reconfiguration import Reconfiguration, Reconfigurator
from plantos.plant.actions import ControlAction
from plantos.plant.plant import initial_state, step_plant
from plantos.plant.state import PlantState
from plantos.simulation.events import DecisionEvent
from plantos.simulation.metrics import RunMetrics, compute_metrics, metrics_to_dict
from plantos.weather.engine import WeatherSample, build_weather
from plantos.weather.forecast import Forecast, ForecastEngine


@dataclass
class StepRecord:
    hour: float
    reality: dict[str, Any]
    belief: dict[str, Any]
    measurement: dict[str, Any]
    forecast_now: dict[str, Any]
    action: dict[str, Any]
    detection: dict[str, Any]
    diagnosis: dict[str, Any]
    mode: str
    weather: dict[str, Any]


@dataclass
class SimulationResult:
    config_name: str
    controller: str
    seed: int
    states: list[PlantState]
    beliefs: list[EstimatedState]
    events: list[DecisionEvent]
    steps: list[StepRecord]
    metrics: RunMetrics
    weather: list[WeatherSample]
    forecasts_origin: list[Forecast] = field(default_factory=list)

    def to_serializable(self, thin: bool = False) -> dict[str, Any]:
        stride = 1 if not thin else max(1, len(self.steps) // 240)
        return {
            "config_name": self.config_name,
            "controller": self.controller,
            "seed": self.seed,
            "metrics": metrics_to_dict(self.metrics),
            "events": [e.to_dict() for e in self.events],
            "timeseries": [self.steps[i].reality | {"hour": self.steps[i].hour, "mode": self.steps[i].mode} for i in range(0, len(self.steps), stride)],
            "steps": None if thin else [s.__dict__ for s in self.steps],
            "weather": [
                {
                    "hour": w.hour,
                    "irradiance_wm2": w.irradiance_wm2,
                    "temperature_c": w.temperature_c,
                    "cloud_cover": w.cloud_cover,
                }
                for w in self.weather[::stride]
            ],
        }


def _belief_dict(b: EstimatedState) -> dict[str, Any]:
    return {
        "hour": b.hour,
        "solar_power_mw": b.solar_power_mw,
        "battery_soc": b.battery_soc,
        "battery_soh": b.battery_soh,
        "electrolyser_power_mw": b.electrolyser_power_mw,
        "electrolyser_health": b.electrolyser_health,
        "hydrogen_rate_kgph": b.hydrogen_rate_kgph,
        "co2_rate_kgph": b.co2_rate_kgph,
        "methane_rate_kgph": b.methane_rate_kgph,
        "h2_stored_kg": b.h2_stored_kg,
        "co2_stored_kg": b.co2_stored_kg,
        "soc_uncertainty": b.soc_uncertainty,
        "forecast_uncertainty": b.forecast_uncertainty,
        "isolated_components": sorted(b.isolated_components),
    }


class Simulator:
    def __init__(self, config: ExperimentConfig):
        self.config = config

    def run(self) -> SimulationResult:
        cfg = self.config
        dt = cfg.simulation.dt_hours
        seed = cfg.simulation.seed
        weather = build_weather(cfg.weather, cfg.simulation.horizon_hours, dt, seed)
        n = len(weather)
        rng_note = np.random.default_rng(seed)

        reality = initial_state(cfg.plant)
        sensors = SensorBank(cfg.sensors, seed)
        estimator = StateEstimator(cfg.plant, reality)
        detector = FaultDetector(cfg.plant)
        reconfigurator = Reconfigurator()
        faults = FaultEngine(cfg.faults)
        controller = make_controller(cfg)
        fengine = ForecastEngine(cfg.forecast, cfg.weather, seed)

        states: list[PlantState] = []
        beliefs: list[EstimatedState] = []
        events: list[DecisionEvent] = []
        steps: list[StepRecord] = []
        last_action = ControlAction()
        last_reason = ""

        believed_el_health = cfg.plant.electrolyser.initial_health
        believed_co2_health = cfg.plant.co2.initial_health
        believed_meth_health = cfg.plant.methanation.initial_health
        believed_soh = cfg.plant.battery.initial_soh
        believed_h2 = cfg.plant.methanation.initial_h2_kg
        believed_co2 = cfg.plant.methanation.initial_co2_kg

        for i in range(n):
            w = weather[i]
            hour = w.hour
            applied, reality, _recs = faults.apply(hour, reality, sensors)

            future = weather[i : i + cfg.forecast.horizon_hours]
            if not future:
                future = [w]
            forecast = fengine.issue(hour, future, dt)
            fu = 0.25 + (0.45 if forecast.failed else 0.0)
            if len(forecast.irradiance_wm2) > 3:
                fu += 0.15 * min(1.0, float(np.std(forecast.irradiance_wm2[:24])) / 350.0)

            measurement = sensors.measure(reality, dt)
            belief = estimator.update(
                measurement,
                dt,
                forecast_uncertainty=fu,
                isolated=reconfigurator.isolated,
                available_capacity=reconfigurator.capacity,
                health_hints={
                    "electrolyser": believed_el_health,
                    "co2_capture": believed_co2_health,
                    "methanation": believed_meth_health,
                },
                soh_hint=believed_soh,
                storage_hints={"h2": believed_h2, "co2": believed_co2},
                status=reality.electrolyser_status.value,
            )
            # status leak: electrolyser status is typically known from the PLC command
            # feedback, not from a hidden reality field. Using commanded/last action
            # status would be purer; we use the plant's reported machine state as
            # an actuator-feedback signal (standard in industrial control).

            irr0, temp0, _ = forecast.at(0)
            detection = detector.update(belief, measurement, irr0, temp0, dt)
            diagnosis = diagnose(detection, measurement)

            if diagnosis.primary == "electrolyser_degradation":
                believed_el_health = max(0.35, min(believed_el_health, 1.0 - 0.6 * diagnosis.severity))
            if diagnosis.primary == "co2_capture_fault":
                believed_co2_health = max(0.4, min(believed_co2_health, 1.0 - 0.5 * diagnosis.severity))
            if diagnosis.primary == "battery_degradation":
                believed_soh = max(0.5, min(believed_soh, 1.0 - 0.4 * diagnosis.severity))
            if diagnosis.primary == "weather_disturbance":
                fu = min(0.95, fu + 0.25)
                belief.forecast_uncertainty = fu

            thermal_em = (
                reality.electrolyser_temperature_c > cfg.plant.electrolyser.max_temperature_c
                or reality.battery_temp_c > 55.0
            )
            # Thermal emergency uses measured temperature, not hidden reality.
            thermal_em = measurement.get("electrolyser_temperature") > cfg.plant.electrolyser.max_temperature_c

            if cfg.controller == ControllerType.NAIVE:
                reconf = Reconfiguration(
                    mode=PlantMode.NORMAL,
                    explanation="Naive baseline: no forecast, isolation or recovery.",
                    reason_code="naive.none",
                )
            else:
                reconf = reconfigurator.update(
                    diagnosis, belief, forecast, dt, thermal_emergency=thermal_em
                )
            belief.isolated_components = set(reconf.isolated)
            belief.available_capacity = dict(reconf.capacity)

            action = controller.compute(belief, forecast, reconf, dt)
            action.isolate |= set(reconf.isolated)
            action.recover |= set(reconf.recover)

            if action.reason_code != last_reason or (events and hour - events[-1].hour >= 3):
                events.append(
                    DecisionEvent(
                        hour=hour,
                        reason_code=action.reason_code or reconf.reason_code,
                        explanation=action.explanation or reconf.explanation,
                        mode=reconf.mode.value,
                        action=action.to_dict(),
                        diagnosis=diagnosis.to_dict(),
                        detection={
                            "fault_type": detection.fault_type,
                            "fault_probability": detection.fault_probability,
                            "confidence": detection.confidence,
                            "alarmed": detection.alarmed,
                            "notes": detection.notes,
                            "efficiency_pp": detection.residuals.efficiency_pp,
                        },
                    )
                )
                last_reason = action.reason_code

            reality, _trace = step_plant(
                reality,
                action,
                w.irradiance_wm2,
                w.temperature_c,
                w.cloud_cover,
                dt,
                cfg.plant,
                faults=applied,
                check=cfg.simulation.check_invariants,
            )
            reality.plant_mode = reconf.mode

            # Integrate believed storage from estimated flows (no tank telemetry).
            believed_h2 = float(
                np.clip(
                    believed_h2 + (belief.hydrogen_rate_kgph - belief.methane_rate_kgph * H2_PER_CH4_KG) * dt,
                    0.0,
                    cfg.plant.methanation.h2_storage_kg,
                )
            )
            believed_co2 = float(
                np.clip(
                    believed_co2 + (belief.co2_rate_kgph - belief.methane_rate_kgph * CO2_PER_CH4_KG) * dt,
                    0.0,
                    cfg.plant.methanation.co2_storage_kg,
                )
            )
            # Slow SOH prior from believed throughput.
            believed_soh = max(0.5, believed_soh - 2.5e-5 * abs(belief.battery_power_mw) * dt)

            states.append(reality.copy())
            beliefs.append(belief)
            steps.append(
                StepRecord(
                    hour=hour,
                    reality=reality.to_dict(),
                    belief=_belief_dict(belief),
                    measurement=measurement.to_dict(),
                    forecast_now={
                        "irradiance_wm2": float(irr0),
                        "temperature_c": float(temp0),
                        "failed": forecast.failed,
                        "uncertainty": fu,
                    },
                    action=action.to_dict(),
                    detection={
                        "fault_type": detection.fault_type,
                        "confidence": detection.confidence,
                        "alarmed": detection.alarmed,
                    },
                    diagnosis=diagnosis.to_dict(),
                    mode=reconf.mode.value,
                    weather={
                        "irradiance_wm2": w.irradiance_wm2,
                        "temperature_c": w.temperature_c,
                        "cloud_cover": w.cloud_cover,
                    },
                )
            )
            last_action = action
            _ = rng_note

        metrics = compute_metrics(
            states, dt, cfg.survival, nameplate_ch4_kgph=cfg.plant.methanation.max_ch4_kg_per_h
        )
        return SimulationResult(
            config_name=cfg.name,
            controller=cfg.controller.value,
            seed=seed,
            states=states,
            beliefs=beliefs,
            events=events,
            steps=steps,
            metrics=metrics,
            weather=weather,
        )


def run_experiment(config: ExperimentConfig) -> SimulationResult:
    return Simulator(config).run()
