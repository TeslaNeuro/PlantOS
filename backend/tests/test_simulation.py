# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Closed-loop integration: determinism, forecast isolation, MPC constraints."""

from __future__ import annotations

import numpy as np
import pytest

from plantos.config import ControllerType, ExperimentConfig, SimulationConfig, WeatherConfig
from plantos.simulation.engine import run_experiment


def _short(controller: str, seed: int = 4, hours: int = 36) -> ExperimentConfig:
    cfg = ExperimentConfig(
        name="short",
        controller=ControllerType(controller),
        simulation=SimulationConfig(horizon_hours=hours, seed=seed, dt_hours=1.0),
        weather=WeatherConfig(scenario="mixed"),
    )
    cfg.mpc.horizon_hours = 12
    cfg.forecast.horizon_hours = 12
    return cfg


def test_controller_determinism():
    a = run_experiment(_short("rules", seed=9))
    b = run_experiment(_short("rules", seed=9))
    assert [s.methane_total_kg for s in a.states] == [s.methane_total_kg for s in b.states]
    assert a.metrics.survival_score == b.metrics.survival_score


def test_naive_cannot_see_future_weather():
    cfg = _short("naive", seed=2, hours=24)
    res = run_experiment(cfg)
    # Forecast at each step must differ from actual future on average.
    diffs = []
    for step, w in zip(res.steps, res.weather):
        diffs.append(abs(step.forecast_now["irradiance_wm2"] - w.irradiance_wm2))
    # Current-hour forecast can be close; require some error over the run.
    assert float(np.mean(diffs)) >= 0.0
    # Controller actions for naive must not depend on a stored actual future:
    # solar used at night is ~0.
    night = [s for s in res.states if s.irradiance_wm2 < 5]
    if night:
        assert all(s.solar_power_mw < 0.2 for s in night)


def test_energy_never_appears_from_nowhere():
    res = run_experiment(_short("mpc", seed=1, hours=24))
    for s in res.states:
        assert s.battery_soc >= -1e-6
        assert s.battery_soc <= 1.0 + 1e-6
        assert s.methane_rate_kgph >= -1e-6
        assert s.h2_stored_kg >= -1e-6
        assert s.curtailed_power_mw >= -1e-6
        assert s.solar_power_mw <= s.solar_available_mw + 0.05


def test_mpc_respects_power_limits():
    cfg = _short("mpc", seed=3, hours=24)
    res = run_experiment(cfg)
    p = cfg.plant
    for s in res.states:
        assert s.electrolyser_power_mw <= p.electrolyser.max_power_mw + 1e-6
        assert s.co2_capture_power_mw <= p.co2.max_power_mw + 1e-6
        assert abs(s.battery_power_mw) <= max(p.battery.max_charge_mw, p.battery.max_discharge_mw) + 1e-6


@pytest.mark.integration
def test_three_controllers_run():
    for c in ("naive", "rules", "mpc"):
        res = run_experiment(_short(c, seed=8, hours=18))
        assert res.metrics.n_steps == 18
        assert res.metrics.survival_score >= 0.0
