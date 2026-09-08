# SPDX-License-Identifier: MIT
# Copyright (c) 2026 TeslaNeuro
"""Weather, forecast uncertainty, and the reality/belief split."""

from __future__ import annotations

import numpy as np

from plantos.config import ForecastConfig, WeatherConfig
from plantos.weather.engine import build_weather, clear_sky_ghi, solar_elevation_deg
from plantos.weather.forecast import ForecastEngine


def test_night_has_zero_ghi():
    el = solar_elevation_deg(50.0, 172, 0.0)
    assert el < 0
    assert clear_sky_ghi(el) == 0.0


def test_synthetic_weather_reproducible():
    cfg = WeatherConfig(scenario="mixed")
    a = build_weather(cfg, 48, 1.0, seed=1)
    b = build_weather(cfg, 48, 1.0, seed=1)
    c = build_weather(cfg, 48, 1.0, seed=2)
    assert [x.irradiance_wm2 for x in a] == [x.irradiance_wm2 for x in b]
    assert [x.irradiance_wm2 for x in a] != [x.irradiance_wm2 for x in c]


def test_storm_has_clear_then_collapse():
    cfg = WeatherConfig(scenario="storm")
    w = build_weather(cfg, 240, 1.0, seed=7)
    day3 = [x.irradiance_wm2 for x in w if 48 <= x.hour < 72]
    day4_afternoon = [x.irradiance_wm2 for x in w if 84 <= x.hour < 96]
    assert max(day3) > max(day4_afternoon)


def test_forecast_differs_from_actual():
    weather_cfg = WeatherConfig(scenario="mixed")
    weather = build_weather(weather_cfg, 72, 1.0, seed=3)
    eng = ForecastEngine(ForecastConfig(bias_wm2=80, noise_std_wm2=40), weather_cfg, seed=3)
    fc = eng.issue(12.0, weather[12:60], 1.0)
    actual = np.array([x.irradiance_wm2 for x in weather[12:12 + len(fc.irradiance_wm2)]])
    mae = float(np.mean(np.abs(fc.irradiance_wm2 - actual)))
    assert mae > 20.0


def test_forecast_failure_is_overconfident():
    weather_cfg = WeatherConfig(scenario="storm")
    weather = build_weather(weather_cfg, 120, 1.0, seed=7)
    eng = ForecastEngine(
        ForecastConfig(failure_start_hour=78, failure_duration_hours=10, bias_wm2=0, noise_std_wm2=10),
        weather_cfg,
        seed=7,
    )
    fc = eng.issue(80.0, weather[80:110], 1.0)
    assert fc.failed
    actual = np.array([x.irradiance_wm2 for x in weather[80:80 + len(fc.irradiance_wm2)]])
    # Failed forecast should not equal truth on the storm collapse.
    assert float(np.mean(np.abs(fc.irradiance_wm2 - actual))) > 10.0
