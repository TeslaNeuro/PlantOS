"""Imperfect weather forecasts.

The controller receives only this object — never the actual future weather.
Error model:

    e(t) = φ e(t-1) + ε_t
    GHI_fcst(t) = clip(GHI_true(t) + bias + e(t), 0, GHI_clear_cap)

A forecast failure replaces the remaining horizon with persistence or an
over-optimistic clear-sky profile (configurable).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plantos.config import ForecastConfig, WeatherConfig
from plantos.weather.engine import WeatherSample, clear_sky_ghi, solar_elevation_deg


@dataclass
class Forecast:
    origin_hour: float
    horizon_hours: int
    irradiance_wm2: np.ndarray
    temperature_c: np.ndarray
    cloud_cover: np.ndarray
    failed: bool = False

    def at(self, step: int) -> tuple[float, float, float]:
        i = min(max(step, 0), len(self.irradiance_wm2) - 1)
        return float(self.irradiance_wm2[i]), float(self.temperature_c[i]), float(self.cloud_cover[i])


class ForecastEngine:
    def __init__(self, config: ForecastConfig, weather_cfg: WeatherConfig, seed: int):
        self.config = config
        self.weather_cfg = weather_cfg
        self.rng = np.random.default_rng(seed + 17)
        self._err_g = 0.0
        self._err_t = 0.0

    def issue(
        self,
        origin_hour: float,
        actual_future: list[WeatherSample],
        dt_hours: float,
    ) -> Forecast:
        h = min(self.config.horizon_hours, len(actual_future))
        irr = np.zeros(h)
        temp = np.zeros(h)
        cloud = np.zeros(h)
        failed = self._is_failed(origin_hour)

        e_g = self._err_g
        e_t = self._err_t
        for i in range(h):
            e_g = self.config.ar1_phi * e_g + self.rng.normal(0.0, self.config.noise_std_wm2)
            e_t = self.config.ar1_phi * e_t + self.rng.normal(0.0, self.config.temp_noise_std_c)
            truth = actual_future[i]
            if failed:
                # Over-confident clear-sky persistence of the first-hour bias.
                doy = self.weather_cfg.start_day_of_year + int((origin_hour + i * dt_hours) // 24)
                hod = (origin_hour + i * dt_hours) % 24.0
                el = solar_elevation_deg(self.weather_cfg.latitude_deg, doy, hod)
                irr[i] = clear_sky_ghi(el) * 0.92
                temp[i] = truth.temperature_c + 3.0
                cloud[i] = 0.08
            else:
                irr[i] = max(truth.irradiance_wm2 + self.config.bias_wm2 + e_g, 0.0)
                temp[i] = truth.temperature_c + self.config.temp_bias_c + e_t
                cloud[i] = float(np.clip(truth.cloud_cover - 0.05 + 0.02 * np.sign(e_g), 0.0, 1.0))
        self._err_g = e_g * 0.3
        self._err_t = e_t * 0.3
        return Forecast(
            origin_hour=origin_hour,
            horizon_hours=h,
            irradiance_wm2=irr,
            temperature_c=temp,
            cloud_cover=cloud,
            failed=failed,
        )

    def _is_failed(self, origin_hour: float) -> bool:
        if self.config.failure_start_hour is not None:
            t0 = self.config.failure_start_hour
            t1 = t0 + self.config.failure_duration_hours
            return t0 <= origin_hour < t1
        if self.config.failure_probability > 0 and self.rng.random() < self.config.failure_probability:
            return True
        return False
